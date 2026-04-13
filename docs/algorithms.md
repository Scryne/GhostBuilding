# Detection Algorithms Explained

GhostBuilding uses a hybrid approach of geospatial data cross-referencing and computer vision techniques.

## 1. Pixel Discrepancy (PixelDiffAnalyzer)
We use Structural Similarity Index Measure (SSIM) and absolute color histogram separation to find identical coordinates that look completely different between Google and Bing.
* **Why:** Identifies updated imagery vs old imagery, or intentional obfuscation by a provider.

## 2. Blur / Censorship (BlurDetector)
Military bases and prisons are often deliberately pixelated or blurred by state orders.
* **Laplacian Variance:** Measures the sharpness of a tile. A sudden, localized drop in variance strictly within an otherwise sharp tile triggers a `CENSORED_AREA` flag.
* **Frequency Analysis (FFT):** High-frequency data loss analysis detects unnatural pixel blocks.

## 3. Geospatial Mismatch (GeospatialAnalyzer)
We query the OpenStreetMap Overpass API for all tags `building=*` and compare the polygons with Satellite tiles.
* **Ghost building:** OSM has a building, satellite shows nothing (ruins or fake data).
* **Hidden structure:** Computer vision detects a building roof, but OSM has no records (clandestine facility).

## 4. Time Series Analysis
Using NASA GIBS and Wayback Machine tile scrapers, we analyze identical coordinates chronologically.
* **Why:** Detects massive topographical changes over short periods indicating excavations, bunkers, or military buildup.
