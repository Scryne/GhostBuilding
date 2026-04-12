"""
test_pixel_diff.py — PixelDiffAnalyzer unit testleri.

Mock görüntülerle piksel farkı hesaplama, SSIM, histogram farkı
ve bölge tespiti fonksiyonlarını test eder.

Harici API bağımlılığı yoktur — tüm görüntüler in-memory oluşturulur.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.services.analyzers.pixel_diff import (
    BoundingBox,
    DiffResult,
    ImageAligner,
    PixelDiffAnalyzer,
    ProviderComparisonResult,
    pil_to_cv2,
    cv2_to_pil,
)


# ---------------------------------------------------------------------------
# Yardımcı: Test görüntüleri oluşturma
# ---------------------------------------------------------------------------


def _create_solid_image(
    width: int = 256,
    height: int = 256,
    color: tuple = (128, 128, 128),
) -> Image.Image:
    """Tek renk düz görüntü oluşturur."""
    return Image.new("RGB", (width, height), color=color)


def _create_gradient_image(
    width: int = 256,
    height: int = 256,
) -> Image.Image:
    """Yatay gradyan görüntü oluşturur."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for x in range(width):
        val = int((x / width) * 255)
        arr[:, x, :] = val
    return Image.fromarray(arr)


def _create_image_with_rect(
    width: int = 256,
    height: int = 256,
    bg_color: tuple = (200, 200, 200),
    rect_color: tuple = (255, 0, 0),
    rect_bounds: tuple = (80, 80, 180, 180),
) -> Image.Image:
    """İçinde dikdörtgen olan görüntü oluşturur."""
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    draw.rectangle(rect_bounds, fill=rect_color)
    return img


def _create_noisy_image(
    width: int = 256,
    height: int = 256,
    seed: int = 42,
) -> Image.Image:
    """Rastgele gürültülü görüntü oluşturur."""
    rng = np.random.RandomState(seed)
    arr = rng.randint(0, 255, (height, width, 3), dtype=np.uint8)
    return Image.fromarray(arr)


# ═══════════════════════════════════════════════════════════════════════════
# PIL ↔ CV2 Dönüşüm Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestColorConversions:
    """PIL ↔ OpenCV dönüşüm testleri."""

    def test_pil_to_cv2_shape(self):
        """PIL→CV2 dönüşümü doğru boyutta numpy dizisi döndürmeli."""
        img = _create_solid_image(100, 80)
        arr = pil_to_cv2(img)
        assert arr.shape == (80, 100, 3)
        assert arr.dtype == np.uint8

    def test_cv2_to_pil_roundtrip(self):
        """PIL→CV2→PIL dönüşümü renkleri korumalı."""
        original = _create_solid_image(64, 64, color=(255, 0, 0))
        cv_arr = pil_to_cv2(original)
        recovered = cv2_to_pil(cv_arr)

        # Kırmızı piksel kontrolü
        pixel = recovered.getpixel((0, 0))
        assert pixel[0] == 255  # R
        assert pixel[1] == 0    # G
        assert pixel[2] == 0    # B

    def test_pil_to_cv2_rgba_input(self):
        """RGBA görüntü de doğru dönüşmeli."""
        img = Image.new("RGBA", (64, 64), color=(100, 150, 200, 255))
        arr = pil_to_cv2(img)
        assert arr.shape == (64, 64, 3)


# ═══════════════════════════════════════════════════════════════════════════
# ImageAligner Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestImageAligner:
    """Görüntü hizalama testleri."""

    def test_align_same_size(self):
        """Aynı boyuttaki görüntüler aynı boyutta çıkmalı."""
        aligner = ImageAligner()
        img1 = _create_solid_image(256, 256)
        img2 = _create_solid_image(256, 256)

        aligned1, aligned2 = aligner.align_tiles(img1, img2)
        assert aligned1.size == aligned2.size

    def test_align_different_sizes(self):
        """Farklı boyuttaki görüntüler aynı boyuta getirilmeli."""
        aligner = ImageAligner()
        img1 = _create_solid_image(256, 256)
        img2 = _create_solid_image(300, 280)

        aligned1, aligned2 = aligner.align_tiles(img1, img2)
        assert aligned1.size == aligned2.size

    def test_center_crop_match(self):
        """Merkez kırpma doğru boyutta sonuç vermeli."""
        import cv2
        arr1 = np.zeros((200, 200, 3), dtype=np.uint8)
        arr2 = np.zeros((300, 250, 3), dtype=np.uint8)

        cropped1, cropped2 = ImageAligner._center_crop_match(arr1, arr2)
        assert cropped1.shape[:2] == (200, 200)
        assert cropped2.shape[:2] == (200, 200)


