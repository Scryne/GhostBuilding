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
