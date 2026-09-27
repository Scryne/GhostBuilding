# Algoritmalar ve kalibrasyon

Bir tarama, koordinat için uygun kaynaklardan (Esri World Imagery, MapTiler Satellite, Fransa'da
IGN ortofoto) aynı z16 karoyu indirir ve iki sinyal ölçer. Ham ölçümler doğrudan puan değildir:
her biri sıradan konumlardan ölçülmüş bir taban dağılımına göre 0–100'e çevrilir.

## 1. Görüntü farkı (`pixel_diff.py`)

- Karolar aynı boyuta **ölçeklenir** (eskiden merkezden kırpılıyordu; farklı çözünürlükteki
  kaynaklar bu yüzden kıyaslanamıyordu).
- Her kaynak çifti için SSIM, mutlak piksel farkı ve histogram ayrışması hesaplanır; "en farklı çift"
  ham farkı verir (%).
- Sıradan bir konum bile ~%70 fark verir (çekim tarihi, mevsim, renk dengesi). Bu yüzden ham fark
  tek başına anlam taşımaz.

## 2. Bulanıklık / sansür (`blur_detector.py`)

Beş kural, her isabet puan katkısıyla birlikte gerekçe olarak yazılır:

| Kural | Katkı |
|---|---|
| Bir kaynağın Laplacian varyansı diğerlerinin yarısından az (z-skoru > 2) | +30 |
| Yalnız bir kaynakta FFT düşük geçiş izi (yüksek frekans kaybı) | +25 |
| Yalnız bir kaynakta bölgesel bulanıklık anomalisi | +20 |
| Bir kaynak şiddetli bulanık, en az bir kaynak keskin | +15 |
| Bulanık olan tek kaynak, en az iki kaynak keskin | +10 |

Toplam (en fazla 100) ham sansür skorudur.

## 3. Taban dağılımına göre puan

`backend/scripts/calibrate_diff.py` sıradan konumları aynı hattan geçirir ve dağılımı çıkarır:

| Taban | Konum | Fark p90 / p99 | Sansür p90 / p99 |
|---|---|---|---|
| 2 kaynak (Esri + MapTiler) | 40 konum, z16 | %80,1 / %87,6 | 15,5 / 20 |
| 3 kaynak (+ IGN) | 20 Fransız konumu, z16 | %88,8 / %99,0 | 1,5 / 19,1 |

Dönüşüm doğrusaldır: taban p90'a kadar 0, p90→p99 arası 0→50, p99→100 arası 50→100. Bir sinyal
50'yi geçerse sıradan konumların %99'undan sıra dışıdır. Üç kaynakta ölçü üç çiftin en büyüğü olduğu
için dağılım yukarı kayar; iki kaynaklı eşik orada sıradan konumların ~%15'ini işaretlerdi.

Kalibrasyondan önceki eşikler (%15 / %30) sıradan 40 konumun 39'unu işaretliyordu.

Yeniden ölçmek için:

```bash
cd backend
python scripts/calibrate_diff.py --zoom 16 --json ../docs/calibration-z16.json
python scripts/calibrate_diff.py --zoom 16 --bolge fransa --json ../docs/calibration-z16-fransa.json
```

## 4. Kategori kuralları (`anomaly_engine.py`)

- **Sansürlü alan:** bulanıklık puanı 50'yi geçer.
- **Görüntü farkı:** piksel farkı puanı 50'yi geçer, bulanıklık sinyali yoktur.
- **Hayalet bina / gizli yapı:** OSM binaları ile hava görüntüsündeki bina tespitleri karşılaştırılır.
  Yalnız `BUILDING_DETECTOR_WEIGHTS` (hava görüntüsünde bina için eğitilmiş YOLO ağırlıkları) verilirse
  çalışır; `pip install -r requirements-detector.txt` gerekir. Genel amaçlı COCO modeli yukarıdan bina
  tanımadığı için varsayılan olarak kapalıdır.

Eşiği geçen sonuç konum başına tek kayıt olarak saklanır; yeniden taramada güncellenir.

## 5. Tarihsel değişim

`WaybackFetcher` Esri Wayback sürüm listesinden aynı karonun zaman serisini çeker, aynı görüntüyü
döndüren sürümleri (içerik özeti) eler. `TimeSeriesAnalyzer` bu seriyi karşılaştırabilir, ama henüz
tarama akışına ve puana bağlı değildir.
