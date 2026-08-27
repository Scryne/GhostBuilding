# GhostBuilding — Portföy Brifingi

> Bu dosya `docs/brifing-prompt.md` içindeki çıkarma promptuna göre üretildi.
> Amaç pazarlama metni değil, veri çıkarmadır.
>
> **Kanıt etiketleri:**
> `[ÖLÇÜLDÜ]` = bu oturumda komut çalıştırılıp çıktısı görüldü.
> `[KODDAN]` = kaynak koda bakılarak çıkarıldı, çalıştırılmadı.
> `[GIT]` = commit geçmişinden okundu.
> `BİLİNMİYOR` = koddan bilinemez.
>
> Ölçüm tarihi: 2026-08-08. Ölçülen commit: `2e94b6d` (HEAD, main).

---

## 1. Künye

**Ne yapar**
Aynı koordinatın farklı harita sağlayıcılarındaki (OSM, Google, Yandex, Bing) uydu tile'larını
indirip birbiriyle ve OpenStreetMap bina verisiyle karşılaştırarak sansürlenmiş, eksik veya
tutarsız bölgeleri işaretleyen; bulguları harita üzerinde topluluk oyuna açan bir web uygulaması.

**Kimin için**
README ve kod içi metinler OSINT araştırmacısı, gazeteci ve akademik araştırmacıyı hedefliyor
(`README.md:105` — "educational, research, and journalistic purposes"). Kodda kurumsal müşteri,
faturalandırma, çok kiracılılık (multi-tenancy) veya kota yönetimi yok — ürün açık topluluk aracı
olarak tasarlanmış. `[KODDAN]`

**Çalışma dönemi** `[GIT]`
- İlk commit: `198286f` — 2026-04-12 15:02
- Son commit: `2e94b6d` — 2026-08-08 19:35

Commit yoğunluğu iki yığına ayrılıyor, aralarında **~4 aylık boşluk** var:

| Dönem | Commit | Not |
| --- | --- | --- |
| 2026-04-12 15:02 → 2026-04-13 09:11 | 9 | ~18 saatte tüm faz teslimi |
| 2026-04-13 → 2026-08-08 | 0 | ara verilmiş |
| 2026-08-08 19:35 | 1 | tek commit ile dönüş |

Yani proje takvimde 4 ay sürmüş görünüyor ama commit kaydı iki oturumluk çalışma gösteriyor.

**Rol** `[GIT]` — Tek geliştirici.
`git shortlog -sn --all` iki isim döndürüyor ama ikisi de aynı kişi:

```
9  Your Name <you@example.com>     ← git config yapılmamış, varsayılan kimlik
1  Scryne <scryne00@gmail.com>
```

İlk 9 commit yapılandırılmamış varsayılan git kimliğiyle atılmış. Dış katkıda bulunan yok.

**Yığın** — mimariyi belirleyen 8 madde `[KODDAN: backend/requirements.txt, frontend/package.json]`

1. **FastAPI 0.110 + SQLAlchemy 2.0 async + asyncpg** — uçtan uca asenkron REST API
2. **PostgreSQL + PostGIS 16-3.4** — `Geometry(Point, 4326)` sütunu ve GIST indeksi ile konum sorguları (`backend/app/models/anomaly.py:20`)
3. **Celery 5.3 + Redis 7** — arka plan tarama kuyruğu, tile önbelleği, oran sınırlama; 3 ayrı worker kuyruğu (`default`, `scan`, `maintenance`)
4. **OpenCV + scikit-image + NumPy** — Laplacian varyans, FFT frekans analizi, SSIM, ORB feature matching
5. **Ultralytics YOLOv8n** — uydu görüntüsünden bina tespiti (`geospatial_analyzer.py:35`, `yolov8n.pt`)
6. **Next.js 14 App Router + TypeScript + Tailwind**
7. **MapLibre GL + react-map-gl** — vektör harita katmanı, clustering
8. **Docker Compose + nginx**; gözlemlenebilirlik için Prometheus + Grafana + Sentry + structlog

**Satır ve dosya sayısı** `[ÖLÇÜLDÜ]`
Sayım yalnızca git tarafından izlenen dosyalar üzerinde; `node_modules`, `.next`, `__pycache__`,
`package-lock.json`, `.docx`, font ve ikon dosyaları hariç.

| | Dosya | Satır |
| --- | --- | --- |
| Backend (Python) | 62 | 21.190 |
| Frontend (tsx/ts/css) | 54 | 10.621 |
| Yapılandırma + doküman (yml/md/json/conf/toml/ini) | 44 | 2.617 |
| **Toplam** | **160** | **34.428** |

Backend'in 3.553 satırı test (`backend/tests/`), 17.202 satırı uygulama kodu (`backend/app/`).

**Commit sayısı** — 10 `[GIT: git rev-list --count HEAD]`

34.428 satırın 10 commit'e dağılması dosya başına değil commit başına ~3.400 satır demek;
bu, aşağıda 5. bölümde ele alınan "faz teslimi" çalışma biçiminin doğrudan sonucu.

---

## 2. Durum

## `geliştirme`

Gerekçe: Uygulama ayağa kalkıyor ve API doğru cevap veriyor, ama temiz bir kurulumda iki temel
akış çalışmıyor — kullanıcı kaydı ve demo veri yükleme. Bu yüzden `GA öncesi` değil; öte yandan
analiz hattı, kuyruk, kimlik doğrulama ve arayüz baştan sona yazılmış olduğu için `prototip` de
değil.

Ölçülebilir ayrıntı — hepsi bu oturumda çalıştırıldı:

| Kontrol | Sonuç | Kanıt |
| --- | --- | --- |
| Backend test paketi | **205/205 geçiyor**, 8,08 sn | `pytest -q` (Docker içinde) `[ÖLÇÜLDÜ]` |
| `alembic upgrade head` | Başarılı | temiz PostGIS 16-3.4 konteynerinde `[ÖLÇÜLDÜ]` |
| `GET /api/v1/health` | `200`, `"status":"degraded"` (celery worker yok) | curl `[ÖLÇÜLDÜ]` |
| `GET /api/v1/anomalies/` ve `/stats` | `200`, boş sonuç | curl `[ÖLÇÜLDÜ]` |
| `POST /api/v1/auth/register` | **`500`** — `column users.hashed_password does not exist` | curl + konteyner logu `[ÖLÇÜLDÜ]` |
| `python scripts/seed_data.py` | **0 satır yazıyor**, hata yutuluyor | `[ÖLÇÜLDÜ]` |
| Frontend `next build` (prod) | **Başarısız** — 7 ESLint hatası | `npm run build` `[ÖLÇÜLDÜ]` |

