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
    Tek bir koordinatı tarar: AnomalyEngine (karolar → OSM → analiz → DB).

    İlerleme Redis üzerinden %0, %10, %90, %100 olarak güncellenir.

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
        - tile_count / providers: Karo gelen uydu kaynakları
        - building_count: Bulunan bina sayısı
        - anomalies: Eşiği geçen (DB'ye yazılan) anomaliler
        - score_breakdown: Konumun sinyal puanları (eşik altı olsa da)
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
        "providers": [],
        "building_count": 0,
        "sensitive_count": 0,
        "anomalies": [],
        "score_breakdown": None,
    }

    try:
        _update_progress(task_id, 0, "Tarama başlatılıyor")
        _update_progress(task_id, 10, "Uydu karoları ve OSM verisi toplanıyor")

        # Motor veriyi kendisi toplar, analiz eder ve eşiği geçen adayları DB'ye yazar.
        # Eskiden görev aynı veriyi motordan önce bir kez daha çekiyor (kaynaklara iki kat
        # yük) ve adayları ikinci kez, yanlış anahtarlarla ("type"/"confidence") yazıyordu.
        # Motor hatası artık sabit güvenli "sezgisel" anomali üretmez: görev başarısız olur.
        from app.services.anomaly_engine import AnomalyEngine

        engine = AnomalyEngine(
            radius_m=int(radius_km * 1000),
            min_confidence=settings.ANOMALY_CONFIDENCE_THRESHOLD,
        )
        # Eşikler ANALYSIS_ZOOM'da ölçüldü; istek zoom'u yalnız harita görünümü içindir.
        candidates = _run_async(engine.analyze(lat, lng, settings.ANALYSIS_ZOOM))
        run = engine.last_run

        result.update(
            tile_count=run.get("tile_count", 0),
            providers=run.get("providers", []),
            building_count=run.get("building_count", 0),
            sensitive_count=run.get("sensitive_count", 0),
            score_breakdown=run.get("score_breakdown"),
            anomalies=[c.to_dict() for c in candidates],
        )
        if result["tile_count"] < 2:
            raise RuntimeError(
                f"Karşılaştırma için en az iki uydu kaynağı gerekli "
                f"(gelen: {result['providers'] or 'yok'})"
            )

        # Kaydedilen bulgulara kanit olarak Wayback zaman serisi; tarama sonucunu bekletmez.
        for anomaly_id in run.get("history_pending_ids", []):
            try:
                build_anomaly_history.delay(anomaly_id)
            except Exception as exc:  # kuyruk yoksa bulgu sayfasi istegi yeniden dener
                logger.warning("Zaman serisi kuyruga atilamadi (%s): %s", anomaly_id, exc)
            if settings.ENABLE_ML_FOOTPRINTS:
                try:
                    build_anomaly_ml_footprints.delay(anomaly_id)
                except Exception as exc:
                    logger.warning("ML izi kaniti kuyruga atilamadi (%s): %s", anomaly_id, exc)

        _update_progress(task_id, 90, "Analiz tamamlandı")
        result["completed_at"] = datetime.now(timezone.utc).isoformat()

        if scan_job_id:
            _update_scan_job_status(
                scan_job_id,
                "COMPLETED",
                anomaly_count=len(candidates),
                completed_at=datetime.now(timezone.utc),
            )

        _update_progress(
            task_id,
            100,
            "Tarama tamamlandı",
            extra={
                "building_count": result["building_count"],
                "anomaly_count": len(candidates),
            },
        )

        logger.info(
            "[%s] Tarama tamamlandı: %d kaynak, %d bina, %d anomali",
            task_id,
            result["tile_count"],
            result["building_count"],
            len(candidates),
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


# ---------------------------------------------------------------------------
# Task: build_anomaly_history
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.scan_tasks.build_anomaly_history",
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
)
def build_anomaly_history(anomaly_id: str) -> Dict[str, Any]:
    """Bulgunun konumu icin Esri Wayback zaman serisini uretip meta_data["history"]'ye yazar.

    Puan degil kanit: tarihsel skor ayirt edici olmadigi icin (history_service) bulgu
    sayfasinda yillar icindeki goruntu ve degisim tarihleri olarak gosterilir.
    """
    from app.services.history_service import store_anomaly_history

    history = _run_async(store_anomaly_history(anomaly_id))
    return {"anomaly_id": anomaly_id, "status": history.get("status"),
            "snapshots": len(history.get("snapshots", []))}


# ---------------------------------------------------------------------------
# Task: build_anomaly_ml_footprints
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.scan_tasks.build_anomaly_ml_footprints",
    max_retries=2,
    default_retry_delay=300,
    acks_late=True,
)
def build_anomaly_ml_footprints(anomaly_id: str) -> Dict[str, Any]:
    """Bulgunun karosunda Microsoft ML bina izi ile OSM bina sayisini kiyaslar.

    Kanit, puan degil (ml_footprints_service): OSM'de bina olup ML izi olmayan karo, Bing
    goruntusunde de binalarin gorunmedigini dusundurur (bagimsiz dorduncu saglayici).
    """
    from app.services.ml_footprints_service import store_anomaly_ml_footprints

    evidence = _run_async(store_anomaly_ml_footprints(anomaly_id))
    return {"anomaly_id": anomaly_id, "status": evidence.get("status"), "flag": evidence.get("flag")}


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

        # Gerçek alt görev kimlikleri (eskiden "pending_0…" diye uyduruluyordu).
        header = pipeline.parent
        task_ids = [r.id for r in header.results] if header is not None else []

        result = {
            "batch_task_id": task_id,
            "total_points": len(grid_points),
            "grid_density": grid_density,
            "cell_radius_km": cell_radius_km,
            "task_ids": task_ids,
            "aggregate_task_id": pipeline.id,
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
                    SELECT DISTINCT lat, lng, confidence_score
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