# ═══════════════════════════════════════════════════════════════════════════
# PixelDiffAnalyzer — compute_diff Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestPixelDiffAnalyzer:
    """Piksel farkı hesaplama testleri."""

    def test_identical_images_zero_diff(self):
        """Aynı görüntüler arası fark 0 olmalı."""
        analyzer = PixelDiffAnalyzer()
        img = _create_solid_image(128, 128, (100, 100, 100))

        result = analyzer.compute_diff(img, img)

        assert isinstance(result, DiffResult)
        assert result.diff_score == 0.0
        assert result.structural_similarity > 0.99
        assert result.pixel_change_count == 0

    def test_completely_different_images(self):
        """Tamamen farklı görüntüler yüksek fark skoru vermeli."""
        analyzer = PixelDiffAnalyzer()
        img1 = _create_solid_image(128, 128, (0, 0, 0))      # Siyah
        img2 = _create_solid_image(128, 128, (255, 255, 255))  # Beyaz

        result = analyzer.compute_diff(img1, img2)

        assert result.diff_score > 50.0
        assert result.structural_similarity < 0.5
        assert result.pixel_change_count > 0

    def test_partial_difference(self):
        """Kısmi farklılık orta düzeyde skor vermeli."""
        analyzer = PixelDiffAnalyzer()
        img1 = _create_solid_image(128, 128, (128, 128, 128))
        img2 = _create_image_with_rect(
            128, 128,
            bg_color=(128, 128, 128),
            rect_color=(255, 0, 0),
            rect_bounds=(40, 40, 90, 90),
        )

        result = analyzer.compute_diff(img1, img2)

        assert 0 < result.diff_score < 100
        assert 0 < result.structural_similarity < 1.0

    def test_diff_result_structure(self):
        """DiffResult tüm beklenen alanları içermeli."""
        analyzer = PixelDiffAnalyzer()
        img = _create_gradient_image(64, 64)

        result = analyzer.compute_diff(img, img)

        assert hasattr(result, "diff_score")
        assert hasattr(result, "diff_image")
        assert hasattr(result, "changed_regions")
        assert hasattr(result, "structural_similarity")
        assert hasattr(result, "histogram_diff")
        assert hasattr(result, "pixel_change_count")
        assert hasattr(result, "total_pixels")

    def test_diff_image_is_pil(self):
        """Fark görselleştirmesi PIL Image olmalı."""
        analyzer = PixelDiffAnalyzer()
        img1 = _create_solid_image(64, 64, (0, 0, 0))
        img2 = _create_solid_image(64, 64, (200, 200, 200))

        result = analyzer.compute_diff(img1, img2)
        assert isinstance(result.diff_image, Image.Image)

    def test_histogram_diff_channels(self):
        """Histogram farkı R, G, B ve mean kanallarını içermeli."""
        analyzer = PixelDiffAnalyzer()
        img1 = _create_gradient_image(64, 64)
        img2 = _create_noisy_image(64, 64)

        result = analyzer.compute_diff(img1, img2)

        assert "red" in result.histogram_diff
        assert "green" in result.histogram_diff
        assert "blue" in result.histogram_diff
        assert "mean" in result.histogram_diff

        for val in result.histogram_diff.values():
            assert 0.0 <= val <= 1.0

    def test_ssim_range(self):
        """SSIM değeri 0-1 aralığında olmalı."""
        analyzer = PixelDiffAnalyzer()
        img1 = _create_noisy_image(64, 64, seed=1)
        img2 = _create_noisy_image(64, 64, seed=2)

        result = analyzer.compute_diff(img1, img2)
        assert 0.0 <= result.structural_similarity <= 1.0

    def test_diff_score_range(self):
        """Diff score 0-100 aralığında olmalı."""
        analyzer = PixelDiffAnalyzer()
        img1 = _create_noisy_image(64, 64, seed=10)
        img2 = _create_noisy_image(64, 64, seed=20)

        result = analyzer.compute_diff(img1, img2)
        assert 0.0 <= result.diff_score <= 100.0

    def test_changed_regions_detection(self):
        """Büyük bir fark bölgesi tespit edilmeli."""
        analyzer = PixelDiffAnalyzer(
            diff_threshold=20,
            min_contour_area=50,
        )
        img1 = _create_solid_image(256, 256, (128, 128, 128))
        img2 = _create_image_with_rect(
            256, 256,
            bg_color=(128, 128, 128),
            rect_color=(255, 0, 0),
            rect_bounds=(60, 60, 200, 200),
        )

        result = analyzer.compute_diff(img1, img2)

        assert len(result.changed_regions) > 0
        region = result.changed_regions[0]
        assert isinstance(region, BoundingBox)
        assert region.area > 0
        assert region.width > 0
        assert region.height > 0

    def test_to_dict(self):
        """DiffResult.to_dict() doğru keys içermeli."""
        analyzer = PixelDiffAnalyzer()
        img = _create_solid_image(64, 64)

        result = analyzer.compute_diff(img, img)
        d = result.to_dict()

        assert "diff_score" in d
        assert "structural_similarity" in d
        assert "histogram_diff" in d
        assert "pixel_change_count" in d
        assert "total_pixels" in d
        assert "changed_regions" in d
        assert "num_changed_regions" in d


