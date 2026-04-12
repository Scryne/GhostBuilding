"""
maintenance_tasks.py — Bakım ve temizlik görevleri.

Periyodik olarak çalışan görevler:
- Eski tile/uydu görüntülerini temizle
- Süresi dolmuş cache girişlerini sil
- Anomali güven skorlarını yeniden hesapla
- Haftalık rapor oluştur
"""

from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery.utils.log import get_task_logger

from app.tasks.celery_app import celery_app
from app.config import settings

logger = get_task_logger(__name__)

# ---------------------------------------------------------------------------
# Yardımcı
# ---------------------------------------------------------------------------


def _get_sync_redis():
    """Senkron Redis client döndürür."""
    import redis

    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _get_sync_engine():
    """Senkron SQLAlchemy engine oluşturur."""
    from sqlalchemy import create_engine

    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    return create_engine(sync_url)


# ---------------------------------------------------------------------------
# Task: cleanup_old_images
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.maintenance_tasks.cleanup_old_images",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def cleanup_old_images(max_age_days: int = 30) -> Dict[str, Any]:
    """
    Belirtilen günden eski tile ve uydu görüntülerini siler.

    Yerel dosya sistemindeki data/satellite/ altında tarih bazlı klasörleri
    kontrol eder ve max_age_days'ten eski olanları temizler.

    Args:
        max_age_days: Maksimum yaş (gün). Varsayılan 30.

    Returns:
        Temizlik sonuç sözlüğü:
        - deleted_dirs: Silinen klasör sayısı
        - deleted_files: Silinen dosya sayısı
        - freed_bytes: Serbest bırakılan disk alanı (byte)
        - errors: Hata listesi
    """
    logger.info(
        "Eski görüntü temizliği başlıyor (max_age=%d gün)", max_age_days
    )

    storage_root = Path(settings.STORAGE_ROOT) / "satellite"
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    deleted_dirs = 0
    deleted_files = 0
    freed_bytes = 0
    errors: List[str] = []

    if not storage_root.exists():
        logger.info("Depolama dizini mevcut değil: %s", storage_root)
        return {
            "deleted_dirs": 0,
            "deleted_files": 0,
            "freed_bytes": 0,
            "errors": [],
        }

    try:
        # satellite/{date}/ klasörlerini tara
        for date_dir in sorted(storage_root.iterdir()):
            if not date_dir.is_dir():
                continue

            # Klasör adından tarihi çıkar (YYYY-MM-DD formatı)
            try:
                dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d")
                dir_date = dir_date.replace(tzinfo=timezone.utc)
            except ValueError:
                logger.debug("Geçersiz tarih klasörü atlanıyor: %s", date_dir.name)
                continue

            if dir_date >= cutoff_date:
                continue

            # Eski klasör — sil
            try:
                dir_size = sum(
                    f.stat().st_size for f in date_dir.rglob("*") if f.is_file()
                )
                file_count = sum(1 for f in date_dir.rglob("*") if f.is_file())

                shutil.rmtree(date_dir)

                deleted_dirs += 1
                deleted_files += file_count
                freed_bytes += dir_size

                logger.info(
                    "Silindi: %s (%d dosya, %.1f MB)",
                    date_dir.name,
                    file_count,
                    dir_size / (1024 * 1024),
                )

            except Exception as exc:
                error_msg = f"Silme hatası ({date_dir.name}): {exc}"
                logger.error(error_msg)
                errors.append(error_msg)

    except Exception as exc:
        error_msg = f"Dizin tarama hatası: {exc}"
        logger.error(error_msg)
        errors.append(error_msg)

    result = {
        "deleted_dirs": deleted_dirs,
        "deleted_files": deleted_files,
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        "cutoff_date": cutoff_date.isoformat(),
        "errors": errors,
    }

    logger.info(
        "Temizlik tamamlandı: %d klasör, %d dosya silindi (%.1f MB serbest)",
        deleted_dirs,
        deleted_files,
        freed_bytes / (1024 * 1024),
    )

    return result


