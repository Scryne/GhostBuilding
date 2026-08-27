# DURUM — GhostBuilding — uydu tile karşılaştırması, sansür tespiti

> **Ne bu dosya:** sertifika değil **envanter**. 2026-08-27 denetiminde ölçülen gerçek durum.
> "Çalışmıyor" yazan satır kusur değil, kayıt. Kapanış standardı:
> `ScryneOS/🎯 100-Command-Center/Kapanis-Standardi.md`

**Ölçüm tarihi:** 2026-08-27
**Tek cümle:** **Frontend derlenmiyor.** Denetimde bulunan tek gerçek kırık derleme; sebebi 7 kullanılmayan import.

## Ne çalışıyor

- Backend kod tabanı ve 7 test dosyası duruyor, `pytest.ini` yapılandırılmış.
- `docker-compose`: db · redis · backend · celery_worker · celery_beat ·
  celery_maintenance · frontend.
- `nginx/` ve `monitoring/` yapılandırmaları mevcut.

## Ne çalışmıyor / doğrulanmadı

- 🔴 **Frontend üretim derlemesi BAŞARISIZ.** `next build` ESLint aşamasında düşüyor,
  `src/app/MapPage.tsx` içinde 7 hata (`@typescript-eslint/no-unused-vars`):
  satır 17 `Globe` · 18 `Eye` · 19 `Settings` · 20 `HelpCircle` · 21 `LogOut` ·
  22 `ChevronRight` · 198 `setSidebarCollapsed`.
  Hepsi kullanılmayan import/değişken — **düzeltmesi dakikalar sürer**, ama bugün proje
  derlenmiyor.
- **Backend testleri koşturulamadı:** yerel `.venv` yok, Docker gerekiyor; bu denetimde
  ayağa kaldırılmadı. 7 test dosyasının durumu BİLİNMİYOR.

## Ne yarım

Portföy brifingi yazılmış ama commit edilmemişti (bu denetimde commit edildi).

## Sonraki adım

**7 kullanılmayan import'u sil, derlemeyi yeşile al.** Denetimdeki en ucuz kazanç.
