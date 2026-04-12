"""
pixel_diff.py — Piksel düzeyinde harita tile karşılaştırma analiz modülü.

Farklı harita sağlayıcılarından (OSM, Google, Bing, Yandex) alınan tile
görüntülerini piksel bazında karşılaştırır. ORB feature matching ile
hizalama, SSIM yapısal benzerlik, histogram farkı ve bounding-box
tabanlı değişiklik bölgesi tespiti sağlar.

Modül üç ana sınıftan oluşur:
  - ImageAligner: Görüntü hizalama (ORB + fallback kırpma)
  - PixelDiffAnalyzer: Piksel farkı hesaplama ve sağlayıcı karşılaştırması
  - DiffVisualizer: Yan yana / blend animasyonu görselleştirme
"""

from __future__ import annotations

import io
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.metrics import structural_similarity as ssim

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

# Fark analizi çıktılarının kaydedileceği kök dizin
DIFF_OUTPUT_ROOT: str = os.path.join(
    getattr(settings, "STORAGE_ROOT", "data"), "diff_results"
)

# Varsayılan eşik değerleri
DEFAULT_DIFF_THRESHOLD: int = 30       # piksel farkı eşiği (0-255)
DEFAULT_MIN_CONTOUR_AREA: int = 100    # minimum bölge alanı (piksel²)
DEFAULT_BLUR_KERNEL: int = 5           # Gaussian bulanıklık çekirdeği

# Anomaly skorlama eşikleri
ANOMALY_HIGH_DIFF: int = 30            # diff_score > 30 → +40 puan
ANOMALY_MEDIUM_DIFF: int = 15          # diff_score > 15 → +20 puan
ANOMALY_MULTI_DISAGREE: int = 3        # 3+ sağlayıcı uyumsuzluğu → +20 puan


# ---------------------------------------------------------------------------
# Veri sınıfları
# ---------------------------------------------------------------------------


@dataclass
class BoundingBox:
    """Fark bölgesini tanımlayan sınırlayıcı kutu.

    Attributes:
        x: Sol üst köşe X koordinatı (piksel).
        y: Sol üst köşe Y koordinatı (piksel).
        width: Kutu genişliği (piksel).
        height: Kutu yüksekliği (piksel).
        area: Kutu alanı (piksel²).
        intensity: Bölgedeki ortalama fark yoğunluğu (0-255).
    """

    x: int
    y: int
    width: int
    height: int
    area: int = 0
    intensity: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "area": self.area,
            "intensity": round(self.intensity, 2),
        }


