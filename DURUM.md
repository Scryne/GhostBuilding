# DURUM — GhostBuilding

> **Ne bu dosya:** sertifika değil **envanter**. Ölçülen gerçek durum; "kapalı" ya da "yok" yazan
> satır kusur değil, kayıt. Kapanış standardı: `ScryneOS/🎯 100-Command-Center/Kapanis-Standardi.md`

**Ölçüm tarihi:** 2026-09-27
**Tek cümle:** Üç resmî uydu kaynağını kalibre edilmiş tabana göre karşılaştıran motor uçtan uca
çalışıyor; referans taramasında 20 tesisin 3'ü işaretlendi, 7 kontrol konumunun hiçbiri.

## Ne çalışıyor (ölçüldü)

- Backend: 230 test, ruff temiz, `pip-audit` 0 açık (python-jose → PyJWT, Pillow 12, FastAPI 0.141).
- Frontend: Next 16 / React 19 / MapLibre 6; lint (0 hata), tip kontrolü, üretim derlemesi temiz;
  üretim bağımlılıklarında `npm audit` 0 açık.
- Uçtan uca: API + PostGIS + Redis + Celery worker + `next start`. Kayıt, giriş, tarama (girişli),
  bulgu paneli, bulgu sayfası, üst üste karşılaştırma, oy verme, profil.
- 24 ekran (12 rota × masaüstü/mobil): 0 yatay taşma, 0 konsol hatası.
- Kaynaklar: Esri World Imagery, MapTiler Satellite, IGN (Fransa). Sabit, dürüst User-Agent.
- Kalibrasyon: `docs/calibration-z16.json` (40 konum), `docs/calibration-z16-fransa.json` (20 konum).
- Referans taraması: `docs/reference-scan.json` (27 konum).
- Lighthouse (mobil): harita 54/100/100/100, keşfet 84/100/100/100 (perf/a11y/BP/SEO).
  Harita performansı düşük: kabuk harita bağlamıyla istemcide yükleniyor (LCP 6,7 sn).
- CI: backend (ruff, pytest, pip-audit), frontend (lint, tip, build, npm audit), Docker imajları.

## Kapalı / yok (bilerek)

- **Bina dedektörü** (hayalet bina / gizli yapı): hava görüntüsü için eğitilmiş ağırlık yok, kapalı.
  `requirements-detector.txt` + `BUILDING_DETECTOR_WEIGHTS` ile açılır.
- **Tarihsel değişim:** `WaybackFetcher` + `TimeSeriesAnalyzer` yazılı, tarama akışına bağlı değil.
- **Staging dağıtımı:** iş akışı yalnız elle tetiklenir; sunucu yok.
- Testler SQLite ile koşar; PostGIS'e özgü sorgular yalnız uçtan uca çalıştırmada doğrulandı.

## Açık kararlar (Scryne)

- Repoda LICENSE dosyası yok (eski README "MIT" diyordu; yeni README lisans iddiası taşımıyor).
- Kullanılmayan bileşenler: `FeaturedAnomalies`, `LayerControls`, `TimelineChart`, `SearchBar`.
  Silinsin mi?
- `PORTFOLYO-BRIFING.md`, `proje_plani.txt`, `GhostBuilding_Proje_Plani.docx`, `wrangler.toml`
  (Cloudflare yapılandırması, kullanılmıyor) repoda duruyor.
- `app/utils/api_key_provider.py` ölü kod.

## Yerel çalıştırma

```bash
docker compose up -d db redis
cd backend && alembic upgrade head
uvicorn app.main:app --port 8000          # DATABASE_URL/REDIS_URL localhost'a
celery -A app.worker.celery_app worker --pool=solo -Q default,scan,scan_batch   # Windows
cd frontend && npm run build && npx next start
```
