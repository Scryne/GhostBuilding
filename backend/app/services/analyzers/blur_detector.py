"""
blur_detector.py — Kasıtlı bulanıklaştırma ve doğal düşük çözünürlük ayrımı modülü.

Harita tile görüntülerinde bulanıklık tespiti yapar ve kasıtlı sansür ile
doğal düşük çözünürlüğü ayırt eder. Laplacian varyans, FFT frekans
analizi, bölgesel bulanıklık haritası ve çapraz sağlayıcı karşılaştırması
ile sansür şüphesi skoru üretir.

Modül iki ana sınıftan oluşur:
  - BlurDetector: Bulanıklık tespiti ve sağlayıcı karşılaştırması
  - BlurVisualizer: Sıcaklık haritası görselleştirme
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
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

# Bulanıklık analizi çıktılarının kaydedileceği kök dizin
BLUR_OUTPUT_ROOT: str = os.path.join(
    getattr(settings, "STORAGE_ROOT", "data"), "blur_results"
)

# Laplacian varyans eşikleri
LAPLACIAN_SEVERE_BLUR: float = 50.0    # < 50: şiddetli bulanıklık
LAPLACIAN_MODERATE_BLUR: float = 100.0  # 50-100: orta bulanıklık
                                         # > 100: net görüntü

# FFT analizi parametreleri
FFT_HIGH_FREQ_RADIUS_RATIO: float = 0.3  # Yüksek frekans eşiği (yarıçap oranı)
FFT_LOW_PASS_THRESHOLD: float = 0.15     # Anormal düşük geçiş filtresi eşiği

# Sansür skoru eşikleri
CENSORSHIP_LIKELY: float = 70.0     # > 70: "Muhtemelen sansürlü"
CENSORSHIP_HIGH: float = 90.0       # > 90: "Yüksek ihtimalle sansürlü"

# Sağlayıcı karşılaştırma eşikleri
PROVIDER_BLUR_DEVIATION_FACTOR: float = 2.0  # Ortalamadan 2x sapma = şüpheli
PROVIDER_MIN_SCORE_DIFF: float = 30.0        # Minimum anlamlı fark

# Varsayılan grid boyutu
DEFAULT_GRID_SIZE: int = 8


# ---------------------------------------------------------------------------
# Veri sınıfları
# ---------------------------------------------------------------------------


@dataclass
class FFTResult:
    """FFT frekans analizi sonucu.

    Attributes:
        high_freq_energy: Yüksek frekans bölgesindeki toplam enerji.
        low_freq_energy: Düşük frekans bölgesindeki toplam enerji.
        power_ratio: Yüksek / düşük frekans enerji oranı.
        has_low_pass_anomaly: Anormal düşük geçiş filtresi tespit edildi mi.
        spectrum_image: Frekans spektrumu görselleştirmesi (log ölçekli).
        total_energy: Toplam spektral enerji.
    """

    high_freq_energy: float
    low_freq_energy: float
    power_ratio: float
    has_low_pass_anomaly: bool
    spectrum_image: np.ndarray
    total_energy: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür (spectrum_image hariç)."""
        return {
            "high_freq_energy": round(self.high_freq_energy, 4),
            "low_freq_energy": round(self.low_freq_energy, 4),
            "power_ratio": round(self.power_ratio, 6),
            "has_low_pass_anomaly": self.has_low_pass_anomaly,
            "total_energy": round(self.total_energy, 4),
        }


@dataclass
class BlurRegion:
    """Anormal bulanık bölgenin koordinat bilgisi.

    Attributes:
        row: Grid satır indeksi (0-indexed).
        col: Grid sütun indeksi (0-indexed).
        x: Sol üst köşe X koordinatı (piksel).
        y: Sol üst köşe Y koordinatı (piksel).
        width: Bölge genişliği (piksel).
        height: Bölge yüksekliği (piksel).
        blur_score: Bölgenin Laplacian varyans değeri.
        is_anomaly: Çevre bölgelere göre anormal mi.
    """

    row: int
    col: int
    x: int
    y: int
    width: int
    height: int
    blur_score: float
    is_anomaly: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "row": self.row,
            "col": self.col,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "blur_score": round(self.blur_score, 2),
            "is_anomaly": self.is_anomaly,
        }