@dataclass
class DiffResult:
    """İki görüntü arasındaki piksel farkı sonucu.

    Attributes:
        diff_score: Genel fark yüzdesi (0–100). 0 = tamamen aynı.
        diff_image: Fark görselleştirmesi (kırmızı = farklı piksel).
        changed_regions: Farkın yoğun olduğu sınırlayıcı kutular.
        structural_similarity: SSIM skoru (0–1). 1 = tamamen aynı.
        histogram_diff: Her kanal (R, G, B) için histogram farkı (0–1).
        pixel_change_count: Değişen piksel sayısı.
        total_pixels: Toplam piksel sayısı.
    """

    diff_score: float
    diff_image: Image.Image
    changed_regions: List[BoundingBox]
    structural_similarity: float
    histogram_diff: Dict[str, float]
    pixel_change_count: int = 0
    total_pixels: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür (diff_image hariç)."""
        return {
            "diff_score": round(self.diff_score, 2),
            "structural_similarity": round(self.structural_similarity, 4),
            "histogram_diff": {
                k: round(v, 4) for k, v in self.histogram_diff.items()
            },
            "pixel_change_count": self.pixel_change_count,
            "total_pixels": self.total_pixels,
            "changed_regions": [r.to_dict() for r in self.changed_regions],
            "num_changed_regions": len(self.changed_regions),
        }


@dataclass
class PairComparison:
    """İki sağlayıcı arasındaki karşılaştırma sonucu.

    Attributes:
        provider_a: Birinci sağlayıcı adı.
        provider_b: İkinci sağlayıcı adı.
        diff_result: Piksel farkı sonucu.
    """

    provider_a: str
    provider_b: str
    diff_result: DiffResult

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "provider_a": self.provider_a,
            "provider_b": self.provider_b,
            **self.diff_result.to_dict(),
        }


@dataclass
class ProviderComparisonResult:
    """Tüm sağlayıcılar arası karşılaştırma sonucu.

    Attributes:
        pair_results: Her sağlayıcı çifti için karşılaştırma sonuçları.
        max_diff_pair: En yüksek fark skoru olan çift.
        anomaly_score: Hesaplanan anomali skoru (0–100).
        summary: İnsan okunabilir özet.
        providers_compared: Karşılaştırmaya dahil edilen sağlayıcılar.
        disagreeing_providers: Yüksek fark gösteren sağlayıcı sayısı.
    """

    pair_results: List[PairComparison]
    max_diff_pair: Optional[PairComparison]
    anomaly_score: float
    summary: str
    providers_compared: List[str] = field(default_factory=list)
    disagreeing_providers: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "anomaly_score": round(self.anomaly_score, 2),
            "summary": self.summary,
            "providers_compared": self.providers_compared,
            "disagreeing_providers": self.disagreeing_providers,
            "max_diff_pair": (
                self.max_diff_pair.to_dict() if self.max_diff_pair else None
            ),
            "pair_results": [p.to_dict() for p in self.pair_results],
        }


# ---------------------------------------------------------------------------
# Yardımcı: NumPy ↔ PIL dönüşümleri
# ---------------------------------------------------------------------------


def pil_to_cv2(img: Image.Image) -> np.ndarray:
    """PIL Image'ı OpenCV BGR numpy dizisine dönüştürür.

    Args:
        img: PIL Image objesi (RGB veya RGBA).

    Returns:
        OpenCV BGR formatında numpy dizisi (uint8).
    """
    img_rgb = img.convert("RGB")
    arr = np.array(img_rgb, dtype=np.uint8)
    # RGB → BGR (OpenCV formatı)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def cv2_to_pil(arr: np.ndarray) -> Image.Image:
    """OpenCV BGR numpy dizisini PIL Image'a dönüştürür.

    Args:
        arr: OpenCV BGR formatında numpy dizisi.

    Returns:
        PIL Image objesi (RGB).
    """
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


# ---------------------------------------------------------------------------
# ImageAligner — Görüntü hizalama
# ---------------------------------------------------------------------------


class ImageAligner:
    """Farklı sağlayıcılardan gelen tile görüntülerini hizalar.

    ORB (Oriented FAST and Rotated BRIEF) feature matching ile
    perspektif dönüşümü uygulayarak iki görüntüyü hizalar. ORB
    yeterli eşleşme bulamazsa merkez kırpma ile boyut eşitleme
    yapılır (fallback).

    Attributes:
        _orb_features: ORB detektörünün arayacağı maksimum feature sayısı.
        _match_threshold: Minimum kabul edilebilir eşleşme sayısı.
        _ratio_test: Lowe'un oran testi eşiği.

    Examples:
        >>> aligner = ImageAligner()
        >>> img_a = Image.open("osm_tile.png")
        >>> img_b = Image.open("google_tile.png")
        >>> aligned_a, aligned_b = aligner.align_tiles(img_a, img_b)
        >>> aligned_a.size == aligned_b.size
        True
    """

    def __init__(
        self,
        *,
        orb_features: int = 1000,
        match_threshold: int = 10,
        ratio_test: float = 0.75,
    ) -> None:
        """
        Args:
            orb_features: ORB'nin tespit edeceği maksimum feature sayısı.
            match_threshold: Homografi hesabı için minimum eşleşme sayısı.
            ratio_test: Lowe'un oran testi eşiği (düşük = daha seçici).
        """
        self._orb_features = orb_features
        self._match_threshold = match_threshold
        self._ratio_test = ratio_test

    def align_tiles(
        self,
        img1: Image.Image,
        img2: Image.Image,
    ) -> Tuple[Image.Image, Image.Image]:
        """İki tile görüntüsünü hizalar ve aynı boyuta getirir.

        Önce ORB feature matching ile perspektif hizalama dener.
        Yeterli eşleşme bulunamazsa merkez kırpma ile boyut
        eşitlemesine düşer.

        Args:
            img1: Referans görüntü (hizalanacak hedef).
            img2: Hizalanacak kaynak görüntü.

        Returns:
            (img1_aligned, img2_aligned) — aynı boyutlarda PIL Image çifti.

        Examples:
            >>> aligner = ImageAligner()
            >>> a, b = aligner.align_tiles(tile_osm, tile_google)
            >>> a.size == b.size
            True
        """
        cv_img1 = pil_to_cv2(img1)
        cv_img2 = pil_to_cv2(img2)

        aligned = self._try_orb_alignment(cv_img1, cv_img2)

        if aligned is not None:
            cv_img2_aligned = aligned
            logger.info(
                "ORB hizalama başarılı: %dx%d → %dx%d",
                img2.width, img2.height,
                cv_img2_aligned.shape[1], cv_img2_aligned.shape[0],
            )
        else:
            logger.info(
                "ORB hizalama başarısız, merkez kırpma uygulanıyor"
            )
            cv_img1, cv_img2_aligned = self._center_crop_match(
                cv_img1, cv_img2
            )

        # Son boyut kontrolü: her ikisini de aynı boyuta getir
        h = min(cv_img1.shape[0], cv_img2_aligned.shape[0])
        w = min(cv_img1.shape[1], cv_img2_aligned.shape[1])
        cv_img1 = cv_img1[:h, :w]
        cv_img2_aligned = cv_img2_aligned[:h, :w]

        return cv2_to_pil(cv_img1), cv2_to_pil(cv_img2_aligned)

    def _try_orb_alignment(
        self,
        ref: np.ndarray,
        src: np.ndarray,
    ) -> Optional[np.ndarray]:
        """ORB feature matching ile perspektif hizalama dener.

        Args:
            ref: Referans görüntü (BGR numpy dizisi).
            src: Kaynak görüntü (BGR numpy dizisi).

        Returns:
            Hizalanmış kaynak görüntü veya None (başarısızsa).
        """
        gray_ref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
        gray_src = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)

        orb = cv2.ORB_create(nfeatures=self._orb_features)
        kp1, des1 = orb.detectAndCompute(gray_ref, None)
        kp2, des2 = orb.detectAndCompute(gray_src, None)

        if des1 is None or des2 is None:
            logger.debug("ORB: Descriptor bulunamadı")
            return None

        if len(des1) < self._match_threshold or len(des2) < self._match_threshold:
            logger.debug(
                "ORB: Yetersiz feature — ref=%d, src=%d",
                len(des1), len(des2),
            )
            return None

        # BFMatcher ile eşleştirme (Hamming mesafesi, ORB için uygun)
        bf = cv2.BFMatcher(cv2.NORM_HAMMING)

        try:
            raw_matches = bf.knnMatch(des1, des2, k=2)
        except cv2.error as exc:
            logger.debug("ORB knnMatch hatası: %s", exc)
            return None

        # Lowe'un oran testi
        good_matches: list = []
        for match_pair in raw_matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < self._ratio_test * n.distance:
                    good_matches.append(m)

        logger.debug(
            "ORB eşleşmeleri: toplam=%d, iyi=%d (eşik=%d)",
            len(raw_matches), len(good_matches), self._match_threshold,
        )

        if len(good_matches) < self._match_threshold:
            return None

        # Homografi matrisi hesapla
        pts_ref = np.float32(
            [kp1[m.queryIdx].pt for m in good_matches]
        ).reshape(-1, 1, 2)
        pts_src = np.float32(
            [kp2[m.trainIdx].pt for m in good_matches]
        ).reshape(-1, 1, 2)

        homography, mask = cv2.findHomography(
            pts_src, pts_ref, cv2.RANSAC, 5.0
        )

        if homography is None:
            logger.debug("ORB: Homografi hesaplanamadı")
            return None

        # Inlier oranı kontrolü
        if mask is not None:
            inlier_ratio = float(np.sum(mask)) / len(mask)
            if inlier_ratio < 0.3:
                logger.debug(
                    "ORB: Düşük inlier oranı: %.2f", inlier_ratio
                )
                return None

        # Perspektif dönüşümü uygula
        h, w = ref.shape[:2]
        aligned = cv2.warpPerspective(src, homography, (w, h))

        return aligned

    @staticmethod
    def _center_crop_match(
        img1: np.ndarray,
        img2: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Her iki görüntüyü merkezden kırparak aynı boyuta getirir.

        Daha büyük görüntünün merkezinden, daha küçük görüntünün boyutunda
        bir bölge kırpar. Her iki görüntü de aynı boyuttaysa olduğu gibi
        döndürülür.

        Args:
            img1: Birinci görüntü (BGR numpy dizisi).
            img2: İkinci görüntü (BGR numpy dizisi).

        Returns:
            Aynı boyutlara kırpılmış (img1, img2) çifti.
        """
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        target_h = min(h1, h2)
        target_w = min(w1, w2)

        def _center_crop(img: np.ndarray, th: int, tw: int) -> np.ndarray:
            h, w = img.shape[:2]
            y_start = (h - th) // 2
            x_start = (w - tw) // 2
            return img[y_start : y_start + th, x_start : x_start + tw]

        cropped1 = _center_crop(img1, target_h, target_w)
        cropped2 = _center_crop(img2, target_h, target_w)

        return cropped1, cropped2