Ayrıca `CHANGELOG.md` bu projeyi `v0.1.0 - production ready` olarak etiketliyor
(commit `9416305`). Yukarıdaki ölçümler bu etiketi desteklemiyor; brifingde ölçüm esas alındı.

---

## 3. Problem

### README'nin anlattığı problem

Büyük harita sağlayıcıları aynı coğrafyayı farklı gösteriyor: bir bina OSM'de kayıtlı ama uydu
görüntüsünde yok; bir tesis uydu görüntüsünde var ama hiçbir haritada yok; bazı bölgeler
sistematik olarak bulanıklaştırılmış. Bu farklar tek tek göze çarpmıyor çünkü kimse aynı
koordinatı dört sağlayıcıda yan yana koymuyor. `README.md:30-36`

### Kodun doğruladığı kısım

Karşılaştırma altyapısı gerçekten var ve README'yi doğruluyor:
- `tile_fetcher.py` — 4 sağlayıcıdan eşzamanlı tile indirme, sağlayıcı başına 10 istek/sn token-bucket, Redis'te 24 saat önbellek
- `pixel_diff.py` — ORB ile hizalama, SSIM, histogram farkı, değişim bölgesi kutuları
- `blur_detector.py` — Laplacian varyans + FFT ile "kasıtlı sansür mü, doğal düşük çözünürlük mü" ayrımı
- `anomaly_engine.py` — beş bileşeni ağırlıklı toplayan skor (`0.30` sağlayıcı uyuşmazlığı, `0.25` piksel farkı, `0.20` bulanıklık, `0.15` mekansal uyuşmazlık, `0.10` tarihsel değişim)

### Ayrışma: README ile kodun uyuşmadığı yerler

`CHANGELOG.md` üç şey iddia ediyor ki kodda karşılığı yok — **README/CHANGELOG güncel değil,
kod güncel:**

| İddia | Kaynak | Kodda durumu |
| --- | --- | --- |
| "Apple Maps tile parsing is currently experimental" | `CHANGELOG.md:22` | **Kodda hiç Apple Maps yok.** `grep -ri apple` yalnızca User-Agent dizelerinde `AppleWebKit` buluyor `[ÖLÇÜLDÜ]` |
| "Automated Alerts: Email and dashboard notification architecture" | `CHANGELOG.md:17` | **Bildirim sistemi yok.** SMTP tek satırlık bir TODO: `auth_service.py:438` |
| "Complete YOLOv8 integration" gelecek yol haritasında | `CHANGELOG.md:26` | YOLOv8 kodu yazılmış (`geospatial_analyzer.py:550-670`) — yol haritası kodun gerisinde |

Ayrıca "Tarihsel değişim" bileşeni: `time_series.py` 1.295 satır yazılmış ama motor onu hiç
çağırmıyor. `anomaly_engine.py:747` skoru sabit sıfırlıyor:

```python
# Wayback Machine analizi gelecekte eklenecek
breakdown.historical_change_score = 0.0
```

Sonuç: ağırlıkların `0.10`'u ölü, ulaşılabilir azami güven skoru **90**, 100 değil. `[KODDAN]`

---

## 4. Sistem

### Ana bileşenler ve sorumluluk sınırları

| Bileşen | Sorumluluk | Sınır ihlali |
| --- | --- | --- |
| `tile_fetcher.py` (861 sat.) | 4 sağlayıcıdan tile indirme, quadkey dönüşümü, önbellek, retry, oran sınırı | — |
| `osm_collector.py` (925 sat.) | Overpass API'den bina poligonları | — |
| `satellite_fetcher.py` (897 sat.) | Sentinel Hub → NASA GIBS fallback | — |
| `pixel_diff.py` (1.253 sat.) | Hizalama + SSIM + fark görselleştirme | Görselleştirme (`DiffVisualizer`) analizle aynı modülde |
| `blur_detector.py` (1.407 sat.) | Bulanıklık/sansür tespiti | Aynı şekilde `BlurVisualizer` içeride |
| `geospatial_analyzer.py` (1.573 sat.) | OSM ↔ uydu eşleştirme + YOLO bina tespiti | **Çok geniş.** Model yükleme, IoU/NMS, coğrafi eşleştirme ve anomali sınıflandırma tek dosyada |
| `anomaly_engine.py` (1.210 sat.) | Tüm analizleri sıraya koyma, skorlama, sınıflandırma, **DB'ye yazma** | **Sınır ihlali var.** Orkestrasyon ile kalıcılık aynı sınıfta (`_save_to_database`, `_save_provider_image`) |
| `routers/anomalies.py` (1.297 sat.) | Liste, detay, istatistik, dışa aktarma, tarama başlatma, tile karşılaştırma | **Çok geniş.** 7 uç nokta, biri (`/tiles/compare`) doğrudan `TileFetcher` çağırıyor — servis katmanını atlıyor |

Bir bileşen "her şeyi yapıyorsa olduğu gibi yaz" talimatı gereği: `anomaly_engine.py` ve
`routers/anomalies.py` bu tarife uyuyor.

### Veri akışı

**Girdi nereden geliyor**
1. Kullanıcı haritada bir noktaya tarama başlatıyor → `POST /api/v1/anomalies/scan`
2. Ya da Celery Beat zamanlanmış `scan_high_priority_regions` görevini tetikliyor (`scan_tasks.py:765`)
3. Dış kaynaklar: 4 harita tile sunucusu, Overpass API, Nominatim, Sentinel Hub / NASA GIBS

**Nerede duruyor**
- Tile ham baytları → Redis, 24 saat TTL (`TILE_CACHE_TTL = 86_400`)
- Üretilen görseller → disk (`STORAGE_ROOT="data"`) veya MinIO (`MINIO_BUCKET="satellite-images"`)
- Anomaliler → PostGIS `anomalies` tablosu, `geom` sütunu GIST indeksli
- Tarama ilerlemesi → Redis, `scan_jobs` tablosuna da yazılıyor
- Güven skoru `MIN_CONFIDENCE_THRESHOLD = 40.0` altındaysa **DB'ye hiç yazılmıyor** (`anomaly_engine.py:49`)

**Nasıl çıkıyor**
`GET /anomalies/` (sayfalı), `/stats`, `/{id}`, `/export`; frontend SWR ile çekiyor;
`/api/og` OpenGraph görseli üretiyor; `sitemap.ts` + `robots.ts` SEO tarafını kuruyor.

### Dış bağımlılıklar