@dataclass
class BlurMap:
    """Bölgesel bulanıklık haritası sonucu.

    Attributes:
        blur_map: 2D numpy array — her hücre bir Laplacian varyans değeri.
        grid_size: Kullanılan grid boyutu (ör. 8 = 8x8).
        mean_score: Tüm bölgelerin ortalama bulanıklık skoru.
        min_score: En düşük (en bulanık) skor.
        max_score: En yüksek (en keskin) skor.
        std_score: Standart sapma (yüksek = tutarsız bulanıklık).
        anomaly_regions: Anormal bulanık bölgelerin listesi.
        all_regions: Tüm bölgelerin listesi.
    """

    blur_map: np.ndarray
    grid_size: int
    mean_score: float
    min_score: float
    max_score: float
    std_score: float
    anomaly_regions: List[BlurRegion]
    all_regions: List[BlurRegion] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür (blur_map numpy dizisi hariç)."""
        return {
            "grid_size": self.grid_size,
            "mean_score": round(self.mean_score, 2),
            "min_score": round(self.min_score, 2),
            "max_score": round(self.max_score, 2),
            "std_score": round(self.std_score, 2),
            "num_anomaly_regions": len(self.anomaly_regions),
            "anomaly_regions": [r.to_dict() for r in self.anomaly_regions],
        }


@dataclass
class ProviderBlurInfo:
    """Tek bir sağlayıcının bulanıklık bilgisi.

    Attributes:
        provider: Sağlayıcı adı.
        laplacian_var: Laplacian varyans değeri.
        fft_power_ratio: FFT yüksek/düşük frekans oranı.
        blur_level: İnsan okunabilir bulanıklık seviyesi.
        regional_std: Bölgesel bulanıklık standart sapması.
        anomaly_region_count: Anormal bölge sayısı.
    """

    provider: str
    laplacian_var: float
    fft_power_ratio: float
    blur_level: str
    regional_std: float = 0.0
    anomaly_region_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "provider": self.provider,
            "laplacian_var": round(self.laplacian_var, 2),
            "fft_power_ratio": round(self.fft_power_ratio, 6),
            "blur_level": self.blur_level,
            "regional_std": round(self.regional_std, 2),
            "anomaly_region_count": self.anomaly_region_count,
        }


@dataclass
class BlurComparisonResult:
    """Çapraz sağlayıcı bulanıklık karşılaştırma sonucu.

    Attributes:
        provider_results: Her sağlayıcının bulanıklık bilgileri.
        censorship_score: Sansür şüphesi skoru (0–100).
        censorship_verdict: İnsan okunabilir karar.
        most_blurred_provider: En bulanık sağlayıcı adı.
        sharpest_provider: En keskin sağlayıcı adı.
        blur_variance: Sağlayıcılar arası bulanıklık varyansı.
        reasons: Sansür skoru gerekçeleri.
    """

    provider_results: List[ProviderBlurInfo]
    censorship_score: float
    censorship_verdict: str
    most_blurred_provider: Optional[str]
    sharpest_provider: Optional[str]
    blur_variance: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "censorship_score": round(self.censorship_score, 2),
            "censorship_verdict": self.censorship_verdict,
            "most_blurred_provider": self.most_blurred_provider,
            "sharpest_provider": self.sharpest_provider,
            "blur_variance": round(self.blur_variance, 2),
            "reasons": self.reasons,
            "provider_results": [p.to_dict() for p in self.provider_results],
        }


# ---------------------------------------------------------------------------
# Yardımcı: PIL ↔ NumPy dönüşümleri
# ---------------------------------------------------------------------------


def pil_to_gray(img: Image.Image) -> np.ndarray:
    """PIL Image'ı gri tonlama numpy dizisine dönüştürür.

    Args:
        img: PIL Image objesi (herhangi bir renk modu).

    Returns:
        Gri tonlama numpy dizisi (uint8, shape: H×W).
    """
    return np.array(img.convert("L"), dtype=np.uint8)


def pil_to_rgb_array(img: Image.Image) -> np.ndarray:
    """PIL Image'ı RGB numpy dizisine dönüştürür.

    Args:
        img: PIL Image objesi.

    Returns:
        RGB numpy dizisi (uint8, shape: H×W×3).
    """
    return np.array(img.convert("RGB"), dtype=np.uint8)


# ---------------------------------------------------------------------------
# BlurDetector — Bulanıklık tespiti
# ---------------------------------------------------------------------------


class BlurDetector:
    """Harita tile görüntülerinde bulanıklık tespit ve analiz eder.

    Laplacian varyans, FFT frekans analizi ve bölgesel bulanıklık haritası
    ile görüntü keskinliğini ölçer. Birden fazla sağlayıcıyı karşılaştırarak
    kasıtlı sansür (bulanıklaştırma) şüphesi tespit eder.

    Kasıtlı bulanıklaştırma belirtileri:
      - Tek bir sağlayıcıda belirgin düşük Laplacian varyans
      - FFT spektrumunda anormal düşük geçiş filtresi izi
      - Bölgesel bulanıklık haritasında tutarsız dağılım
      - Diğer sağlayıcılardan sapan keskinlik profili

    Attributes:
        _grid_size: Bölgesel analiz grid boyutu.
        _anomaly_std_factor: Anomali tespiti için standart sapma çarpanı.

    Examples:
        >>> detector = BlurDetector()
        >>> lap_var = detector.compute_laplacian_variance(tile_image)
        >>> print(f"Laplacian varyans: {lap_var:.1f}")
        Laplacian varyans: 85.3
    """

    def __init__(
        self,
        *,
        grid_size: int = DEFAULT_GRID_SIZE,
        anomaly_std_factor: float = 1.5,
    ) -> None:
        """
        Args:
            grid_size: Bölgesel bulanıklık analizi için grid boyutu.
            anomaly_std_factor: Anomali tespitinde kullanılacak std çarpanı.
                Bir bölgenin skoru, ortalamadan (std × factor) kadar
                düşükse anomali olarak işaretlenir.
        """
        self._grid_size = grid_size
        self._anomaly_std_factor = anomaly_std_factor

    # ------------------------------------------------------------------ #
    # compute_laplacian_variance — Laplacian varyans
    # ------------------------------------------------------------------ #

    def compute_laplacian_variance(self, image: Image.Image) -> float:
        """Görüntünün Laplacian varyansını hesaplar.

        Laplacian operatörü kenar tespiti yapar ve varyansı görüntü
        keskinliğinin bir göstergesidir. Düşük değerler bulanıklığı,
        yüksek değerler keskin bir görüntüyü ifade eder.

        Eşik değerleri:
          - < 50: şiddetli bulanıklık (kasıtlı sansür olabilir)
          - 50–100: orta bulanıklık (düşük çözünürlük olabilir)
          - > 100: net görüntü

        Args:
            image: Analiz edilecek PIL Image.

        Returns:
            Laplacian varyans değeri (float ≥ 0). Yüksek = keskin.

        Examples:
            >>> detector = BlurDetector()
            >>> score = detector.compute_laplacian_variance(sharp_tile)
            >>> score > 100
            True
        """
        gray = pil_to_gray(image)

        # Laplacian operatörü uygula (64-bit float çıktı)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)

        # Varyans hesapla
        variance = float(laplacian.var())

        logger.debug(
            "Laplacian varyans: %.2f (boyut: %dx%d)",
            variance, gray.shape[1], gray.shape[0],
        )

        return variance

    @staticmethod
    def classify_blur_level(laplacian_var: float) -> str:
        """Laplacian varyans değerine göre bulanıklık seviyesi belirler.

        Args:
            laplacian_var: Laplacian varyans değeri.

        Returns:
            İnsan okunabilir bulanıklık seviyesi:
            "severe" | "moderate" | "sharp".
        """
        if laplacian_var < LAPLACIAN_SEVERE_BLUR:
            return "severe"
        elif laplacian_var < LAPLACIAN_MODERATE_BLUR:
            return "moderate"
        else:
            return "sharp"

    # ------------------------------------------------------------------ #
    # analyze_frequency_spectrum — FFT frekans analizi
    # ------------------------------------------------------------------ #

    def analyze_frequency_spectrum(self, image: Image.Image) -> FFTResult:
        """Görüntünün FFT frekans spektrumunu analiz eder.

        2D FFT ile frekans uzayına çevirerek yüksek frekans enerjisi,
        düşük frekans enerjisi ve anormal düşük geçiş filtresi tespiti
        yapar. Kasıtlı bulanıklaştırma genellikle yüksek frekans
        bileşenlerini bastırır.

        Args:
            image: Analiz edilecek PIL Image.

        Returns:
            FFTResult — frekans analizi sonuçları.

        Examples:
            >>> detector = BlurDetector()
            >>> fft = detector.analyze_frequency_spectrum(tile_image)
            >>> fft.power_ratio > 0
            True
        """
        gray = pil_to_gray(image)
        h, w = gray.shape

        # 2D FFT ve merkezleme
        f_transform = np.fft.fft2(gray.astype(np.float64))
        f_shift = np.fft.fftshift(f_transform)

        # Büyüklük spektrumu (log ölçekli)
        magnitude = np.abs(f_shift)
        # Sıfır bölme koruması
        magnitude_log = np.log1p(magnitude)

        # Toplam enerji
        total_energy = float(np.sum(magnitude ** 2))

        # Merkez koordinatları
        cy, cx = h // 2, w // 2

        # Frekans bölgelerini tanımla
        # Düşük frekans: merkeze yakın (yarıçap < %30)
        # Yüksek frekans: merkezden uzak (yarıçap ≥ %30)
        max_radius = min(cy, cx)
        high_freq_threshold = int(max_radius * FFT_HIGH_FREQ_RADIUS_RATIO)

        # Mesafe matrisi oluştur
        y_coords, x_coords = np.ogrid[:h, :w]
        distance = np.sqrt((y_coords - cy) ** 2 + (x_coords - cx) ** 2)

        # Enerji hesapla
        low_mask = distance < high_freq_threshold
        high_mask = distance >= high_freq_threshold

        low_freq_energy = float(np.sum(magnitude[low_mask] ** 2))
        high_freq_energy = float(np.sum(magnitude[high_mask] ** 2))

        # Yüksek/düşük frekans oranı
        power_ratio = (
            high_freq_energy / low_freq_energy
            if low_freq_energy > 0
            else 0.0
        )

        # Anormal düşük geçiş filtresi tespiti
        # Kasıtlı bulanıklaştırma → yüksek frekans enerjisi çok düşük
        has_low_pass_anomaly = self._detect_low_pass_anomaly(
            magnitude, distance, high_freq_threshold, max_radius
        )

        # Spektrum görselleştirmesi (normalize edilmiş log büyüklük)
        spectrum_vis = self._create_spectrum_visualization(magnitude_log)

        logger.info(
            "FFT analizi: high_e=%.2f, low_e=%.2f, ratio=%.6f, "
            "low_pass_anomaly=%s",
            high_freq_energy, low_freq_energy, power_ratio,
            has_low_pass_anomaly,
        )

        return FFTResult(
            high_freq_energy=high_freq_energy,
            low_freq_energy=low_freq_energy,
            power_ratio=power_ratio,
            has_low_pass_anomaly=has_low_pass_anomaly,
            spectrum_image=spectrum_vis,
            total_energy=total_energy,
        )

    @staticmethod
    def _detect_low_pass_anomaly(
        magnitude: np.ndarray,
        distance: np.ndarray,
        high_freq_start: int,
        max_radius: int,
    ) -> bool:
        """Anormal düşük geçiş filtresi izi tespit eder.

        Frekans spektrumunda belirli bir yarıçap ötesinde enerji
        ani düşüş gösteriyorsa kasıtlı düşük geçiş filtresi
        uygulanmış olabilir.

        Args:
            magnitude: FFT büyüklük dizisi.
            distance: Merkezden mesafe dizisi.
            high_freq_start: Yüksek frekans başlangıç yarıçapı.
            max_radius: Maksimum yarıçap.

        Returns:
            True ise anormal düşük geçiş filtresi tespit edildi.
        """
        if max_radius <= 0:
            return False

        # Radyal enerji profili oluştur
        num_bins = min(50, max_radius)
        radial_bins = np.linspace(0, max_radius, num_bins + 1)
        radial_energy: List[float] = []

        for i in range(num_bins):
            ring_mask = (distance >= radial_bins[i]) & (distance < radial_bins[i + 1])
            ring_pixels = magnitude[ring_mask]
            if ring_pixels.size > 0:
                radial_energy.append(float(np.mean(ring_pixels ** 2)))
            else:
                radial_energy.append(0.0)

        if not radial_energy or max(radial_energy) == 0:
            return False

        # Normalize et
        max_energy = max(radial_energy)
        normalized = [e / max_energy for e in radial_energy]

        # Keskin düşüş tespiti: ardışık iki bin arasında büyük fark
        # ve düşüş sonrası enerji çok düşük kalıyorsa → düşük geçiş filtresi
        threshold_bin = int(num_bins * FFT_HIGH_FREQ_RADIUS_RATIO)
        if threshold_bin >= len(normalized) - 1:
            return False

        # Eşik sonrası ortalama enerji
        post_threshold_energy = np.mean(normalized[threshold_bin:])

        # Eşik öncesi ortalama enerji
        pre_threshold_energy = np.mean(normalized[:threshold_bin]) if threshold_bin > 0 else 1.0

        # Ani düşüş kontrolü
        if pre_threshold_energy > 0:
            drop_ratio = post_threshold_energy / pre_threshold_energy
            return drop_ratio < FFT_LOW_PASS_THRESHOLD

        return False

    @staticmethod
    def _create_spectrum_visualization(magnitude_log: np.ndarray) -> np.ndarray:
        """FFT büyüklük spektrumunu görselleştirilebilir forma dönüştürür.

        Args:
            magnitude_log: Log ölçekli büyüklük dizisi.

        Returns:
            Normalize edilmiş uint8 görselleştirme dizisi (H×W).
        """
        # 0-255 aralığına normalize et
        if magnitude_log.max() > magnitude_log.min():
            normalized = (
                (magnitude_log - magnitude_log.min())
                / (magnitude_log.max() - magnitude_log.min())
                * 255.0
            )
        else:
            normalized = np.zeros_like(magnitude_log)

        return normalized.astype(np.uint8)

    # ------------------------------------------------------------------ #
    # detect_regional_blur — Bölgesel bulanıklık haritası
    # ------------------------------------------------------------------ #

    def detect_regional_blur(
        self,
        image: Image.Image,
        grid_size: Optional[int] = None,
    ) -> BlurMap:
        """Görüntüyü grid'e bölerek bölgesel bulanıklık haritası oluşturur.

        Her bölge için ayrı Laplacian varyans hesaplar ve çevresine
        göre anormal bulanık bölgeleri tespit eder. Bu yöntem kasıtlı
        olarak belirli bölgelerin bulanıklaştırıldığı durumları
        yakalamak için tasarlanmıştır (ör. askeri tesisler).

        Args:
            image: Analiz edilecek PIL Image.
            grid_size: Grid boyutu (ör. 8 = 8×8). None ise varsayılan.

        Returns:
            BlurMap — bölgesel bulanıklık analizi sonuçları.

        Examples:
            >>> detector = BlurDetector()
            >>> bmap = detector.detect_regional_blur(tile_image, grid_size=8)
            >>> bmap.blur_map.shape
            (8, 8)
        """
        gs = grid_size or self._grid_size
        gray = pil_to_gray(image)
        h, w = gray.shape

        # Her hücrenin boyutu
        cell_h = h // gs
        cell_w = w // gs

        # Sıfır boyutlu hücre kontrolü
        if cell_h < 4 or cell_w < 4:
            logger.warning(
                "Görüntü grid için çok küçük: %dx%d, grid=%d, "
                "hücre=%dx%d",
                w, h, gs, cell_w, cell_h,
            )
            # Küçük görüntü için 1×1 grid kullan
            gs = 1
            cell_h = h
            cell_w = w

        blur_scores = np.zeros((gs, gs), dtype=np.float64)
        all_regions: List[BlurRegion] = []

        for row in range(gs):
            for col in range(gs):
                y_start = row * cell_h
                x_start = col * cell_w

                # Son satır/sütunda kalan pikselleri de dahil et
                y_end = (row + 1) * cell_h if row < gs - 1 else h
                x_end = (col + 1) * cell_w if col < gs - 1 else w

                cell = gray[y_start:y_end, x_start:x_end]

                # Laplacian varyans hesapla
                if cell.size > 0:
                    laplacian = cv2.Laplacian(cell, cv2.CV_64F)
                    variance = float(laplacian.var())
                else:
                    variance = 0.0

                blur_scores[row, col] = variance

                all_regions.append(
                    BlurRegion(
                        row=row,
                        col=col,
                        x=x_start,
                        y=y_start,
                        width=x_end - x_start,
                        height=y_end - y_start,
                        blur_score=variance,
                    )
                )

        # İstatistikler
        mean_score = float(np.mean(blur_scores))
        min_score = float(np.min(blur_scores))
        max_score = float(np.max(blur_scores))
        std_score = float(np.std(blur_scores))

        # Anomali tespiti: ortalamadan belirgin şekilde düşük bölgeler
        anomaly_threshold = mean_score - (std_score * self._anomaly_std_factor)
        anomaly_regions: List[BlurRegion] = []

        for region in all_regions:
            # Eşiğin altında VE genel olarak bulanık değilse anormal kabul et
            # (tüm görüntü bulanıksa anomali değil, doğal düşük çözünürlük)
            if (
                region.blur_score < anomaly_threshold
                and mean_score > LAPLACIAN_SEVERE_BLUR
                and std_score > 5.0
            ):
                region.is_anomaly = True
                anomaly_regions.append(region)

        logger.info(
            "Bölgesel bulanıklık: grid=%dx%d, ort=%.1f, min=%.1f, "
            "max=%.1f, std=%.1f, anomali=%d bölge",
            gs, gs, mean_score, min_score, max_score,
            std_score, len(anomaly_regions),
        )

        return BlurMap(
            blur_map=blur_scores,
            grid_size=gs,
            mean_score=mean_score,
            min_score=min_score,
            max_score=max_score,
            std_score=std_score,
            anomaly_regions=anomaly_regions,
            all_regions=all_regions,
        )

    # ------------------------------------------------------------------ #
    # compare_blur_across_providers — Çapraz sağlayıcı karşılaştırması
    # ------------------------------------------------------------------ #

    def compare_blur_across_providers(
        self,
        images: Dict[str, Image.Image],
    ) -> BlurComparisonResult:
        """Farklı sağlayıcıların aynı lokasyon görüntülerini karşılaştırır.

        Her sağlayıcı için bulanıklık profili çıkarır ve diğerleriyle
        karşılaştırarak kasıtlı sansür şüphesi skoru hesaplar.
        Bir sağlayıcı diğerlerinden belirgin şekilde daha bulanıksa
        sansür olasılığı yüksektir.

        Sansür skoru kuralları:
          - Bir sağlayıcı diğerlerinden 2x+ daha bulanık: +30 puan
          - FFT'de düşük geçiş anomalisi: +25 puan
          - Bölgesel anomali tespit edildi: +20 puan
          - Şiddetli bulanıklık seviyesi: +15 puan
          - Diğer sağlayıcılar keskin ama biri bulanık: +10 puan

        Karar eşikleri:
          - > 90: "Yüksek ihtimalle sansürlü"
          - > 70: "Muhtemelen sansürlü"
          - > 40: "Şüpheli"
          - ≤ 40: "Normal"

        Args:
            images: Sağlayıcı adı → PIL Image sözlüğü.
                    Örn: {"osm": img_osm, "google": img_google}

        Returns:
            BlurComparisonResult — sansür analizi sonuçları.

        Raises:
            ValueError: 2'den az sağlayıcı görüntüsü verilirse.

        Examples:
            >>> detector = BlurDetector()
            >>> result = detector.compare_blur_across_providers({
            ...     "osm": tile_osm,
            ...     "google": tile_google,
            ...     "bing": tile_bing,
            ... })
            >>> 0 <= result.censorship_score <= 100
            True
        """
        provider_names = list(images.keys())

        if len(provider_names) < 2:
            raise ValueError(
                f"En az 2 sağlayıcı görüntüsü gerekli, "
                f"{len(provider_names)} verildi."
            )

        logger.info(
            "Bulanıklık karşılaştırması başlatılıyor: %s",
            ", ".join(provider_names),
        )

        # Her sağlayıcı için bulanıklık profili çıkar
        provider_infos: List[ProviderBlurInfo] = []
        laplacian_scores: Dict[str, float] = {}
        fft_results: Dict[str, FFTResult] = {}
        blur_maps: Dict[str, BlurMap] = {}

        for name in provider_names:
            img = images[name]

            # Laplacian varyans
            lap_var = self.compute_laplacian_variance(img)
            laplacian_scores[name] = lap_var

            # FFT analizi
            fft = self.analyze_frequency_spectrum(img)
            fft_results[name] = fft

            # Bölgesel analiz
            bmap = self.detect_regional_blur(img)
            blur_maps[name] = bmap

            blur_level = self.classify_blur_level(lap_var)

            provider_infos.append(
                ProviderBlurInfo(
                    provider=name,
                    laplacian_var=lap_var,
                    fft_power_ratio=fft.power_ratio,
                    blur_level=blur_level,
                    regional_std=bmap.std_score,
                    anomaly_region_count=len(bmap.anomaly_regions),
                )
            )

        # Sansür skoru hesapla
        censorship_score, reasons = self._calculate_censorship_score(
            provider_infos, fft_results, blur_maps, laplacian_scores
        )

        # En bulanık ve en keskin sağlayıcıları bul
        sorted_by_blur = sorted(
            provider_infos, key=lambda p: p.laplacian_var
        )
        most_blurred = sorted_by_blur[0].provider if sorted_by_blur else None
        sharpest = sorted_by_blur[-1].provider if sorted_by_blur else None

        # Sağlayıcılar arası varyans
        all_scores = [p.laplacian_var for p in provider_infos]
        blur_variance = float(np.var(all_scores)) if all_scores else 0.0

        # Karar
        censorship_verdict = self._determine_verdict(censorship_score)

        result = BlurComparisonResult(
            provider_results=provider_infos,
            censorship_score=censorship_score,
            censorship_verdict=censorship_verdict,
            most_blurred_provider=most_blurred,
            sharpest_provider=sharpest,
            blur_variance=blur_variance,
            reasons=reasons,
        )

        logger.info(
            "Bulanıklık karşılaştırması tamamlandı: sansür=%.1f (%s), "
            "en_bulanık=%s, en_keskin=%s",
            censorship_score, censorship_verdict,
            most_blurred, sharpest,
        )

        return result

    @staticmethod
    def _calculate_censorship_score(
        provider_infos: List[ProviderBlurInfo],
        fft_results: Dict[str, FFTResult],
        blur_maps: Dict[str, BlurMap],
        laplacian_scores: Dict[str, float],
    ) -> Tuple[float, List[str]]:
        """Sansür şüphesi skoru ve gerekçeleri hesaplar.

        Args:
            provider_infos: Sağlayıcı bulanıklık bilgileri.
            fft_results: Her sağlayıcının FFT sonuçları.
            blur_maps: Her sağlayıcının bölgesel bulanıklık haritaları.
            laplacian_scores: Her sağlayıcının Laplacian varyansları.

        Returns:
            (censorship_score, reasons) çifti.
        """
        score: float = 0.0
        reasons: List[str] = []

        if len(provider_infos) < 2:
            return 0.0, ["Yetersiz sağlayıcı sayısı."]

        # Laplacian skorlarının ortalaması ve std'si
        all_laps = list(laplacian_scores.values())
        mean_lap = float(np.mean(all_laps))
        std_lap = float(np.std(all_laps))

        # --- Kural 1: Bir sağlayıcı diğerlerinden çok daha bulanık ---
        for info in provider_infos:
            if std_lap > 0 and mean_lap > 0:
                # Z-skoru ile sapma kontrolü
                z_score = (mean_lap - info.laplacian_var) / std_lap
                if z_score > PROVIDER_BLUR_DEVIATION_FACTOR:
                    # Bu sağlayıcının skoru ortalamanın çok altında
                    other_scores = [
                        v for k, v in laplacian_scores.items()
                        if k != info.provider
                    ]
                    other_mean = float(np.mean(other_scores))

                    if other_mean > 0:
                        ratio = info.laplacian_var / other_mean
                        if ratio < 0.5:
                            score += 30.0
                            reasons.append(
                                f"{info.provider}: Laplacian varyansı "
                                f"({info.laplacian_var:.1f}) diğerlerinin "
                                f"ortalamasından ({other_mean:.1f}) çok "
                                f"düşük (oran: {ratio:.2f})"
                            )

        # --- Kural 2: FFT'de düşük geçiş anomalisi ---
        for name, fft in fft_results.items():
            if fft.has_low_pass_anomaly:
                # Diğer sağlayıcılarda anomali yoksa şüpheli
                others_have_anomaly = any(
                    fft_results[n].has_low_pass_anomaly
                    for n in fft_results if n != name
                )
                if not others_have_anomaly:
                    score += 25.0
                    reasons.append(
                        f"{name}: FFT spektrumunda düşük geçiş filtresi "
                        f"anomalisi tespit edildi (diğerlerinde yok)"
                    )

        # --- Kural 3: Bölgesel anomali tespiti ---
        for name, bmap in blur_maps.items():
            if bmap.anomaly_regions:
                # Diğer sağlayıcılarda aynı bölgelerde anomali yoksa
                others_have_regional = any(
                    len(blur_maps[n].anomaly_regions) > 0
                    for n in blur_maps if n != name
                )
                if not others_have_regional:
                    score += 20.0
                    reasons.append(
                        f"{name}: {len(bmap.anomaly_regions)} bölgesel "
                        f"bulanıklık anomalisi (diğerlerinde yok)"
                    )

        # --- Kural 4: Şiddetli bulanıklık seviyesi ---
        for info in provider_infos:
            if info.blur_level == "severe":
                others_sharp = sum(
                    1 for p in provider_infos
                    if p.provider != info.provider
                    and p.blur_level == "sharp"
                )
                if others_sharp > 0:
                    score += 15.0
                    reasons.append(
                        f"{info.provider}: Şiddetli bulanıklık "
                        f"({info.laplacian_var:.1f}) ama {others_sharp} "
                        f"sağlayıcı keskin"
                    )

        # --- Kural 5: Diğerleri keskin, biri bulanık ---
        sharp_providers = [
            p for p in provider_infos if p.blur_level == "sharp"
        ]
        blurred_providers = [
            p for p in provider_infos
            if p.blur_level in ("severe", "moderate")
        ]
        if (
            len(sharp_providers) >= 2
            and len(blurred_providers) == 1
        ):
            blurred = blurred_providers[0]
            score += 10.0
            reasons.append(
                f"{blurred.provider}: Tek bulanık sağlayıcı "
                f"({len(sharp_providers)} keskin sağlayıcı var)"
            )

        # Skoru 0-100 arasına sınırla
        score = min(100.0, max(0.0, score))

        if not reasons:
            reasons.append("Kayda değer sansür belirtisi tespit edilmedi.")

        return score, reasons

    @staticmethod
    def _determine_verdict(censorship_score: float) -> str:
        """Sansür skoru için karar metni üretir.

        Args:
            censorship_score: Hesaplanan sansür skoru (0–100).

        Returns:
            İnsan okunabilir karar metni.
        """
        if censorship_score > CENSORSHIP_HIGH:
            return "Yüksek ihtimalle sansürlü"
        elif censorship_score > CENSORSHIP_LIKELY:
            return "Muhtemelen sansürlü"
        elif censorship_score > 40:
            return "Şüpheli"
        else:
            return "Normal"

    # ------------------------------------------------------------------ #
    # Tam bulanıklık analizi — Tek sağlayıcı
    # ------------------------------------------------------------------ #

    def full_analysis(self, image: Image.Image) -> Dict[str, Any]:
        """Tek bir görüntü için kapsamlı bulanıklık analizi yapar.

        Tüm bulanıklık metriklerini tek seferde hesaplar:
        Laplacian varyans, FFT frekans analizi ve bölgesel harita.

        Args:
            image: Analiz edilecek PIL Image.

        Returns:
            Tüm sonuçları içeren sözlük:
            {
                "laplacian_variance": float,
                "blur_level": str,
                "fft": FFTResult.to_dict(),
                "regional": BlurMap.to_dict(),
            }

        Examples:
            >>> detector = BlurDetector()
            >>> analysis = detector.full_analysis(tile_image)
            >>> analysis["blur_level"] in ("severe", "moderate", "sharp")
            True
        """
        lap_var = self.compute_laplacian_variance(image)
        blur_level = self.classify_blur_level(lap_var)
        fft_result = self.analyze_frequency_spectrum(image)
        blur_map = self.detect_regional_blur(image)

        logger.info(
            "Tam bulanıklık analizi: lap=%.1f (%s), fft_ratio=%.6f, "
            "bölgesel_anomali=%d",
            lap_var, blur_level, fft_result.power_ratio,
            len(blur_map.anomaly_regions),
        )

        return {
            "laplacian_variance": round(lap_var, 2),
            "blur_level": blur_level,
            "fft": fft_result.to_dict(),
            "regional": blur_map.to_dict(),
        }


# ---------------------------------------------------------------------------
# BlurVisualizer — Sıcaklık haritası görselleştirme
# ---------------------------------------------------------------------------


class BlurVisualizer:
    """Bulanıklık analizi sonuçlarını görselleştirir.

    Sıcaklık haritası overlay oluşturarak bulanıklık dağılımını
    görselleştirir. Kırmızı = bulanık, mavi = keskin.

    Attributes:
        _output_dir: Çıktı dosyalarının kaydedileceği dizin.
        _alpha: Overlay saydamlık oranı (0–1).

    Examples:
        >>> viz = BlurVisualizer()
        >>> heatmap = viz.create_blur_heatmap(tile_image, blur_map)
        >>> heatmap.mode
        'RGB'
    """

    def __init__(
        self,
        *,
        output_dir: Optional[str] = None,
        alpha: float = 0.5,
    ) -> None:
        """
        Args:
            output_dir: Çıktı dizini. None ise varsayılan kullanılır.
            alpha: Sıcaklık haritası overlay saydamlığı (0–1).
        """
        self._output_dir = Path(output_dir or BLUR_OUTPUT_ROOT)
        self._alpha = alpha

    def _ensure_output_dir(self) -> Path:
        """Çıktı dizininin var olduğunu garanti eder.

        Returns:
            Çıktı dizini Path objesi.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._output_dir

    def _generate_filename(self, prefix: str, ext: str) -> str:
        """Benzersiz dosya adı üretir.

        Args:
            prefix: Dosya adı ön eki.
            ext: Dosya uzantısı (noktasız, örn. "png").

        Returns:
            Benzersiz dosya adı.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"{prefix}_{timestamp}_{unique_id}.{ext}"

    def create_blur_heatmap(
        self,
        image: Image.Image,
        blur_map: BlurMap,
        *,
        save: bool = True,
        show_grid: bool = True,
        show_anomalies: bool = True,
    ) -> Image.Image:
        """Bulanıklık haritasını sıcaklık haritası olarak görselleştirir.

        Orijinal görüntü üzerine yarı saydam sıcaklık haritası bindirerek
        bulanıklık dağılımını gösterir. Renk kodlaması:
          - Kırmızı: bulanık bölge (düşük Laplacian varyans)
          - Mavi: keskin bölge (yüksek Laplacian varyans)
          - Sarı çerçeve: anomali bölgeleri

        Args:
            image: Orijinal görüntü (alt katman).
            blur_map: BlurMap analiz sonucu.
            save: Dosyaya kaydet.
            show_grid: Grid çizgilerini göster.
            show_anomalies: Anomali bölgelerini vurgula.

        Returns:
            Sıcaklık haritası overlay'li PIL Image.

        Examples:
            >>> viz = BlurVisualizer()
            >>> detector = BlurDetector()
            >>> bmap = detector.detect_regional_blur(tile_image)
            >>> heatmap = viz.create_blur_heatmap(tile_image, bmap)
            >>> heatmap.size == tile_image.size
            True
        """
        img_rgb = image.convert("RGB")
        w, h = img_rgb.size

        # Sıcaklık haritası oluştur
        heatmap_array = self._blur_map_to_heatmap(
            blur_map.blur_map,
            target_width=w,
            target_height=h,
        )

        heatmap_img = Image.fromarray(heatmap_array)

        # Orijinal ile birleştir (alfa blending)
        blended = Image.blend(img_rgb, heatmap_img, self._alpha)

        # Grid ve anomali çizimi
        draw = ImageDraw.Draw(blended)

        if show_grid:
            self._draw_grid(draw, w, h, blur_map.grid_size)

        if show_anomalies and blur_map.anomaly_regions:
            self._draw_anomaly_boxes(draw, blur_map.anomaly_regions)

        # Renk skalası lejandı
        self._draw_legend(draw, w, h, blur_map)

        # Dosyaya kaydet
        if save:
            out_dir = self._ensure_output_dir()
            filename = self._generate_filename("blur_heatmap", "png")
            filepath = out_dir / filename
            blended.save(str(filepath), "PNG", optimize=True)

            logger.info("Bulanıklık haritası kaydedildi: %s", filepath)

        return blended

    @staticmethod
    def _blur_map_to_heatmap(
        blur_map: np.ndarray,
        target_width: int,
        target_height: int,
    ) -> np.ndarray:
        """Blur skor matrisini renkli sıcaklık haritasına dönüştürür.

        Düşük skorlar (bulanık) → kırmızı, yüksek skorlar (keskin) → mavi.
        OpenCV JET colormap kullanılır.

        Args:
            blur_map: 2D bulanıklık skor matrisi (grid_size × grid_size).
            target_width: Hedef görüntü genişliği (piksel).
            target_height: Hedef görüntü yüksekliği (piksel).

        Returns:
            RGB sıcaklık haritası numpy dizisi (target_height × target_width × 3).
        """
        scores = blur_map.astype(np.float64)

        # 0-255 aralığına normalize et (ters: düşük skor = yüksek ısı)
        if scores.max() > scores.min():
            normalized = (
                (scores - scores.min())
                / (scores.max() - scores.min())
                * 255.0
            )
        else:
            normalized = np.full_like(scores, 128.0)

        # Ters çevir: düşük skor (bulanık) = 255 (kırmızı), yüksek = 0 (mavi)
        normalized = 255.0 - normalized

        # uint8'e çevir
        norm_uint8 = normalized.astype(np.uint8)

        # Hedef boyuta yeniden boyutlandır (nearest neighbor — grid görünümü korur)
        resized = cv2.resize(
            norm_uint8,
            (target_width, target_height),
            interpolation=cv2.INTER_LINEAR,
        )

        # JET colormap uygula (BGR)
        colored_bgr = cv2.applyColorMap(resized, cv2.COLORMAP_JET)

        # BGR → RGB
        colored_rgb = cv2.cvtColor(colored_bgr, cv2.COLOR_BGR2RGB)

        return colored_rgb

    @staticmethod
    def _draw_grid(
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        grid_size: int,
    ) -> None:
        """Sıcaklık haritası üzerine grid çizgileri çizer.

        Args:
            draw: PIL ImageDraw objesi.
            width: Görüntü genişliği.
            height: Görüntü yüksekliği.
            grid_size: Grid boyutu.
        """
        cell_w = width // grid_size
        cell_h = height // grid_size
        grid_color = (255, 255, 255, 80)  # yarı saydam beyaz

        # Dikey çizgiler
        for col in range(1, grid_size):
            x = col * cell_w
            draw.line([(x, 0), (x, height)], fill=grid_color, width=1)

        # Yatay çizgiler
        for row in range(1, grid_size):
            y = row * cell_h
            draw.line([(0, y), (width, y)], fill=grid_color, width=1)

    @staticmethod
    def _draw_anomaly_boxes(
        draw: ImageDraw.ImageDraw,
        anomaly_regions: List[BlurRegion],
    ) -> None:
        """Anomali bölgelerini sarı çerçevelerle işaretler.

        Args:
            draw: PIL ImageDraw objesi.
            anomaly_regions: Anomali olarak tesapit edilen bölgeler.
        """
        for region in anomaly_regions:
            x1 = region.x
            y1 = region.y
            x2 = region.x + region.width
            y2 = region.y + region.height

            # Sarı çerçeve (2 piksel kalınlığında)
            draw.rectangle(
                [x1, y1, x2, y2],
                outline=(255, 255, 0),
                width=2,
            )

            # Ünlem işareti
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            draw.text(
                (cx - 3, cy - 6),
                "!",
                fill=(255, 255, 0),
            )

    @staticmethod
    def _draw_legend(
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        blur_map: BlurMap,
    ) -> None:
        """Sıcaklık haritasına renk skalası lejandı ekler.

        Args:
            draw: PIL ImageDraw objesi.
            width: Görüntü genişliği.
            height: Görüntü yüksekliği.
            blur_map: BlurMap analiz sonucu (istatistikler için).
        """
        # Lejand arka planı (sağ alt köşe)
        legend_w = 120
        legend_h = 60
        lx = width - legend_w - 5
        ly = height - legend_h - 5

        # Yarı saydam arka plan
        draw.rectangle(
            [lx, ly, lx + legend_w, ly + legend_h],
            fill=(0, 0, 0),
        )

        # Metin
        draw.text(
            (lx + 5, ly + 3),
            "Kırmızı = Bulanık",
            fill=(255, 100, 100),
        )
        draw.text(
            (lx + 5, ly + 18),
            "Mavi = Keskin",
            fill=(100, 150, 255),
        )
        draw.text(
            (lx + 5, ly + 33),
            f"Ort: {blur_map.mean_score:.0f}",
            fill=(200, 200, 200),
        )
        if blur_map.anomaly_regions:
            draw.text(
                (lx + 5, ly + 45),
                f"Anomali: {len(blur_map.anomaly_regions)}",
                fill=(255, 255, 0),
            )

    def create_provider_comparison_visual(
        self,
        images: Dict[str, Image.Image],
        result: BlurComparisonResult,
        *,
        save: bool = True,
    ) -> Image.Image:
        """Sağlayıcı karşılaştırmasını görsel olarak özetler.

        Her sağlayıcının görüntüsünü yan yana bulanıklık skoru
        etiketiyle gösterir. Sansürlü olduğu şüphelenilen
        sağlayıcı kırmızı çerçevelenir.

        Args:
            images: Sağlayıcı adı → PIL Image sözlüğü.
            result: BlurComparisonResult analiz sonucu.
            save: Dosyaya kaydet.

        Returns:
            Karşılaştırma görseli PIL Image.
        """
        provider_names = list(images.keys())
        n = len(provider_names)

        if n == 0:
            return Image.new("RGB", (200, 100), (30, 30, 30))

        # Her görüntüyü aynı boyuta getir
        target_w = 256
        target_h = 256

        # Etiket alanı
        label_h = 50
        padding = 8

        # Tuval boyutu
        canvas_w = n * target_w + (n + 1) * padding
        canvas_h = label_h + target_h + padding * 2 + 30  # alt bilgi alanı

        canvas = Image.new("RGB", (canvas_w, canvas_h), (30, 30, 30))
        draw = ImageDraw.Draw(canvas)

        # Sağlayıcı bilgilerini indeksle
        info_map: Dict[str, ProviderBlurInfo] = {
            p.provider: p for p in result.provider_results
        }

        for i, name in enumerate(provider_names):
            x_offset = padding + i * (target_w + padding)

            # Görüntüyü yapıştır
            img_resized = images[name].convert("RGB").resize(
                (target_w, target_h), Image.LANCZOS
            )
            canvas.paste(img_resized, (x_offset, label_h))

            # Sağlayıcı etiketi
            info = info_map.get(name)
            if info:
                blur_text = f"{name.upper()}"
                score_text = f"Lap: {info.laplacian_var:.0f} ({info.blur_level})"
            else:
                blur_text = name.upper()
                score_text = ""

            draw.text((x_offset + 5, 5), blur_text, fill=(255, 255, 255))
            draw.text((x_offset + 5, 22), score_text, fill=(180, 180, 180))

            # Sansürlü şüphelisi → kırmızı çerçeve
            if (
                result.most_blurred_provider == name
                and result.censorship_score > CENSORSHIP_LIKELY
            ):
                draw.rectangle(
                    [x_offset - 1, label_h - 1,
                     x_offset + target_w, label_h + target_h],
                    outline=(255, 50, 50),
                    width=3,
                )
                draw.text(
                    (x_offset + 5, label_h + target_h - 20),
                    "⚠ SANSÜR ŞÜPHESİ",
                    fill=(255, 50, 50),
                )

        # Alt bilgi
        footer_y = label_h + target_h + padding
        verdict_color = (
            (255, 50, 50) if result.censorship_score > CENSORSHIP_LIKELY
            else (255, 200, 50) if result.censorship_score > 40
            else (100, 255, 100)
        )
        draw.text(
            (padding, footer_y),
            f"Sansür Skoru: {result.censorship_score:.0f}/100 — "
            f"{result.censorship_verdict}",
            fill=verdict_color,
        )

        # Dosyaya kaydet
        if save:
            out_dir = self._ensure_output_dir()
            filename = self._generate_filename("blur_comparison", "png")
            filepath = out_dir / filename
            canvas.save(str(filepath), "PNG", optimize=True)

            logger.info(
                "Sağlayıcı karşılaştırma görseli kaydedildi: %s", filepath
            )

        return canvas