# ---------------------------------------------------------------------------
# PixelDiffAnalyzer — Piksel farkı hesaplama
# ---------------------------------------------------------------------------


class PixelDiffAnalyzer:
    """Harita tile görüntüleri arasındaki piksel farklarını analiz eder.

    İki görüntüyü karşılaştırarak fark skoru, SSIM, histogram farkı
    ve değişen bölgeleri hesaplar. Birden fazla sağlayıcıyı çapraz
    olarak karşılaştırıp anomali skoru üretebilir.

    Attributes:
        _aligner: Görüntü hizalama modülü.
        _diff_threshold: Piksel farkı eşiği (0-255).
        _min_contour_area: Minimum bölge alanı (piksel²).
        _blur_kernel: Gaussian bulanıklık çekirdeği boyutu.

    Examples:
        >>> analyzer = PixelDiffAnalyzer()
        >>> result = analyzer.compute_diff(tile_osm, tile_google)
        >>> print(f"Fark: %{result.diff_score:.1f}, SSIM: {result.structural_similarity:.3f}")
        Fark: %12.5, SSIM: 0.847
    """

    def __init__(
        self,
        *,
        aligner: Optional[ImageAligner] = None,
        diff_threshold: int = DEFAULT_DIFF_THRESHOLD,
        min_contour_area: int = DEFAULT_MIN_CONTOUR_AREA,
        blur_kernel: int = DEFAULT_BLUR_KERNEL,
    ) -> None:
        """
        Args:
            aligner: Kullanılacak ImageAligner. None ise varsayılan oluşturulur.
            diff_threshold: Piksel farklı sayılması için eşik (0-255).
            min_contour_area: Bölge tespitinde minimum kontur alanı (px²).
            blur_kernel: Gürültü azaltma için Gaussian çekirdeği boyutu.
        """
        self._aligner = aligner or ImageAligner()
        self._diff_threshold = diff_threshold
        self._min_contour_area = min_contour_area
        self._blur_kernel = blur_kernel

    # ------------------------------------------------------------------ #
    # compute_diff — İki görüntü arası fark
    # ------------------------------------------------------------------ #

    def compute_diff(
        self,
        img1: Image.Image,
        img2: Image.Image,
    ) -> DiffResult:
        """İki görüntü arasındaki piksel farkını hesaplar.

        Görüntüler önce hizalanır, ardından piksel bazında fark haritası
        çıkarılır. Sonuçta fark skoru (0–100), SSIM, histogram farkı ve
        değişen bölge kutuları döndürülür.

        Args:
            img1: Birinci görüntü (PIL Image).
            img2: İkinci görüntü (PIL Image).

        Returns:
            DiffResult — fark analizi sonuçları.

        Examples:
            >>> analyzer = PixelDiffAnalyzer()
            >>> result = analyzer.compute_diff(tile_a, tile_b)
            >>> 0 <= result.diff_score <= 100
            True
            >>> 0 <= result.structural_similarity <= 1
            True
        """
        # Hizalama
        aligned1, aligned2 = self._aligner.align_tiles(img1, img2)

        # NumPy dizilerine dönüştür
        arr1 = np.array(aligned1.convert("RGB"), dtype=np.uint8)
        arr2 = np.array(aligned2.convert("RGB"), dtype=np.uint8)

        # --- Piksel farkı ---
        abs_diff = cv2.absdiff(arr1, arr2)
        gray_diff = cv2.cvtColor(abs_diff, cv2.COLOR_RGB2GRAY)

        # Gürültü azaltma
        if self._blur_kernel > 1:
            gray_diff = cv2.GaussianBlur(
                gray_diff,
                (self._blur_kernel, self._blur_kernel),
                0,
            )

        # Binary eşikleme
        _, thresh = cv2.threshold(
            gray_diff, self._diff_threshold, 255, cv2.THRESH_BINARY
        )

        # Fark skoru (değişen piksel yüzdesi)
        total_pixels = thresh.shape[0] * thresh.shape[1]
        changed_pixels = int(np.count_nonzero(thresh))
        diff_score = (changed_pixels / total_pixels) * 100.0 if total_pixels > 0 else 0.0

        # --- SSIM ---
        ssim_score = self._compute_ssim(arr1, arr2)

        # --- Histogram farkı ---
        hist_diff = self._compute_histogram_diff(arr1, arr2)

        # --- Değişen bölgeler ---
        changed_regions = self._find_changed_regions(gray_diff, thresh)

        # --- Fark görselleştirmesi ---
        diff_image = self._create_diff_visualization(arr1, thresh, gray_diff)

        logger.info(
            "Piksel farkı hesaplandı: score=%.2f%%, SSIM=%.4f, "
            "bölge_sayısı=%d, değişen_px=%d/%d",
            diff_score, ssim_score,
            len(changed_regions), changed_pixels, total_pixels,
        )

        return DiffResult(
            diff_score=diff_score,
            diff_image=diff_image,
            changed_regions=changed_regions,
            structural_similarity=ssim_score,
            histogram_diff=hist_diff,
            pixel_change_count=changed_pixels,
            total_pixels=total_pixels,
        )

    @staticmethod
    def _compute_ssim(arr1: np.ndarray, arr2: np.ndarray) -> float:
        """SSIM (Structural Similarity Index) hesaplar.

        scikit-image kütüphanesinin SSIM uygulamasını kullanır.
        Çok küçük görüntülerde pencere boyutunu otomatik ayarlar.

        Args:
            arr1: Birinci görüntü (RGB uint8 numpy dizisi).
            arr2: İkinci görüntü (RGB uint8 numpy dizisi).

        Returns:
            SSIM skoru (0–1). 1 = tamamen aynı.
        """
        # SSIM için gri tonlama
        gray1 = cv2.cvtColor(arr1, cv2.COLOR_RGB2GRAY)
        gray2 = cv2.cvtColor(arr2, cv2.COLOR_RGB2GRAY)

        # Pencere boyutu: görüntü boyutundan küçük olmalı, tek sayı
        min_dim = min(gray1.shape[0], gray1.shape[1])
        win_size = min(7, min_dim)
        if win_size % 2 == 0:
            win_size -= 1
        win_size = max(3, win_size)

        try:
            score, _ = ssim(
                gray1,
                gray2,
                win_size=win_size,
                full=True,
                data_range=255,
            )
            return float(score)
        except Exception as exc:
            logger.warning("SSIM hesaplama hatası: %s", exc)
            return 0.0

    @staticmethod
    def _compute_histogram_diff(
        arr1: np.ndarray,
        arr2: np.ndarray,
    ) -> Dict[str, float]:
        """İki görüntünün renk kanal histogramlarını karşılaştırır.

        Her kanal (R, G, B) için ayrı histogram hesaplar ve Bhattacharyya
        uzaklığını kullanarak farkı ölçer.

        Args:
            arr1: Birinci görüntü (RGB uint8 numpy dizisi).
            arr2: İkinci görüntü (RGB uint8 numpy dizisi).

        Returns:
            {"red": float, "green": float, "blue": float, "mean": float}
            Her değer 0–1 arası; 0 = aynı dağılım.
        """
        channels = {"red": 0, "green": 1, "blue": 2}
        diffs: Dict[str, float] = {}

        for name, idx in channels.items():
            hist1 = cv2.calcHist([arr1], [idx], None, [256], [0, 256])
            hist2 = cv2.calcHist([arr2], [idx], None, [256], [0, 256])

            # Normalize et
            cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
            cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)

            # Bhattacharyya uzaklığı (0 = aynı, 1 = tamamen farklı)
            dist = cv2.compareHist(hist1, hist2, cv2.HISTCMP_BHATTACHARYYA)
            diffs[name] = float(dist)

        diffs["mean"] = sum(diffs.values()) / 3.0
        return diffs

    def _find_changed_regions(
        self,
        gray_diff: np.ndarray,
        thresh: np.ndarray,
    ) -> List[BoundingBox]:
        """Fark haritasından yoğun değişim bölgelerini tespit eder.

        Binary eşikleme sonrası morfolojik temizleme uygular ve kontur
        bularak her farklı bölge için bir BoundingBox oluşturur.

        Args:
            gray_diff: Gri tonlama fark haritası (0-255).
            thresh: Binary eşiklenmiş fark maskesi.

        Returns:
            BoundingBox listesi, alan büyüklüğüne göre sıralı (büyükten küçüğe).
        """
        # Morfolojik temizleme: küçük gürültüleri kaldır
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)

        # Kontur bul
        contours, _ = cv2.findContours(
            cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        regions: List[BoundingBox] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self._min_contour_area:
                continue

            x, y, w, h = cv2.boundingRect(contour)

            # Bölge içindeki ortalama fark yoğunluğu
            roi = gray_diff[y : y + h, x : x + w]
            intensity = float(np.mean(roi)) if roi.size > 0 else 0.0

            regions.append(
                BoundingBox(
                    x=int(x),
                    y=int(y),
                    width=int(w),
                    height=int(h),
                    area=int(area),
                    intensity=intensity,
                )
            )

        # Alan büyüklüğüne göre sırala
        regions.sort(key=lambda r: r.area, reverse=True)

        return regions

    @staticmethod
    def _create_diff_visualization(
        original: np.ndarray,
        thresh: np.ndarray,
        gray_diff: np.ndarray,
    ) -> Image.Image:
        """Fark haritasını kırmızı overlay olarak görselleştirir.

        Orijinal görüntü üzerine farklı pikselleri yarı saydam kırmızı
        olarak bindirerek değişiklikleri vurgular.

        Args:
            original: Orijinal görüntü (RGB uint8 numpy dizisi).
            thresh: Binary eşiklenmiş fark maskesi.
            gray_diff: Gri tonlama fark haritası (yoğunluk için).

        Returns:
            Farkların kırmızı overlay ile işaretlendiği PIL Image.
        """
        # Orijinal görüntüyü kopyala
        vis = original.copy()

        # Kırmızı overlay oluştur
        red_overlay = np.zeros_like(vis)
        red_overlay[:, :, 0] = 255  # Kırmızı kanal

        # Yoğunluğa göre alfa hesapla (daha büyük fark = daha opak kırmızı)
        alpha = gray_diff.astype(np.float32) / 255.0
        alpha = np.clip(alpha * 2.0, 0.0, 0.8)  # max %80 opaklık

        # Sadece eşik üstü piksellere uygula
        mask = thresh > 0
        alpha_3ch = np.stack([alpha] * 3, axis=-1)

        vis_float = vis.astype(np.float32)
        overlay_float = red_overlay.astype(np.float32)

        # Alfa birleştirme: sadece maskeli piksellerde
        mask_3ch = np.stack([mask] * 3, axis=-1)
        blended = np.where(
            mask_3ch,
            vis_float * (1.0 - alpha_3ch) + overlay_float * alpha_3ch,
            vis_float,
        )

        blended = np.clip(blended, 0, 255).astype(np.uint8)
        return Image.fromarray(blended)

    # ------------------------------------------------------------------ #
    # compare_providers — Çoklu sağlayıcı karşılaştırması
    # ------------------------------------------------------------------ #

    def compare_providers(
        self,
        images: Dict[str, Image.Image],
    ) -> ProviderComparisonResult:
        """Birden fazla sağlayıcıdan gelen görüntüleri çapraz karşılaştırır.

        Tüm olası sağlayıcı çiftlerini karşılaştırır, en yüksek fark
        çiftini bulur ve anomali skoru hesaplar.

        Anomaly skorlama kuralları:
          - diff_score > 30: +40 puan
          - diff_score > 15: +20 puan
          - 3+ sağlayıcı aynı fikirde değilse: +20 puan

        Args:
            images: Sağlayıcı adı → PIL Image sözlüğü.
                    Örn: {"osm": img_osm, "google": img_google, ...}

        Returns:
            ProviderComparisonResult — çapraz karşılaştırma sonuçları.

        Raises:
            ValueError: 2'den az sağlayıcı görüntüsü verilirse.

        Examples:
            >>> analyzer = PixelDiffAnalyzer()
            >>> result = analyzer.compare_providers({
            ...     "osm": tile_osm,
            ...     "google": tile_google,
            ...     "bing": tile_bing,
            ... })
            >>> 0 <= result.anomaly_score <= 100
            True
        """
        provider_names = list(images.keys())

        if len(provider_names) < 2:
            raise ValueError(
                f"En az 2 sağlayıcı görüntüsü gerekli, {len(provider_names)} verildi."
            )

        logger.info(
            "Sağlayıcı karşılaştırması başlatılıyor: %s",
            ", ".join(provider_names),
        )

        # Tüm çift kombinasyonlarını karşılaştır
        pair_results: List[PairComparison] = []
        for name_a, name_b in combinations(provider_names, 2):
            logger.info("Karşılaştırılıyor: %s ↔ %s", name_a, name_b)

            diff_result = self.compute_diff(images[name_a], images[name_b])

            pair_results.append(
                PairComparison(
                    provider_a=name_a,
                    provider_b=name_b,
                    diff_result=diff_result,
                )
            )

        # En yüksek fark çiftini bul
        max_diff_pair: Optional[PairComparison] = None
        if pair_results:
            max_diff_pair = max(
                pair_results, key=lambda p: p.diff_result.diff_score
            )

        # Anomali skoru hesapla
        anomaly_score, disagreeing_count, summary = self._calculate_anomaly(
            pair_results, provider_names
        )

        result = ProviderComparisonResult(
            pair_results=pair_results,
            max_diff_pair=max_diff_pair,
            anomaly_score=anomaly_score,
            summary=summary,
            providers_compared=provider_names,
            disagreeing_providers=disagreeing_count,
        )

        logger.info(
            "Sağlayıcı karşılaştırması tamamlandı: anomaly=%.1f, "
            "max_diff=%.1f%% (%s↔%s), uyumsuz_sağlayıcı=%d",
            anomaly_score,
            max_diff_pair.diff_result.diff_score if max_diff_pair else 0.0,
            max_diff_pair.provider_a if max_diff_pair else "-",
            max_diff_pair.provider_b if max_diff_pair else "-",
            disagreeing_count,
        )

        return result

    @staticmethod
    def _calculate_anomaly(
        pair_results: List[PairComparison],
        provider_names: List[str],
    ) -> Tuple[float, int, str]:
        """Anomali skoru, uyumsuz sağlayıcı sayısı ve özet üretir.

        Args:
            pair_results: Çiftler arası karşılaştırma sonuçları.
            provider_names: Karşılaştırılan sağlayıcı adları.

        Returns:
            (anomaly_score, disagreeing_count, summary) üçlüsü.
        """
        if not pair_results:
            return 0.0, 0, "Karşılaştırma yapılamadı."

        anomaly_score: float = 0.0
        reasons: List[str] = []

        # En yüksek fark skoru
        max_score = max(p.diff_result.diff_score for p in pair_results)

        if max_score > ANOMALY_HIGH_DIFF:
            anomaly_score += 40.0
            reasons.append(
                f"Yüksek fark tespit edildi (maks: {max_score:.1f}% > {ANOMALY_HIGH_DIFF}%)"
            )
        elif max_score > ANOMALY_MEDIUM_DIFF:
            anomaly_score += 20.0
            reasons.append(
                f"Orta düzey fark tespit edildi (maks: {max_score:.1f}% > {ANOMALY_MEDIUM_DIFF}%)"
            )

        # Uyumsuz sağlayıcı sayısı
        # Bir sağlayıcı, herhangi bir çiftte diff_score > 15 ise "uyumsuz"
        disagreeing: set[str] = set()
        for pair in pair_results:
            if pair.diff_result.diff_score > ANOMALY_MEDIUM_DIFF:
                disagreeing.add(pair.provider_a)
                disagreeing.add(pair.provider_b)

        disagreeing_count = len(disagreeing)

        if disagreeing_count >= ANOMALY_MULTI_DISAGREE:
            anomaly_score += 20.0
            reasons.append(
                f"{disagreeing_count} sağlayıcı uyumsuz "
                f"(eşik: {ANOMALY_MULTI_DISAGREE})"
            )

        # SSIM ortalaması düşükse ek puan
        avg_ssim = (
            sum(p.diff_result.structural_similarity for p in pair_results)
            / len(pair_results)
        )
        if avg_ssim < 0.7:
            bonus = min(20.0, (0.7 - avg_ssim) * 100.0)
            anomaly_score += bonus
            reasons.append(
                f"Düşük yapısal benzerlik (ort. SSIM: {avg_ssim:.3f})"
            )

        # Skoru 0–100 arasına sınırla
        anomaly_score = min(100.0, max(0.0, anomaly_score))

        # Özet oluştur
        if anomaly_score >= 60:
            level = "YÜKSEK"
        elif anomaly_score >= 30:
            level = "ORTA"
        elif anomaly_score > 0:
            level = "DÜŞÜK"
        else:
            level = "YOK"

        summary = (
            f"Anomali seviyesi: {level} ({anomaly_score:.0f}/100). "
            f"Karşılaştırılan: {len(provider_names)} sağlayıcı, "
            f"{len(pair_results)} çift. "
        )
        if reasons:
            summary += "Nedenler: " + "; ".join(reasons) + "."
        else:
            summary += "Kayda değer fark tespit edilmedi."

        return anomaly_score, disagreeing_count, summary


# ---------------------------------------------------------------------------
# DiffVisualizer — Görselleştirme çıktıları
# ---------------------------------------------------------------------------


class DiffVisualizer:
    """Fark analizi sonuçlarını görselleştirir ve dosyaya kaydeder.

    Yan yana karşılaştırma ve blend animasyonu (GIF) üretir. Çıktıları
    yerel dosya sistemine kaydeder ve erişim yolu döndürür.

    Attributes:
        _output_dir: Çıktı dosyalarının kaydedileceği dizin.
        _font_size: Etiket yazı tipi boyutu.
        _padding: Görseller arası boşluk (piksel).

    Examples:
        >>> viz = DiffVisualizer()
        >>> path = viz.create_side_by_side(
        ...     tile_osm, tile_google,
        ...     label1="OSM", label2="Google",
        ... )
        >>> os.path.exists(path)
        True
    """

    def __init__(
        self,
        *,
        output_dir: Optional[str] = None,
        font_size: int = 16,
        padding: int = 10,
    ) -> None:
        """
        Args:
            output_dir: Çıktı dizini. None ise varsayılan kullanılır.
            font_size: Etiket yazı tipi boyutu (piksel).
            padding: Görseller arası boşluk (piksel).
        """
        self._output_dir = Path(output_dir or DIFF_OUTPUT_ROOT)
        self._font_size = font_size
        self._padding = padding

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

    def _get_font(self) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Etiketleme için yazı tipi yükler.

        TrueType font bulunamazsa PIL varsayılan fontuna düşer.

        Returns:
            PIL Font objesi.
        """
        # Yaygın sistem fontlarını dene
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    return ImageFont.truetype(font_path, self._font_size)
                except (OSError, IOError):
                    continue

        # Fallback: PIL varsayılan fontu
        return ImageFont.load_default()

    def create_side_by_side(
        self,
        img1: Image.Image,
        img2: Image.Image,
        label1: str = "Sağlayıcı A",
        label2: str = "Sağlayıcı B",
        *,
        diff_image: Optional[Image.Image] = None,
        save: bool = True,
    ) -> str:
        """İki görüntüyü yan yana karşılaştırma görseli oluşturur.

        Sol tarafta birinci görüntü, sağ tarafta ikinci görüntü ve
        isteğe bağlı olarak altta fark haritası gösterilir. Her
        görüntünün üstüne sağlayıcı etiketi yazılır.

        Args:
            img1: Sol taraftaki görüntü.
            img2: Sağ taraftaki görüntü.
            label1: Sol görüntü etiketi.
            label2: Sağ görüntü etiketi.
            diff_image: Opsiyonel fark görselleştirmesi (altta gösterilir).
            save: Dosyaya kaydet (True) veya sadece Image döndür (False).

        Returns:
            Kaydedilen dosyanın yolu. save=False ise boş string.
        """
        img1_rgb = img1.convert("RGB")
        img2_rgb = img2.convert("RGB")

        # Boyutları eşitle
        target_h = max(img1_rgb.height, img2_rgb.height)
        target_w = max(img1_rgb.width, img2_rgb.width)
        img1_rgb = img1_rgb.resize((target_w, target_h), Image.LANCZOS)
        img2_rgb = img2_rgb.resize((target_w, target_h), Image.LANCZOS)

        # Etiket alanı yüksekliği
        label_h = self._font_size + 12

        # Tuval boyutu hesapla
        has_diff = diff_image is not None
        canvas_w = target_w * 2 + self._padding * 3

        if has_diff:
            diff_rgb = diff_image.convert("RGB").resize(
                (target_w * 2 + self._padding, target_h), Image.LANCZOS
            )
            canvas_h = label_h + target_h + self._padding + label_h + target_h + self._padding
        else:
            canvas_h = label_h + target_h + self._padding * 2

        # Tuval oluştur (koyu arka plan)
        canvas = Image.new("RGB", (canvas_w, canvas_h), (30, 30, 30))
        draw = ImageDraw.Draw(canvas)
        font = self._get_font()

        # Etiketler
        x1 = self._padding
        x2 = target_w + self._padding * 2
        y_label = 4

        draw.text((x1, y_label), label1, fill=(255, 255, 255), font=font)
        draw.text((x2, y_label), label2, fill=(255, 255, 255), font=font)

        # Görüntüleri yapıştır
        y_img = label_h
        canvas.paste(img1_rgb, (x1, y_img))
        canvas.paste(img2_rgb, (x2, y_img))

        # Fark haritası (varsa)
        if has_diff and diff_rgb is not None:
            y_diff_label = y_img + target_h + self._padding
            draw.text(
                (x1, y_diff_label - label_h + 4),
                "Fark Haritası",
                fill=(255, 100, 100),
                font=font,
            )
            canvas.paste(diff_rgb, (x1, y_diff_label))

        # Dosyaya kaydet
        if save:
            out_dir = self._ensure_output_dir()
            filename = self._generate_filename("side_by_side", "png")
            filepath = out_dir / filename
            canvas.save(str(filepath), "PNG", optimize=True)

            logger.info("Yan yana karşılaştırma kaydedildi: %s", filepath)
            return str(filepath)

        return ""

    def create_blend_animation(
        self,
        img1: Image.Image,
        img2: Image.Image,
        *,
        frames: int = 20,
        duration_ms: int = 100,
        save: bool = True,
    ) -> List[Image.Image]:
        """İki görüntü arasında yumuşak geçiş animasyonu oluşturur.

        Birinci görüntüden ikincisine kademeli olarak geçiş yapan
        kare dizisi üretir. İsteğe bağlı olarak GIF dosyası olarak
        kaydeder.

        Args:
            img1: Başlangıç görüntüsü.
            img2: Bitiş görüntüsü.
            frames: Animasyon kare sayısı (varsayılan 20).
            duration_ms: Her karenin gösterim süresi (ms).
            save: GIF dosyası olarak kaydet.

        Returns:
            PIL Image karelerinin listesi.

        Examples:
            >>> viz = DiffVisualizer()
            >>> frames = viz.create_blend_animation(tile_a, tile_b, save=False)
            >>> len(frames) == 20
            True
        """
        img1_rgb = img1.convert("RGB")
        img2_rgb = img2.convert("RGB")

        # Boyutları eşitle
        target_w = max(img1_rgb.width, img2_rgb.width)
        target_h = max(img1_rgb.height, img2_rgb.height)
        img1_rgb = img1_rgb.resize((target_w, target_h), Image.LANCZOS)
        img2_rgb = img2_rgb.resize((target_w, target_h), Image.LANCZOS)

        arr1 = np.array(img1_rgb, dtype=np.float32)
        arr2 = np.array(img2_rgb, dtype=np.float32)

        frame_list: List[Image.Image] = []

        # İleri geçiş: img1 → img2
        for i in range(frames):
            alpha = i / max(frames - 1, 1)
            blended = ((1.0 - alpha) * arr1 + alpha * arr2).astype(np.uint8)
            frame_list.append(Image.fromarray(blended))

        # Geri geçiş: img2 → img1 (ping-pong efekti)
        for i in range(frames - 2, 0, -1):
            alpha = i / max(frames - 1, 1)
            blended = ((1.0 - alpha) * arr1 + alpha * arr2).astype(np.uint8)
            frame_list.append(Image.fromarray(blended))

        # GIF olarak kaydet
        if save and frame_list:
            out_dir = self._ensure_output_dir()
            filename = self._generate_filename("blend_anim", "gif")
            filepath = out_dir / filename

            frame_list[0].save(
                str(filepath),
                format="GIF",
                save_all=True,
                append_images=frame_list[1:],
                duration=duration_ms,
                loop=0,  # sonsuz döngü
                optimize=True,
            )

            logger.info(
                "Blend animasyonu kaydedildi: %s (%d kare, %d ms/kare)",
                filepath, len(frame_list), duration_ms,
            )

        return frame_list

    def save_diff_result(
        self,
        diff_result: DiffResult,
        label1: str = "A",
        label2: str = "B",
    ) -> Dict[str, str]:
        """DiffResult'ı dosyalara kaydeder ve yolları döndürür.

        Fark görselleştirmesini (PNG) ve sonuç özetini (JSON) kaydeder.

        Args:
            diff_result: Kaydedilecek DiffResult.
            label1: Birinci sağlayıcı etiketi.
            label2: İkinci sağlayıcı etiketi.

        Returns:
            {"diff_image": str, "summary_json": str} dosya yolları sözlüğü.
        """
        import json

        out_dir = self._ensure_output_dir()
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]

        paths: Dict[str, str] = {}

        # Fark görseli
        diff_filename = f"diff_{label1}_{label2}_{timestamp}_{unique_id}.png"
        diff_path = out_dir / diff_filename
        diff_result.diff_image.save(str(diff_path), "PNG", optimize=True)
        paths["diff_image"] = str(diff_path)

        # Özet JSON
        json_filename = f"diff_{label1}_{label2}_{timestamp}_{unique_id}.json"
        json_path = out_dir / json_filename
        summary = {
            "provider_a": label1,
            "provider_b": label2,
            "analyzed_at": datetime.utcnow().isoformat(),
            **diff_result.to_dict(),
        }
        json_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        paths["summary_json"] = str(json_path)

        logger.info(
            "DiffResult kaydedildi: %s, %s",
            diff_path.name, json_path.name,
        )

        return paths