| Bağımlılık | Ne için | Anahtar gerekli mi |
| --- | --- | --- |
| PostgreSQL + PostGIS | Konum verisi | — |
| Redis | Celery broker, tile önbelleği, oran sınırı, e-posta doğrulama token'ı | — |
| OSM / Google / Yandex / Bing tile sunucuları | Karşılaştırılacak görüntüler | Hayır (resmi API kullanılmıyor — bkz. 9. bölüm) |
| Overpass API (2 uç nokta) | OSM bina poligonları | Hayır |
| Nominatim | Ters geokodlama, arama | Hayır |
| Sentinel Hub | Sentinel-2 uydu görüntüsü (10 m/px) | **Evet** — `SENTINEL_HUB_CLIENT_ID/SECRET` |
| NASA GIBS WMTS | Anahtarsız fallback, MODIS Terra **250 m/px** | Hayır |
| Sentry / Prometheus / Grafana | Hata ve metrik toplama | Sentry için DSN |

### Diyagram için önerilen kutular — 9 adet

```
1. Next.js Arayüz (harita + keşif)
2. nginx (ters proxy, :80)
3. FastAPI  /api/v1
4. Celery Worker + Beat
5. Anomali Motoru (piksel · bulanıklık · mekansal)
6. PostgreSQL + PostGIS
7. Redis (önbellek · kuyruk · oran sınırı)
8. Harita Tile Sağlayıcıları (OSM · Google · Yandex · Bing)
9. Uydu & Vektör Kaynakları (Sentinel Hub → NASA GIBS · Overpass · Nominatim)
```

Akış yönleri: 1 → 2 → 3; 3 → 4 (kuyruk); 4 → 5; 5 → 8, 9 (dış çağrı); 5 → 6, 7 (yazma);
3 → 6, 7 (okuma).

---

## 5. Kritik kararlar

### Karar 1 — Testler gerçek veritabanına değil, kopya modellerle SQLite'a koşuyor

- **Seçim:** `backend/tests/conftest.py` uygulamanın ORM sınıflarını `unittest.mock.patch` ile
  kendi yazdığı `TestUser` / `TestAnomaly` / `TestScanJob` sınıflarıyla değiştiriyor
  (`conftest.py:186-200`) ve SQLite in-memory üzerinde koşuyor. PostGIS `Geometry` sütunu
  test modellerinden çıkarılmış: *"geom sütunu yok — PostGIS gerektirdiği için test'lerde kaldırıldı"*
  (`conftest.py:72`).
- **Alternatif:** CI service container ya da `testcontainers` ile gerçek PostGIS örneği kaldırmak.
  `docker-compose.yml` zaten `postgis/postgis:16-3.4` imajını tanımlıyor; CI'da service olarak
  bağlamak birkaç satırlık iş.
- **Gerekçe:** Test paketi hiçbir altyapı olmadan, 8 saniyede koşuyor `[ÖLÇÜLDÜ]`. `ci.yml`
  yorumunda niyet açıkça yazılı: *"Exclude DB tests strictly if no DB available"* (`ci.yml:36`).
- **Bedel:** Şema hataları test tarafından görülemiyor. **Ölçülen sonuç:** 205 test geçerken
  temiz bir migration üzerine yapılan `POST /auth/register` `500` veriyor, çünkü migration'daki
  `users` tablosunda `hashed_password` kolonu yok. 16 auth testi ve 99 güvenlik testi bu hatayı
  yakalayamıyor — çünkü hepsi kolonun var olduğu kopya modeli test ediyor. Ayrıntı 6. bölümde.

### Karar 2 — Uydu görüntüsünde anahtarsız fallback olarak MODIS (250 m/piksel)

- **Seçim:** `satellite_fetcher.py` önce Sentinel Hub'ı deniyor, başarısız olursa NASA GIBS'e
  düşüyor: `GIBS_LAYER = "MODIS_Terra_CorrectedReflectance_TrueColor"`,
  `GIBS_TILE_MATRIX_SET = "250m"` (`satellite_fetcher.py:42-43`).
- **Alternatif:** Sentinel Hub anahtarı yoksa mekansal analiz adımını tamamen atlamak ve
  `geospatial_mismatch` ağırlığını skordan çıkarmak.
- **Gerekçe:** Sentinel Hub kimlik bilgileri `config.py`'de `Optional` ve varsayılanı `None`.
  Fallback sayesinde anahtarsız kurulumda da hat uçtan uca çalışıyor, sessizce durmuyor.
- **Bedel:** 250 m/piksel görüntüde tek bir bina bir pikselin çok çok altında kalıyor. Bu
  kaynaktan gelen görüntüde `BuildingDetector`'ın YOLOv8 çıktısı fiziksel olarak anlamsız — ama
  motor bunu ayırt etmiyor, sonucu `WEIGHT_GEOSPATIAL_MISMATCH = 0.15` ağırlığıyla toplama
  katıyor (`anomaly_engine.py:44`). Yani anahtarsız kurulumda "hayalet bina" kararının %15'i,
  binayı çözemeyen bir görüntüden geliyor. Kaynak `_fetch_satellite_image` dönüşünde
  `result["source"]` olarak taşınıyor ama skorlamada kullanılmıyor. `[KODDAN]`

### Karar 3 — Faz başına tek dev commit

- **Seçim:** 34.428 satır 10 commit'e sığdırılmış; 9'u 2026-04-12/13'te, faz adlarıyla
  (`Phase 1 Completion`, `complete phase 2`, `feat(phase3)`, `feat(phase4)`, `feat(phase5)`).
  En büyüğü `e3c8ccc`: 55 dosya, 9.967 ekleme. `[GIT]`
- **Alternatif:** Faz içi küçük commit'ler veya PR akışı. Repo bunun altyapısını zaten kurmuş —
  `.github/PULL_REQUEST_TEMPLATE.md`, `CONTRIBUTING.md`, issue şablonları mevcut ama tek bir PR
  yok, tüm commit'ler doğrudan `main`'e.
- **Gerekçe:** `proje_plani.txt` faz faz bir plan içeriyor ve commit mesajları bu planı birebir
  takip ediyor. Teslim birimi olarak faz seçilmiş.
- **Bedel:** Git geçmişi bir olay kaydı değil. Hangi kararın neden alındığı, neyin denenip
  bırakıldığı, hangi hatanın nasıl bulunduğu geçmişten okunamıyor. 6. bölüm için "geri alan
  commit", "kısa aralıkla defalarca değişen dosya" gibi klasik izlerin hiçbiri yok — çünkü
  dosyaların çoğu tek kez yazılmış. Ayrıca 9 commit varsayılan `Your Name <you@example.com>`
  kimliğiyle atıldığı için GitHub'da yazarlık atfı kopuk.

