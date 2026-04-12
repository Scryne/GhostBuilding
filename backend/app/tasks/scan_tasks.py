"""
scan_tasks.py — Koordinat tarama ve bölge analiz görevleri.

Tek bir koordinatı veya geniş bir bölgeyi grid halinde tarar.
Her tarama adımında:
  1. Harita tile'ları indirilir (tüm sağlayıcılardan)
  2. OSM bina verileri çekilir
  3. Uydu görüntüsü alınır
  4. Analiz motoru çağrılır (henüz implemente edilecek)
  5. Sonuçlar veritabanına yazılır

İlerleme Redis üzerinden anlık olarak takip edilir.
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from celery import chord, group
from celery.utils.log import get_task_logger

from app.tasks.celery_app import celery_app
from app.config import settings

logger = get_task_logger(__name__)

# ---------------------------------------------------------------------------
# Yardımcı: async → sync köprüsü
# ---------------------------------------------------------------------------


def _run_async(coro):
    """
    Celery worker'da async fonksiyonları çalıştırmak için event loop oluşturur.

    Celery sync çalıştığı için, async servislerimizi bu köprü ile çağırırız.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# Yardımcı: Redis ilerleme takibi
# ---------------------------------------------------------------------------


def _get_sync_redis():
    """Senkron Redis client döndürür (Celery worker için)."""
    import redis

    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _update_progress(
    task_id: str,
    percent: int,
    step: str,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Görev ilerlemesini Redis'te günceller.

    Key formatı: scan:progress:{task_id}
    TTL: 1 saat (görev bitse de erişilebilir)

    Args:
        task_id: Celery task ID.
        percent: İlerleme yüzdesi (0–100).
        step: Mevcut adım açıklaması.
        extra: Ek metadata.
    """
    import json

    r = _get_sync_redis()
    data = {
        "task_id": task_id,
        "percent": percent,
        "step": step,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        data["extra"] = extra

    r.set(
        f"scan:progress:{task_id}",
        json.dumps(data, ensure_ascii=False),
        ex=3600,
    )
    logger.info("[%s] İlerleme: %d%% — %s", task_id, percent, step)


# ---------------------------------------------------------------------------
# Yardımcı: ScanJob DB güncelleme (senkron)
# ---------------------------------------------------------------------------


def _update_scan_job_status(
    job_id: str,
    status: str,
    *,
    anomaly_count: Optional[int] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> None:
    """
    ScanJob kaydını veritabanında günceller.

    Celery worker'da async session kullanamadığımız için
    senkron SQLAlchemy engine kullanıyoruz.

    Args:
        job_id: ScanJob UUID string.
        status: Yeni durum ('RUNNING', 'COMPLETED', 'FAILED').
        anomaly_count: Bulunan anomali sayısı.
        started_at: Başlangıç zamanı.
        completed_at: Bitiş zamanı.
    """
    from sqlalchemy import create_engine, text

    # async URL'yi sync'e çevir
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    engine = create_engine(sync_url)

    updates = ["status = :status"]
    params: Dict[str, Any] = {"job_id": job_id, "status": status}

    if anomaly_count is not None:
        updates.append("anomaly_count = :anomaly_count")
        params["anomaly_count"] = anomaly_count

    if started_at is not None:
        updates.append("started_at = :started_at")
        params["started_at"] = started_at

    if completed_at is not None:
        updates.append("completed_at = :completed_at")
        params["completed_at"] = completed_at

    update_sql = f"UPDATE scan_jobs SET {', '.join(updates)} WHERE id = :job_id"

    try:
        with engine.connect() as conn:
            conn.execute(text(update_sql), params)
            conn.commit()
        logger.info("ScanJob %s durumu güncellendi: %s", job_id, status)
    except Exception as exc:
        logger.error("ScanJob güncelleme hatası (%s): %s", job_id, exc)
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Task: scan_coordinate
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.tasks.scan_tasks.scan_coordinate",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
)
def scan_coordinate(
    self,
    lat: float,
    lng: float,
    zoom: int = 15,
    radius_km: float = 1.0,
    scan_job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tek bir koordinatı tarar: tile indirme → OSM veri → uydu → analiz → DB.

    Bu görev tüm veri toplama ve analiz pipeline'ını çalıştırır.
    İlerleme Redis üzerinden %0, %25, %50, %75, %100 olarak güncellenir.

    Args:
        lat: Hedef enlemi.
        lng: Hedef boylamı.
        zoom: Tile zoom seviyesi (varsayılan 15).
        radius_km: Tarama yarıçapı (km).
        scan_job_id: İlişkili ScanJob UUID (opsiyonel).

    Returns:
        Tarama sonuç sözlüğü:
        - task_id: Celery task ID
        - lat, lng: Tarama koordinatları
        - tile_count: İndirilen tile sayısı
        - building_count: Bulunan bina sayısı
        - anomalies: Tespit edilen anomali listesi
        - satellite_source: Uydu görüntü kaynağı
        - completed_at: Tamamlanma zamanı

    Raises:
        Retry: Geçici hata durumunda (max 3 kez).
    """
    task_id = self.request.id or str(uuid.uuid4())

    logger.info(
        "[%s] Tarama başlıyor: lat=%.4f lng=%.4f zoom=%d r=%.1fkm",
        task_id, lat, lng, zoom, radius_km,
    )

    # Job başladı
    if scan_job_id:
        _update_scan_job_status(
            scan_job_id,
            "RUNNING",
            started_at=datetime.now(timezone.utc),
        )

    result: Dict[str, Any] = {
        "task_id": task_id,
        "lat": lat,
        "lng": lng,
        "zoom": zoom,
        "radius_km": radius_km,
        "tile_count": 0,
        "building_count": 0,
        "sensitive_count": 0,
        "anomalies": [],
        "satellite_source": None,
        "errors": [],
    }

    try:
        # ============================================================
        # %0 — Başlatıldı
        # ============================================================
        _update_progress(task_id, 0, "Tarama başlatılıyor")

        # ============================================================
        # %25 — Harita tile'larını indir
        # ============================================================
        _update_progress(task_id, 10, "Harita tile'ları indiriliyor")

        tile_results = {}
        try:
            from app.services.tile_fetcher import TileFetcher, TileProvider

            async def _fetch_tiles():
                async with TileFetcher() as fetcher:
                    return await fetcher.fetch_all_providers(lat, lng, zoom)

            tile_results = _run_async(_fetch_tiles())
            result["tile_count"] = len(tile_results)
            logger.info(
                "[%s] %d sağlayıcıdan tile indirildi",
                task_id, len(tile_results),
            )
        except Exception as exc:
            logger.warning("[%s] Tile indirme hatası: %s", task_id, exc)
            result["errors"].append(f"tile_fetch: {str(exc)}")

        _update_progress(task_id, 25, "Tile'lar indirildi")

        # ============================================================
        # %50 — OSM bina verisi çek
        # ============================================================
        _update_progress(task_id, 30, "OSM bina verileri çekiliyor")

        buildings = []
        geojson = {}
        try:
            from app.services.osm_collector import OSMCollector

            radius_m = int(radius_km * 1000)

            async def _fetch_osm():
                async with OSMCollector() as collector:
                    blds = await collector.fetch_buildings(lat, lng, radius_m)
                    amenities = await collector.fetch_amenities(lat, lng, radius_m)
                    return blds, amenities

            buildings, amenities = _run_async(_fetch_osm())

            # Amenity'leri birleştir
            existing_ids = {b.osm_id for b in buildings}
            for am in amenities:
                if am.osm_id not in existing_ids:
                    buildings.append(am)

            result["building_count"] = len(buildings)
            result["sensitive_count"] = sum(1 for b in buildings if b.is_sensitive)

            logger.info(
                "[%s] %d bina bulundu (%d hassas)",
                task_id,
                len(buildings),
                result["sensitive_count"],
            )
        except Exception as exc:
            logger.warning("[%s] OSM veri çekme hatası: %s", task_id, exc)
            result["errors"].append(f"osm_fetch: {str(exc)}")

        _update_progress(task_id, 50, "OSM verileri alındı")

        # ============================================================
        # %75 — Uydu görüntüsü al
        # ============================================================
        _update_progress(task_id, 55, "Uydu görüntüsü indiriliyor")

        satellite_result = {}
        try:
            from app.services.satellite_fetcher import fetch_best_available

            async def _fetch_satellite():
                return await fetch_best_available(
                    lat, lng, zoom,
                    radius_m=int(radius_km * 1000),
                    save=True,
                )

            satellite_result = _run_async(_fetch_satellite())
            result["satellite_source"] = satellite_result.get("source")

            logger.info(
                "[%s] Uydu görüntüsü alındı: %s",
                task_id,
                result["satellite_source"],
            )
        except Exception as exc:
            logger.warning("[%s] Uydu görüntüsü hatası: %s", task_id, exc)
            result["errors"].append(f"satellite_fetch: {str(exc)}")

        _update_progress(task_id, 75, "Uydu görüntüsü alındı")

        # ============================================================
        # %90 — Analiz motoru (placeholder — ileride implemente edilecek)
        # ============================================================
        _update_progress(task_id, 80, "Anomali analizi çalıştırılıyor")

        anomalies_detected: List[Dict[str, Any]] = []

        try:
            # --- Basit heuristic anomali tespiti ---
            # Gerçek analiz motoru (CV, diff, vb.) implemente edildiğinde
            # burası değiştirilecek.

            # Heuristic 1: Hassas yapıları anomali olarak işaretle
            for b in buildings:
                if b.is_sensitive:
                    anomalies_detected.append({
                        "type": "HIDDEN_STRUCTURE",
                        "lat": b.centroid[0],
                        "lng": b.centroid[1],
                        "confidence": 65.0,
                        "description": (
                            f"Hassas yapı tespit edildi: "
                            f"{b.building_type} — {b.name or 'İsimsiz'}"
                        ),
                        "osm_id": b.osm_id,
                        "source_providers": list(tile_results.keys()) if tile_results else [],
                    })

            # Heuristic 2: Tile eksikliği — sağlayıcı farkı
            if tile_results and len(tile_results) < 3:
                anomalies_detected.append({
                    "type": "IMAGE_DISCREPANCY",
                    "lat": lat,
                    "lng": lng,
                    "confidence": 40.0,
                    "description": (
                        f"Bazı harita sağlayıcıları tile döndürmedi "
                        f"(mevcut: {len(tile_results)}/4)"
                    ),
                    "source_providers": list(tile_results.keys()) if tile_results else [],
                })

            result["anomalies"] = anomalies_detected

            logger.info(
                "[%s] Analiz tamamlandı: %d anomali tespit edildi",
                task_id,
                len(anomalies_detected),
            )

        except Exception as exc:
            logger.warning("[%s] Analiz hatası: %s", task_id, exc)
            result["errors"].append(f"analysis: {str(exc)}")

        _update_progress(task_id, 90, "Analiz tamamlandı")

        # ============================================================
        # %100 — Sonuçları DB'ye yaz
        # ============================================================
        _update_progress(task_id, 95, "Sonuçlar veritabanına yazılıyor")

        try:
            _write_anomalies_to_db(
                anomalies_detected,
                task_id=task_id,
                zoom=zoom,
                tile_results=tile_results,
            )
        except Exception as exc:
            logger.warning("[%s] DB yazma hatası: %s", task_id, exc)
            result["errors"].append(f"db_write: {str(exc)}")

        # Job tamamlandı
        result["completed_at"] = datetime.now(timezone.utc).isoformat()

        if scan_job_id:
            _update_scan_job_status(
                scan_job_id,
                "COMPLETED",
                anomaly_count=len(anomalies_detected),
                completed_at=datetime.now(timezone.utc),
            )

        _update_progress(
            task_id,
            100,
            "Tarama tamamlandı",
            extra={
                "building_count": result["building_count"],
                "anomaly_count": len(anomalies_detected),
            },
        )

        logger.info(
            "[%s] Tarama tamamlandı: %d bina, %d anomali",
            task_id,
            result["building_count"],
            len(anomalies_detected),
        )

        return result

    except Exception as exc:
        logger.error("[%s] Tarama başarısız: %s", task_id, exc)

        # ScanJob'u FAILED olarak işaretle
        if scan_job_id:
            _update_scan_job_status(scan_job_id, "FAILED")

        _update_progress(task_id, -1, f"HATA: {str(exc)}")

        # Retry
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


def _write_anomalies_to_db(
    anomalies: List[Dict[str, Any]],
    *,
    task_id: str,
    zoom: int,
    tile_results: dict,
) -> None:
    """
    Tespit edilen anomalileri veritabanına yazar.

    Args:
        anomalies: Anomali sözlükleri listesi.
        task_id: İlişkili task ID.
        zoom: Zoom seviyesi.
        tile_results: Tile sonuçları.
    """
    if not anomalies:
        return

    from sqlalchemy import create_engine, text

    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    engine = create_engine(sync_url)

    try:
        with engine.connect() as conn:
            for anomaly in anomalies:
                anomaly_id = str(uuid.uuid4())
                alat = anomaly.get("lat", 0.0)
                alng = anomaly.get("lng", 0.0)

                conn.execute(
                    text("""
                        INSERT INTO anomalies
                            (id, lat, lng, geom, category, confidence_score,
                             description, status, source_providers, detection_methods,
                             meta_data)
                        VALUES
                            (:id, :lat, :lng,
                             ST_SetSRID(ST_MakePoint(:lng, :lat), 4326),
                             :category, :confidence,
                             :description, 'PENDING',
                             :source_providers, :detection_methods,
                             :meta_data)
                    """),
                    {
                        "id": anomaly_id,
                        "lat": alat,
                        "lng": alng,
                        "category": anomaly.get("type", "IMAGE_DISCREPANCY"),
                        "confidence": anomaly.get("confidence", 0.0),
                        "description": anomaly.get("description", ""),
                        "source_providers": str(
                            anomaly.get("source_providers", [])
                        ).replace("'", '"'),
                        "detection_methods": '["heuristic"]',
                        "meta_data": f'{{"task_id": "{task_id}"}}',
                    },
                )

            conn.commit()
            logger.info(
                "[%s] %d anomali veritabanına yazıldı",
                task_id,
                len(anomalies),
            )
    except Exception as exc:
        logger.error("[%s] Anomali DB yazma hatası: %s", task_id, exc)
        raise
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Task: batch_scan_region
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.tasks.scan_tasks.batch_scan_region",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    track_started=True,
)
def batch_scan_region(
    self,
    center_lat: float,
    center_lng: float,
    radius_km: float,
    grid_density: int = 3,
    zoom: int = 15,
    scan_job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Geniş bir bölgeyi grid halinde tarar.

    Belirtilen merkez ve yarıçap kullanılarak bir grid oluşturulur.
    Her grid noktası için scan_coordinate görevi paralel olarak
    chord ile çalıştırılır.

    Args:
        center_lat: Bölge merkez enlemi.
        center_lng: Bölge merkez boylamı.
        radius_km: Tarama yarıçapı (km).
        grid_density: Grid yoğunluğu — çap boyunca kaç nokta (varsayılan 3).
        zoom: Tile zoom seviyesi.
        scan_job_id: İlişkili ScanJob UUID.

    Returns:
        Batch tarama sonuç sözlüğü:
        - total_points: Grid noktası sayısı
        - task_ids: Başlatılan alt görev ID'leri
        - scan_job_id: İlişkili ScanJob UUID

    Raises:
        Retry: Geçici hata durumunda.
    """
    task_id = self.request.id or str(uuid.uuid4())

    logger.info(
        "[%s] Bölge taraması başlıyor: center=(%.4f, %.4f), "
        "r=%.1fkm, grid=%d",
        task_id, center_lat, center_lng, radius_km, grid_density,
    )

    if scan_job_id:
        _update_scan_job_status(
            scan_job_id,
            "RUNNING",
            started_at=datetime.now(timezone.utc),
        )

    try:
        # --- Grid noktalarını hesapla ---
        grid_points = _generate_grid_points(
            center_lat, center_lng, radius_km, grid_density,
        )

        logger.info(
            "[%s] %d grid noktası oluşturuldu",
            task_id, len(grid_points),
        )

        # Her grid noktasının yarıçapı
        cell_radius_km = radius_km / grid_density

        # --- Paralel görevler oluştur (chord) ---
        scan_tasks = group(
            scan_coordinate.s(
                lat=point[0],
                lng=point[1],
                zoom=zoom,
                radius_km=cell_radius_km,
                scan_job_id=None,  # Alt görevler kendi job'larını oluşturmasın
            )
            for point in grid_points
        )

        # Callback: tüm alt görevler bitince sonuçları topla
        callback = _aggregate_batch_results.s(
            scan_job_id=scan_job_id,
            batch_task_id=task_id,
        )

        # chord ile çalıştır: paralel scan → aggregate
        pipeline = chord(scan_tasks)(callback)

        task_ids = [
            f"pending_{i}" for i in range(len(grid_points))
        ]

        result = {
            "batch_task_id": task_id,
            "total_points": len(grid_points),
            "grid_density": grid_density,
            "cell_radius_km": cell_radius_km,
            "task_ids": task_ids,
            "scan_job_id": scan_job_id,
            "status": "DISPATCHED",
        }

        _update_progress(
            task_id,
            10,
            f"{len(grid_points)} alt görev başlatıldı",
            extra={"total_points": len(grid_points)},
        )

        return result

    except Exception as exc:
        logger.error("[%s] Bölge taraması başarısız: %s", task_id, exc)

        if scan_job_id:
            _update_scan_job_status(scan_job_id, "FAILED")

        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    name="app.tasks.scan_tasks._aggregate_batch_results",
    max_retries=2,
)
def _aggregate_batch_results(
    results: List[Dict[str, Any]],
    scan_job_id: Optional[str] = None,
    batch_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Batch scan sonuçlarını toplar ve ScanJob'u günceller.

    chord callback'i olarak çağrılır — tüm scan_coordinate görevleri
    bittikten sonra sonuçları birleştirir.

    Args:
        results: scan_coordinate sonuçları listesi.
        scan_job_id: İlişkili ScanJob UUID.
        batch_task_id: Batch görev ID.

    Returns:
        Toplu sonuç sözlüğü.
    """
    total_buildings = sum(r.get("building_count", 0) for r in results if r)
    total_anomalies = sum(len(r.get("anomalies", [])) for r in results if r)
    total_tiles = sum(r.get("tile_count", 0) for r in results if r)
    errors = []
    for r in results:
        if r and r.get("errors"):
            errors.extend(r["errors"])

    aggregate = {
        "batch_task_id": batch_task_id,
        "scan_count": len(results),
        "total_buildings": total_buildings,
        "total_anomalies": total_anomalies,
        "total_tiles": total_tiles,
        "error_count": len(errors),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    if scan_job_id:
        _update_scan_job_status(
            scan_job_id,
            "COMPLETED",
            anomaly_count=total_anomalies,
            completed_at=datetime.now(timezone.utc),
        )

    if batch_task_id:
        _update_progress(
            batch_task_id,
            100,
            "Bölge taraması tamamlandı",
            extra=aggregate,
        )

    logger.info(
        "Batch tarama toplandı: %d scan, %d bina, %d anomali",
        len(results),
        total_buildings,
        total_anomalies,
    )

    return aggregate


# ---------------------------------------------------------------------------
# Task: scan_high_priority_regions (periyodik)
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.scan_tasks.scan_high_priority_regions",
    max_retries=2,
    default_retry_delay=120,
)
def scan_high_priority_regions() -> Dict[str, Any]:
    """
    Yüksek öncelikli bölgeleri periyodik olarak tarar.

    Beat schedule tarafından her 6 saatte bir çağrılır.
    Veritabanındaki yüksek skorlu anomalilerin çevresini yeniden tarar
    ve skor değişikliklerini takip eder.

    Returns:
        Sonuç sözlüğü:
        - regions_scanned: Taranan bölge sayısı
        - new_anomalies: Yeni tespit edilen anomali sayısı
    """
    logger.info("Yüksek öncelikli bölge taraması başlıyor")

    from sqlalchemy import create_engine, text

    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    engine = create_engine(sync_url)

    try:
        # Yüksek güven skorlu anomalileri çek
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT DISTINCT lat, lng
                    FROM anomalies
                    WHERE confidence_score >= :threshold
                      AND status != 'REJECTED'
                    ORDER BY confidence_score DESC
                    LIMIT 20
                """),
                {"threshold": settings.ANOMALY_CONFIDENCE_THRESHOLD},
            ).fetchall()

        if not rows:
            logger.info("Taranacak yüksek öncelikli bölge bulunamadı")
            return {"regions_scanned": 0, "new_anomalies": 0}

        # Her bölge için scan başlat
        dispatched = 0
        for row in rows:
            scan_coordinate.delay(
                lat=row[0],
                lng=row[1],
                zoom=16,
                radius_km=0.5,
            )
            dispatched += 1

        logger.info(
            "Yüksek öncelikli tarama: %d bölge dispatch edildi",
            dispatched,
        )

        return {
            "regions_scanned": dispatched,
            "status": "DISPATCHED",
        }

    except Exception as exc:
        logger.error("Yüksek öncelikli tarama hatası: %s", exc)
        return {"error": str(exc)}

    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Yardımcı: Grid noktası oluşturma
# ---------------------------------------------------------------------------


def _generate_grid_points(
    center_lat: float,
    center_lng: float,
    radius_km: float,
    density: int,
) -> List[tuple[float, float]]:
    """
    Daire içine düzgün dağılmış grid noktaları üretir.

    Args:
        center_lat: Merkez enlemi.
        center_lng: Merkez boylamı.
        radius_km: Daire yarıçapı (km).
        density: Çap boyunca nokta sayısı.

    Returns:
        [(lat, lng), ...] koordinat listesi. Sadece daire içindekiler.
    """
    points: List[tuple[float, float]] = []

    # Hücre boyutu
    step_km = (2 * radius_km) / density

    # Derece başına km
    km_per_lat = 111.32
    km_per_lng = 111.32 * math.cos(math.radians(center_lat))

    step_lat = step_km / km_per_lat
    step_lng = step_km / km_per_lng if km_per_lng > 0 else step_km / 111.32

    # Grid oluştur (kare grid, sonra daire içindekini filtrele)
    half = density // 2

    for i in range(-half, half + 1):
        for j in range(-half, half + 1):
            plat = center_lat + i * step_lat
            plng = center_lng + j * step_lng

            # Merkeze uzaklık kontrolü (km)
            dlat = (plat - center_lat) * km_per_lat
            dlng = (plng - center_lng) * km_per_lng
            dist = math.sqrt(dlat ** 2 + dlng ** 2)

            if dist <= radius_km:
                points.append((round(plat, 6), round(plng, 6)))

    return points
