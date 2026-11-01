# Deneme: ağırlıksız "hayalet bina" sinyali — Overture bina izleri (2026-10-31)

**Soru.** Bina dedektörü z16'da (~2,4 m/piksel) çalışacak hazır ağırlık bekliyor; böyle bir ağırlık
yok (2026-10-31 araştırması: açık modeller 0,3–0,5 m/piksel için eğitilmiş). Görüntüden makine
öğrenmesiyle çıkarılmış hazır bina izleri, OSM ile karşılaştırılarak aynı soruyu ağırlıksız
cevaplayabilir mi? Mantık: sansürlü bir tesis OSM'de çizili, ama görüntüden çıkarılan izlerde
yoksa, bu görüntü sansürünün bağımsız bir işaretidir.

**Yöntem.** Overture Maps `2026-10-21.0` sürümü, `theme=buildings/type=building` GeoParquet,
DuckDB (`httpfs` + bbox süzgeci) ile z16 karosu büyüklüğünde (~0,009° kutu) iki konum: Île Longue
(Fransa'nın nükleer denizaltı üssü; Esri'de bulanık, MapTiler'da mozaik) ve Lyon merkez (sıradan).
Her bina `sources[].dataset` alanına göre OSM ve ML (Microsoft/Google) olarak sayıldı.

| Konum | Toplam | OSM | ML | Sorgu süresi |
|---|---:|---:|---:|---:|
| Île Longue | 42 | 42 | 0 | 63 s |
| Lyon merkez | 1154 | 1149 | 5 | 36 s |

**Sonuç: Overture bu iş için kullanılamaz.** Overture binaları birleştirirken OSM'yi önceler: OSM'nin
çizdiği yerde ML izi atılır, ML yalnız OSM'nin boş bıraktığı yeri doldurur. "OSM var, ML yok" durumu
bu yüzden her yerde olağandır ve sansür hakkında bir şey söylemez (Île Longue'daki 0 ML, Lyon'daki
5 ML ile aynı nedenden). Karşılaştırma için ML katmanının **birleştirilmemiş** hali gerekir.

**Sonraki adım (yapılmadı).** Bağımsız kaynak Microsoft Global ML Building Footprints'tir (Bing
görüntüsünden, Avrupa dahil; `dataset-links.csv` z9 quadkey → dosya). Konum başına ilgili z9 dosyası
(onlarca MB) indirilip önbelleğe alınır, karo kutusu süzülür, OSM bina sayısıyla oranlanır ve diğer
sinyaller gibi **sıradan konumların taban dağılımına** göre puana çevrilir (taban ölçülmeden
bağlanmaz: tarihsel sinyalde olduğu gibi). Not: ML izleri Bing görüntüsünden çıkar; GhostBuilding'in
karşılaştırdığı Esri/MapTiler/IGN'den bağımsız dördüncü bir sağlayıcı sinyali olur, aynı
görüntünün sansürünü doğrudan ölçmez.

Deneme betiği: DuckDB, `read_parquet('s3://overturemaps-us-west-2/release/<sürüm>/theme=buildings/type=building/*')`,
`bbox.xmin/ymin` aralık süzgeci, `sources` listesinde `OpenStreetMap` sayımı.

---

# Deneme 2: Microsoft Global ML Building Footprints (2026-11-01)

**Yöntem.** Overture'ın atladığı birleştirilmemiş ML katmanı doğrudan Microsoft'un
`dataset-links.csv` dizininden alındı: her konumun z9 quadkey dosyası (sıkıştırılmış GeoJSON,
dosya başına onlarca MB) indirildi, z16 karo kutusuna düşen izler sayıldı. OSM bina sayısı, Overpass
o gün kapasite hatası verdiği için Overture'daki `sources.dataset = OpenStreetMap` kayıtlarından
alındı (Overture OSM binalarını değiştirmeden taşır). 86 konum: 59 taban (sıradan), 7 referans
kontrol, 20 referans tesis (askeri/nükleer). 5 konumda ML dosyası yok (Kore, İran, Yeni Zelanda,
bir Normandiya karosu): değerlendirme dışı. Ham veri: `olcum-bina-izleri-ml-osm.json`.

**Kural.** OSM'de en az 4 bina var ve ML payı `ml / (osm + ml) < 0,02` → "görüntüden çıkarılmış iz
yok" işareti.

| Grup | Değerlendirilebilir | İşaret |
|---|---:|---:|
| Taban (sıradan) | 49 | **0** |
| Referans kontrol | 7 | 0 |
| Referans tesis | 12 | **5** |

İşaretlenen beşi de Fransa'da: Brest askeri limanı (OSM 371 / ML 1), CEA Valduc (15 / 0), Marcoule
(25 / 0), Saint-Dizier BA 113 (4 / 0), Luxeuil BA 116 (7 / 0). Aynı ülkedeki sıradan konumlarda ML
payı normal (Lyon, Strasbourg, Bretagne kıyısı, Montpellier, Paris: %20–40). Fransa dışındaki
tesislerde (Menwith Hill, Pine Gap, Dimona, Sivastopol) ML izleri var. Tek yönlü Fisher testi
("OSM'de bina var, ML sıfır" oranı, tesis 8/16 – taban 4/54): p ≈ 0,0004. Eşik 10 binaya
çıkarılınca tesis isabeti 3/9'a düşüyor, taban yanlış alarmı yine 0/48.

**Yorum.** Sinyal ayırıyor, ama ayırdığı şey büyük ihtimalle Fransız sahalarının Bing
görüntüsünde de gizlendiği (Microsoft'un modeli o görüntüden bina çıkaramadı). Bu, GhostBuilding'in
karşılaştırdığı Esri / MapTiler / IGN'den **bağımsız dördüncü bir sağlayıcının** sansür izidir;
aynı görüntünün sansürünü doğrudan ölçmez. Sınırlar: referans listesini ben seçtim (etiket
yanlılığı), tesis örneklemi küçük ve Fransa ağırlıklı, Microsoft dosyaları 2022–2023 görüntüsünden
(güncellik farkı), z9 dosyası konum başına onlarca MB.

**Karar.** Puana bağlanmaz. Tarihsel değişim sinyalinde olduğu gibi önce **kanıt** olarak
eklenmeli: bulgu kartında "Microsoft ML izleri bu karoda yok (OSM: N bina)" satırı, taban ölçüsüyle
birlikte. Puana girmesi için Fransa dışından en az 20 tesis ve ülke başına taban gerekir.
Ürünleştirme maliyeti: z9 dosyasının indirilip önbelleklenmesi (konum başına bir kez, ~10–80 MB),
karo süzgeci akışla (dosya belleğe alınmadan). Bu iş yol haritasında ayrı bir adım olarak duruyor.

**Ürünleşti (2026-11-01):** `backend/app/services/ml_footprints_service.py`, uç `GET /anomalies/{id}/ml-footprints`,
ön yüz `MlFootprintsRow`. Fark: deney konuma ortalanmış kutu kullanıyordu, ürün taramanın z16 karo sınırını kullanır
(Kadıköy 322 → 315). Puana bağlanması için yukarıdaki koşul (Fransa dışından ≥ 20 tesis, ülke başına taban) hâlâ geçerli.