### Karar 4 — Dört ayrı dağıtım hedefi repoda birlikte duruyor

- **Seçim:** `wrangler.toml` (Cloudflare Pages/Workers), `backend/railway.toml` (Railway),
  `frontend/vercel.json` (Vercel), `docker-compose.prod.yml` + `nginx/nginx.conf` (kendi sunucu).
  Dördü de HEAD'de mevcut.
- **Alternatif:** Bir hedef seçip diğerlerini silmek.
- **Gerekçe:** `git log` bu konuda gerekçe içermiyor. Kronoloji şunu gösteriyor: her faz yeni bir
  hedef eklemiş, önceki silinmemiş; nginx + compose son commit'te (`2e94b6d`) gelmiş ve
  frontend'in portu artık doğrudan yayımlanmıyor. `[GIT]`
- **Bedel:** En az bir yapılandırma ölü ve bu ölçülebilir bir çelişki: `wrangler.toml`
  `bucket = "./frontend/out"` ile statik export bekliyor, ama `next.config.mjs`
  `output: "standalone"` diyor — bu ikisi aynı anda üretilemez. Depoyu devralan birinin hangi
  hedefin gerçek olduğunu anlaması mümkün değil; dört yapılandırmanın üçü yanlış yola sokuyor.

---

## 6. Zorlandığım yer

Bu bölümde iki ayrım var ve karıştırılmaması önemli:

- **6.1** — bu oturumda ölçerek bulduğum, projede *yaşayan* ama daha önce fark edilmemiş hata.
- **6.2** — geçmişte gerçekten yaşanmış, commit mesajıyla belgelenmiş hata.
- **6.3** — geçmişten çıkarılabilecek olay kaydının neden zayıf olduğu.

### 6.1 — Migration ile model birbirinden ayrıldı; test paketi yapısı gereği bunu göremiyor

Bu, projenin en ciddi teknik borcu. Dört soruyla:

**Nasıl fark edildi**
Bu brifing için yapılan kurulum denemesinde. Temiz bir `postgis/postgis:16-3.4` konteynerine
`alembic upgrade head` çalıştırıldı (başarılı), ardından kayıt uç noktası denendi: `[ÖLÇÜLDÜ]`

```
POST /api/v1/auth/register  →  HTTP 500
```

Konteyner logu:

```
sqlalchemy.exc.ProgrammingError: asyncpg.exceptions.UndefinedColumnError:
column users.hashed_password does not exist
```

**Önemli dürüstlük notu:** bu hata *bu oturumda* bulundu, geçmişte fark edilmiş olduğuna dair
hiçbir kayıt yok — ne commit, ne TODO, ne yorum. Yaşanmış bir olayın anlatısı değil,
ölçülerek bulunmuş yaşayan bir hata.

**Kök sebep**
Tek bir migration var ve o da ilk commit'ten kalma: `backend/alembic/versions/a1_initial_schema.py`,
commit `198286f` (2026-04-12 15:02). `git log -- backend/alembic/versions/` tek satır döndürüyor. `[GIT]`

Modeller sonradan büyüdü, migration büyümedi:

| Model | Eklenen kolon | Hangi commit'te | Migration'da var mı |
| --- | --- | --- | --- |
| `User` | `hashed_password`, `is_active`, `is_verified`, `created_at` | `9a91642` (2026-04-12 18:11) | **Hayır** |
| `ScanJob` | `user_id` (FK → users), `created_at` | `2e94b6d` (2026-08-08) | **Hayır** |

Migration sonrası gerçek tablo — `psql \d users` çıktısı: `[ÖLÇÜLDÜ]`

```
id | email | username | role | trust_score | verified_count | submitted_count
```

Model ise 11 kolon bekliyor. `anomalies` tablosu ise modele birebir uyuyor — çünkü ilk
commit'ten sonra hiç değişmemiş.

**Neden testler yakalamadı:** Karar 1'in doğrudan bedeli. `conftest.py:186-200` model
sınıflarını patch'liyor; `TestUser` sınıfında `hashed_password` kolonu **var** ve tablo
`TestBase.metadata.create_all` ile modelden üretiliyor — migration hiç devreye girmiyor.
Yani test paketi migration'ı değil, kendi ürettiği şemayı doğruluyor. 205 test yeşil,
ürün kırık.

