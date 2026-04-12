"""
test_tile_coordinates.py — Tile koordinat dönüşüm testleri.

lat_lng_to_tile, tile_to_lat_lng ve tile_to_quadkey fonksiyonlarının
doğruluğunu bilinen değerlerle test eder.

Harici API bağımlılığı yoktur.
"""

from __future__ import annotations

import math

import pytest

from app.services.tile_fetcher import (
    lat_lng_to_tile,
    tile_to_lat_lng,
    tile_to_quadkey,
)


# ═══════════════════════════════════════════════════════════════════════════
# lat_lng_to_tile Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestLatLngToTile:
    """Enlem/boylam → tile koordinat dönüşüm testleri."""

    def test_istanbul_zoom_15(self):
        """İstanbul (41.0082, 28.9784) zoom 15 → bilinen tile."""
        x, y, z = lat_lng_to_tile(41.0082, 28.9784, 15)

        assert z == 15
        assert isinstance(x, int)
        assert isinstance(y, int)
        assert x == 19021
        assert y == 11826

    def test_origin_zoom_0(self):
        """(0, 0) zoom 0 → (0, 0, 0)."""
        x, y, z = lat_lng_to_tile(0.0, 0.0, 0)

        assert (x, y, z) == (0, 0, 0)

    def test_london_zoom_10(self):
        """Londra (51.5074, -0.1278) zoom 10 → makul tile."""
        x, y, z = lat_lng_to_tile(51.5074, -0.1278, 10)

        assert z == 10
        # Zoom 10'da toplam 1024 tile/eksen
        assert 0 <= x < 1024
        assert 0 <= y < 1024
        # Londra kuzey yarımkürede → y merkezden düşük olmalı
        assert y < 512

    def test_equator_prime_meridian(self):
        """Ekvator/başlangıç meridyeni zoom 1."""
        x, y, z = lat_lng_to_tile(0.0, 0.0, 1)

        assert z == 1
        # Zoom 1: 2×2 grid
        assert x == 1  # Sağ yarı (boylam 0° pozitif tarafta)
        assert y == 1  # Alt yarı (enlem 0° merkez)

    def test_negative_longitude(self):
        """Batı boylamı doğru dönüşmeli."""
        x, y, z = lat_lng_to_tile(40.7128, -74.0060, 10)  # New York

        assert z == 10
        assert 0 <= x < 1024
        # Batı boylamı → x merkezden düşük olmalı
        assert x < 512

    def test_negative_latitude(self):
        """Güney enlemi doğru dönüşmeli."""
        x, y, z = lat_lng_to_tile(-33.8688, 151.2093, 10)  # Sydney

        assert z == 10
        assert 0 <= y < 1024
        # Güney yarımküre → y merkezden büyük olmalı
        assert y > 512

    def test_max_zoom(self):
        """Zoom 20 çalışmalı (en detaylı)."""
        x, y, z = lat_lng_to_tile(41.0082, 28.9784, 20)

        assert z == 20
        max_n = 2 ** 20
        assert 0 <= x < max_n
        assert 0 <= y < max_n

    def test_invalid_latitude_raises(self):
        """Geçersiz enlem ValueError vermeli."""
        with pytest.raises(ValueError, match="Geçersiz enlem"):
            lat_lng_to_tile(90.0, 0.0, 10)  # 90 > 85.0511

    def test_invalid_longitude_raises(self):
        """Geçersiz boylam ValueError vermeli."""
        with pytest.raises(ValueError, match="Geçersiz boylam"):
            lat_lng_to_tile(0.0, 200.0, 10)

    def test_invalid_zoom_raises(self):
        """Geçersiz zoom ValueError vermeli."""
        with pytest.raises(ValueError, match="Geçersiz zoom"):
            lat_lng_to_tile(0.0, 0.0, 25)

    def test_boundary_latitude(self):
        """Sınır enlem değerleri çalışmalı."""
        # En kuzey sınır
        x1, y1, z1 = lat_lng_to_tile(85.0511, 0.0, 5)
        assert y1 == 0  # En üst satır

        # En güney sınır
        x2, y2, z2 = lat_lng_to_tile(-85.0511, 0.0, 5)
        assert y2 == 31  # En alt satır (2^5 - 1)


