# DURUM — GhostBuilding

> **Ne bu dosya:** sertifika değil **envanter**. Ölçülen gerçek durum; "kapalı" ya da "yok" yazan
> satır kusur değil, kayıt. Kapanış standardı: `ScryneOS/🎯 100-Command-Center/Kapanis-Standardi.md`

**Ölçüm tarihi:** 2026-09-27 (bağımlılık ve temizlik: 2026-10-26; tarihsel kanıt: 2026-10-31; ML izi kanıtı: 2026-11-01)
**Tek cümle:** Üç resmî uydu kaynağını kalibre edilmiş tabana göre karşılaştıran motor uçtan uca
çalışıyor; referans taramasında 20 tesisin 3'ü işaretlendi, 7 kontrol konumunun hiçbiri.

## Ne çalışıyor (ölçüldü)

- **ML bina izi kanıtı (2026-11-01):** bulgu sayfasında "Bağımsız sağlayıcı · Microsoft ML bina izleri" satırı.
  Karonun z9 dosyası diske önbelleklenir (akışla, yarım dosya bırakmadan), ML izleri karo kutusunda sayılır, OSM
  bina sayısıyla kıyaslanır; OSM ≥ 4 ve ML payı < %2 ise işaret. **Puana girmez**, taban ölçüsüyle (0/49) gösterilir.
  Tarama sonrası Celery görevi + bulgu ucu yeniden kuyruğa alma (tarihsel şeritle aynı desen); `ENABLE_ML_FOOTPRINTS`.
  Gerçek veriyle duman: Kadıköy karosu 315 ML izi (deneyde 322: deney konuma ortalanmış ~0,009° kutu, ürün gerçek z16
  karo sınırı), pay %30,6, işaret yok; ilk üretim 27 sn, 48 MB önbellek. Kore/İran gibi ML dosyası olmayan bölgeler
  `no_coverage`. Görsel tur yapılmadı (yığın bu oturumda ayağa kaldırılmadı).
- Backend: 243 test (2026-11-01; ML izi +16), ruff temiz, `pip-audit` 0 açık (python-jose → PyJWT, Pillow 13, FastAPI 0.141). 2026-10-26: Pillow
  12.3.0'da 37 kayıt çıkmıştı → 13.0.0; ölü `api_key_provider` ve onun 11 testi kaldırıldı.
- Frontend: Next 16.4.3 / React 19 / MapLibre 6; lint (0 hata), tip kontrolü, üretim derlemesi temiz;
  `npm audit` 0 açık (2026-10-26: next 16.3.6'daki kritik RCE ve sharp/zod/follow-redirects kapandı).
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
- **Tarihsel değişim puanı:** ölçüldü ve ayırt edici çıkmadı (sıradan konum medyanı 95/100, tesisler daha
  düşük); puana katılmaz. Zaman serisi 2026-10-31'den beri bulguya **kanıt** olarak eklenir (bulgu sayfasında
  "Yıllar içinde" şeridi). Ayrıntı: `docs/algorithms.md` §5.
- **Staging dağıtımı:** iş akışı yalnız elle tetiklenir; sunucu yok.
- Testler SQLite ile koşar; PostGIS'e özgü sorgular yalnız uçtan uca çalıştırmada doğrulandı.

## Açık kararlar (Scryne)

- ~~Repoda LICENSE dosyası yok~~ → 2026-10-31: MIT (eski README'nin iddiasıyla aynı).
- ~~Kullanılmayan bileşenler, eski plan belgeleri, `wrangler.toml`, `api_key_provider.py`~~: 2026-10-26'da
  kaldırıldı (git geçmişinde duruyor). `TimelineChart` tarihsel değişim bağlanırsa geçmişten geri alınabilir.

## Yerel çalıştırma

```bash
docker compose up -d db redis
cd backend && alembic upgrade head
uvicorn app.main:app --port 8000          # DATABASE_URL/REDIS_URL localhost'a
celery -A app.worker.celery_app worker --pool=solo -Q default,scan,scan_batch   # Windows
cd frontend && npm run build && npx next start
```