# ---------------------------------------------------------------------------
# Task: cleanup_expired_cache
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.maintenance_tasks.cleanup_expired_cache",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def cleanup_expired_cache() -> Dict[str, Any]:
    """
    Redis'teki süresi dolmuş cache girişlerini temizler.

    tile:*, osm:*, scan:progress:* prefix'li anahtarları tarar.
    TTL'i olmayan veya artık gerekli olmayan geçici verileri siler.

    Beat schedule tarafından her gün gece yarısı çağrılır.

    Returns:
        Temizlik sonuç sözlüğü:
        - scanned_keys: Taranan anahtar sayısı
        - deleted_keys: Silinen anahtar sayısı
        - orphaned_progress: Temizlenen progress anahtarı sayısı
    """
    logger.info("Cache temizliği başlıyor")

    r = _get_sync_redis()
    deleted_count = 0
    scanned_count = 0
    orphaned_progress = 0

    # 1. Süresi geçmiş progress anahtarlarını temizle
    # (scan:progress:* — genellikle 1 saat TTL, ama kontrol et)
    try:
        progress_keys = []
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match="scan:progress:*", count=100)
            progress_keys.extend(keys)
            scanned_count += len(keys)
            if cursor == 0:
                break

        for key in progress_keys:
            ttl = r.ttl(key)
            if ttl == -1:
                # TTL yok — 1 saat TTL ata veya sil
                try:
                    raw = r.get(key)
                    if raw:
                        data = json.loads(raw)
                        updated_at = data.get("updated_at", "")
                        if updated_at:
                            updated = datetime.fromisoformat(updated_at)
                            age = datetime.now(timezone.utc) - updated.replace(
                                tzinfo=timezone.utc
                            )
                            # 6 saatten eski progress'leri sil
                            if age > timedelta(hours=6):
                                r.delete(key)
                                orphaned_progress += 1
                                deleted_count += 1
                                continue
                    # TTL ata
                    r.expire(key, 3600)
                except Exception:
                    r.delete(key)
                    orphaned_progress += 1
                    deleted_count += 1

    except Exception as exc:
        logger.warning("Progress cache temizleme hatası: %s", exc)

    # 2. TTL'siz tile cache anahtarlarına TTL ekle
    try:
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match="tile:*", count=200)
            scanned_count += len(keys)

            for key in keys:
                ttl = r.ttl(key)
                if ttl == -1:
                    # 24 saat TTL ata
                    r.expire(key, 86400)

            if cursor == 0:
                break

    except Exception as exc:
        logger.warning("Tile cache TTL düzeltme hatası: %s", exc)

    # 3. TTL'siz OSM cache anahtarlarına TTL ekle
    try:
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match="osm:*", count=200)
            scanned_count += len(keys)

            for key in keys:
                ttl = r.ttl(key)
                if ttl == -1:
                    # 6 saat TTL ata
                    r.expire(key, 21600)

            if cursor == 0:
                break

    except Exception as exc:
        logger.warning("OSM cache TTL düzeltme hatası: %s", exc)

    result = {
        "scanned_keys": scanned_count,
        "deleted_keys": deleted_count,
        "orphaned_progress": orphaned_progress,
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "Cache temizliği tamamlandı: %d anahtar tarandı, %d silindi",
        scanned_count,
        deleted_count,
    )

    return result


