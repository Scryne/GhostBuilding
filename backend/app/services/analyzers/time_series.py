"""
time_series.py — Tarihsel harita degisim analiz modulu.

Bir lokasyonun yillar icindeki harita tile degisimlerini analiz eder.
Wayback Machine arsivinden tarihsel snapshot'lar toplayarak ardisik
yillar arasindaki degisimleri tespit eder. Ani silme/gorunme, blur
uygulanmasi ve cozunurluk degisimi gibi olaylari yakalar.

Modul iki ana siniftan olusur:
  - TimeSeriesAnalyzer: Tarihsel snapshot toplama ve degisim tespiti
  - ChangeVisualizer: Zaman cizelgesi ve karsilastirma gorselleri
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

# Cikti dizini
TIMESERIES_OUTPUT_ROOT: str = os.path.join(
    getattr(settings, "STORAGE_ROOT", "data"), "timeseries_results"
)

# Degisim tespiti esikleri
DIFF_THRESHOLD_SUDDEN: float = 25.0     # Ani degisim esigi (diff_score)
DIFF_THRESHOLD_MODERATE: float = 12.0   # Orta degisim esigi
DIFF_THRESHOLD_MINOR: float = 5.0       # Kucuk degisim esigi

# Blur tespiti esikleri (Laplacian varyans)
BLUR_SHARP_THRESHOLD: float = 100.0     # Net goruntu
BLUR_SEVERE_THRESHOLD: float = 50.0     # Siddetli bulaniklik

# Tarihsel skor esikleri
HISTORICAL_SCORE_MAX: float = 100.0
SCORE_SUDDEN_APPEAR: float = 35.0       # Ani yapi belirme
SCORE_SUDDEN_DISAPPEAR: float = 40.0    # Ani yapi kaybolma
SCORE_BLUR_APPLIED: float = 45.0        # Blur'un belirli tarihte baslamasi
SCORE_RESOLUTION_CHANGE: float = 15.0   # Cozunurluk degisimi

# Normalize boyutu (tum snapshot'lar bu boyuta getirilir)
NORMALIZE_SIZE: Tuple[int, int] = (256, 256)

# Varsayilan tarihsel arama parametreleri
DEFAULT_YEARS_BACK: int = 10
MAX_TIMELINE_ENTRIES: int = 15


# ---------------------------------------------------------------------------
# Enum: Degisim turleri
# ---------------------------------------------------------------------------


class ChangeType(str, Enum):
    """Tespit edilebilen degisim turleri."""

    STRUCTURE_APPEARED = "STRUCTURE_APPEARED"
    STRUCTURE_DISAPPEARED = "STRUCTURE_DISAPPEARED"
    BLUR_APPLIED = "BLUR_APPLIED"
    BLUR_REMOVED = "BLUR_REMOVED"
    RESOLUTION_CHANGED = "RESOLUTION_CHANGED"
    SIGNIFICANT_CHANGE = "SIGNIFICANT_CHANGE"
    MINOR_CHANGE = "MINOR_CHANGE"
    NO_CHANGE = "NO_CHANGE"


# ---------------------------------------------------------------------------
# Veri siniflari
# ---------------------------------------------------------------------------


@dataclass
class TimelineEntry:
    """Tek bir tarihsel snapshot bilgisi.

    Attributes:
        date: Snapshot tarihi (ISO 8601).
        year: Yil (kisa erisim icin).
        image: Normalize edilmis PIL Image.
        wayback_url: Wayback Machine erisim URL'si.
        digest: Icerik hash'i (degisiklik tespiti icin).
        laplacian_variance: Goruntunun Laplacian varyans degeri.
        mean_intensity: Ortalama piksel yogunlugu (0-255).
        source: Veri kaynagi (orn. "wayback_osm").
    """

    date: str
    year: int
    image: Image.Image
    wayback_url: str = ""
    digest: str = ""
    laplacian_variance: float = 0.0
    mean_intensity: float = 0.0
    source: str = "wayback"

    def to_dict(self) -> Dict[str, Any]:
        """Sozluk temsiline donusturur (image haric)."""
        return {
            "date": self.date,
            "year": self.year,
            "wayback_url": self.wayback_url,
            "digest": self.digest,
            "laplacian_variance": round(self.laplacian_variance, 2),
            "mean_intensity": round(self.mean_intensity, 2),
            "source": self.source,
        }


@dataclass
class Timeline:
    """Tarihsel snapshot dizisi.

    Attributes:
        entries: Kronolojik siradaki snapshot'lar.
        lat: Merkez enlemi.
        lng: Merkez boylami.
        zoom: Zoom seviyesi.
        provider: Tile saglayicisi.
        date_range: (baslangic, bitis) tarih araligi.
    """

    entries: List[TimelineEntry]
    lat: float
    lng: float
    zoom: int
    provider: str = "osm"
    date_range: Tuple[str, str] = ("", "")

    @property
    def year_count(self) -> int:
        """Kapsanan farkli yil sayisi."""
        return len(set(e.year for e in self.entries))

    @property
    def span_years(self) -> int:
        """Ilk ve son snapshot arasindaki yil farki."""
        if len(self.entries) < 2:
            return 0
        return self.entries[-1].year - self.entries[0].year

    def to_dict(self) -> Dict[str, Any]:
        """Sozluk temsiline donusturur."""
        return {
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "zoom": self.zoom,
            "provider": self.provider,
            "date_range": self.date_range,
            "year_count": self.year_count,
            "span_years": self.span_years,
            "entry_count": len(self.entries),
            "entries": [e.to_dict() for e in self.entries],
        }


@dataclass
class ChangeEvent:
    """Iki ardisik snapshot arasinda tespit edilen degisim olayi.

    Attributes:
        date: Degisimin tespit edildigi tarih (sonraki snapshot).
        date_before: Onceki snapshot tarihi.
        diff_score: Piksel fark yuzdesi (0-100).
        change_type: Degisim turu.
        description: Insan okunabilir aciklama.
        confidence: Tespit guven skoru (0-1).
        thumbnail_before: Onceki goruntu kucuk resmi.
        thumbnail_after: Sonraki goruntu kucuk resmi.
        laplacian_before: Onceki goruntuun Laplacian varyansi.
        laplacian_after: Sonraki goruntuun Laplacian varyansi.
        ssim_score: Yapisal benzerlik skoru (0-1).
    """

    date: str
    date_before: str
    diff_score: float
    change_type: ChangeType
    description: str
    confidence: float = 0.0
    thumbnail_before: Optional[Image.Image] = None
    thumbnail_after: Optional[Image.Image] = None
    laplacian_before: float = 0.0
    laplacian_after: float = 0.0
    ssim_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Sozluk temsiline donusturur (thumbnail'lar haric)."""
        return {
            "date": self.date,
            "date_before": self.date_before,
            "diff_score": round(self.diff_score, 2),
            "change_type": self.change_type.value,
            "description": self.description,
            "confidence": round(self.confidence, 3),
            "laplacian_before": round(self.laplacian_before, 2),
            "laplacian_after": round(self.laplacian_after, 2),
            "ssim_score": round(self.ssim_score, 4),
        }