**Nasıl çözüldü**
**Çözülmedi.** Bu brifingde tespit edildi. Gereken iş: `alembic revision --autogenerate` ile
eksik kolonları ekleyen ikinci bir migration, ve CI'a migration'ın modelle uyumunu doğrulayan
bir kontrol (`alembic check` veya gerçek PostGIS'e karşı bir duman testi).

**Sonrasında ne değişti**
Henüz bir şey değişmedi. Etkisi şu an ölçülmüş haliyle: temiz kurulumda kayıt, giriş ve
`/auth/me` çalışmıyor; dolayısıyla topluluk doğrulama akışının tamamı (oy verme, trust score)
erişilemez durumda.

### 6.2 — Belgelenmiş gerçek hata: Docker imajı Debian güncellemesiyle kırıldı

Geçmişte yaşanmış ve commit mesajında kök sebebiyle birlikte yazılmış tek olay bu. `[GIT]`

- **Nasıl fark edildi:** Nisan'da çalışan `backend/Dockerfile` Ağustos'ta imaj kurulumunda
  patlamış (4 aylık aradan sonra `python:3.12-slim` tabanı güncellenmiş).
- **Kök sebep:** `libgl1-mesa-glx` paketi yeni Debian sürümlerinde kaldırıldı. Commit mesajı
  bunu açıkça yazıyor: *"Fix Dockerfile: libgl1-mesa-glx -> libgl1 (removed in newer Debian)"*.
  Paket OpenCV'nin çalışma zamanı bağımlılığıydı, yani kurulum tamamen duruyordu.
- **Nasıl çözüldü:** `2e94b6d` — tek satırlık değişiklik, `libgl1-mesa-glx` → `libgl1`.
- **Sonrasında ne değişti:** İmaj yeniden kuruluyor. Bu oturumda doğrulandı: `docker compose
  build backend` 186,6 saniyede başarıyla tamamlandı `[ÖLÇÜLDÜ]`.

Küçük bir hata ama gerçek ve izlenebilir; "4 ay dokunulmayan bir projenin taban imajı çürür"
dersinin somut örneği.

### 6.3 — Yarım kalmış geçişler: iki yaklaşım kodda birlikte duruyor

Son commit (`2e94b6d`) üç geçişi başlatmış, üçünü de tamamlamamış. Hepsi kodda birlikte duran
iki yaklaşım örneği:

**(a) Bing → Mapbox geçişi yarım.** `config.py`'den `BING_MAPS_API_KEY` alanı silinmiş, yerine
`MAPBOX_API_KEY` gelmiş. Ama `tile_fetcher.py:367` hâlâ silinen alanı okuyor:

```python
if provider == TileProvider.BING and settings.BING_MAPS_API_KEY:
```

Konteyner içinde doğrudan denendi: `[ÖLÇÜLDÜ]`

```
>>> settings.BING_MAPS_API_KEY
AttributeError: 'Settings' object has no attribute 'BING_MAPS_API_KEY'
>>> TileFetcher()._build_headers(TileProvider.BING)
AttributeError: 'Settings' object has no attribute 'BING_MAPS_API_KEY'
```

`fetch_all_providers` varsayılan olarak `list(TileProvider)` yani 4 sağlayıcının hepsini
deniyor (`tile_fetcher.py:559`), ve `_safe_fetch` istisnayı yutup yalnızca logluyor
(`tile_fetcher.py:566`). Sonuç: **çökme yok, sessiz kayıp.** Ürünün "4+ sağlayıcı karşılaştırması"
iddiası pratikte 3 sağlayıcı. Ayrıca `api_key_provider.py:139` hâlâ eski `bing_maps` sağlayıcısını
kayıtlı tutuyor.

**(b) İki ayrı CSP tanımı.** `next.config.mjs` `headers()` içinde bir CSP var (Google/Bing tile
alan adlarına izin veriyor), `middleware.ts:104-116`'da son commit'te eklenen ikinci bir CSP var
(cartocdn/mapbox/sentinel-hub'a izin veriyor, Google/Bing'e vermiyor). Eski tanım silinmemiş.
İki liste birbirinden farklı ve hangi rotada hangisinin geçerli olduğu koddan bakarak kesin
söylenemez — `[KODDAN]`, ölçülmedi. Pratik bedel: tile kaynağı eklerken iki dosyayı birden
güncellemek gerekiyor, biri unutulursa görsel sessizce engellenir.

**(c) API taban URL'i düzeltmesi bir dosyada eksik kalmış.** Son commit `lib/api.ts`'e
konteynerler arası çağrı düzeltmesi eklemiş — sunucu tarafında göreli URL geldiğinde
`http://backend:8000` ile mutlaklaştırıyor (`api.ts:33-39`). Ama `app/explore/[id]/page.tsx:11`
bu yardımcıyı kullanmıyor, ham `fetch` ile doğrudan `process.env.NEXT_PUBLIC_API_URL` okuyor.
Üretim yapılandırmasında bu değişken `/api/v1` (göreli) olarak veriliyor
(`docker-compose.prod.yml:90`). Sunucu tarafında göreli URL ile `fetch` çağrısı geçersizdir;
`catch` bloğu `null` döndürür ve sayfa `notFound()`'a düşer. Yani **üretimde anomali detay
sayfasının 404 vermesi bekleniyor.** `[KODDAN]` — bu tahmin ölçülmedi, üretim derlemesi
zaten (aşağıdaki lint hatası nedeniyle) alınamadı.

---

## 7. Ekran görüntüsü hazırlığı

### Yerelde ayağa kalkıyor mu?

**Backend: evet, doğrulandı.** `[ÖLÇÜLDÜ]` Aşağıdaki zincir bu oturumda çalıştırıldı
(izole bir Docker ağında, projenin kendi compose'u yerine — çünkü `docker-compose.yml`
5432 ve 6379 portlarını yayımlıyor ve bu makinede o portlar başka projelerin konteynerleri
tarafından tutuluyor):

```bash
cp .env.example .env          # sonra .env'i doldur
docker compose build backend  # 186,6 sn (torch/ultralytics indirmesi dahil, ~9,7 GB imaj)
docker compose up -d db redis
docker compose run --rm backend alembic upgrade head
docker compose up -d backend celery_worker celery_beat frontend
```

Doğrulanan sonuçlar: migration başarılı; uvicorn açılıyor; `redis_connected` logu düşüyor;
`GET /api/v1/health` → `200`. Sağlık durumu `"degraded"` çünkü ölçüm sırasında Celery
worker'ı ayakta değildi — worker'la birlikte `healthy` olması bekleniyor `[KODDAN]`.

**Frontend: üretim derlemesi kırık, dev modu denenmedi.** `npm run build` **başarısız**
`[ÖLÇÜLDÜ]`:

```
./src/app/MapPage.tsx
17:3   Error: 'Globe' is defined but never used.
18:3   Error: 'Eye' is defined but never used.
19:3   Error: 'Settings' is defined but never used.
20:3   Error: 'HelpCircle' is defined but never used.
21:3   Error: 'LogOut' is defined but never used.
22:3   Error: 'ChevronRight' is defined but never used.
198:28 Error: 'setSidebarCollapsed' is assigned a value but never used.
```

Yedisi de son commit'te eklenen `MapPage.tsx`'ten geliyor. TypeScript derlemesi geçiyor
("Compiled successfully"), yalnızca lint kapısı kapatıyor. Yani `ci.yml`'deki `frontend-build`
işi HEAD'de başarısız olur ve ona bağımlı `docker-build-test` işi hiç koşmaz `[KODDAN]`.

**Ekran görüntüsü için iki seçenek var:**
1. Yedi kullanılmayan import'u silmek (5 dakikalık iş, kalıcı düzeltme) — **önerilen**.
2. `next dev` ile çalıştırmak; dev sunucusu lint hatasında durmaz. Denenmedi.

### Ön koşullar

| Ön koşul | Olmadan ne olur |
| --- | --- |
| PostgreSQL **+ PostGIS eklentisi** | Uygulama açılmaz. `anomalies.geom` `Geometry(Point,4326)`; migration ilk iş olarak `CREATE EXTENSION postgis` çalıştırıyor. Düz Postgres yetmez. |
| Redis | Uygulama **açılır** ama `app.state.redis = None` ile devam eder (`main.py:66`); tile önbelleği, oran sınırı, tarama ilerlemesi ve e-posta doğrulama token'ı çalışmaz. |
| `alembic upgrade head` | Tablolar yok, tüm veri uç noktaları hata verir. |
| `DATABASE_URL` ve `REDIS_URL` | **Zorunlu.** `config.py`'de varsayılanları yok; eksikse pydantic açılışta hata verir. |
| `SECRET_KEY` | Varsayılanı var (`"supersecretkey_change_in_production"`) — açılır ama üretimde kullanılamaz. |
| Celery worker | API açılır, `/health` `degraded` döner, tarama başlatılabilir ama hiç işlenmez. |
| Sentinel Hub anahtarı | Opsiyonel — yoksa MODIS fallback'e düşer (bkz. Karar 2). |
| Google/Mapbox/Sentry anahtarları | Opsiyonel, hepsi `Optional[str] = None`. |
| Ödeme sağlayıcı | **Yok** — projede ödeme akışı hiç yok. |

Not: `docker-compose.yml` 5432, 6379, 8000 ve 3000 portlarını yayımlıyor. Bu makinede
5432/6379 başka projelerin konteynerleri tarafından kullanılıyor `[ÖLÇÜLDÜ: docker ps]`;
ekran görüntüsü öncesi ya o konteynerler durdurulmalı ya da port eşlemesi değiştirilmeli.

### Demo veri var mı?

**Var ama çalışmıyor.** `backend/scripts/seed_data.py` elle yazılmış 20 gerçek dünya kaydı
içeriyor. Çalıştırıldı: `[ÖLÇÜLDÜ]`

```
🌱 Starting database seeding process...
Inserting 20 anomalies...
❌ Error during seeding: asyncpg.exceptions.UndefinedColumnError:
   column "image_type" of relation "anomaly_images" does not exist
```

Sonrasında satır sayımı:

```
 anomalies      | 0
 anomaly_images | 0
 users          | 0
```

**Kök sebep:** Script `anomaly_images` tablosuna `image_type`, `resolution`, `metadata_json`
kolonlarını yazmaya çalışıyor (`seed_data.py:228-231`); bu üç kolon ne modelde ne migration'da
var. Anomali `INSERT`'leri ile görsel `INSERT`'leri aynı işlemde ve tek `commit` döngünün
**sonunda** olduğu için, ilk görselde patlayan işlem hiçbir şey yazamadan geri alınıyor.
Üstelik `except Exception` bloğu hatayı yalnızca yazdırıp yutuyor — script sıfır çıkış koduyla
biter, "başarısız oldu" sinyali vermez.

**Düzeltme maliyeti: düşük.** Ya `seed_data.py`'deki görsel `INSERT`'inden üç fazla kolon
çıkarılır, ya kolonlar migration'a eklenir. 15 dakikalık iş. Ekran görüntüsü almadan önce
**zorunlu** — aksi halde her ekran boş görünür.

Ayrıca: seed script hiç kullanıcı üretmiyor. Kullanıcı gereken ekranlar için (profil, oy
verme) önce 6.1'deki migration eksiği kapatılmalı, sonra kayıt akışıyla kullanıcı yaratılmalı.

### Ekran görüntüsü alınabilecek anlamlı ekranlar

| # | Rota / görünüm | Neden önemli |
| --- | --- | --- |
| 1 | `/` — `MapPage.tsx` | Ürünün ana iddiası: küresel harita üzerinde anomali katmanı, yanında canlı istatistik paneli ve son tespitler listesi. Tek bir kare ürünün ne olduğunu anlatıyor. **Not:** veri yoksa liste yerine "API bağlantısı bekleniyor" iskeleti çıkıyor (`MapPage.tsx:397`) — seed düzeltilmeden çekilmemeli. |
| 2 | `/explore` — `ExploreContent.tsx` + `FilterPanel.tsx` | "Bu bir gösteri değil, üzerinde çalışılabilir bir veri kümesi" iddiasını kanıtlıyor: kategori/skor/tarih filtreleri, sayfalama, kart listesi. Gerçek API'ye bağlı (`useAnomalyList`). |
| 3 | `/explore/{id}` — `ProviderComparison.tsx` | **En değerli kare.** Aynı koordinatın farklı sağlayıcılardaki tile'larını yan yana gösteriyor — projenin tüm tezi bu görselde. **Uyarı:** üretim yapılandırmasında bu sayfanın 404 vermesi bekleniyor (bkz. 6.3c); `next dev` ile mutlak `NEXT_PUBLIC_API_URL` vererek çekilmeli. |
| 4 | `/api/v1/docs` — FastAPI OpenAPI | Arayüzün arkasında gerçek bir API olduğunu kanıtlıyor: 5 etiketli grup, 21 uç nokta. `DEBUG=true` gerekli — üretimde `docs_url=None` (`main.py:91`). |
| 5 | Grafana panosu — `docker-compose.monitoring.yml` | "Gözlemlenebilirlik kurulu" iddiasını kanıtlayan tek kare (Prometheus metrikleri + istek gecikmesi). **Bu oturumda kurulmadı, denenmedi.** Ayağa kaldırma maliyeti bilinmiyor. |
| 6 | `/auth/register` — `RegisterForm.tsx` | Form tasarımı ve doğrulama (zod + react-hook-form, parola gücü göstergesi). **Yalnızca form karesi alınabilir** — 6.1 nedeniyle gönderim `500` veriyor, "başarılı kayıt" ekranı şu an mümkün değil. |

**Kaçınılması gereken ekran:** `/profile/{username}`. Bu sayfa (813 satır) tamamen uydurma
veriyle çalışıyor — `ProfileView.tsx:427` API çağrısı yorum satırında, altında elle yazılmış
rozetler, trust score'lar, katkı ısı haritası ve şehir listesi var. Backend'de karşılık gelen
`/users/{username}` uç noktası **hiç yok**. Bu ekranın portföyde yer alması, olmayan bir
özelliği varmış gibi göstermek olur.

### Gerçek veri riski

Kişisel veri riski **düşük**: veritabanı boş, gerçek kullanıcı yok, script kullanıcı üretmiyor.

Ama **farklı ve daha ciddi bir risk var** — seed verisinin kendisi:

`seed_data.py` içindeki 20 kayıt gerçek, adı konmuş yerler: Area 51, Doğu Pyongyang, Novaya
Zemlya, Kremlin, Élysée Sarayı, Şam, Kabil, Riyad, İsrail'in orta bölgesi. Güven skorları
(`98.5`, `94.2`, `100.0`) **elle yazılmış sabitler** — analiz hattının çıktısı değil.
Statüleri de doğrudan `VERIFIED` olarak yazılıyor (`seed_data.py:213`).

Yani bu veriyle alınan bir ekran görüntüsü şunu iddia eder: *"sistem Novaya Zemlya'yı %100
güvenle sansürlü tespit etti ve doğruladı."* Gerçekte sistem hiçbir şey tespit etmemiştir;
sayı bir Python listesine yazılmıştır. Portföyde bunun **görsel altında açıkça belirtilmesi**
gerekiyor, yoksa ölçülmemiş bir iddia ölçülmüş gibi sunulmuş olur.

Ayrıca aynı görsellerde askeri ve devlet tesisi koordinatlarının "sansürlü / gizli yapı"
etiketiyle görünmesi jeopolitik olarak hassas — bkz. 9. bölüm.

---

## 8. Ölçülebilir ne varsa

Yalnızca kanıtı olanlar. Kanıtı olmayan hiçbir sayı bu tabloya alınmadı.

| Ölçüm | Değer | Kanıt |
| --- | --- | --- |
| Backend testleri | **205 geçti, 0 başarısız, 16 uyarı** | `pytest -q` → `205 passed, 16 warnings in 8.08s` `[ÖLÇÜLDÜ]` |
| Test süresi | 8,08 sn | aynı çıktı `[ÖLÇÜLDÜ]` |
| Test dosyası / test fonksiyonu | 8 dosya / 205 fonksiyon | `grep -c "def test_"` `[ÖLÇÜLDÜ]` |
| En büyük test dosyası | `test_security.py` — 1.206 satır, 99 test, 11 sınıf | `wc -l`, `grep` `[ÖLÇÜLDÜ]` |
| Backend imajı derleme süresi | 186,6 sn | `docker compose build backend` `[ÖLÇÜLDÜ]` |
| Backend imaj boyutu | 9,7 GB (disk), 3,27 GB (içerik) | `docker images` `[ÖLÇÜLDÜ]` — ultralytics→torch bağımlılığından |
| `alembic upgrade head` | Başarılı (`Running upgrade -> a1`) | temiz PostGIS konteyneri `[ÖLÇÜLDÜ]` |
| `seed_data.py` sonrası satır sayısı | **0 / 0 / 0** (anomalies / images / users) | `psql SELECT count(*)` `[ÖLÇÜLDÜ]` |
| Frontend üretim derlemesi | **Başarısız** — 7 ESLint hatası | `npm run build` `[ÖLÇÜLDÜ]` |
| `GET /api/v1/health` | `200`, `status=degraded`, redis gecikmesi 1,23 ms | curl `[ÖLÇÜLDÜ]` |
| `POST /api/v1/auth/register` | **`500`** | curl + log `[ÖLÇÜLDÜ]` |
| Toplam izlenen satır | 34.428 (160 dosya) | `git ls-files \| xargs wc -l`, üretilmiş dosyalar hariç `[ÖLÇÜLDÜ]` |
| Backend / frontend dağılımı | 21.190 Python / 10.621 tsx-ts-css | aynı `[ÖLÇÜLDÜ]` |
| Uygulama kodu / test kodu | 17.202 / 3.553 satır | `wc -l backend/app`, `backend/tests` `[ÖLÇÜLDÜ]` |
| Commit sayısı | 10 | `git rev-list --count HEAD` `[GIT]` |
| API uç noktası sayısı | 21 (5 router) | `grep "@router\."` `[ÖLÇÜLDÜ]` |
| Veritabanı tablosu | 5 (`users`, `anomalies`, `anomaly_images`, `verifications`, `scan_jobs`) | modeller + migration `[ÖLÇÜLDÜ]` |
| Testin hiç dokunmadığı çekirdek kod | **7.685 satır** | testlerin import ettiği 16 modül listelendi; `anomaly_engine`, `geospatial_analyzer`, `time_series`, `osm_collector`, `satellite_fetcher`, `scan_tasks`, `maintenance_tasks`, `map_routes` hiçbirinde yok `[ÖLÇÜLDÜ]` |

### Kanıtı olmadığı için listelenmeyenler

- **Test kapsamı (coverage) yüzdesi** — `BİLİNMİYOR`. `pytest-cov` bağımlılıklarda yok, kapsam
  raporu üretilmiyor. Yukarıdaki "7.685 satır" modül bazlı bir alt sınırdır, kapsam yüzdesi değildir.
- **CI durumu** — `BİLİNMİYOR`. 4 workflow tanımlı (`ci`, `deploy-staging`, `lighthouse`,
  `security-scan`) ve README'de bir build rozeti var, ama bunların bir kez bile koştuğuna dair
  repoda kanıt yok. HEAD'de `frontend-build` işinin başarısız olacağı ölçüldü (yukarıdaki lint
  hatası).
