"""
Microsoft ML bina izi kanıtı (docs/spike-bina-izleri.md, Deneme 2): saf karo/quadkey/sayım/kural
yardımcıları, sahte HTTP ve OSM ile kanıt üretimi (ağa çıkmadan), bulgu ucunun kuyruk davranışı.
"""

from __future__ import annotations

import gzip
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import ml_footprints_service as mlf
from tests.conftest import TestAnomaly


# ═══ saf yardımcılar ═══════════════════════════════════════════════════════════


def test_quadkey_bing_ornegi_ve_ust_karo():
    # Bing Maps Tile System belgesindeki örnek: seviye 3, karo (3, 5) → "213".
    assert mlf.quadkey(3, 5, 3) == "213"
    # z16 karonun z9 atası: x, y 7 bit sağa kayar.
    assert mlf.parent_quadkey(3 << 7, 5 << 7, 10, parent_zoom=3) == "213"
    assert len(mlf.parent_quadkey(*mlf.lat_lng_to_tile(48.3, -4.5, 16), 16)) == 9


def test_karo_kutusu_konumu_icerir():
    lat, lng = 40.9903, 29.029
    x, y = mlf.lat_lng_to_tile(lat, lng, 16)
    south, west, north, east = mlf.tile_bbox(x, y, 16)
    assert south < lat < north and west < lng < east
    assert 0 < north - south < 0.01 and 0 < east - west < 0.01


def _ozellik(lng: float, lat: float, d: float = 0.0001, cok: bool = False) -> str:
    halka = [[lng, lat], [lng + d, lat], [lng + d, lat + d], [lng, lat + d], [lng, lat]]
    geom = (
        {"type": "MultiPolygon", "coordinates": [[halka]]}
        if cok
        else {"type": "Polygon", "coordinates": [halka]}
    )
    return json.dumps({"type": "Feature", "properties": {}, "geometry": geom})


def test_kutudaki_izleri_sayar_bozuk_satiri_atlar():
    bbox = (10.0, 20.0, 10.01, 20.01)
    satirlar = [
        _ozellik(20.002, 10.002),
        _ozellik(20.005, 10.005, cok=True),  # MultiPolygon da sayılır
        _ozellik(20.02, 10.002),  # kutu dışı (doğu)
        _ozellik(20.009999, 10.009999, d=0.01),  # köşeden taşan: ortalama dışarıda
        "{bozuk json",
        json.dumps({"type": "Feature", "geometry": None}),
        "",
    ]
    assert mlf.count_in_bbox(satirlar, bbox) == 2


@pytest.mark.parametrize(
    "osm, ml, pay, isaret",
    [
        (371, 1, 1 / 372, True),  # Brest askeri liman (deneyde işaretli)
        (713, 322, 322 / 1035, False),  # Kadıköy (taban)
        (4, 0, 0.0, True),  # eşik: tam 4 OSM binası
        (3, 0, 0.0, False),  # OSM eşiğin altında
        (98, 2, 0.02, False),  # pay tam %2: işaret değil (< kuralı)
        (0, 0, None, False),  # ikisi de boş: tanımsız
    ],
)
def test_karar(osm, ml, pay, isaret):
    k = mlf.karar(osm, ml)
    assert k.isaret is isaret
    assert (k.ml_pay is None and pay is None) or k.ml_pay == pytest.approx(pay)


def test_quadkey_birden_cok_parca():
    csv = (
        "Location,QuadKey,Url,Size,UploadDate\n"
        "France,120210233,https://x/a.csv.gz,10MB,2026-02-23\n"
        "Spain,120210233,https://x/b.csv.gz,1MB,2026-02-23\n"
        "France,120210232,https://x/c.csv.gz,5MB,2026-02-23\n"
    )
    assert mlf.urls_for_quadkey(csv, "120210233") == ["https://x/a.csv.gz", "https://x/b.csv.gz"]
    assert mlf.urls_for_quadkey(csv, "999") == []


# ═══ kanıt üretimi (sahte ağ) ═══════════════════════════════════════════════════


class _Yanit:
    def __init__(self, veri: bytes):
        self._veri = veri

    def raise_for_status(self):
        return None

    async def aiter_bytes(self, _boy: int):
        yield self._veri


class _Akis:
    def __init__(self, veri: bytes):
        self._veri = veri

    async def __aenter__(self):
        return _Yanit(self._veri)

    async def __aexit__(self, *_):
        return None


class _SahteHttp:
    def __init__(self, dosyalar: dict[str, bytes]):
        self.dosyalar = dosyalar
        self.istekler: list[str] = []

    def stream(self, _yontem: str, url: str):
        self.istekler.append(url)
        return _Akis(self.dosyalar[url])