# ═══════════════════════════════════════════════════════════════════════════
# PixelDiffAnalyzer — compare_providers Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestProviderComparison:
    """Çoklu sağlayıcı karşılaştırma testleri."""

    def test_compare_two_providers(self):
        """İki sağlayıcı karşılaştırması sonuç döndürmeli."""
        analyzer = PixelDiffAnalyzer()
        images = {
            "osm": _create_solid_image(128, 128, (100, 100, 100)),
            "google": _create_solid_image(128, 128, (150, 150, 150)),
        }

        result = analyzer.compare_providers(images)

        assert isinstance(result, ProviderComparisonResult)
        assert len(result.pair_results) == 1  # C(2,1) = 1 çift
        assert "osm" in result.providers_compared
        assert "google" in result.providers_compared
        assert 0 <= result.anomaly_score <= 100

    def test_compare_three_providers(self):
        """Üç sağlayıcı → 3 çift karşılaştırma."""
        analyzer = PixelDiffAnalyzer()
        images = {
            "osm": _create_solid_image(64, 64, (50, 50, 50)),
            "google": _create_solid_image(64, 64, (100, 100, 100)),
            "bing": _create_solid_image(64, 64, (200, 200, 200)),
        }

        result = analyzer.compare_providers(images)
        assert len(result.pair_results) == 3  # C(3,2) = 3 çift

    def test_compare_less_than_two_raises(self):
        """2'den az sağlayıcı ValueError vermeli."""
        analyzer = PixelDiffAnalyzer()

        with pytest.raises(ValueError, match="En az 2"):
            analyzer.compare_providers({"single": _create_solid_image()})

    def test_max_diff_pair(self):
        """En yüksek fark çifti doğru bulunmalı."""
        analyzer = PixelDiffAnalyzer()
        images = {
            "a": _create_solid_image(64, 64, (0, 0, 0)),
            "b": _create_solid_image(64, 64, (0, 0, 0)),
            "c": _create_solid_image(64, 64, (255, 255, 255)),
        }

        result = analyzer.compare_providers(images)

        # a vs c veya b vs c en yüksek fark olmalı
        if result.max_diff_pair:
            pair_names = {
                result.max_diff_pair.provider_a,
                result.max_diff_pair.provider_b,
            }
            assert "c" in pair_names

    def test_comparison_result_to_dict(self):
        """ProviderComparisonResult.to_dict() doğru yapıda olmalı."""
        analyzer = PixelDiffAnalyzer()
        images = {
            "osm": _create_solid_image(64, 64),
            "google": _create_solid_image(64, 64),
        }

        result = analyzer.compare_providers(images)
        d = result.to_dict()

        assert "anomaly_score" in d
        assert "summary" in d
        assert "providers_compared" in d
        assert "pair_results" in d
