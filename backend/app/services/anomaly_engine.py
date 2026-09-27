"""
anomaly_engine.py — Tüm analiz sonuçlarını birleştiren ana anomali motoru.

Harita tile karşılaştırması, bulanıklık tespiti ve mekansal analiz
sonuçlarını ağırlıklı bir skorlama sistemiyle birleştirerek nihai
anomali kararını verir. Sonuçları veritabanına kaydeder.

Pipeline sırası:
  1. Tüm sağlayıcılardan tile çek (TileFetcher)
  2. OSM bina verisi çek (OSMCollector)
  3. Uydu görüntüsü çek (SatelliteFetcher)
  4. Pixel diff analizi (PixelDiffAnalyzer)
  5. Blur tespiti (BlurDetector)
  6. Geospatial join (GeospatialAnalyzer)
  7. Güven skoru hesapla (ağırlıklı toplam)
  8. Kategorilere sınıflandır
  9. DB'ye kaydet
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from PIL import Image

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.enums import AnomalyCategory, AnomalyStatus
from app.services.analyzers.blur_detector import CENSORSHIP_BASELINE_P90, censorship_to_score, tr_decimal
from app.services.analyzers.pixel_diff import diff_baseline, diff_to_score
from app.services.tile_fetcher import provider_name

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

# Ağırlıklı skorlama katsayıları (toplam = 1.0)
WEIGHT_PROVIDER_DISAGREEMENT: float = 0.30
WEIGHT_PIXEL_DIFF: float = 0.25
WEIGHT_BLUR_CENSORSHIP: float = 0.20
WEIGHT_GEOSPATIAL_MISMATCH: float = 0.15
WEIGHT_HISTORICAL_CHANGE: float = 0.10

# Minimum güven eşiği — altı DB'ye yazılmaz
MIN_CONFIDENCE_THRESHOLD: float = 40.0

# Kategori belirleme: her sinyal taban dağılımına göre 0–100'e ölçeklenir; 50 = sıradan
# konumların p99'u (scripts/calibrate_diff.py). Kategori, puanı 50'yi AŞAN sinyalden doğar:
# sansür skoru kaba basamaklıdır ve tabanın %10'u tam p99 değerini (20) alır; eşitlik işaret değildir.
SIGNAL_FLAG_SCORE: float = 50.0

# Varsayılan analiz yarıçapı (metre)
DEFAULT_ANALYSIS_RADIUS_M: int = 500

# Aynı kategoride bu mesafe içindeki reddedilmemiş kayıt "aynı bulgu" sayılır ve güncellenir.
# Eskiden her tarama yeni satır ekliyordu; 6 saatlik yeniden tarama görevi bulguları çoğaltıyordu.
DEDUP_RADIUS_M: float = 50.0

# Skora katkı veremeyen sinyaller (neden) — adayın meta verisinde görünür.
INACTIVE_GEOSPATIAL = "geospatial_mismatch: bina dedektörü tanımlı değil (BUILDING_DETECTOR_WEIGHTS)"
INACTIVE_HISTORICAL = "historical_change: tarama akışına bağlı değil (Wayback analizcisi hazır, çağrılmıyor)"


# ---------------------------------------------------------------------------
# Veri sınıfları
# ---------------------------------------------------------------------------


@dataclass
class ScoreBreakdown:
    """Anomali skorunun bileşen bazlı dağılımı.

    Attributes:
        provider_disagreement_score: Sağlayıcı uyumsuzluk skoru (0–100).
        pixel_diff_score: En yüksek piksel fark skoru (0–100).
        blur_censorship_score: Sansür/bulanıklık skoru (0–100).
        geospatial_mismatch_score: Mekansal uyumsuzluk skoru (0–100).
        historical_change_score: Tarihsel değişim skoru (0–100).
        weighted_total: Ağırlıklı toplam (0–100).
    """

    provider_disagreement_score: float = 0.0
    pixel_diff_score: float = 0.0
    blur_censorship_score: float = 0.0
    geospatial_mismatch_score: float = 0.0
    historical_change_score: float = 0.0
    weighted_total: float = 0.0
    raw_max_diff: float = 0.0
    raw_censorship: float = 0.0
    # Ham degerin siradan konumlarda (taban p90) nereye kadar normal oldugu; arayuz yanina yazar.
    raw_max_diff_p90: Optional[float] = None
    raw_censorship_p90: Optional[float] = None
    inactive_signals: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "provider_disagreement_score": round(self.provider_disagreement_score, 2),
            "pixel_diff_score": round(self.pixel_diff_score, 2),
            "blur_censorship_score": round(self.blur_censorship_score, 2),
            "geospatial_mismatch_score": round(self.geospatial_mismatch_score, 2),
            "historical_change_score": round(self.historical_change_score, 2),
            "weighted_total": round(self.weighted_total, 2),
            "raw_max_diff": round(self.raw_max_diff, 2),
            "raw_censorship": round(self.raw_censorship, 2),
            "raw_max_diff_p90": self.raw_max_diff_p90,
            "raw_censorship_p90": self.raw_censorship_p90,
            "inactive_signals": list(self.inactive_signals),
            "weights": {
                "provider_disagreement": WEIGHT_PROVIDER_DISAGREEMENT,
                "pixel_diff": WEIGHT_PIXEL_DIFF,
                "blur_censorship": WEIGHT_BLUR_CENSORSHIP,
                "geospatial_mismatch": WEIGHT_GEOSPATIAL_MISMATCH,
                "historical_change": WEIGHT_HISTORICAL_CHANGE,
            },
        }


@dataclass
class AnomalyCandidate:
    """Anomali motoru tarafından üretilen aday sonuç.

    Attributes:
        category: Anomali kategorisi (AnomalyCategory enum değeri).
        lat: Anomalinin enlemi.
        lng: Anomalinin boylamı.
        confidence_score: Nihai güven skoru (0–100).
        title: Kısa başlık.
        description: Detaylı açıklama.
        score_breakdown: Skor bileşen dağılımı.
        source_providers: İlgili veri kaynakları.
        detection_methods: Kullanılan tespit yöntemleri.
        meta_data: Ek metaveriler.
        provider_images: Sağlayıcı adı → PIL Image sözlüğü.
        diff_image: Piksel fark görselleştirmesi.
        blur_heatmap: Bulanıklık sıcaklık haritası.
    """

    category: str
    lat: float
    lng: float
    confidence_score: float
    title: str
    description: str
    score_breakdown: ScoreBreakdown
    source_providers: List[str] = field(default_factory=list)
    detection_methods: List[str] = field(default_factory=list)
    meta_data: Dict[str, Any] = field(default_factory=dict)
    provider_images: Dict[str, Image.Image] = field(default_factory=dict)
    diff_image: Optional[Image.Image] = None
    blur_heatmap: Optional[Image.Image] = None

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür (görüntüler hariç)."""
        return {
            "category": self.category,
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "confidence_score": round(self.confidence_score, 2),
            "title": self.title,
            "description": self.description,
            "score_breakdown": self.score_breakdown.to_dict(),
            "source_providers": self.source_providers,
            "detection_methods": self.detection_methods,
            "meta_data": self.meta_data,
        }


