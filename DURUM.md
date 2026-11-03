# DURUM — GhostBuilding

> **Ne bu dosya:** sertifika değil **envanter**. Ölçülen gerçek durum; "kapalı" ya da "yok" yazan
> satır kusur değil, kayıt. Kapanış standardı: `ScryneOS/🎯 100-Command-Center/Kapanis-Standardi.md`

**Ölçüm tarihi:** 2026-09-27 (bağımlılık ve temizlik: 2026-10-26; tarihsel kanıt: 2026-10-31; ML izi kanıtı: 2026-11-01; harita ilk boyaması ve ana parça: 2026-11-03; e-posta ve şifre sıfırlama: 2026-11-03)
**Tek cümle:** Üç resmî uydu kaynağını kalibre edilmiş tabana göre karşılaştıran motor uçtan uca
çalışıyor; referans taramasında 20 tesisin 3'ü işaretlendi, 7 kontrol konumunun hiçbiri.

## Ne çalışıyor (ölçüldü)

- **E-posta doğrulama ve şifre sıfırlama (2026-11-03):** SMTP (`smtplib`, STARTTLS/SSL/düz) ile gerçek gönderim;
  `SMTP_HOST` yoksa uygulama çalışır, açılış log'u + `/health` (`email: disabled`) + kayıt yanıtı
  (`email_delivery`) "kapalı" der, sıfırlama/yeniden gönderme 503. Bağlantılar `FRONTEND_URL` kökünden ve token
  URL **parçasında** (`#token=`): nginx/Next erişim log'una ve Referer'a düşmez. Log'a adres ve token yazılmaz.
  Token'lar ayrı `aud`'lu imzalı JWT (oturum token'ı olarak kullanılamaz); sıfırlama token'ı 30 dk, oturum
  sürümü + şifre hash parmak izine bağlı → tek kullanımlık. Sıfırlama `users.session_version`'ı artırır (göç a3),
  eski access/refresh token'ları `session_revoked` ile düşer. Unuttum/yeniden gönder yanıtı hesabın varlığını
  sızdırmaz (gönderim arka planda), IP başına saatte 5 + adres başına saatte 3 (aşımda yanıt aynı, e-posta yok).
  Ön yüz: `/auth/verify-email` (doğrulandı · zaten doğrulanmış · süresi dolmuş + tek tık yeniden gönder ·
  geçersiz · bağlantısız), `/auth/forgot-password`, `/auth/reset-password`. Doğrulama: 47 yeni test (aiosmtpd
  sahte sunucusuna gerçek SMTP konuşması; STARTTLS ve SMTPS `trustme` sertifikasıyla, doğrulama açık); uçtan uca
  Playwright turu (SQLite + gerçek Redis + sahte SMTP + `next start`): kayıt → e-postadaki bağlantı → doğrulandı,
  süresi dolmuş/geçersiz/yeniden gönder, unuttum → bağlantı → zayıf şifre reddi → sıfırlama → eski token 401,
  eski şifre 401, yeni şifre 200, aynı bağlantı ikinci kez geçersiz; log'da 0 adres, 0 token.
  Ölçülmedi: gerçek bir SMTP sağlayıcısıyla teslim (SPF/DKIM, istenmeyen klasörü) ve göçün PostGIS'li Postgres'te koşusu
  (SQL'i `alembic --sql` ile üretildi: tek `ALTER TABLE … ADD COLUMN session_version INTEGER DEFAULT 0 NOT NULL`).

- **ML bina izi kanıtı (2026-11-01):** bulgu sayfasında "Bağımsız sağlayıcı · Microsoft ML bina izleri" satırı.
  Karonun z9 dosyası diske önbelleklenir (akışla, yarım dosya bırakmadan), ML izleri karo kutusunda sayılır, OSM
  bina sayısıyla kıyaslanır; OSM ≥ 4 ve ML payı < %2 ise işaret. **Puana girmez**, taban ölçüsüyle (0/49) gösterilir.
  Tarama sonrası Celery görevi + bulgu ucu yeniden kuyruğa alma (tarihsel şeritle aynı desen); `ENABLE_ML_FOOTPRINTS`.
  Gerçek veriyle duman: Kadıköy karosu 315 ML izi (deneyde 322: deney konuma ortalanmış ~0,009° kutu, ürün gerçek z16
  karo sınırı), pay %30,6, işaret yok; ilk üretim 27 sn, 48 MB önbellek. Kore/İran gibi ML dosyası olmayan bölgeler
  `no_coverage`. Görsel tur yapılmadı (yığın bu oturumda ayağa kaldırılmadı).
- Backend: 290 test (2026-11-03; e-posta/sıfırlama +47; 2026-11-01: 243, ML izi +16), ruff temiz, `pip-audit` 0 açık (python-jose → PyJWT, Pillow 13, FastAPI 0.141). 2026-10-26: Pillow
  12.3.0'da 37 kayıt çıkmıştı → 13.0.0; ölü `api_key_provider` ve onun 11 testi kaldırıldı.
- Frontend: Next 16.4.3 / React 19 / MapLibre 6; lint (0 hata), tip kontrolü, üretim derlemesi temiz;
  `npm audit` 0 açık (2026-10-26: next 16.3.6'daki kritik RCE ve sharp/zod/follow-redirects kapandı).
- Uçtan uca: API + PostGIS + Redis + Celery worker + `next start`. Kayıt, giriş, tarama (girişli),
  bulgu paneli, bulgu sayfası, üst üste karşılaştırma, oy verme, profil.
- 24 ekran (12 rota × masaüstü/mobil): 0 yatay taşma, 0 konsol hatası.
- Kaynaklar: Esri World Imagery, MapTiler Satellite, IGN (Fransa). Sabit, dürüst User-Agent.
- Kalibrasyon: `docs/calibration-z16.json` (40 konum), `docs/calibration-z16-fransa.json` (20 konum).
- Referans taraması: `docs/reference-scan.json` (27 konum).
- **Harita ilk boyaması (2026-11-03):** kabuk (üst çubuk, paneller, kontroller, bulgu paneli) artık statik
  ön-render edilen HTML'de; MapLibre'den bağımsız bağlam `MapState.tsx`'te. Harita tuvali (`GhostMap`,
  maplibre-gl + CSS) `next/dynamic` + `ssr: false` ile ayrı parça olarak kabuktan sonra yüklenir; yerinde
  "Harita yükleniyor…" yer tutucusu durur. URL durumu (`?a=&lat=&lng=&z=`) hidrasyondan sonra
  `useSyncExternalStore` ile okunur. Worker kurulumu değişmedi (`setWorkerUrl` GhostMap modülünde, `public/maplibre/`).
  Ölçüm: Lighthouse 13.6 mobil ön ayar, `next build` + `next start`, yerel Chromium headless, 3'er koşu:
  önce perf 55/60/47, LCP 6,6/6,3/7,5 sn, TBT 1030/700/2180 ms; sonra perf 84/81/78, LCP 0,8/0,8/0,8 sn,
  TBT 640/780/1000 ms; FCP 0,9 → 0,8 sn, CLS 0. LCP öğesi iki durumda da arama kutusunun yer tutucusu.
  Ortamda dış ağ yoktu: CARTO stili ve karolar yüklenmedi, API kapalıydı (önce/sonra aynı koşul; gerçek
  ağda tuvalin karo yükü ölçülmedi). Tarayıcı doğrulaması (Playwright, CARTO stili yerel stille taklit):
  mobil + masaüstü tuval çiziliyor, worker `/maplibre/maplibre-gl-worker.mjs` 200, `onLoad` çalışıyor,
  `?a=` bulgu panelini, `?z=` zoom'u açıyor, yakınlaştır düğmesi haritayı sürüyor, konsolda worker/hidrasyon hatası yok.
- **Ana parça (2026-11-03, ikinci tur):** Sentry SDK'sı (Session Replay/rrweb dahil) `instrumentation-client.ts`
  ve `global-error.tsx`'teki statik importla DSN tanımsızken bile her sayfanın ana parçasındaydı. Artık yalnız
  `NEXT_PUBLIC_SENTRY_DSN` varken dinamik import (`src/lib/sentry-client.ts`). Bulgu paneli ve tarama bildirimi
  `next/dynamic` ile ayrı parça. Ana sayfa HTML'inin başvurduğu JS 1,11 MB → 0,69 MB. Ölçüm (aynı makine, aynı
  ağsız koşul, ana dal ile yeni derleme sırayla iç içe, Lighthouse 13.6 mobil): önce perf 90/86/90, TBT
  410/550/410 ms; sonra perf 96/91/92, TBT 220/370/350 ms. Bu makinede ana dal TBT'si PR #1'deki 640–1000 ms'den
  düşük çıktı (ilk ardışık turda 1390/540/400): mutlak sayılar makineye bağlı, karşılaştırılabilir olan fark.
  Gerçek longtask toplamı (Playwright, CPU 4x, 7 koşu medyanı): 524 → 404 ms.
  **Kalan maliyet ve sınırı:** en büyük tek görev MapLibre modülünün değerlendirilmesi (~300 ms simüle) ve
  haritanın kurulması; sonra Next yönlendirici/hidrasyon. Haritayı `requestIdleCallback` ile ertelemek denendi:
  longtask toplamı düşmedi (404 → 427 ms, gürültü içinde), uzun görev yalnız kayıyor; değişiklik alınmadı.
- Lighthouse (mobil): harita 91–96 perf (2026-11-03, yukarıda; önceki tur 78–84/100/96/100, BP 96 = kapalı API
  ve ağsız ortamın konsol hataları), keşfet 84/100/100/100 (perf/a11y/BP/SEO; Sentry ayrımı sonrası yeniden
  ölçülmedi).
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
