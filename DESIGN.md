---
version: alpha
name: GhostBuilding
description: Uydu kaynakları arasındaki farkları, kanıt karolarını öne koyarak gösteren karanlık harita arayüzü.
colors:
  primary: "#1A3A5C"
  background: "#0F1117"
  surface: "#181A20"
  card: "#1E2028"
  border: "#2A2D38"
  foreground: "#F0F2F5"
  muted: "#8B8FA3"
  muted-foreground: "#80859A"
  secondary: "#4A7CF7"
  accent: "#E63946"
  censored: "#F4C95D"
  discrepancy: "#6CB4EE"
  ghost: "#F4A261"
  concealed: "#B79CFF"
typography:
  sans:
    fontFamily: Inter
  mono:
    fontFamily: JetBrains Mono
rounded:
  2xl: 1rem
  3xl: 1.25rem
  4xl: 1.5rem
---

## Overview

GhostBuilding aynı konumun farklı uydu kaynaklarındaki karolarını karşılaştırır ve sıradan
konumlara göre sıra dışı olan farkları işaretler. Arayüzün tek işi, bir bulgunun neden
işaretlendiğini kanıtla göstermektir. Karolar yan yana durur, puanın yanında taban çizgisi
görünür, kapalı sinyaller gerekçesiyle yazılır. Ton gece vardiyasındaki bir analiz masasıdır:
karanlık harita, az renk, sayılar eş aralıklı yazılır.

## Colors

- Renk yalnız anlam taşır. Kategori renkleri (`censored`, `discrepancy`, `ghost`,
  `concealed`) yalnız kategori noktasında, etiketinde ve puan çubuğunda kullanılır. Birbirinden
  ve koyu zeminden ayırt edilecek parlaklıktadır.
- `secondary` yalnız etkileşim içindir: bağlantı, seçili altlık, odak halkası, kaydırıcı. `primary`
  (koyu lacivert) yalnız logo degradesinin ve derin yüzeylerin tabanıdır.
- `accent` (kırmızı) yalnız hata içindir. Bir bulguyu "tehlikeli" göstermek için kullanılmaz.
- Puanın "iyi/kötü" rengi yoktur. Anomali puanı olasılık değildir, taban dağılımına göre sıra
  dışılıktır. Yeşil/kırmızı ölçek bunu yanlış okutur.

## Typography

- Koordinat, puan, kayıt kimliği ve zoom `mono` ile, `tabular-nums` kullanılarak yazılır.
  Bunlar karşılaştırılan değerlerdir.
- Metin Türkçedir. Sayılar Türkçe biçimlenir (53,1). Başlıklarda `text-balance` kullanılır.

## Layout

- Ana ekran tam ekran haritadır. Kabuk yalnız kenarlarda durur: üstte arama çubuğu, solda
  katman ve bulgu paneli, altta durum sayıları, sağda bulgu paneli. Bulgu paneli üst çubuğun
  altından başlar.
- Mobilde sol panel bir alt çekmeceye, bulgu paneli tam genişlikli bir yüzeye dönüşür.
- Bulgu sayfasında sol sütun kanıttır (karolar, üst üste karşılaştırma), sağ sütun
  gerekçedir (neden işaretlendi, doğrulama, künye).

## Elevation & Depth

- Cam (yarı saydam yüzey ve bulanıklaştırma) yalnız harita üstündeki yüzen yüzeylerde
  kullanılır: üst çubuk, paneller, alt sayaç. Harita dışındaki sayfalarda yüzeyler
  opaktır (`surface`, `card`) ve `border` ile ayrılır.
- Bulanıklaştırma canlandırılmaz. Harita hareket ederken cam katmanları sabit kalır.

## Components

- **Kanıt karosu:** kare ve siyah zeminlidir. `image-rendering: pixelated` kullanılır, çünkü
  mozaik sansürü yumuşatılırsa kanıt kaybolur. Görseller yeniden sıkıştırılmaz. Altında
  kaynak adı ve kaynağın rengi yazar; karo grubunun altında kaynak atıfları yer alır.
- **Puan ölçeği:** 0–100 çubuğu, 50'de dikey bir çizgi ("sıradan konumların %99'u") ve
  yanında sayının kendisi. Puan gösterilen her yerde bu çizgi de gösterilir.
- **Kapalı sinyal:** çalışmayan bir sinyal gizlenmez. "kapalı" etiketi ve nedeniyle listelenir.

## Do's and Don'ts

- Yapın: Kaynak atıflarını (Esri, MapTiler, IGN, CARTO/OSM) her görüntünün yanında gösterin.
  Kullanım koşulu bunu gerektirir.
- Yapmayın: API'den gelmeyen bir sayıyı göstermeyin. Veri yoksa "—" yazın; demo sayısı,
  "canlı" rozeti ya da uydurma trend kullanmayın.