@dataclass
class AnalysisPipelineResult:
    """Tam analiz pipeline sonucu.

    Attributes:
        candidates: Tüm anomali adayları.
        saved_count: DB'ye kaydedilen anomali sayısı.
        skipped_count: Eşik altında kalan (loglanıp atlanan) sayısı.
        pipeline_duration_ms: Pipeline toplam süresi (ms).
        raw_scores: Her analiz modülünün ham sonuçları.
    """

    candidates: List[AnomalyCandidate]
    saved_count: int = 0
    skipped_count: int = 0
    pipeline_duration_ms: float = 0.0
    raw_scores: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "total_candidates": len(self.candidates),
            "saved_count": self.saved_count,
            "skipped_count": self.skipped_count,
            "pipeline_duration_ms": round(self.pipeline_duration_ms, 1),
            "candidates": [c.to_dict() for c in self.candidates],
        }


# ---------------------------------------------------------------------------
# AnomalyEngine — Ana motor
# ---------------------------------------------------------------------------


class AnomalyEngine:
    """Tüm analiz modüllerini orkestre ederek anomali kararı veren motor.

    Pipeline sırası:
      1. TileFetcher: Uydu kaynaklarından karolar (Esri, MapTiler)
      2. OSMCollector: OpenStreetMap bina verileri
      3. PixelDiffAnalyzer: Sağlayıcılar arası piksel farkı (taban dağılımına göre puan)
      4. BlurDetector: Kasıtlı bulanıklaştırma tespiti
      5. GeospatialAnalyzer: OSM vs görüntü (yalnız BUILDING_DETECTOR_WEIGHTS tanımlıysa)
      7. Ağırlıklı skor hesaplama
      8. Kategori belirleme
      9. Veritabanına yazma

    Kategori güveni, kategoriyi doğuran sinyalin taban-göreli puanıdır (50 = sıradan
    konumların p99'u). Ağırlıklı toplam yalnız özet olarak tutulur:
      - provider_disagreement × 0.30
      - pixel_diff × 0.25
      - blur_censorship × 0.20
      - geospatial_mismatch × 0.15
      - historical_change × 0.10

    Attributes:
        _radius_m: Analiz yarıçapı (metre).
        _min_confidence: Minimum güven eşiği (DB kaydı için).

    Examples:
        >>> engine = AnomalyEngine()
        >>> candidates = await engine.analyze(41.0082, 28.9784, 16)
        >>> for c in candidates:
        ...     print(f"{c.category}: {c.confidence_score:.1f}")
    """

    def __init__(
        self,
        *,
        radius_m: int = DEFAULT_ANALYSIS_RADIUS_M,
        min_confidence: float = MIN_CONFIDENCE_THRESHOLD,
    ) -> None:
        """
        Args:
            radius_m: Analiz yarıçapı (metre). OSM sorgusu ve uydu
                görüntüsü bu yarıçapla çekilir.
            min_confidence: Minimum güven eşiği. Altındaki anomaliler
                DB'ye yazılmaz, sadece loglanır.
        """
        self._radius_m = radius_m
        self._min_confidence = min_confidence
        # Son analiz çağrısının özeti (tarama görevi ilerleme/sonuç için okur)
        self.last_run: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # analyze — Ana pipeline
    # ------------------------------------------------------------------ #

    async def analyze(
        self,
        lat: float,
        lng: float,
        zoom: int,
    ) -> List[AnomalyCandidate]:
        """Tam anomali analiz pipeline'ı çalıştırır.

        Verilen konum için tüm veri kaynaklarını toplar, analiz
        modüllerini çalıştırır, sonuçları birleştirerek nihai skor
        hesaplar ve DB'ye kaydeder.

        Args:
            lat: Analiz merkezi enlemi.
            lng: Analiz merkezi boylamı.
            zoom: Harita zoom seviyesi (tile çekimi için).

        Returns:
            AnomalyCandidate listesi (confidence ≥ min_confidence olanlar).
            Eşik altındakilar loglanır ama listeye dahil edilmez.

        Examples:
            >>> engine = AnomalyEngine()
            >>> results = await engine.analyze(41.0082, 28.9784, 16)
            >>> len(results) >= 0
            True
        """
        import time

        start_time = time.monotonic()

        logger.info(
            "Anomali analizi baslatiliyor: (%.4f, %.4f) zoom=%d, "
            "yaricap=%dm",
            lat, lng, zoom, self._radius_m,
        )

        # --- 1. Tile'lari cek ---
        provider_tiles = await self._fetch_provider_tiles(lat, lng, zoom)

        # --- 2. OSM bina verisi (yalniz mekansal analiz aciksa) ---
        # Dedektor yokken OSM verisi hicbir sinyale girmez; kamuya acik Overpass'a
        # gereksiz (tarama yaricapi 5 km'ye kadar) sorgu atilmaz.
        osm_buildings: List[Any] = []
        if settings.BUILDING_DETECTOR_WEIGHTS:
            osm_buildings = await self._fetch_osm_buildings(lat, lng)

        # --- 3. Bina karsilastirmasi icin goruntu ---
        # Dedektor, sagladigi karo ile ayni cografi sinirlara sahip yuksek cozunurluklu
        # goruntu ister: Esri karosu (z16 ~2 m/px). Sentinel/GIBS (10–250 m/px) bina
        # ayirt edemez; eskiden buraya o veriliyordu.
        satellite_image = provider_tiles.get("esri")

        # --- 4. Pixel diff analizi ---
        pixel_diff_result = await self._run_pixel_diff(provider_tiles)

        # --- 5. Blur tespiti ---
        blur_result = await self._run_blur_detection(provider_tiles)

        # --- 6. Geospatial analiz (yalniz bina dedektoru tanimliysa) ---
        geospatial_result = None
        if settings.BUILDING_DETECTOR_WEIGHTS:
            geospatial_result = await self._run_geospatial_analysis(
                lat, lng, zoom, osm_buildings, satellite_image
            )

        # --- 7. Skor hesaplama ---
        score_breakdown = self._compute_confidence_score(
            pixel_diff_result=pixel_diff_result,
            blur_result=blur_result,
            geospatial_result=geospatial_result,
            provider_count=len(provider_tiles),
        )

        # --- 8. Adaylari olustur ---
        candidates = self._build_candidates(
            lat=lat,
            lng=lng,
            score_breakdown=score_breakdown,
            pixel_diff_result=pixel_diff_result,
            blur_result=blur_result,
            geospatial_result=geospatial_result,
            provider_tiles=provider_tiles,
        )

        # --- 9. Filtrele ve DB'ye yaz ---
        saved_candidates: List[AnomalyCandidate] = []
        skipped = 0

        for candidate in candidates:
            if candidate.confidence_score >= self._min_confidence:
                saved_candidates.append(candidate)
            else:
                skipped += 1
                logger.debug(
                    "Esik alti anomali atlandi: %s (score=%.1f < %.1f)",
                    candidate.category,
                    candidate.confidence_score,
                    self._min_confidence,
                )

        # DB'ye kaydet
        saved_count = 0
        if saved_candidates:
            saved_count = await self._save_to_database(
                saved_candidates, zoom
            )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        self.last_run = {
            "providers": sorted(provider_tiles.keys()),
            "tile_count": len(provider_tiles),
            "building_count": len(osm_buildings),
            "sensitive_count": sum(
                1 for b in osm_buildings if getattr(b, "is_sensitive", False)
            ),
            "candidate_count": len(candidates),
            "saved_count": saved_count,
            "skipped_count": skipped,
            "score_breakdown": score_breakdown.to_dict(),
            "duration_ms": round(elapsed_ms, 1),
        }

        logger.info(
            "Anomali analizi tamamlandi: %.0f ms, "
            "%d aday, %d kaydedildi, %d atlandi",
            elapsed_ms,
            len(candidates),
            saved_count,
            skipped,
        )

        return saved_candidates

    # ------------------------------------------------------------------ #
    # Pipeline adimlari — Veri toplama
    # ------------------------------------------------------------------ #

    async def _fetch_provider_tiles(
        self,
        lat: float,
        lng: float,
        zoom: int,
    ) -> Dict[str, Image.Image]:
        """Tüm saglayicilardan tile görüntülerini indirir.

        Args:
            lat: Enlem.
            lng: Boylam.
            zoom: Zoom seviyesi.

        Returns:
            Saglayici adi → PIL Image sozlugu.
            Basarisiz saglayicilar dahil edilmez.
        """
        from app.services.tile_fetcher import TileFetcher, imagery_providers

        tiles: Dict[str, Image.Image] = {}

        try:
            async with TileFetcher() as fetcher:
                result = await fetcher.fetch_all_providers(lat, lng, zoom)

                for provider, img in result.items():
                    tiles[provider.value] = img

            logger.info(
                "Tile indirme tamamlandi: %d/%d saglayici basarili",
                len(tiles), len(imagery_providers(lat, lng)),
            )

        except Exception as exc:
            logger.error("Tile indirme hatasi: %s", exc)

        return tiles

    async def _fetch_osm_buildings(
        self,
        lat: float,
        lng: float,
    ) -> List[Any]:
        """OSM bina verilerini ceker.

        Args:
            lat: Enlem.
            lng: Boylam.

        Returns:
            Building objeleri listesi.
        """
        from app.services.osm_collector import OSMCollector

        buildings: List[Any] = []

        try:
            async with OSMCollector() as collector:
                buildings = await collector.fetch_buildings(
                    lat, lng, self._radius_m
                )

                # Hassas yapilari da cek
                amenities = await collector.fetch_amenities(
                    lat, lng, self._radius_m
                )

                # Duplikasyonu onleyerek birlestir
                existing_ids = {b.osm_id for b in buildings}
                for am in amenities:
                    if am.osm_id not in existing_ids:
                        buildings.append(am)

            logger.info(
                "OSM veri toplama tamamlandi: %d bina", len(buildings)
            )

        except Exception as exc:
            logger.error("OSM veri toplama hatasi: %s", exc)

        return buildings

    # ------------------------------------------------------------------ #
    # Pipeline adimlari — Analiz modulleri
    # ------------------------------------------------------------------ #

    async def _run_pixel_diff(
        self,
        provider_tiles: Dict[str, Image.Image],
    ) -> Optional[Dict[str, Any]]:
        """Pixel diff analizini calistirir.

        Args:
            provider_tiles: Saglayici adi → PIL Image sozlugu.

        Returns:
            PixelDiffAnalyzer sonuclari veya None.
        """
        if len(provider_tiles) < 2:
            logger.warning(
                "Pixel diff icin yetersiz saglayici: %d",
                len(provider_tiles),
            )
            return None

        try:
            from app.services.analyzers.pixel_diff import PixelDiffAnalyzer

            analyzer = PixelDiffAnalyzer()
            result = analyzer.compare_providers(provider_tiles)

            logger.info(
                "Pixel diff tamamlandi: anomaly=%.1f, max_diff=%.1f%%",
                result.anomaly_score,
                (
                    result.max_diff_pair.diff_result.diff_score
                    if result.max_diff_pair
                    else 0.0
                ),
            )

            return {
                "comparison": result,
                "anomaly_score": result.anomaly_score,
                "max_diff_score": (
                    result.max_diff_pair.diff_result.diff_score
                    if result.max_diff_pair
                    else 0.0
                ),
                "max_diff_pair": (
                    (result.max_diff_pair.provider_a, result.max_diff_pair.provider_b)
                    if result.max_diff_pair
                    else None
                ),
                "disagreeing_count": result.disagreeing_providers,
                "diff_image": (
                    result.max_diff_pair.diff_result.diff_image
                    if result.max_diff_pair
                    else None
                ),
            }

        except Exception as exc:
            logger.error("Pixel diff hatasi: %s", exc)
            return None

    async def _run_blur_detection(
        self,
        provider_tiles: Dict[str, Image.Image],
    ) -> Optional[Dict[str, Any]]:
        """Bulaniklik tespitini calistirir.

        Args:
            provider_tiles: Saglayici adi → PIL Image sozlugu.

        Returns:
            BlurDetector sonuclari veya None.
        """
        if len(provider_tiles) < 2:
            logger.warning(
                "Blur tespiti icin yetersiz saglayici: %d",
                len(provider_tiles),
            )
            return None

        try:
            from app.services.analyzers.blur_detector import (
                BlurDetector,
                BlurVisualizer,
            )

            detector = BlurDetector()
            comparison = detector.compare_blur_across_providers(provider_tiles)

            # Isitma haritasi olustur (en bulanik saglayici icin)
            heatmap: Optional[Image.Image] = None
            if comparison.most_blurred_provider:
                blurred_img = provider_tiles.get(
                    comparison.most_blurred_provider
                )
                if blurred_img:
                    blur_map = detector.detect_regional_blur(blurred_img)
                    visualizer = BlurVisualizer()
                    heatmap = visualizer.create_blur_heatmap(
                        blurred_img, blur_map, save=True
                    )

            logger.info(
                "Blur tespiti tamamlandi: sansur=%.1f (%s), "
                "en_bulanik=%s",
                comparison.censorship_score,
                comparison.censorship_verdict,
                comparison.most_blurred_provider,
            )

            return {
                "comparison": comparison,
                "censorship_score": comparison.censorship_score,
                "censorship_verdict": comparison.censorship_verdict,
                "most_blurred": comparison.most_blurred_provider,
                "sharpest": comparison.sharpest_provider,
                "heatmap": heatmap,
            }

        except Exception as exc:
            logger.error("Blur tespiti hatasi: %s", exc)
            return None

    async def _run_geospatial_analysis(
        self,
        lat: float,
        lng: float,
        zoom: int,
        osm_buildings: List[Any],
        satellite_image: Optional[Image.Image],
    ) -> Optional[Dict[str, Any]]:
        """Mekansal analizi calistirir (OSM vs uydu).

        Args:
            lat: Enlem.
            lng: Boylam.
            zoom: Zoom seviyesi.
            osm_buildings: OSM bina listesi.
            satellite_image: Uydu goruntusu.

        Returns:
            GeospatialAnalyzer sonuclari veya None.
        """
        if not osm_buildings or satellite_image is None:
            logger.warning(
                "Geospatial analiz icin yetersiz veri: "
                "OSM=%d, uydu=%s",
                len(osm_buildings),
                "var" if satellite_image else "yok",
            )
            return None

        try:
            from app.services.analyzers.geospatial_analyzer import (
                GeospatialAnalyzer,
            )

            from app.services.analyzers.geospatial_analyzer import BuildingDetector

            analyzer = GeospatialAnalyzer(
                building_detector=BuildingDetector(
                    model_name=settings.BUILDING_DETECTOR_WEIGHTS,
                ),
            )
            result = analyzer.analyze(
                lat=lat,
                lng=lng,
                zoom=zoom,
                osm_buildings=osm_buildings,
                satellite_image=satellite_image,
            )

            logger.info(
                "Geospatial analiz tamamlandi: ghost=%d, hidden=%d, "
                "coverage=%.2f",
                len(result.ghost_buildings),
                len(result.hidden_structures),
                result.coverage_ratio,
            )

            return {
                "result": result,
                "ghost_count": len(result.ghost_buildings),
                "hidden_count": len(result.hidden_structures),
                "coverage_ratio": result.coverage_ratio,
                "ghost_buildings": result.ghost_buildings,
                "hidden_structures": result.hidden_structures,
            }

        except Exception as exc:
            logger.error("Geospatial analiz hatasi: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    # Skor hesaplama
    # ------------------------------------------------------------------ #

    def _compute_confidence_score(
        self,
        *,
        pixel_diff_result: Optional[Dict[str, Any]],
        blur_result: Optional[Dict[str, Any]],
        geospatial_result: Optional[Dict[str, Any]],
        provider_count: int,
    ) -> ScoreBreakdown:
        """Agirlikli toplam ile nihai guven skoru hesaplar.

        Bilesen skorlari (her biri 0–100):
          - provider_disagreement: Kac saglayici birbirinden farkli?
          - pixel_diff: En yuksek saglayici farki
          - blur_censorship: Kasitli bulaniklik tespiti
          - geospatial_mismatch: OSM vs uydu uyumsuzlugu
          - historical_change: Tarihsel degisim skoru

        Args:
            pixel_diff_result: PixelDiffAnalyzer sonuclari.
            blur_result: BlurDetector sonuclari.
            geospatial_result: GeospatialAnalyzer sonuclari.
            provider_count: Basarili saglayici sayisi.

        Returns:
            ScoreBreakdown — bilesen bazli skor dagilimi.
        """
        breakdown = ScoreBreakdown()

        # --- Provider disagreement score ---
        # "Uyumsuz" = taban p90 ustu fark veren cift (pixel_diff.ANOMALY_MEDIUM_DIFF).
        # Iki kaynakli duzende (Esri + MapTiler) en fazla 50 puan.
        if pixel_diff_result:
            disagreeing = pixel_diff_result.get("disagreeing_count", 0)
            # Uyumsuz saglayici sayisini 0-100'e normalize et
            if provider_count >= 4 and disagreeing >= 4:
                breakdown.provider_disagreement_score = 100.0
            elif provider_count >= 3 and disagreeing >= 3:
                breakdown.provider_disagreement_score = 80.0
            elif disagreeing >= 2:
                breakdown.provider_disagreement_score = 50.0
            elif disagreeing >= 1:
                breakdown.provider_disagreement_score = 25.0

        # --- Pixel diff score ---
        # Ham fark dogrudan puan degildir (siradan konum ~%70); taban dagilimina gore olceklenir.
        if pixel_diff_result:
            max_diff = pixel_diff_result.get("max_diff_score", 0.0)
            breakdown.raw_max_diff = max_diff
            breakdown.pixel_diff_score = diff_to_score(max_diff, provider_count)
            breakdown.raw_max_diff_p90 = diff_baseline(provider_count)[0]

        # --- Blur censorship score ---
        if blur_result:
            breakdown.raw_censorship = blur_result.get("censorship_score", 0.0)
            breakdown.blur_censorship_score = censorship_to_score(breakdown.raw_censorship)
            breakdown.raw_censorship_p90 = CENSORSHIP_BASELINE_P90

        # --- Geospatial mismatch score ---
        if geospatial_result:
            ghost_count = geospatial_result.get("ghost_count", 0)
            hidden_count = geospatial_result.get("hidden_count", 0)
            coverage = geospatial_result.get("coverage_ratio", 1.0)

            # Ghost + hidden sayisina gore skor
            structure_score = min(100.0, (ghost_count + hidden_count) * 15.0)

            # Dusuk kapsam bonusu
            coverage_penalty = 0.0
            if coverage < 0.3:
                coverage_penalty = 40.0
            elif coverage < 0.5:
                coverage_penalty = 20.0

            breakdown.geospatial_mismatch_score = min(
                100.0, structure_score + coverage_penalty
            )

        # --- Historical change score ---
        # Zaman serisi (Esri Wayback) ayri bir uctan sunulur; skora henuz bagli degil.
        breakdown.historical_change_score = 0.0
        if not settings.BUILDING_DETECTOR_WEIGHTS:
            breakdown.inactive_signals.append(INACTIVE_GEOSPATIAL)
        breakdown.inactive_signals.append(INACTIVE_HISTORICAL)

        # --- Agirlikli toplam ---
        breakdown.weighted_total = min(100.0, (
            breakdown.provider_disagreement_score * WEIGHT_PROVIDER_DISAGREEMENT
            + breakdown.pixel_diff_score * WEIGHT_PIXEL_DIFF
            + breakdown.blur_censorship_score * WEIGHT_BLUR_CENSORSHIP
            + breakdown.geospatial_mismatch_score * WEIGHT_GEOSPATIAL_MISMATCH
            + breakdown.historical_change_score * WEIGHT_HISTORICAL_CHANGE
        ))

        logger.info(
            "Skor hesaplandi: provider=%.1f, pixel=%.1f, blur=%.1f, "
            "geo=%.1f, hist=%.1f => toplam=%.1f",
            breakdown.provider_disagreement_score,
            breakdown.pixel_diff_score,
            breakdown.blur_censorship_score,
            breakdown.geospatial_mismatch_score,
            breakdown.historical_change_score,
            breakdown.weighted_total,
        )

        return breakdown

    # ------------------------------------------------------------------ #
    # Kategori belirleme ve aday olusturma
    # ------------------------------------------------------------------ #

    def _build_candidates(
        self,
        *,
        lat: float,
        lng: float,
        score_breakdown: ScoreBreakdown,
        pixel_diff_result: Optional[Dict[str, Any]],
        blur_result: Optional[Dict[str, Any]],
        geospatial_result: Optional[Dict[str, Any]],
        provider_tiles: Dict[str, Image.Image],
    ) -> List[AnomalyCandidate]:
        """Analiz sonuclarindan anomali adaylarini olusturur.

        Kategori belirleme kurallari (oncelik sirasina gore):
          1. blur_score > 70 → CENSORED_AREA
          2. hidden_structures > 0 → HIDDEN_STRUCTURE
          3. ghost_buildings > 0 → GHOST_BUILDING
          4. pixel_diff yuksek, digerleri dusuk → IMAGE_DISCREPANCY

        Birden fazla kategori gecerliyse her biri icin ayri aday olusturulur.

        Args:
            lat: Enlem.
            lng: Boylam.
            score_breakdown: Hesaplanan skor dagilimi.
            pixel_diff_result: Pixel diff sonuclari.
            blur_result: Blur sonuclari.
            geospatial_result: Geospatial sonuclari.
            provider_tiles: Saglayici tile goruntueri.

        Returns:
            AnomalyCandidate listesi.
        """
        candidates: List[AnomalyCandidate] = []

        # Gorselleri bagla
        diff_image = None
        if pixel_diff_result:
            diff_image = pixel_diff_result.get("diff_image")

        blur_heatmap = None
        if blur_result:
            blur_heatmap = blur_result.get("heatmap")

        # ---- Kural 1: CENSORED_AREA ----
        if blur_result:
            censorship_score = blur_result.get("censorship_score", 0.0)
            if score_breakdown.blur_censorship_score > SIGNAL_FLAG_SCORE:
                most_blurred = blur_result.get("most_blurred", "bilinmiyor")
                sharpest = blur_result.get("sharpest", "bilinmiyor")
                comparison = blur_result.get("comparison")
                reasons = list(getattr(comparison, "reasons", []) or [])

                candidates.append(
                    AnomalyCandidate(
                        category=AnomalyCategory.CENSORED_AREA.value,
                        lat=lat,
                        lng=lng,
                        confidence_score=self._category_score(
                            score_breakdown, AnomalyCategory.CENSORED_AREA
                        ),
                        title=f"Bulanıklık farkı: {provider_name(most_blurred)}",
                        description=(
                            f"{provider_name(most_blurred)} karosu {provider_name(sharpest)} "
                            f"karosuna göre belirgin "
                            f"biçimde daha bulanık (ham skor {censorship_score:.0f}; "
                            f"sıradan konumlarda en fazla 20). Kasıtlı bulanıklaştırma, "
                            f"düşük çözünürlüklü mozaik ya da bulut olabilir; insan "
                            f"doğrulaması gerekir."
                        ),
                        score_breakdown=score_breakdown,
                        source_providers=list(provider_tiles.keys()),
                        detection_methods=["blur_detection", "fft_analysis",
                                           "regional_blur_map"],
                        meta_data={
                            "censorship_score": censorship_score,
                            "most_blurred_provider": most_blurred,
                            "sharpest_provider": sharpest,
                            "reasons": reasons,
                        },
                        provider_images=provider_tiles,
                        blur_heatmap=blur_heatmap,
                    )
                )

        # ---- Kural 2: HIDDEN_STRUCTURE ----
        if geospatial_result:
            hidden_count = geospatial_result.get("hidden_count", 0)
            if hidden_count > 0:
                hidden_structures = geospatial_result.get("hidden_structures", [])
                # En yuksek skorlu hidden structure
                top_hidden = hidden_structures[0] if hidden_structures else None
                top_lat = lat
                top_lng = lng
                if top_hidden and hasattr(top_hidden, "center_geo") and top_hidden.center_geo:
                    top_lat, top_lng = top_hidden.center_geo

                candidates.append(
                    AnomalyCandidate(
                        category=AnomalyCategory.HIDDEN_STRUCTURE.value,
                        lat=top_lat,
                        lng=top_lng,
                        confidence_score=self._category_score(
                            score_breakdown, AnomalyCategory.HIDDEN_STRUCTURE
                        ),
                        title=f"Gizli yapı adayı ({hidden_count} yapı)",
                        description=(
                            f"Uydu görüntüsünde {hidden_count} yapı tespit "
                            f"edildi ancak OSM'de kayıtlı değil. "
                            f"Eksik harita verisi ya da yeni inşaat olabilir."
                        ),
                        score_breakdown=score_breakdown,
                        source_providers=["satellite", "osm"],
                        detection_methods=["yolo_v8", "geospatial_cross_reference"],
                        meta_data={
                            "hidden_count": hidden_count,
                            "hidden_structures": [
                                h.to_dict() for h in hidden_structures[:5]
                            ],
                        },
                        provider_images=provider_tiles,
                        diff_image=diff_image,
                    )
                )

        # ---- Kural 3: GHOST_BUILDING ----
        if geospatial_result:
            ghost_count = geospatial_result.get("ghost_count", 0)
            if ghost_count > 0:
                ghost_buildings = geospatial_result.get("ghost_buildings", [])
                # En yuksek skorlu ghost
                top_ghost = ghost_buildings[0] if ghost_buildings else None
                ghost_lat = lat
                ghost_lng = lng
                if top_ghost and hasattr(top_ghost, "centroid"):
                    ghost_lat, ghost_lng = top_ghost.centroid

                candidates.append(
                    AnomalyCandidate(
                        category=AnomalyCategory.GHOST_BUILDING.value,
                        lat=ghost_lat,
                        lng=ghost_lng,
                        confidence_score=self._category_score(
                            score_breakdown, AnomalyCategory.GHOST_BUILDING
                        ),
                        title=f"Hayalet bina adayı ({ghost_count} bina)",
                        description=(
                            f"OSM'de {ghost_count} bina kayıtlı ancak uydu "
                            f"görüntüsünde tespit edilemedi. Hatalı veri, "
                            f"yıkılmış bina ya da sahte kayıt olabilir."
                        ),
                        score_breakdown=score_breakdown,
                        source_providers=["osm", "satellite"],
                        detection_methods=["geospatial_cross_reference",
                                           "yolo_v8"],
                        meta_data={
                            "ghost_count": ghost_count,
                            "ghost_buildings": [
                                g.to_dict() for g in ghost_buildings[:5]
                            ],
                        },
                        provider_images=provider_tiles,
                        diff_image=diff_image,
                    )
                )

        # ---- Kural 4: IMAGE_DISCREPANCY ----
        if pixel_diff_result:
            max_diff = pixel_diff_result.get("max_diff_score", 0.0)
            geo_score = score_breakdown.geospatial_mismatch_score

            # Pixel diff taban p99 ustu AMA bulaniklik ve mekansal sinyal yok → gorsel tutarsizlik
            if (
                score_breakdown.pixel_diff_score > SIGNAL_FLAG_SCORE
                and score_breakdown.blur_censorship_score <= SIGNAL_FLAG_SCORE
                and geo_score < 30
            ):
                diff_pair = pixel_diff_result.get("max_diff_pair")
                pair_label = (
                    f"{provider_name(diff_pair[0])} ↔ {provider_name(diff_pair[1])}"
                    if diff_pair
                    else "bilinmiyor"
                )

                candidates.append(
                    AnomalyCandidate(
                        category=AnomalyCategory.IMAGE_DISCREPANCY.value,
                        lat=lat,
                        lng=lng,
                        confidence_score=self._category_score(
                            score_breakdown, AnomalyCategory.IMAGE_DISCREPANCY
                        ),
                        title=f"Görüntü farkı ({pair_label})",
                        description=(
                            f"Kaynaklar arası piksel farkı %{tr_decimal(max_diff)} "
                            f"({pair_label}); sıradan konumların %99'unda "
                            f"%{tr_decimal(diff_baseline(len(provider_tiles))[1])} altında. "
                            f"Bulanıklık farkı yok; fark çekim tarihi, mevsim, "
                            f"yeni inşaat ya da yıkım olabilir."
                        ),
                        score_breakdown=score_breakdown,
                        source_providers=list(provider_tiles.keys()),
                        detection_methods=["pixel_diff", "ssim",
                                           "histogram_comparison"],
                        meta_data={
                            "max_diff_score": max_diff,
                            "max_diff_pair": diff_pair,
                            "anomaly_score": pixel_diff_result.get(
                                "anomaly_score", 0.0
                            ),
                        },
                        provider_images=provider_tiles,
                        diff_image=diff_image,
                    )
                )

        return candidates

    @staticmethod
    def _category_score(
        breakdown: ScoreBreakdown,
        category: AnomalyCategory,
    ) -> float:
        """Kategoriye ozel guven skoru hesaplar.

        Her kategori icin en ilgili bilesen skorlarini agirliklandirir.

        Args:
            breakdown: Skor bilesen dagilimi.
            category: Anomali kategorisi.

        Returns:
            Kategoriye ozel guven skoru (0–100).
        """
        if category == AnomalyCategory.CENSORED_AREA:
            # Kategoriyi doguran sinyalin taban-goreli puani
            return breakdown.blur_censorship_score

        elif category == AnomalyCategory.HIDDEN_STRUCTURE:
            # Geospatial agirlikli
            return min(100.0, (
                breakdown.geospatial_mismatch_score * 0.45
                + breakdown.pixel_diff_score * 0.20
                + breakdown.blur_censorship_score * 0.20
                + breakdown.provider_disagreement_score * 0.15
            ))

        elif category == AnomalyCategory.GHOST_BUILDING:
            # Geospatial + provider agirlikli
            return min(100.0, (
                breakdown.geospatial_mismatch_score * 0.40
                + breakdown.provider_disagreement_score * 0.25
                + breakdown.pixel_diff_score * 0.20
                + breakdown.blur_censorship_score * 0.15
            ))

        elif category == AnomalyCategory.IMAGE_DISCREPANCY:
            # Kategoriyi doguran sinyalin taban-goreli puani
            return breakdown.pixel_diff_score

        # Fallback: agirlikli toplam
        return breakdown.weighted_total

    # ------------------------------------------------------------------ #
    # Veritabani kaydi
    # ------------------------------------------------------------------ #

    async def _save_to_database(
        self,
        candidates: List[AnomalyCandidate],
        zoom: int,
    ) -> int:
        """Anomali adaylarini veritabanina kaydeder.

        Her aday icin:
          - anomalies tablosuna ana kayit
          - anomaly_images tablosuna saglayici gorselleri

        Args:
            candidates: Kaydedilecek anomali adaylari.
            zoom: Zoom seviyesi (tile bilgisi icin).

        Returns:
            Basariyla kaydedilen anomali sayisi.
        """
        from app.models.anomaly import Anomaly
        from app.models.anomaly_image import AnomalyImage

        saved = 0

        try:
            async with AsyncSessionLocal() as session:
                for candidate in candidates:
                    try:
                        existing = await self._find_existing(session, candidate)
                        if existing is not None:
                            await self._refresh_existing(session, existing, candidate, zoom)
                            saved += 1
                            continue

                        # Anomaly kaydı olustur
                        anomaly_id = uuid.uuid4()

                        anomaly = Anomaly(
                            id=anomaly_id,
                            lat=candidate.lat,
                            lng=candidate.lng,
                            geom=f"SRID=4326;POINT({candidate.lng} {candidate.lat})",
                            category=candidate.category,
                            confidence_score=candidate.confidence_score,
                            title=candidate.title,
                            description=candidate.description,
                            status=AnomalyStatus.PENDING.value,
                            source_providers=candidate.source_providers,
                            detection_methods=candidate.detection_methods,
                            meta_data={
                                **candidate.meta_data,
                                "score_breakdown": candidate.score_breakdown.to_dict(),
                            },
                        )
                        session.add(anomaly)

                        # Saglayici gorsellerini kaydet
                        for provider_name, img in candidate.provider_images.items():
                            try:
                                image_url = await self._save_provider_image(
                                    img, provider_name,
                                    candidate.lat, candidate.lng,
                                )

                                anomaly_image = AnomalyImage(
                                    id=uuid.uuid4(),
                                    anomaly_id=anomaly_id,
                                    provider=provider_name,
                                    image_url=image_url,
                                    captured_at=datetime.now(timezone.utc),
                                    zoom_level=zoom,
                                    is_blurred=(
                                        provider_name == candidate.meta_data.get(
                                            "most_blurred_provider"
                                        )
                                    ),
                                )
                                session.add(anomaly_image)

                            except Exception as img_exc:
                                logger.warning(
                                    "Gorsel kaydi basarisiz (%s): %s",
                                    provider_name, img_exc,
                                )

                        saved += 1
                        logger.info(
                            "Anomali kaydedildi: %s @ (%.4f, %.4f) "
                            "score=%.1f",
                            candidate.category,
                            candidate.lat, candidate.lng,
                            candidate.confidence_score,
                        )

                    except Exception as row_exc:
                        logger.error(
                            "Anomali kaydi hatasi: %s", row_exc
                        )

                await session.commit()

        except Exception as db_exc:
            logger.error("Veritabani yazma hatasi: %s", db_exc)

        logger.info(
            "Veritabani kaydi tamamlandi: %d/%d basarili",
            saved, len(candidates),
        )

        return saved

    @staticmethod
    async def _find_existing(session: Any, candidate: AnomalyCandidate) -> Optional[Any]:
        """Aynı kategoride DEDUP_RADIUS_M içindeki reddedilmemiş kaydı döndürür."""
        from geoalchemy2 import Geography
        from sqlalchemy import func, select

        from app.models.anomaly import Anomaly

        point = func.ST_GeographyFromText(f"SRID=4326;POINT({candidate.lng} {candidate.lat})")
        stmt = (
            select(Anomaly)
            .where(
                Anomaly.category == candidate.category,
                Anomaly.status != AnomalyStatus.REJECTED.value,
                func.ST_DWithin(Anomaly.geom.cast(Geography), point, DEDUP_RADIUS_M),
            )
            .order_by(Anomaly.detected_at.asc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _refresh_existing(
        self, session: Any, existing: Any, candidate: AnomalyCandidate, zoom: int
    ) -> None:
        """Var olan bulguyu son ölçümle günceller; doğrulama durumu ve oylar korunur."""
        from sqlalchemy import delete

        from app.models.anomaly_image import AnomalyImage

        previous = dict(existing.meta_data or {})
        existing.confidence_score = candidate.confidence_score
        existing.title = candidate.title
        existing.description = candidate.description
        existing.source_providers = candidate.source_providers
        existing.detection_methods = candidate.detection_methods
        existing.meta_data = {
            **previous,
            **candidate.meta_data,
            "score_breakdown": candidate.score_breakdown.to_dict(),
            "scan_count": int(previous.get("scan_count", 1)) + 1,
            "last_scanned_at": datetime.now(timezone.utc).isoformat(),
        }
        existing.updated_at = datetime.now(timezone.utc)

        # Kanıt karoları son ölçümün karolarıyla değiştirilir.
        await session.execute(delete(AnomalyImage).where(AnomalyImage.anomaly_id == existing.id))
        for provider_name_, img in candidate.provider_images.items():
            image_url = await self._save_provider_image(img, provider_name_, candidate.lat, candidate.lng)
            session.add(
                AnomalyImage(
                    id=uuid.uuid4(),
                    anomaly_id=existing.id,
                    provider=provider_name_,
                    image_url=image_url,
                    captured_at=datetime.now(timezone.utc),
                    zoom_level=zoom,
                    is_blurred=(provider_name_ == candidate.meta_data.get("most_blurred_provider")),
                )
            )
        logger.info(
            "Var olan anomali guncellendi: %s @ (%.4f, %.4f) score=%.1f",
            candidate.category, candidate.lat, candidate.lng, candidate.confidence_score,
        )

    @staticmethod
    async def _save_provider_image(
        image: Image.Image,
        provider: str,
        lat: float,
        lng: float,
    ) -> str:
        """Saglayici gorselini dosyaya kaydeder ve URL dondurur.

        Args:
            image: PIL Image objesi.
            provider: Saglayici adi.
            lat: Enlem.
            lng: Boylam.

        Returns:
            API'nin servis ettigi yol: ``/media/anomaly_images/<dosya>`` (bkz. main.py).
            Eskiden diskteki yol donuyordu; tarayici o adresi hicbir zaman acamiyordu.
        """
        from pathlib import Path

        storage_root = Path(
            getattr(settings, "STORAGE_ROOT", "data")
        ) / "anomaly_images"
        storage_root.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{provider}_{lat:.4f}_{lng:.4f}_{timestamp}_{unique_id}.png"

        filepath = storage_root / filename
        image.convert("RGB").save(str(filepath), "PNG", optimize=True)

        return f"/media/anomaly_images/{filename}"