@pytest.mark.asyncio
async def test_kanit_uretimi_ve_onbellek(tmp_path, monkeypatch):
    monkeypatch.setattr(mlf.settings, "STORAGE_ROOT", str(tmp_path))
    lat, lng = 48.383, -4.495
    x, y = mlf.lat_lng_to_tile(lat, lng, 16)
    s, w, n, e = mlf.tile_bbox(x, y, 16)
    qk = mlf.parent_quadkey(x, y, 16)
    icerde = _ozellik((w + e) / 2, (s + n) / 2, d=0.00001)
    disarda = _ozellik(e + 0.01, n + 0.01)
    gz = gzip.compress(("\n".join([icerde, disarda]) + "\n").encode())
    dizin = f"Location,QuadKey,Url,Size,UploadDate\nFrance,{qk},https://ml/f.csv.gz,1KB,2026-02-23\n"
    http = _SahteHttp({mlf.DATASET_INDEX_URL: dizin.encode(), "https://ml/f.csv.gz": gz})
    gelen: list[tuple] = []

    async def osm(bbox):
        gelen.append(bbox)
        return 371

    kanit = await mlf.build_ml_evidence(lat, lng, 16, http_client=http, osm_counter=osm)
    assert (kanit["status"], kanit["osm"], kanit["ml"], kanit["flag"]) == ("ready", 371, 1, True)
    assert kanit["quadkey"] == qk and kanit["ml_share"] == round(1 / 372, 4)
    assert gelen == [(s, w, n, e)]
    # İkinci üretim diskten okur: ağa yeniden çıkmaz.
    await mlf.build_ml_evidence(lat, lng, 16, http_client=http, osm_counter=osm)
    assert http.istekler == [mlf.DATASET_INDEX_URL, "https://ml/f.csv.gz"]
    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.asyncio
async def test_kapsama_yoksa_no_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(mlf.settings, "STORAGE_ROOT", str(tmp_path))
    http = _SahteHttp({mlf.DATASET_INDEX_URL: b"Location,QuadKey,Url,Size,UploadDate\n"})

    async def osm(_bbox):
        raise AssertionError("kapsama yoksa OSM sorgulanmamalı")

    kanit = await mlf.build_ml_evidence(37.5, 127.0, 16, http_client=http, osm_counter=osm)
    assert kanit["status"] == "no_coverage" and kanit["flag"] is False and kanit["ml"] is None


# ═══ GET /anomalies/{id}/ml-footprints ══════════════════════════════════════════


async def _anomaly(db: AsyncSession, meta: dict) -> TestAnomaly:
    anomaly = TestAnomaly(
        id=str(uuid.uuid4()), lat=48.383, lng=-4.495, category="CENSORED_AREA",
        confidence_score=61.0, title="ML izi testi", status="PENDING",
        source_providers=["esri", "maptiler"], detection_methods=["blur_detection"], meta_data=meta,
    )  # fmt: skip
    db.add(anomaly)
    await db.commit()
    return anomaly


@pytest.mark.asyncio
async def test_uc_bir_kez_kuyruga_atar(client: AsyncClient, db_session: AsyncSession):
    anomaly = await _anomaly(db_session, {})
    task = MagicMock()
    with patch("app.tasks.scan_tasks.build_anomaly_ml_footprints", task):
        first = await client.get(f"/api/v1/anomalies/{anomaly.id}/ml-footprints")
        second = await client.get(f"/api/v1/anomalies/{anomaly.id}/ml-footprints")
    assert first.status_code == 200 and first.json()["status"] == "pending"
    assert second.json()["status"] == "pending"
    task.delay.assert_called_once_with(str(anomaly.id))


@pytest.mark.asyncio
async def test_uc_hazir_kaniti_dondurur(client: AsyncClient, db_session: AsyncSession):
    hazir = {
        "status": "ready", "source": mlf.ML_SOURCE, "zoom": 16, "quadkey": "031313131",
        "generated_at": datetime.now(timezone.utc).isoformat(), "osm": 371, "ml": 1,
        "ml_share": 0.0027, "flag": True, "rule": {"osm_min": 4, "ml_share_max": 0.02},
        "baseline": {"false_alarms": 0, "baseline_n": 49, "reference_hits": 5, "reference_n": 12},
    }  # fmt: skip
    anomaly = await _anomaly(db_session, {"ml_footprints": hazir})
    task = MagicMock()
    with patch("app.tasks.scan_tasks.build_anomaly_ml_footprints", task):
        r = await client.get(f"/api/v1/anomalies/{anomaly.id}/ml-footprints")
    body = r.json()
    assert (body["status"], body["osm"], body["ml"], body["flag"]) == ("ready", 371, 1, True)
    assert body["baseline"]["baseline_n"] == 49
    task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_uc_basarisizi_bir_saat_sonra_yeniden_dener(client: AsyncClient, db_session: AsyncSession):
    eski = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    anomaly = await _anomaly(db_session, {"ml_footprints": {"status": "failed", "generated_at": eski}})
    task = MagicMock()
    with patch("app.tasks.scan_tasks.build_anomaly_ml_footprints", task):
        await client.get(f"/api/v1/anomalies/{anomaly.id}/ml-footprints")
    task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_uc_kapaliyken_disabled_ve_404(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    anomaly = await _anomaly(db_session, {})
    monkeypatch.setattr("app.routers.anomalies.settings.ENABLE_ML_FOOTPRINTS", False)
    r = await client.get(f"/api/v1/anomalies/{anomaly.id}/ml-footprints")
    assert r.json()["status"] == "disabled"
    r = await client.get(f"/api/v1/anomalies/{uuid.uuid4()}/ml-footprints")
    assert r.status_code == 404