@dataclass
class ChartData:
    """D3.js uyumlu zaman cizelgesi veri yapisi.

    Attributes:
        data_points: Her nokta icin {date, diff_score, is_anomaly, label}.
        anomaly_points: Anomali olarak isaretlenen nokta indeksleri.
        y_label: Y ekseni etiketi.
        x_label: X ekseni etiketi.
        title: Grafik basligi.
    """

    data_points: List[Dict[str, Any]]
    anomaly_points: List[int] = field(default_factory=list)
    y_label: str = "Degisim Skoru (%)"
    x_label: str = "Tarih"
    title: str = "Tarihsel Degisim Analizi"

    def to_json(self) -> str:
        """JSON string'e donusturur."""
        return json.dumps(
            {
                "data": self.data_points,
                "anomaly_indices": self.anomaly_points,
                "y_label": self.y_label,
                "x_label": self.x_label,
                "title": self.title,
            },
            indent=2,
            ensure_ascii=False,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Sozluk temsiline donusturur."""
        return {
            "data": self.data_points,
            "anomaly_indices": self.anomaly_points,
            "y_label": self.y_label,
            "x_label": self.x_label,
            "title": self.title,
        }


# ---------------------------------------------------------------------------
# Yardimci: Goruntu metrikleri
# ---------------------------------------------------------------------------


def _compute_laplacian_var(img: Image.Image) -> float:
    """Goruntuun Laplacian varyansini hesaplar.

    Args:
        img: PIL Image objesi.

    Returns:
        Laplacian varyans (float). Yuksek = keskin.
    """
    gray = np.array(img.convert("L"), dtype=np.uint8)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return float(laplacian.var())


def _compute_mean_intensity(img: Image.Image) -> float:
    """Goruntuun ortalama piksel yogunlugunu hesaplar.

    Args:
        img: PIL Image objesi.

    Returns:
        Ortalama yogunluk (0-255).
    """
    gray = np.array(img.convert("L"), dtype=np.uint8)
    return float(np.mean(gray))


def _compute_diff_score(img1: Image.Image, img2: Image.Image) -> float:
    """Iki goruntu arasindaki piksel fark yuzdesini hesaplar.

    Args:
        img1: Birinci goruntu.
        img2: Ikinci goruntu.

    Returns:
        Fark yuzdesi (0-100). 0 = ayni, 100 = tamamen farkli.
    """
    # Ayni boyuta getir
    size = (
        min(img1.width, img2.width),
        min(img1.height, img2.height),
    )
    arr1 = np.array(img1.convert("RGB").resize(size, Image.LANCZOS), dtype=np.uint8)
    arr2 = np.array(img2.convert("RGB").resize(size, Image.LANCZOS), dtype=np.uint8)

    # Mutlak fark
    abs_diff = cv2.absdiff(arr1, arr2)
    gray_diff = cv2.cvtColor(abs_diff, cv2.COLOR_RGB2GRAY)

    # Gurultu azaltma
    gray_diff = cv2.GaussianBlur(gray_diff, (5, 5), 0)

    # Esikleme (30 piksel farki)
    _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)

    total = thresh.shape[0] * thresh.shape[1]
    changed = int(np.count_nonzero(thresh))

    return (changed / total) * 100.0 if total > 0 else 0.0


def _compute_ssim(img1: Image.Image, img2: Image.Image) -> float:
    """Iki goruntu arasindaki SSIM skorunu hesaplar.

    Args:
        img1: Birinci goruntu.
        img2: Ikinci goruntu.

    Returns:
        SSIM skoru (0-1). 1 = tamamen ayni.
    """
    try:
        from skimage.metrics import structural_similarity as ssim

        size = (
            min(img1.width, img2.width),
            min(img1.height, img2.height),
        )
        gray1 = np.array(img1.convert("L").resize(size, Image.LANCZOS), dtype=np.uint8)
        gray2 = np.array(img2.convert("L").resize(size, Image.LANCZOS), dtype=np.uint8)

        min_dim = min(gray1.shape[0], gray1.shape[1])
        win_size = min(7, min_dim)
        if win_size % 2 == 0:
            win_size -= 1
        win_size = max(3, win_size)

        score, _ = ssim(
            gray1, gray2,
            win_size=win_size,
            full=True,
            data_range=255,
        )
        return float(score)

    except ImportError:
        logger.warning("scikit-image yuklu degil, SSIM atlanıyor")
        return 0.0
    except Exception as exc:
        logger.warning("SSIM hesaplama hatasi: %s", exc)
        return 0.0


def _create_thumbnail(img: Image.Image, size: int = 128) -> Image.Image:
    """Goruntunun kucuk resmini olusturur.

    Args:
        img: Kaynak goruntu.
        size: Kucuk resim boyutu (kare).

    Returns:
        Kucultulmus PIL Image.
    """
    thumb = img.copy()
    thumb.thumbnail((size, size), Image.LANCZOS)
    return thumb


# ---------------------------------------------------------------------------
# TimeSeriesAnalyzer — Tarihsel degisim analizi
# ---------------------------------------------------------------------------


class TimeSeriesAnalyzer:
    """Bir lokasyonun tarihsel harita degisimlerini analiz eder.

    Wayback Machine CDX API'den tarihsel tile snapshot'lari toplayarak
    ardisik yillar arasindaki degisimleri tespit eder. Ani yapi
    belirme/kaybolma, blur uygulanmasi ve cozunurluk degisimi gibi
    olaylari sinifllandirir ve tarihsel anomali skoru uretir.

    Attributes:
        _years_back: Kac yil geriye bakılacak.
        _max_entries: Maksimum timeline girisi sayisi.

    Examples:
        >>> analyzer = TimeSeriesAnalyzer()
        >>> timeline = await analyzer.fetch_timeline(41.0082, 28.9784, 15)
        >>> changes = analyzer.detect_changes(timeline)
        >>> for c in changes:
        ...     print(f"{c.date}: {c.change_type} ({c.diff_score:.1f}%)")
    """

    def __init__(
        self,
        *,
        years_back: int = DEFAULT_YEARS_BACK,
        max_entries: int = MAX_TIMELINE_ENTRIES,
    ) -> None:
        """
        Args:
            years_back: Tarihsel arama icin kac yil geriye gidilecek.
            max_entries: Maksimum timeline girisi sayisi.
        """
        self._years_back = years_back
        self._max_entries = max_entries

    # ------------------------------------------------------------------ #
    # fetch_timeline — Tarihsel snapshot toplama
    # ------------------------------------------------------------------ #

    async def fetch_timeline(
        self,
        lat: float,
        lng: float,
        zoom: int,
        *,
        years_back: Optional[int] = None,
        provider: str = "osm",
    ) -> Timeline:
        """Wayback Machine'den tarihsel tile snapshot dizisini toplar.

        CDX API'den snapshot listesi alir, her yil icin en temiz
        (benzersiz digest'li) snapshot'i secer ve goruntulerini
        indirip normalize eder.

        Args:
            lat: Enlem.
            lng: Boylam.
            zoom: Zoom seviyesi.
            years_back: Kac yil geriye gidilecek. None ise varsayilan.
            provider: Tile saglayicisi (varsayilan "osm").

        Returns:
            Timeline — kronolojik snapshot dizisi.

        Examples:
            >>> analyzer = TimeSeriesAnalyzer()
            >>> tl = await analyzer.fetch_timeline(41.0, 29.0, 15)
            >>> len(tl.entries) > 0
            True
        """
        from app.services.tile_fetcher import WaybackFetcher, TileProvider

        yb = years_back or self._years_back
        now = datetime.utcnow()
        date_from = datetime(now.year - yb, 1, 1)
        date_to = now

        # TileProvider enum degerini bul
        try:
            tile_provider = TileProvider(provider)
        except ValueError:
            tile_provider = TileProvider.OSM

        logger.info(
            "Timeline toplaniyor: (%.4f, %.4f) zoom=%d, "
            "%d yil gerisi, saglayici=%s",
            lat, lng, zoom, yb, provider,
        )

        # CDX sorgula
        snapshots: List[Dict[str, Any]] = []
        try:
            async with WaybackFetcher() as wb:
                raw_snapshots = await wb.fetch_historical(
                    lat, lng, zoom,
                    date_from=date_from,
                    date_to=date_to,
                    provider=tile_provider,
                )

                # Her yil icin en iyi snapshot'i sec
                yearly_best = self._select_best_per_year(raw_snapshots)

                # Goruntulerini indir
                for snap_info in yearly_best[:self._max_entries]:
                    url = snap_info.get("wayback_url", "")
                    if not url:
                        continue

                    img = await wb.fetch_snapshot_image(url)
                    if img is None:
                        logger.debug("Snapshot indirilemedi: %s", url)
                        continue

                    # Normalize et
                    img_normalized = img.convert("RGB").resize(
                        NORMALIZE_SIZE, Image.LANCZOS
                    )

                    # Metrikleri hesapla
                    lap_var = _compute_laplacian_var(img_normalized)
                    mean_int = _compute_mean_intensity(img_normalized)

                    # Tarih parse
                    ts = snap_info.get("timestamp", "")
                    year = self._parse_year(ts)

                    snapshots.append(snap_info)

                    # (sonraki islemde entries listesine eklenecek)
                    snap_info["_image"] = img_normalized
                    snap_info["_laplacian"] = lap_var
                    snap_info["_mean_intensity"] = mean_int
                    snap_info["_year"] = year

        except Exception as exc:
            logger.error("Timeline toplama hatasi: %s", exc)

        # TimelineEntry listesi olustur
        entries: List[TimelineEntry] = []
        for snap_info in snapshots:
            img_norm = snap_info.get("_image")
            if img_norm is None:
                continue

            entries.append(
                TimelineEntry(
                    date=snap_info.get("timestamp", ""),
                    year=snap_info.get("_year", 0),
                    image=img_norm,
                    wayback_url=snap_info.get("wayback_url", ""),
                    digest=snap_info.get("digest", ""),
                    laplacian_variance=snap_info.get("_laplacian", 0.0),
                    mean_intensity=snap_info.get("_mean_intensity", 0.0),
                    source=f"wayback_{provider}",
                )
            )

        # Kronolojik sirala
        entries.sort(key=lambda e: e.date)

        timeline = Timeline(
            entries=entries,
            lat=lat,
            lng=lng,
            zoom=zoom,
            provider=provider,
            date_range=(
                date_from.isoformat(),
                date_to.isoformat(),
            ),
        )

        logger.info(
            "Timeline tamamlandi: %d snapshot, %d yil kapsam",
            len(entries), timeline.span_years,
        )

        return timeline

    @staticmethod
    def _select_best_per_year(
        snapshots: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Her yil icin en iyi snapshot'i secer.

        Ayni yilda birden fazla snapshot varsa benzersiz digest'e
        sahip olan ve yilin ortasina en yakin olani secilir.

        Args:
            snapshots: Ham snapshot listesi.

        Returns:
            Yil bazinda filtrelenmis snapshot listesi.
        """
        yearly: Dict[int, List[Dict[str, Any]]] = {}

        for snap in snapshots:
            ts = snap.get("timestamp", "")
            year = TimeSeriesAnalyzer._parse_year(ts)
            if year <= 0:
                continue

            if year not in yearly:
                yearly[year] = []
            yearly[year].append(snap)

        # Her yildan birini sec
        best: List[Dict[str, Any]] = []
        for year in sorted(yearly.keys()):
            candidates = yearly[year]

            if len(candidates) == 1:
                best.append(candidates[0])
            else:
                # Yilin ortasina (1 Temmuz) en yakin olani sec
                mid_year_target = f"{year}0701"
                candidates.sort(
                    key=lambda s: abs(
                        int(s.get("timestamp", "0")[:8] or "0")
                        - int(mid_year_target)
                    )
                )
                best.append(candidates[0])

        return best

    @staticmethod
    def _parse_year(timestamp: str) -> int:
        """Timestamp string'inden yili cikarir.

        Args:
            timestamp: ISO 8601 veya yyyyMMddHHmmss formati.

        Returns:
            Yil (int) veya 0 (parse edilemezse).
        """
        if not timestamp:
            return 0

        # ISO 8601: 2020-01-15T...
        if "-" in timestamp[:5]:
            try:
                return int(timestamp[:4])
            except (ValueError, IndexError):
                return 0

        # CDX formati: 20200115120000
        try:
            return int(timestamp[:4])
        except (ValueError, IndexError):
            return 0

    # ------------------------------------------------------------------ #
    # detect_changes — Degisim tespiti
    # ------------------------------------------------------------------ #

    def detect_changes(
        self,
        timeline: Timeline,
    ) -> List[ChangeEvent]:
        """Ardisik snapshot'lar arasindaki degisimleri tespit eder.

        Her ardisik cift icin piksel farki, SSIM ve Laplacian varyans
        karsilastirmasi yapar. Degisim turunu siniflandirir:
          - STRUCTURE_APPEARED: Yeni yapi belirmesi
          - STRUCTURE_DISAPPEARED: Yapi kaybolmasi
          - BLUR_APPLIED: Bulaniklistirma uygulanmasi
          - BLUR_REMOVED: Bulanikligin kaldirilmasi
          - RESOLUTION_CHANGED: Cozunurluk degisimi
          - SIGNIFICANT_CHANGE: Onemli ama siniflanamayan degisim
          - MINOR_CHANGE: Kucuk degisim
          - NO_CHANGE: Kayda deger degisim yok

        Args:
            timeline: Tarihsel snapshot dizisi.

        Returns:
            ChangeEvent listesi (kronolojik sirada).

        Examples:
            >>> changes = analyzer.detect_changes(timeline)
            >>> for c in changes:
            ...     print(f"{c.date}: {c.change_type.value}")
        """
        if len(timeline.entries) < 2:
            logger.info("Degisim tespiti icin yetersiz snapshot: %d", len(timeline.entries))
            return []

        events: List[ChangeEvent] = []

        for i in range(1, len(timeline.entries)):
            entry_before = timeline.entries[i - 1]
            entry_after = timeline.entries[i]

            # Piksel farki hesapla
            diff_score = _compute_diff_score(entry_before.image, entry_after.image)

            # SSIM
            ssim_score = _compute_ssim(entry_before.image, entry_after.image)

            # Laplacian degisimi
            lap_before = entry_before.laplacian_variance
            lap_after = entry_after.laplacian_variance

            # Degisim turunu belirle
            change_type = self._classify_change(
                diff_score=diff_score,
                ssim_score=ssim_score,
                lap_before=lap_before,
                lap_after=lap_after,
                mean_before=entry_before.mean_intensity,
                mean_after=entry_after.mean_intensity,
            )

            # Guven skoru
            confidence = self._compute_change_confidence(
                diff_score, ssim_score, change_type
            )

            # Aciklama
            description = self._build_change_description(
                change_type=change_type,
                diff_score=diff_score,
                ssim_score=ssim_score,
                lap_before=lap_before,
                lap_after=lap_after,
                date_before=entry_before.date,
                date_after=entry_after.date,
            )

            # Kucuk resimler
            thumb_before = _create_thumbnail(entry_before.image)
            thumb_after = _create_thumbnail(entry_after.image)

            events.append(
                ChangeEvent(
                    date=entry_after.date,
                    date_before=entry_before.date,
                    diff_score=diff_score,
                    change_type=change_type,
                    description=description,
                    confidence=confidence,
                    thumbnail_before=thumb_before,
                    thumbnail_after=thumb_after,
                    laplacian_before=lap_before,
                    laplacian_after=lap_after,
                    ssim_score=ssim_score,
                )
            )

        # Onemli olaylari logla
        significant = [
            e for e in events
            if e.change_type not in (ChangeType.NO_CHANGE, ChangeType.MINOR_CHANGE)
        ]
        logger.info(
            "Degisim tespiti tamamlandi: %d toplam, %d onemli olay",
            len(events), len(significant),
        )

        return events

    @staticmethod
    def _classify_change(
        *,
        diff_score: float,
        ssim_score: float,
        lap_before: float,
        lap_after: float,
        mean_before: float,
        mean_after: float,
    ) -> ChangeType:
        """Metrik degerlerine gore degisim turunu siniflandirir.

        Args:
            diff_score: Piksel fark yuzdesi.
            ssim_score: SSIM yapisal benzerlik.
            lap_before: Onceki Laplacian varyans.
            lap_after: Sonraki Laplacian varyans.
            mean_before: Onceki ortalama yogunluk.
            mean_after: Sonraki ortalama yogunluk.

        Returns:
            ChangeType enum degeri.
        """
        # Onemli degisim yoksa
        if diff_score < DIFF_THRESHOLD_MINOR:
            return ChangeType.NO_CHANGE

        # Blur uygulanmasi: net goruntu → bulanik goruntu
        if (
            lap_before > BLUR_SHARP_THRESHOLD
            and lap_after < BLUR_SEVERE_THRESHOLD
            and diff_score > DIFF_THRESHOLD_MODERATE
        ):
            return ChangeType.BLUR_APPLIED

        # Blur kaldirilmasi: bulanik goruntu → net goruntu
        if (
            lap_before < BLUR_SEVERE_THRESHOLD
            and lap_after > BLUR_SHARP_THRESHOLD
            and diff_score > DIFF_THRESHOLD_MODERATE
        ):
            return ChangeType.BLUR_REMOVED

        # Cozunurluk degisimi: Laplacian onemli degisti ama icerik benzer
        lap_ratio = lap_after / lap_before if lap_before > 0 else 1.0
        if (
            (lap_ratio > 2.5 or lap_ratio < 0.4)
            and ssim_score > 0.5
            and diff_score < DIFF_THRESHOLD_SUDDEN
        ):
            return ChangeType.RESOLUTION_CHANGED

        # Ani degisim — yapi belirme/kaybolma
        if diff_score > DIFF_THRESHOLD_SUDDEN:
            # Yogunluk artisi (daha aydinlik icerik geldi = yapi belirdi)
            intensity_diff = mean_after - mean_before
            if intensity_diff > 15:
                return ChangeType.STRUCTURE_APPEARED
            elif intensity_diff < -15:
                return ChangeType.STRUCTURE_DISAPPEARED
            else:
                return ChangeType.SIGNIFICANT_CHANGE

        # Orta duzeyde degisim
        if diff_score > DIFF_THRESHOLD_MODERATE:
            return ChangeType.SIGNIFICANT_CHANGE

        # Kucuk degisim
        return ChangeType.MINOR_CHANGE

    @staticmethod
    def _compute_change_confidence(
        diff_score: float,
        ssim_score: float,
        change_type: ChangeType,
    ) -> float:
        """Degisim tespiti icin guven skoru hesaplar (0-1).

        Args:
            diff_score: Piksel fark yuzdesi.
            ssim_score: SSIM yapisal benzerlik.
            change_type: Belirlenen degisim turu.

        Returns:
            Guven skoru (0-1).
        """
        if change_type == ChangeType.NO_CHANGE:
            return 0.0

        # Temel guven: diff_score bazli
        base = min(1.0, diff_score / 50.0)

        # SSIM ayarlamasi: dusuk SSIM = daha guvenilir degisim
        ssim_factor = 1.0 - ssim_score * 0.3

        # Tur bazli bonus
        type_bonus = {
            ChangeType.BLUR_APPLIED: 0.2,
            ChangeType.BLUR_REMOVED: 0.15,
            ChangeType.STRUCTURE_APPEARED: 0.1,
            ChangeType.STRUCTURE_DISAPPEARED: 0.15,
            ChangeType.RESOLUTION_CHANGED: 0.05,
            ChangeType.SIGNIFICANT_CHANGE: 0.0,
            ChangeType.MINOR_CHANGE: -0.1,
        }.get(change_type, 0.0)

        return min(1.0, max(0.0, base * ssim_factor + type_bonus))

    @staticmethod
    def _build_change_description(
        *,
        change_type: ChangeType,
        diff_score: float,
        ssim_score: float,
        lap_before: float,
        lap_after: float,
        date_before: str,
        date_after: str,
    ) -> str:
        """Degisim olayi icin aciklama metni olusturur.

        Args:
            change_type: Degisim turu.
            diff_score: Piksel fark yuzdesi.
            ssim_score: SSIM skoru.
            lap_before: Onceki Laplacian varyans.
            lap_after: Sonraki Laplacian varyans.
            date_before: Onceki tarih.
            date_after: Sonraki tarih.

        Returns:
            Insan okunabilir aciklama.
        """
        descriptions = {
            ChangeType.STRUCTURE_APPEARED: (
                f"Yeni yapi/icerik tespit edildi. "
                f"Piksel farki: {diff_score:.1f}%."
            ),
            ChangeType.STRUCTURE_DISAPPEARED: (
                f"Yapi/icerik kayboldu veya silindi. "
                f"Piksel farki: {diff_score:.1f}%."
            ),
            ChangeType.BLUR_APPLIED: (
                f"Bulaniklistirma uygulanmis. "
                f"Laplacian: {lap_before:.0f} → {lap_after:.0f}. "
                f"Kasitli sansur olabilir."
            ),
            ChangeType.BLUR_REMOVED: (
                f"Bulaniklik kaldirilmis. "
                f"Laplacian: {lap_before:.0f} → {lap_after:.0f}."
            ),
            ChangeType.RESOLUTION_CHANGED: (
                f"Cozunurluk/keskinlik degisimi. "
                f"Laplacian: {lap_before:.0f} → {lap_after:.0f}."
            ),
            ChangeType.SIGNIFICANT_CHANGE: (
                f"Onemli gorsel degisim. "
                f"Piksel farki: {diff_score:.1f}%, SSIM: {ssim_score:.3f}."
            ),
            ChangeType.MINOR_CHANGE: (
                f"Kucuk degisim. "
                f"Piksel farki: {diff_score:.1f}%."
            ),
            ChangeType.NO_CHANGE: "Kayda deger degisim yok.",
        }

        base = descriptions.get(change_type, f"Degisim: {diff_score:.1f}%.")
        return f"{date_before[:10]} → {date_after[:10]}: {base}"

    # ------------------------------------------------------------------ #
    # compute_historical_score — Tarihsel anomali skoru
    # ------------------------------------------------------------------ #

    def compute_historical_score(
        self,
        timeline: Timeline,
        changes: Optional[List[ChangeEvent]] = None,
    ) -> float:
        """Timeline uzerinden tarihsel anomali skoru hesaplar.

        Skorlama kurallari:
          - Ani silme/kaybolma olayi: +40 puan
          - Ani yapi belirme olayi: +35 puan
          - Blur'un belirli bir tarihte baslamasi: +45 puan (maks)
          - Cozunurluk degisimi: +15 puan
          - Smooth/organik degisim: dusuk skor (normal)

        Args:
            timeline: Tarihsel snapshot dizisi.
            changes: Onceden hesaplanmis degisim listesi. None ise
                yeniden hesaplanir.

        Returns:
            Tarihsel anomali skoru (0–100).

        Examples:
            >>> score = analyzer.compute_historical_score(timeline)
            >>> 0 <= score <= 100
            True
        """
        if len(timeline.entries) < 2:
            return 0.0

        if changes is None:
            changes = self.detect_changes(timeline)

        if not changes:
            return 0.0

        score: float = 0.0

        for event in changes:
            if event.change_type == ChangeType.BLUR_APPLIED:
                score += SCORE_BLUR_APPLIED * event.confidence
            elif event.change_type == ChangeType.STRUCTURE_DISAPPEARED:
                score += SCORE_SUDDEN_DISAPPEAR * event.confidence
            elif event.change_type == ChangeType.STRUCTURE_APPEARED:
                score += SCORE_SUDDEN_APPEAR * event.confidence
            elif event.change_type == ChangeType.RESOLUTION_CHANGED:
                score += SCORE_RESOLUTION_CHANGE * event.confidence
            elif event.change_type == ChangeType.SIGNIFICANT_CHANGE:
                score += 10.0 * event.confidence

        # Pattern bonusu: blur sonrasi degisim yok = sansur sabitlesmis
        blur_events = [
            i for i, e in enumerate(changes)
            if e.change_type == ChangeType.BLUR_APPLIED
        ]
        if blur_events:
            last_blur_idx = blur_events[-1]
            # Blur'dan sonra gelen olaylar
            post_blur = changes[last_blur_idx + 1:]
            if post_blur:
                all_minor = all(
                    e.change_type in (ChangeType.NO_CHANGE, ChangeType.MINOR_CHANGE)
                    for e in post_blur
                )
                if all_minor:
                    # Blur uygulanmis ve sonrasinda hic onemli degisim yok
                    # → sansur sabitlesmis
                    score += 15.0

        # 0-100 araligina sinirla
        final = min(HISTORICAL_SCORE_MAX, max(0.0, score))

        logger.info(
            "Tarihsel skor: %.1f/100 (%d degisim olayi)",
            final, len(changes),
        )

        return final


# ---------------------------------------------------------------------------
# ChangeVisualizer — Gorselleştirme
# ---------------------------------------------------------------------------


class ChangeVisualizer:
    """Tarihsel degisim analizi sonuclarini gorsellestirir.

    Zaman cizelgesi (D3.js uyumlu JSON), karsilastirma izgarasi
    ve diff overlay gorselleri uretir.

    Attributes:
        _output_dir: Cikti dosyalarinin kaydedilecegi dizin.

    Examples:
        >>> viz = ChangeVisualizer()
        >>> chart = viz.create_timeline_chart(timeline, changes)
        >>> chart.to_json()
        '{"data": [...], "anomaly_indices": [...]}'
    """

    def __init__(
        self,
        *,
        output_dir: Optional[str] = None,
    ) -> None:
        """
        Args:
            output_dir: Cikti dizini. None ise varsayilan kullanilir.
        """
        self._output_dir = Path(output_dir or TIMESERIES_OUTPUT_ROOT)

    def _ensure_output_dir(self) -> Path:
        """Cikti dizininin var oldugunu garanti eder."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._output_dir

    def _generate_filename(self, prefix: str, ext: str) -> str:
        """Benzersiz dosya adi uretir."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"{prefix}_{timestamp}_{unique_id}.{ext}"

    # ------------------------------------------------------------------ #
    # create_timeline_chart — D3.js uyumlu zaman cizelgesi
    # ------------------------------------------------------------------ #

    def create_timeline_chart(
        self,
        timeline: Timeline,
        changes: List[ChangeEvent],
        *,
        save: bool = True,
    ) -> ChartData:
        """Degisim olaylarindan D3.js uyumlu zaman cizelgesi verisi olusturur.

        Her veri noktasi bir degisim olayini temsil eder.
        Anomali noktalar (ani degisimler) kirmizi ile isaretlenir.

        Args:
            timeline: Tarihsel snapshot dizisi.
            changes: Degisim olayi listesi.
            save: JSON dosyasina kaydet.

        Returns:
            ChartData — D3.js uyumlu veri yapisi.

        Examples:
            >>> chart = viz.create_timeline_chart(timeline, changes)
            >>> len(chart.data_points) == len(changes)
            True
        """
        data_points: List[Dict[str, Any]] = []
        anomaly_indices: List[int] = []

        for idx, event in enumerate(changes):
            is_anomaly = event.change_type in (
                ChangeType.BLUR_APPLIED,
                ChangeType.STRUCTURE_DISAPPEARED,
                ChangeType.STRUCTURE_APPEARED,
                ChangeType.SIGNIFICANT_CHANGE,
            )

            point: Dict[str, Any] = {
                "date": event.date[:10] if len(event.date) >= 10 else event.date,
                "date_before": event.date_before[:10] if len(event.date_before) >= 10 else event.date_before,
                "diff_score": round(event.diff_score, 2),
                "ssim_score": round(event.ssim_score, 4),
                "change_type": event.change_type.value,
                "is_anomaly": is_anomaly,
                "label": event.description[:80],
                "confidence": round(event.confidence, 3),
                "laplacian_before": round(event.laplacian_before, 1),
                "laplacian_after": round(event.laplacian_after, 1),
            }
            data_points.append(point)

            if is_anomaly:
                anomaly_indices.append(idx)

        chart = ChartData(
            data_points=data_points,
            anomaly_points=anomaly_indices,
            title=f"Tarihsel Degisim: ({timeline.lat:.4f}, {timeline.lng:.4f})",
        )

        # JSON dosyasina kaydet
        if save:
            out_dir = self._ensure_output_dir()
            filename = self._generate_filename("timeline_chart", "json")
            filepath = out_dir / filename

            filepath.write_text(
                chart.to_json(), encoding="utf-8"
            )
            logger.info("Timeline chart kaydedildi: %s", filepath)

        return chart

    # ------------------------------------------------------------------ #
    # create_comparison_grid — Karsilastirma izgarasi
    # ------------------------------------------------------------------ #

    def create_comparison_grid(
        self,
        timeline: Timeline,
        *,
        max_frames: int = 6,
        cell_size: int = 200,
        save: bool = True,
    ) -> Image.Image:
        """Tarihsel snapshot'larin karsilastirmali izgara gorselini olusturur.

        Her hucrede bir yilin tile goruntusu ve uzerine yil etiketi
        yazilir. Maksimum 6 kare gosterilir (esit aralikla secilir).

        Args:
            timeline: Tarihsel snapshot dizisi.
            max_frames: Maksimum gosterilecek kare sayisi (varsayilan 6).
            cell_size: Her hucrenin piksel boyutu (kare).
            save: Dosyaya kaydet.

        Returns:
            Karsilastirma izgarasi PIL Image.

        Examples:
            >>> grid = viz.create_comparison_grid(timeline)
            >>> grid.size[0] > 0
            True
        """
        entries = timeline.entries

        if not entries:
            # Bos goruntu dondur
            canvas = Image.new("RGB", (cell_size, cell_size), (30, 30, 30))
            draw = ImageDraw.Draw(canvas)
            draw.text((10, 10), "Veri yok", fill=(200, 200, 200))
            return canvas

        # Esit aralikla snapshot sec
        selected = self._select_evenly_spaced(entries, max_frames)
        n = len(selected)

        # Izgara boyutu hesapla (max 3 sutun)
        cols = min(3, n)
        rows = (n + cols - 1) // cols

        # Etiket alani
        label_h = 28
        padding = 6

        # Tuval boyutu
        canvas_w = cols * cell_size + (cols + 1) * padding
        canvas_h = rows * (cell_size + label_h) + (rows + 1) * padding

        canvas = Image.new("RGB", (canvas_w, canvas_h), (25, 25, 30))
        draw = ImageDraw.Draw(canvas)
        font = self._get_font()

        for idx, entry in enumerate(selected):
            col = idx % cols
            row = idx // cols

            x = padding + col * (cell_size + padding)
            y = padding + row * (cell_size + label_h + padding)

            # Goruntuyu boyutlandir ve yapistir
            img_resized = entry.image.convert("RGB").resize(
                (cell_size, cell_size), Image.LANCZOS
            )
            canvas.paste(img_resized, (x, y + label_h))

            # Yil etiketi
            year_text = str(entry.year) if entry.year > 0 else entry.date[:10]
            draw.text(
                (x + 4, y + 4),
                year_text,
                fill=(255, 255, 255),
                font=font,
            )

            # Laplacian varyans bilgisi
            lap_text = f"L:{entry.laplacian_variance:.0f}"
            draw.text(
                (x + cell_size - 60, y + 4),
                lap_text,
                fill=(180, 180, 180),
                font=font,
            )

            # Sinirlayici cizgi (ince)
            draw.rectangle(
                [x - 1, y + label_h - 1,
                 x + cell_size, y + label_h + cell_size],
                outline=(60, 60, 70),
                width=1,
            )

        # Alt bilgi
        footer_y = canvas_h - 20
        draw.text(
            (padding, footer_y),
            f"Konum: ({timeline.lat:.4f}, {timeline.lng:.4f}) | "
            f"Zoom: {timeline.zoom} | {n} snapshot",
            fill=(120, 120, 130),
        )

        # Dosyaya kaydet
        if save:
            out_dir = self._ensure_output_dir()
            filename = self._generate_filename("comparison_grid", "png")
            filepath = out_dir / filename
            canvas.save(str(filepath), "PNG", optimize=True)
            logger.info("Karsilastirma izgarasi kaydedildi: %s", filepath)

        return canvas

    # ------------------------------------------------------------------ #
    # Yardimcilar
    # ------------------------------------------------------------------ #

    @staticmethod
    def _select_evenly_spaced(
        entries: List[TimelineEntry],
        max_count: int,
    ) -> List[TimelineEntry]:
        """Listeden esit aralikla eleman secer.

        Args:
            entries: Kaynak liste.
            max_count: Maksimum secilecek eleman sayisi.

        Returns:
            Esit aralikla secilmis alt liste.
        """
        n = len(entries)
        if n <= max_count:
            return list(entries)

        # Ilk ve son her zaman dahil
        indices = [0]
        step = (n - 1) / (max_count - 1)
        for i in range(1, max_count - 1):
            indices.append(int(round(i * step)))
        indices.append(n - 1)

        # Duplikatlari kaldir ve sirala
        indices = sorted(set(indices))

        return [entries[i] for i in indices]

    @staticmethod
    def _get_font() -> Any:
        """Etiketleme icin yazi tipi yukler."""
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]

        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, 14)
                except (OSError, IOError):
                    continue

        return ImageFont.load_default()
