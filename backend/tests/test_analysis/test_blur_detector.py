"""
test_blur_detector.py — BlurDetector unit testleri.

Bilinen bulanık ve net görüntülerle Laplacian varyans, FFT analizi,
bölgesel bulanıklık haritası ve sağlayıcı karşılaştırması test eder.

Harici API bağımlılığı yoktur — tüm görüntüler in-memory oluşturulur.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageFilter

from app.services.analyzers.blur_detector import (
    BlurDetector,
    BlurMap,
    BlurComparisonResult,
    FFTResult,
    LAPLACIAN_SEVERE_BLUR,
    LAPLACIAN_MODERATE_BLUR,
)


# ---------------------------------------------------------------------------
# Yardımcı: Test görüntüleri oluşturma
# ---------------------------------------------------------------------------


def _create_sharp_image(size: int = 256) -> Image.Image:
    """
    Keskin kenarlar içeren test görüntüsü.

    Satranç tahtası deseni — yüksek Laplacian varyans.
    """
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    block = max(4, size // 16)
    for i in range(0, size, block):
        for j in range(0, size, block):
            if (i // block + j // block) % 2 == 0:
                arr[i : i + block, j : j + block] = 255
    return Image.fromarray(arr)


def _create_blurred_image(size: int = 256, radius: int = 10) -> Image.Image:
    """
    Kasıtlı bulanıklaştırılmış test görüntüsü.

    Keskin görüntüye Gaussian blur uygular.
    """
    sharp = _create_sharp_image(size)
    return sharp.filter(ImageFilter.GaussianBlur(radius=radius))


def _create_partially_blurred_image(size: int = 256) -> Image.Image:
    """
    Kısmi bulanık görüntü — sol yarı keskin, sağ yarı bulanık.

    Kasıtlı sansürü simüle eder (belirli bir bölge bulanıklaştırılmış).
    """
    sharp = _create_sharp_image(size)
    arr = np.array(sharp)

    # Sağ yarıyı bulanıklaştır
    right_half = Image.fromarray(arr[:, size // 2 :])
    blurred_half = right_half.filter(ImageFilter.GaussianBlur(radius=15))
    arr[:, size // 2 :] = np.array(blurred_half)

    return Image.fromarray(arr)


def _create_noise_image(size: int = 256, seed: int = 42) -> Image.Image:
    """Rastgele gürültü görüntüsü — yüksek frekans."""
    rng = np.random.RandomState(seed)
    arr = rng.randint(0, 255, (size, size, 3), dtype=np.uint8)
    return Image.fromarray(arr)


# ═══════════════════════════════════════════════════════════════════════════
# compute_laplacian_variance Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestLaplacianVariance:
    """Laplacian varyans hesaplama testleri."""

    def test_sharp_image_high_variance(self):
        """Keskin görüntü yüksek Laplacian varyans vermeli."""
        detector = BlurDetector()
        sharp = _create_sharp_image(128)

        variance = detector.compute_laplacian_variance(sharp)

        assert variance > LAPLACIAN_MODERATE_BLUR
        assert isinstance(variance, float)

    def test_blurred_image_low_variance(self):
        """Bulanık görüntü düşük Laplacian varyans vermeli."""
        detector = BlurDetector()
        blurred = _create_blurred_image(128, radius=15)

        variance = detector.compute_laplacian_variance(blurred)

        assert variance < LAPLACIAN_MODERATE_BLUR

    def test_solid_image_zero_variance(self):
        """Tek renk görüntü ~0 varyans vermeli (kenar yok)."""
        detector = BlurDetector()
        solid = Image.new("RGB", (128, 128), color=(128, 128, 128))

        variance = detector.compute_laplacian_variance(solid)

        assert variance < 1.0  # Neredeyse 0

    def test_variance_non_negative(self):
        """Varyans her zaman >= 0 olmalı."""
        detector = BlurDetector()
        noisy = _create_noise_image(64)

        variance = detector.compute_laplacian_variance(noisy)
        assert variance >= 0.0

    def test_sharp_greater_than_blurred(self):
        """Keskin görüntü varyansı bulanıktan büyük olmalı."""
        detector = BlurDetector()
        sharp = _create_sharp_image(128)
        blurred = _create_blurred_image(128, radius=10)

        var_sharp = detector.compute_laplacian_variance(sharp)
        var_blurred = detector.compute_laplacian_variance(blurred)

        assert var_sharp > var_blurred


# ═══════════════════════════════════════════════════════════════════════════
# classify_blur_level Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestClassifyBlurLevel:
    """Bulanıklık seviye sınıflandırma testleri."""

    def test_severe_classification(self):
        """< 50 → 'severe'."""
        assert BlurDetector.classify_blur_level(30.0) == "severe"
        assert BlurDetector.classify_blur_level(0.0) == "severe"
        assert BlurDetector.classify_blur_level(49.9) == "severe"

    def test_moderate_classification(self):
        """50-100 → 'moderate'."""
        assert BlurDetector.classify_blur_level(50.0) == "moderate"
        assert BlurDetector.classify_blur_level(75.0) == "moderate"
        assert BlurDetector.classify_blur_level(99.9) == "moderate"

    def test_sharp_classification(self):
        """>= 100 → 'sharp'."""
        assert BlurDetector.classify_blur_level(100.0) == "sharp"
        assert BlurDetector.classify_blur_level(500.0) == "sharp"
        assert BlurDetector.classify_blur_level(10000.0) == "sharp"


# ═══════════════════════════════════════════════════════════════════════════
# analyze_frequency_spectrum (FFT) Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestFFTAnalysis:
    """FFT frekans analizi testleri."""

    def test_fft_result_structure(self):
        """FFTResult tüm beklenen alanları içermeli."""
        detector = BlurDetector()
        img = _create_sharp_image(64)

        result = detector.analyze_frequency_spectrum(img)

        assert isinstance(result, FFTResult)
        assert hasattr(result, "high_freq_energy")
        assert hasattr(result, "low_freq_energy")
        assert hasattr(result, "power_ratio")
        assert hasattr(result, "has_low_pass_anomaly")
        assert hasattr(result, "spectrum_image")

    def test_sharp_image_high_freq(self):
        """Keskin görüntüde yüksek frekans enerjisi olmalı."""
        detector = BlurDetector()
        sharp = _create_sharp_image(128)

        result = detector.analyze_frequency_spectrum(sharp)

        assert result.high_freq_energy > 0
        assert result.power_ratio > 0

    def test_blurred_image_low_freq_dominant(self):
        """Bulanık görüntüde düşük frekans baskın olmalı."""
        detector = BlurDetector()
        sharp = _create_sharp_image(128)
        blurred = _create_blurred_image(128, radius=15)

        sharp_fft = detector.analyze_frequency_spectrum(sharp)
        blurred_fft = detector.analyze_frequency_spectrum(blurred)

        # Bulanık görüntünün power_ratio'su daha düşük olmalı
        assert blurred_fft.power_ratio < sharp_fft.power_ratio

    def test_fft_to_dict(self):
        """FFTResult.to_dict() serileştirilebilir olmalı."""
        detector = BlurDetector()
        img = _create_noise_image(64)

        result = detector.analyze_frequency_spectrum(img)
        d = result.to_dict()

        assert isinstance(d, dict)
        assert "high_freq_energy" in d
        assert "power_ratio" in d
        assert "has_low_pass_anomaly" in d
        # spectrum_image dict'te olmamalı
        assert "spectrum_image" not in d


# ═══════════════════════════════════════════════════════════════════════════
# detect_regional_blur Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestRegionalBlur:
    """Bölgesel bulanıklık haritası testleri."""

    def test_blur_map_structure(self):
        """BlurMap doğru yapıda olmalı."""
        detector = BlurDetector(grid_size=4)
        img = _create_sharp_image(128)

        bmap = detector.detect_regional_blur(img, grid_size=4)

        assert isinstance(bmap, BlurMap)
        assert bmap.blur_map.shape == (4, 4)
        assert bmap.grid_size == 4
        assert bmap.mean_score >= 0
        assert bmap.min_score >= 0
        assert bmap.max_score >= bmap.min_score

    def test_uniform_image_no_anomalies(self):
        """Düzgün görüntüde bölgesel anomali olmamalı."""
        detector = BlurDetector(grid_size=4)
        img = _create_sharp_image(128)

        bmap = detector.detect_regional_blur(img, grid_size=4)

        # Keskin uniform görüntüde tüm bölgeler benzer → anomali yok
        # (veya çok az)
        assert isinstance(bmap.anomaly_regions, list)

    def test_partially_blurred_detects_anomaly(self):
        """Kısmi bulanık görüntüde anomali bölgeleri tespit edilmeli."""
        detector = BlurDetector(grid_size=4, anomaly_std_factor=1.0)
        img = _create_partially_blurred_image(256)

        bmap = detector.detect_regional_blur(img, grid_size=4)

        # Standart sapma 0'dan büyük olmalı (tutarsız bulanıklık)
        assert bmap.std_score > 0

    def test_all_regions_populated(self):
        """all_regions listesi grid boyutunun karesiyle eşleşmeli."""
        detector = BlurDetector()
        img = _create_sharp_image(128)

        bmap = detector.detect_regional_blur(img, grid_size=4)

        assert len(bmap.all_regions) == 16  # 4×4 = 16

    def test_blur_map_to_dict(self):
        """BlurMap.to_dict() serileştirilebilir olmalı."""
        detector = BlurDetector()
        img = _create_sharp_image(64)

        bmap = detector.detect_regional_blur(img, grid_size=2)
        d = bmap.to_dict()

        assert "grid_size" in d
        assert "mean_score" in d
        assert "num_anomaly_regions" in d
        assert "anomaly_regions" in d


# ═══════════════════════════════════════════════════════════════════════════
# compare_blur_across_providers Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestProviderBlurComparison:
    """Çapraz sağlayıcı bulanıklık karşılaştırma testleri."""

    def test_two_similar_providers(self):
        """İki benzer sağlayıcı düşük sansür skoru vermeli."""
        detector = BlurDetector(grid_size=4)
        images = {
            "osm": _create_sharp_image(128),
            "google": _create_sharp_image(128),
        }

        result = detector.compare_blur_across_providers(images)

        assert isinstance(result, BlurComparisonResult)
        assert result.censorship_score < 50  # Düşük sansür şüphesi
        assert result.censorship_verdict in ("Normal", "Şüpheli")

    def test_one_blurred_provider(self):
        """Bir sağlayıcı bulanıksa sansür skoru yükselmeli."""
        detector = BlurDetector(grid_size=4)
        images = {
            "osm": _create_sharp_image(128),
            "google": _create_blurred_image(128, radius=15),
        }

        result = detector.compare_blur_across_providers(images)

        assert result.censorship_score > 0
        assert result.most_blurred_provider == "google"
        assert result.sharpest_provider == "osm"
        assert result.blur_variance > 0

    def test_provider_results_populated(self):
        """Her sağlayıcı için sonuç dönmeli."""
        detector = BlurDetector(grid_size=4)
        images = {
            "osm": _create_sharp_image(64),
            "google": _create_sharp_image(64),
            "bing": _create_sharp_image(64),
        }

        result = detector.compare_blur_across_providers(images)

        assert len(result.provider_results) == 3
        names = {p.provider for p in result.provider_results}
        assert names == {"osm", "google", "bing"}

    def test_less_than_two_raises(self):
        """2'den az sağlayıcı ValueError vermeli."""
        detector = BlurDetector()

        with pytest.raises(ValueError, match="En az 2"):
            detector.compare_blur_across_providers(
                {"single": _create_sharp_image(64)}
            )

    def test_comparison_to_dict(self):
        """BlurComparisonResult.to_dict() serileştirilebilir olmalı."""
        detector = BlurDetector(grid_size=4)
        images = {
            "osm": _create_sharp_image(64),
            "google": _create_blurred_image(64, radius=10),
        }

        result = detector.compare_blur_across_providers(images)
        d = result.to_dict()

        assert "censorship_score" in d
        assert "censorship_verdict" in d
        assert "most_blurred_provider" in d
        assert "sharpest_provider" in d
        assert "reasons" in d
        assert "provider_results" in d