# ═══════════════════════════════════════════════════════════════════════════
# tile_to_lat_lng Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestTileToLatLng:
    """Tile koordinat → enlem/boylam dönüşüm testleri."""

    def test_origin_tile(self):
        """Tile (0, 0, 0) → (-180, 85.0511) civarı (sol-üst köşe)."""
        lat, lng = tile_to_lat_lng(0, 0, 0)

        # Zoom 0: tek tile, sol-üst köşe
        assert abs(lng - (-180.0)) < 0.01
        assert lat > 80  # Kuzey sınır yakını

    def test_roundtrip_istanbul(self):
        """lat→tile→lat roundtrip yakınsak olmalı."""
        original_lat, original_lng = 41.0082, 28.9784
        x, y, z = lat_lng_to_tile(original_lat, original_lng, 15)
        recovered_lat, recovered_lng = tile_to_lat_lng(x, y, z)

        # Tile sol-üst köşesi — orijinalden biraz farklı olabilir
        # ancak aynı tile içinde olmalı
        lat_error = abs(recovered_lat - original_lat)
        lng_error = abs(recovered_lng - original_lng)

        # Zoom 15'te bir tile ~0.01° kaplar
        assert lat_error < 0.02
        assert lng_error < 0.02

    def test_invalid_tile_raises(self):
        """Geçersiz tile koordinatı ValueError vermeli."""
        with pytest.raises(ValueError, match="Geçersiz tile"):
            tile_to_lat_lng(100, 0, 1)  # x > 2^1 - 1 = 1

    def test_zoom_1_center(self):
        """Zoom 1 merkez tile (1, 1) → (0°, 0°) civarı."""
        lat, lng = tile_to_lat_lng(1, 1, 1)

        assert abs(lng) < 1.0  # 0° boylam civarı
        assert abs(lat) < 1.0  # 0° enlem civarı

    def test_multiple_zooms_consistent(self):
        """Aynı nokta farklı zoomlarda tutarlı olmalı."""
        lat10, lng10 = tile_to_lat_lng(512, 340, 10)

        # Zoom 11'de aynı bölge 2× daha detaylı
        lat11, lng11 = tile_to_lat_lng(1024, 680, 11)

        assert abs(lat10 - lat11) < 0.1
        assert abs(lng10 - lng11) < 0.1


# ═══════════════════════════════════════════════════════════════════════════
# tile_to_quadkey Testleri
# ═══════════════════════════════════════════════════════════════════════════


class TestTileToQuadkey:
    """Tile → Bing Maps quadkey dönüşüm testleri."""

    def test_known_quadkey(self):
        """Bilinen tile → quadkey eşleşmesi."""
        # (3, 5, 3) → "213" (docstring'ten)
        qk = tile_to_quadkey(3, 5, 3)
        assert qk == "213"

    def test_quadkey_length(self):
        """Quadkey uzunluğu zoom seviyesine eşit olmalı."""
        for z in range(1, 10):
            qk = tile_to_quadkey(0, 0, z)
            assert len(qk) == z

    def test_quadkey_valid_digits(self):
        """Quadkey sadece 0, 1, 2, 3 rakamlarını içermeli."""
        qk = tile_to_quadkey(15, 10, 5)
        valid_digits = set("0123")
        for ch in qk:
            assert ch in valid_digits

    def test_zoom_0_raises(self):
        """Zoom 0 ValueError vermeli (quadkey min zoom 1)."""
        with pytest.raises(ValueError, match="zoom ≥ 1"):
            tile_to_quadkey(0, 0, 0)

    def test_top_left_is_zeros(self):
        """Sol-üst tile (0, 0) quadkey tüm 0 olmalı."""
        qk = tile_to_quadkey(0, 0, 5)
        assert qk == "00000"

    def test_different_tiles_different_keys(self):
        """Farklı tile'lar farklı quadkey'ler üretmeli."""
        qk1 = tile_to_quadkey(5, 10, 5)
        qk2 = tile_to_quadkey(6, 10, 5)
        qk3 = tile_to_quadkey(5, 11, 5)

        assert qk1 != qk2
        assert qk1 != qk3
        assert qk2 != qk3