- **Lighthouse skorları** — `BİLİNMİYOR`. `lighthouserc.json` var, sonuç raporu yok.
- **Performans ölçümü** — `BİLİNMİYOR`. Prometheus metrik altyapısı kurulu (`metrics.py`,
  148 satır) ama toplanmış hiçbir veri yok. Tek gerçek gecikme rakamı sağlık uç noktasının
  bildirdiği redis 1,23 ms.
- **Veri hacmi / kullanıcı sayısı / anomali sayısı** — **sıfır.** Üretim ortamı yok, veritabanı boş.
- **Tespit doğruluğu (precision/recall)** — `BİLİNMİYOR` ve **ölçülmemiş**. Ne etiketli veri
  kümesi, ne değerlendirme scripti, ne de doğrulanmış sonuç var. Skor ağırlıkları
  (`0.30/0.25/0.20/0.15/0.10`) ve eşikler (`40.0`, `60.0`, `70.0`) elle seçilmiş sabitler —
  hiçbirinin kalibrasyon kaydı yok. Portföyde "şu kadar doğrulukla tespit ediyor" denemez.

---

## 9. Yayına çıkarma engelleri

Emin olunmayanlar da yazıldı ki karar sende olsun.

### Yüksek öncelik

**1. `.env` dosyasında gerçek kimlik bilgileri var.** [GİZLİ]
Dosya `.gitignore`'da (satır 14) ve git tarafından izlenmiyor — yani depoya sızmamış
`[ÖLÇÜLDÜ: git ls-files]`. Ama diskte duruyor ve dolu alanlar arasında **gerçek görünen bir
Sentinel Hub OAuth istemci kimliği ve gizli anahtarı** var (uzunlukları gerçek kimlik bilgisiyle
tutarlı). Ayrıca doldurulmuş bir `SECRET_KEY`, veritabanı parolası, Grafana yönetici parolası
ve bir MapLibre token'ı mevcut. **Değerleri bu brifinge yazılmadı.**
→ Yapılacak: terminal veya editör ekran görüntüsü alınırken `.env` görünmemeli. Bu anahtarlar
daha önce herhangi bir yere yapıştırıldıysa Sentinel Hub tarafında döndürülmeli.