# ---------------------------------------------------------------------------
# Task: recalculate_confidence_scores
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.maintenance_tasks.recalculate_confidence_scores",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def recalculate_confidence_scores() -> Dict[str, Any]:
    """
    Tüm anomalilerin güven skorlarını yeniden hesaplar.

    Doğrulama (verification) verisi, sağlayıcı sayısı ve
    tespit yöntemi çeşitliliğine göre skoru günceller.

    Skor hesaplama kuralları:
    - Birden fazla sağlayıcıda tespit: +15 puan
    - Hassas yapı tespiti: +10 puan
    - Community doğrulama: CONFIRM +20, DENY -30, UNCERTAIN +5
    - Birden fazla tespit yöntemi: +10 puan

    Returns:
        Güncelleme sonuç sözlüğü:
        - total_anomalies: İşlenen anomali sayısı
        - updated: Güncellenen anomali sayısı
        - avg_score_before: Önceki ortalama skor
        - avg_score_after: Sonraki ortalama skor
    """
    logger.info("Güven skoru yeniden hesaplanıyor")

    engine = _get_sync_engine()
    updated_count = 0
    total_count = 0
    score_sum_before = 0.0
    score_sum_after = 0.0

    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            # Tüm anomalileri çek
            rows = conn.execute(
                text("""
                    SELECT
                        a.id,
                        a.confidence_score,
                        a.source_providers,
                        a.detection_methods,
                        a.category,
                        COALESCE(
                            (SELECT COUNT(*)
                             FROM verifications v
                             WHERE v.anomaly_id = a.id AND v.vote = 'CONFIRM'),
                            0
                        ) AS confirm_count,
                        COALESCE(
                            (SELECT COUNT(*)
                             FROM verifications v
                             WHERE v.anomaly_id = a.id AND v.vote = 'DENY'),
                            0
                        ) AS deny_count,
                        COALESCE(
                            (SELECT COUNT(*)
                             FROM verifications v
                             WHERE v.anomaly_id = a.id AND v.vote = 'UNCERTAIN'),
                            0
                        ) AS uncertain_count
                    FROM anomalies a
                    WHERE a.status != 'REJECTED'
                """)
            ).fetchall()

            total_count = len(rows)

            for row in rows:
                anomaly_id = row[0]
                old_score = float(row[1] or 0.0)
                source_providers = row[2] or []
                detection_methods = row[3] or []
                category = row[4] or ""
                confirm_count = int(row[5])
                deny_count = int(row[6])
                uncertain_count = int(row[7])

                score_sum_before += old_score

                # --- Skor hesapla ---
                new_score = 30.0  # Baz skor

                # Sağlayıcı çeşitliliği
                provider_count = (
                    len(source_providers)
                    if isinstance(source_providers, list)
                    else 1
                )
                if provider_count >= 2:
                    new_score += 15.0
                if provider_count >= 3:
                    new_score += 10.0

                # Hassas yapı bonusu
                if category in ("HIDDEN_STRUCTURE", "CENSORED_AREA"):
                    new_score += 10.0

                # Tespit yöntemi çeşitliliği
                method_count = (
                    len(detection_methods)
                    if isinstance(detection_methods, list)
                    else 1
                )
                if method_count >= 2:
                    new_score += 10.0

                # Community doğrulama
                new_score += confirm_count * 20.0
                new_score -= deny_count * 30.0
                new_score += uncertain_count * 5.0

                # Sınırlar
                new_score = max(0.0, min(100.0, new_score))

                score_sum_after += new_score

                # Sadece değişiklik varsa güncelle
                if abs(new_score - old_score) > 0.01:
                    conn.execute(
                        text("""
                            UPDATE anomalies
                            SET confidence_score = :score,
                                updated_at = NOW()
                            WHERE id = :id
                        """),
                        {"id": anomaly_id, "score": new_score},
                    )
                    updated_count += 1

            conn.commit()

    except Exception as exc:
        logger.error("Skor hesaplama hatası: %s", exc)
        raise

    finally:
        engine.dispose()

    avg_before = score_sum_before / total_count if total_count else 0.0
    avg_after = score_sum_after / total_count if total_count else 0.0

    result = {
        "total_anomalies": total_count,
        "updated": updated_count,
        "avg_score_before": round(avg_before, 2),
        "avg_score_after": round(avg_after, 2),
        "recalculated_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "Skor yeniden hesaplama tamamlandı: %d/%d güncellendi "
        "(ort. skor: %.1f → %.1f)",
        updated_count,
        total_count,
        avg_before,
        avg_after,
    )

    return result


