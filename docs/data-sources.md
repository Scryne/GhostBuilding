# Veri kaynakları ve kullanım koşulları

GhostBuilding yalnız resmî, belgelenmiş uçları kullanır. Her istek projeyi tanıtan sabit bir
User-Agent taşır (`GhostBuilding/0.2 (+https://github.com/Scryne/GhostBuilding)`); sahte tarayıcı
kimliği, Referer ya da kota aşma yoktur. Atıflar arayüzde her karonun ve altlığın yanında gösterilir.

| Kaynak | Uç | Kullanım | Koşul |
|---|---|---|---|
| Esri World Imagery | `server.arcgisonline.com/.../World_Imagery/MapServer/tile` | Analiz karosu, altlık | Atıf: "Esri, Maxar, Earthstar Geographics, and the GIS User Community" |
| Esri Wayback | `waybackconfig.json` + sürüm karoları | Tarihsel sürümler (taramaya henüz bağlı değil) | Esri atfı |
| MapTiler Satellite | `api.maptiler.com/tiles/satellite-v2` | Analiz karosu, altlık | `MAPTILER_API_KEY`; anahtarı alan adınıza kısıtlayın; atıf "© MapTiler" |
| IGN Géoplateforme | `data.geopf.fr` WMTS ortofoto | Fransa'da üçüncü kaynak, altlık | Licence Ouverte Etalab 2.0, anahtarsız |
| CARTO koyu altlık | `basemaps.cartocdn.com` | Harita altlığı | © OpenStreetMap contributors, © CARTO |
| OpenStreetMap Overpass | `overpass-api.de` | Bina verisi (yalnız bina dedektörü açıksa) | ODbL |

## Neden Google, Bing ve Yandex yok

İlk sürüm bu sağlayıcıların resmî olmayan karo uçlarını rastgele User-Agent'larla çekiyordu. Bu,
sağlayıcıların kullanım koşullarına ve OSM karo politikasına aykırıdır; herkese açık bir repoda
savunulamaz. Resmî API'leri toplu karo indirmeye ve görüntüyü analiz için saklamaya izin vermediğinden
kaldırıldılar.

## Önbellek

Karolar Redis'te kısa süre önbelleğe alınır. Bulgu görselleri (kanıt karoları) yalnız eşiği geçen
konumlar için saklanır ve kaynak atfıyla gösterilir.