**2. Harita sağlayıcılarının kullanım şartları.** Bu, projenin doğasında olan ve portföyde
görünür hale gelecek olan risk. `tile_fetcher.py` tile'ları resmi API'ler üzerinden değil,
doğrudan iç uç noktalardan çekiyor: `mt1.google.com/vt/lyrs=s`, `sat01.maps.yandex.net/tiles`,
`ecn.t{n}.tiles.virtualearth.net`. Üstelik:
- 5 farklı tarayıcı User-Agent'ı arasında rastgele dönüş yapıyor (`tile_fetcher.py:57-68`)
- `Referer` başlığını sabit olarak `https://www.openstreetmap.org/` gönderiyor — istek başka
  bir siteden geliyormuş gibi (`tile_fetcher.py:363`)
- Sağlayıcı başına saniyede 10 istek hedefliyor (`RATE_LIMIT_PER_SECOND = 10`)

Bu davranış Google ve Yandex'in kullanım şartlarına aykırı. README bunu bir feragatname ile
geçiştiriyor (`README.md:105`, "public APIs and open data sources") ama kullanılan uç noktalar
public API değil. **Karar senin:** public portföyde User-Agent döndürme ve Referer sahteciliği
yapan kodu sergilemek, teknik olarak ilginç ama itibar açısından tartışmalı. En azından vaka
çalışmasında bu sınırın farkında olunduğunun yazılması gerekir.