# ---------------------------------------------------------------------------
# Task: generate_weekly_report
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.maintenance_tasks.generate_weekly_report",
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
)
def generate_weekly_report() -> Dict[str, Any]:
    """
    Haftalık aktivite raporu oluşturur.

    Son 7 günün tarama, anomali ve doğrulama istatistiklerini toplar.
    Beat schedule tarafından her Pazartesi 03:00 UTC'de çağrılır.

    Returns:
        Haftalık rapor sözlüğü:
        - period: Raporun kapsadığı tarih aralığı
        - scans: Tarama istatistikleri
        - anomalies: Anomali istatistikleri
        - verifications: Doğrulama istatistikleri
        - top_regions: En aktif bölgeler
    """
    logger.info("Haftalık rapor oluşturuluyor")

    engine = _get_sync_engine()
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    report: Dict[str, Any] = {
        "period": {
            "from": week_ago.isoformat(),
            "to": now.isoformat(),
        },
        "generated_at": now.isoformat(),
        "scans": {},
        "anomalies": {},
        "verifications": {},
        "top_regions": [],
    }

    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            # --- Tarama istatistikleri ---
            scan_stats = conn.execute(
                text("""
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed,
                        COUNT(*) FILTER (WHERE status = 'FAILED') AS failed,
                        COALESCE(SUM(anomaly_count), 0) AS total_anomalies_found,
                        COALESCE(AVG(
                            EXTRACT(EPOCH FROM (completed_at - started_at))
                        ), 0) AS avg_duration_sec
                    FROM scan_jobs
                    WHERE started_at >= :since
                """),
                {"since": week_ago},
            ).fetchone()

            if scan_stats:
                report["scans"] = {
                    "total": scan_stats[0],
                    "completed": scan_stats[1],
                    "failed": scan_stats[2],
                    "anomalies_found": scan_stats[3],
                    "avg_duration_sec": round(float(scan_stats[4] or 0), 1),
                }

            # --- Anomali istatistikleri ---
            anomaly_stats = conn.execute(
                text("""
                    SELECT
                        COUNT(*) AS total_new,
                        COUNT(*) FILTER (WHERE category = 'GHOST_BUILDING') AS ghost,
                        COUNT(*) FILTER (WHERE category = 'HIDDEN_STRUCTURE') AS hidden,
                        COUNT(*) FILTER (WHERE category = 'CENSORED_AREA') AS censored,
                        COUNT(*) FILTER (WHERE category = 'IMAGE_DISCREPANCY') AS discrepancy,
                        COALESCE(AVG(confidence_score), 0) AS avg_confidence,
                        COUNT(*) FILTER (WHERE confidence_score >= 85.0) AS high_confidence
                    FROM anomalies
                    WHERE created_at >= :since
                """),
                {"since": week_ago},
            ).fetchone()

            if anomaly_stats:
                report["anomalies"] = {
                    "total_new": anomaly_stats[0],
                    "by_category": {
                        "ghost_building": anomaly_stats[1],
                        "hidden_structure": anomaly_stats[2],
                        "censored_area": anomaly_stats[3],
                        "image_discrepancy": anomaly_stats[4],
                    },
                    "avg_confidence": round(float(anomaly_stats[5] or 0), 1),
                    "high_confidence_count": anomaly_stats[6],
                }

            # --- Doğrulama istatistikleri ---
            verify_stats = conn.execute(
                text("""
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE vote = 'CONFIRM') AS confirms,
                        COUNT(*) FILTER (WHERE vote = 'DENY') AS denies,
                        COUNT(*) FILTER (WHERE vote = 'UNCERTAIN') AS uncertain
                    FROM verifications
                    WHERE created_at >= :since
                """),
                {"since": week_ago},
            ).fetchone()

            if verify_stats:
                report["verifications"] = {
                    "total": verify_stats[0],
                    "confirms": verify_stats[1],
                    "denies": verify_stats[2],
                    "uncertain": verify_stats[3],
                }

            # --- En aktif bölgeler (top 5) ---
            top_regions = conn.execute(
                text("""
                    SELECT
                        ROUND(CAST(lat AS numeric), 2) AS region_lat,
                        ROUND(CAST(lng AS numeric), 2) AS region_lng,
                        COUNT(*) AS anomaly_count,
                        ROUND(CAST(AVG(confidence_score) AS numeric), 1) AS avg_score
                    FROM anomalies
                    WHERE created_at >= :since
                    GROUP BY region_lat, region_lng
                    ORDER BY anomaly_count DESC
                    LIMIT 5
                """),
                {"since": week_ago},
            ).fetchall()

            report["top_regions"] = [
                {
                    "lat": float(row[0]),
                    "lng": float(row[1]),
                    "anomaly_count": row[2],
                    "avg_confidence": float(row[3]),
                }
                for row in top_regions
            ]

    except Exception as exc:
        logger.error("Haftalık rapor oluşturma hatası: %s", exc)
        report["error"] = str(exc)

    finally:
        engine.dispose()

    # Raporu Redis'e kaydet (30 gün TTL)
    try:
        r = _get_sync_redis()
        report_key = f"report:weekly:{now.strftime('%Y-%W')}"
        r.set(
            report_key,
            json.dumps(report, ensure_ascii=False, default=str),
            ex=30 * 86400,  # 30 gün
        )
        logger.info("Haftalık rapor kaydedildi: %s", report_key)
    except Exception as exc:
        logger.warning("Rapor Redis'e kaydedilemedi: %s", exc)

    logger.info(
        "Haftalık rapor tamamlandı: %d tarama, %d yeni anomali, %d doğrulama",
        report.get("scans", {}).get("total", 0),
        report.get("anomalies", {}).get("total_new", 0),
        report.get("verifications", {}).get("total", 0),
    )

    return report