**3. Seed verisindeki jeopolitik hassasiyet.** 20 kayıt arasında Area 51, Doğu Pyongyang,
Novaya Zemlya nükleer test sahası, Kremlin, Élysée Sarayı, Şam, Kabil ve "İsrail'in orta
bölgesi" var; hepsi "sansürlü alan" veya "gizli yapı" etiketiyle ve elle yazılmış %90+ güven
skorlarıyla. Bunlar ölçüm değil, örnek veridir (bkz. 7. bölüm). Portföyde ölçüm gibi görünmeleri
hem yanlış beyan hem de gereksiz bir hassasiyet yükü yaratır.
→ Öneri: ekran görüntüleri için seed verisini siyaseten nötr yerlerle (terkedilmiş sanayi
alanları, havalimanı çevreleri, inşaat sahaları) değiştirmek.

### Orta öncelik

**4. LICENSE dosyası yok.** `README.md:103` MIT lisansı olduğunu söylüyor ve `LICENSE` dosyasına
link veriyor; o dosya depoda **yok** `[ÖLÇÜLDÜ: ls LICENSE*]`. Depo public yapılırsa lisanssız
kod olur — kimse yasal olarak kullanamaz, ve README kırık bir söz vermiş olur.

**5. README ve CHANGELOG'da doğrulanamayan iddialar.** 3. bölümde listelendi: Apple Maps desteği
(kod yok), otomatik e-posta uyarıları (kod yok). Ayrıca README `https://ghostbuilding.io`
adresini **"Live Demo"** olarak, `map_routes.py:127` ise `https://ghostbuilding.dev` adresini
User-Agent'ta veriyor. İki farklı alan adı ve ikisinin de ayakta olup olmadığı `BİLİNMİYOR` —
kontrol edilmedi. Public bir portföyden çalışmayan bir "canlı demo" linkine gitmek kötü bir ilk
izlenim.

**6. `GhostBuilding_Proje_Plani.docx` depoda izleniyor** (27 KB, commit `2e94b6d`).
İçeriği **okunmadı** — ikili dosya. İçinde kişisel not, gerçek kurum/kişi adı veya ticari plan
varsa public depoda bulunmamalı. → Yapılacak: açıp gözden geçir, gerekiyorsa `.gitignore`'a ekle
ve geçmişten temizle. Aynısı `proje_plani.txt` (272 satır, aynı commit) için de geçerli.

### Düşük öncelik / bilgi

**7. Yazarlık geçmişi kopuk.** 10 commit'in 9'u `Your Name <you@example.com>` kimliğiyle atılmış
`[GIT]`. Depo public yapılırsa GitHub katkı grafiğinde bu commit'ler sana atfedilmez. Düzeltmek
geçmişi yeniden yazmayı gerektirir (`git filter-repo`) — portföy açısından bunun değip değmediği
senin kararın, ama vaka çalışmasında "tek geliştirici" denecekse commit geçmişi bunu ilk bakışta
desteklemiyor.

**8. Müşteri işi / NDA:** Kodda hiçbir müşteri, kurum veya sözleşme izi yok — ne müşteri adı, ne
faturalandırma, ne özel API. Bu bir **kişisel/açık kaynak proje** görünümünde. Bildiğim kadarıyla
NDA engeli yok, ama bunu kesin olarak yalnızca sen bilebilirsin.

**9. Üçüncü parti veri lisansları:** OpenStreetMap verisi ODbL lisanslı ve **atıf zorunluluğu**
var. `docs/data-sources.md` (19 satır) mevcut ama arayüzde harita üzerinde bir OSM atıf
metni olup olmadığı kontrol edilmedi — `BİLİNMİYOR`. Ekran görüntüsü almadan önce bakılmalı;
atıfsız OSM tile'ı gösteren bir kare lisans ihlali sergiler.

---

## Portföy oturumuna not

Bu brifingin doldurmadığı alanlar, prompt gereği kasten boş: `slug`, `featured`, `order`,
`diagram`, `cover`, `updated`. Bunlar site geneli sıralama ve dosya yolu kararlarıdır.

Doldurulabilenler:

```yaml
title: GhostBuilding
tagline: Harita sağlayıcıları arasındaki farkları tarayıp sansürlenmiş
         ve eksik yapıları işaretleyen OSINT aracı
period: 2026-04 → 2026-08
role: Tek geliştirici
stack: [FastAPI, PostGIS, Celery, Redis, OpenCV, YOLOv8, Next.js, MapLibre]
status: geliştirme
statusDetail: >
  205 backend testi geçiyor, analiz hattı ve arayüz baştan sona yazılmış;
  ancak temiz kurulumda kullanıcı kaydı migration eksiği yüzünden 500 veriyor,
  demo veri script'i sıfır satır yazıyor ve frontend üretim derlemesi
  lint hatasıyla duruyor.
```

**Ekran görüntüsü almadan önce yapılması gerekenler** (hepsi küçük, toplam ~1 saat):
1. `MapPage.tsx`'teki 7 kullanılmayan import/değişkeni sil → üretim derlemesi açılır.
2. `seed_data.py`'deki görsel `INSERT`'inden `image_type`, `resolution`, `metadata_json`
   kolonlarını çıkar → demo veri yüklenir.
3. Eksik kolonlar için ikinci bir alembic migration üret → kayıt/giriş çalışır.
4. Seed verisindeki hassas konumları nötr olanlarla değiştir.
