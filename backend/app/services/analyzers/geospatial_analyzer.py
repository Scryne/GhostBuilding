"""
geospatial_analyzer.py — OSM vektör verisi ile uydu görüntüsü karşılaştırma modülü.

OpenStreetMap bina verilerini YOLO v8 nano ile uydu görüntüsünden tespit
edilen yapılarla karşılaştırarak "ghost building" (hayalet bina) ve
"hidden structure" (gizli yapı) anomalilerini tespit eder.

Modül üç ana bileşenden oluşur:
  - BuildingDetector: YOLO v8 ile uydu görüntüsünden bina tespiti
  - GeospatialAnalyzer: OSM ↔ uydu karşılaştırması ve anomali tespiti
  - Veri sınıfları: Detection, GhostBuilding, HiddenStructure, AnomalyCandidate
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

# YOLO model ayarları
YOLO_MODEL_NAME: str = "yolov8n.pt"
YOLO_CONFIDENCE_THRESHOLD: float = 0.4
YOLO_BUILDING_CLASS_ID: int = 12       # COCO dataset: class 12 ≈ building ilişkili
YOLO_IOU_NMS_THRESHOLD: float = 0.45   # Non-maximum suppression IoU eşiği

# Ghost building / Hidden structure eşikleri
GHOST_IOU_THRESHOLD: float = 0.1       # IoU < 0.1 → ghost building
HIDDEN_IOU_THRESHOLD: float = 0.1      # IoU < 0.1 → hidden structure
HIDDEN_CONFIDENCE_MIN: float = 0.6     # Gizli yapı için minimum confidence

# Coverage (kapsam) analiz eşikleri
COVERAGE_LOW_THRESHOLD: float = 0.3    # Kapsam < %30 → sistematik gizleme şüphesi
COVERAGE_CRITICAL_THRESHOLD: float = 0.1  # Kapsam < %10 → yüksek şüphe

# Anomali kategorileri
CATEGORY_GHOST_BUILDING: str = "ghost_building"
CATEGORY_HIDDEN_STRUCTURE: str = "hidden_structure"
CATEGORY_COVERAGE_ANOMALY: str = "coverage_anomaly"

# Derece → metre dönüşüm sabiti
METERS_PER_DEGREE_LAT: float = 111_320.0


# ---------------------------------------------------------------------------
# Veri sınıfları
# ---------------------------------------------------------------------------


@dataclass
class BBox:
    """Eksen hizalı sınırlayıcı kutu (piksel koordinatları).

    Attributes:
        x1: Sol üst köşe X (piksel).
        y1: Sol üst köşe Y (piksel).
        x2: Sağ alt köşe X (piksel).
        y2: Sağ alt köşe Y (piksel).
    """

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        """Kutu genişliği (piksel)."""
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        """Kutu yüksekliği (piksel)."""
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        """Kutu alanı (piksel²)."""
        return max(0.0, self.width) * max(0.0, self.height)

    @property
    def center(self) -> Tuple[float, float]:
        """Merkez noktası (x, y) piksel."""
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "x1": round(self.x1, 1),
            "y1": round(self.y1, 1),
            "x2": round(self.x2, 1),
            "y2": round(self.y2, 1),
            "width": round(self.width, 1),
            "height": round(self.height, 1),
            "area": round(self.area, 1),
        }


@dataclass
class GeoBBox:
    """Coğrafi sınırlayıcı kutu (derece koordinatları).

    Attributes:
        south: Güney sınırı (enlem).
        west: Batı sınırı (boylam).
        north: Kuzey sınırı (enlem).
        east: Doğu sınırı (boylam).
    """

    south: float
    west: float
    north: float
    east: float

    @property
    def center_lat(self) -> float:
        """Merkez enlemi."""
        return (self.south + self.north) / 2

    @property
    def center_lng(self) -> float:
        """Merkez boylamı."""
        return (self.west + self.east) / 2

    @property
    def width_deg(self) -> float:
        """Genişlik (derece)."""
        return self.east - self.west

    @property
    def height_deg(self) -> float:
        """Yükseklik (derece)."""
        return self.north - self.south

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "south": round(self.south, 6),
            "west": round(self.west, 6),
            "north": round(self.north, 6),
            "east": round(self.east, 6),
        }


@dataclass
class Detection:
    """YOLO model tespiti sonucu.

    Attributes:
        bbox: Piksel koordinatlarında sınırlayıcı kutu.
        confidence: Tespit güven skoru (0–1).
        class_id: COCO sınıf ID'si.
        class_name: Sınıf adı.
    """

    bbox: BBox
    confidence: float
    class_id: int
    class_name: str

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "bbox": self.bbox.to_dict(),
            "confidence": round(self.confidence, 4),
            "class_id": self.class_id,
            "class_name": self.class_name,
        }


@dataclass
class GhostBuilding:
    """OSM'de kayıtlı ama uydu görüntüsünde tespit edilemeyen bina.

    "Ghost building" — haritada var ama gerçekte olmayabilecek yapı.
    Hatalı OSM verisi, yıkılmış bina veya kasıtlı sahte veri olabilir.

    Attributes:
        osm_id: OSM element ID'si.
        osm_type: OSM element tipi ("way" | "relation").
        building_type: OSM'deki bina türü.
        centroid: Bina merkezi (lat, lng).
        area_m2: OSM'deki bina alanı (m²).
        best_iou: En yakın YOLO tespiti ile IoU değeri.
        ghost_score: Hayalet bina şüphesi skoru (0–100).
        is_sensitive: Hassas yapı mı (askeri vb.).
        reason: Neden ghost kabul edildiği.
    """

    osm_id: int
    osm_type: str
    building_type: str
    centroid: Tuple[float, float]
    area_m2: float
    best_iou: float
    ghost_score: float
    is_sensitive: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "osm_id": self.osm_id,
            "osm_type": self.osm_type,
            "building_type": self.building_type,
            "centroid": {"lat": self.centroid[0], "lng": self.centroid[1]},
            "area_m2": round(self.area_m2, 2),
            "best_iou": round(self.best_iou, 4),
            "ghost_score": round(self.ghost_score, 2),
            "is_sensitive": self.is_sensitive,
            "reason": self.reason,
        }


@dataclass
class HiddenStructure:
    """Uydu görüntüsünde tespit edilen ama OSM'de kayıtlı olmayan yapı.

    "Hidden structure" — uydudan görülen ama haritada bulunmayan yapı.
    Kasıtlı gizleme, yeni inşaat veya sınıflandırılmamış yapı olabilir.

    Attributes:
        detection: YOLO tespit bilgisi.
        geo_bbox: Coğrafi koordinatlardaki konum.
        center_geo: Merkez noktası (lat, lng).
        best_iou: En yakın OSM binası ile IoU değeri.
        hidden_score: Gizli yapı şüphesi skoru (0–100).
        reason: Neden hidden kabul edildiği.
    """

    detection: Detection
    geo_bbox: Optional[GeoBBox]
    center_geo: Optional[Tuple[float, float]]
    best_iou: float
    hidden_score: float
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        result: Dict[str, Any] = {
            "detection": self.detection.to_dict(),
            "best_iou": round(self.best_iou, 4),
            "hidden_score": round(self.hidden_score, 2),
            "reason": self.reason,
        }
        if self.geo_bbox:
            result["geo_bbox"] = self.geo_bbox.to_dict()
        if self.center_geo:
            result["center_geo"] = {
                "lat": self.center_geo[0],
                "lng": self.center_geo[1],
            }
        return result


@dataclass
class AnomalyCandidate:
    """Anomali motoru için aday sonuç.

    GeospatialAnalyzer çıktısını anomali motoruna aktarmak için
    standart veri yapısı.

    Attributes:
        category: Anomali kategorisi (ghost_building | hidden_structure | coverage_anomaly).
        lat: Anomalinin enlemi.
        lng: Anomalinin boylamı.
        confidence_score: Güven skoru (0–100).
        title: Kısa başlık.
        description: Detaylı açıklama.
        source_providers: İlgili veri kaynakları.
        detection_methods: Kullanılan tespit yöntemleri.
        meta_data: Ek metaveriler.
    """

    category: str
    lat: float
    lng: float
    confidence_score: float
    title: str
    description: str
    source_providers: List[str] = field(default_factory=list)
    detection_methods: List[str] = field(default_factory=list)
    meta_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "category": self.category,
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "confidence_score": round(self.confidence_score, 2),
            "title": self.title,
            "description": self.description,
            "source_providers": self.source_providers,
            "detection_methods": self.detection_methods,
            "meta_data": self.meta_data,
        }


@dataclass
class GeospatialResult:
    """GeospatialAnalyzer.analyze() tam sonucu.

    Attributes:
        ghost_buildings: Hayalet bina listesi.
        hidden_structures: Gizli yapı listesi.
        osm_building_count: OSM'deki toplam bina sayısı.
        detected_building_count: YOLO tespiti bina sayısı.
        coverage_ratio: OSM / tespit kapsam oranı.
        anomaly_candidates: Anomali motoru için aday listesi.
        summary: İnsan okunabilir özet.
    """

    ghost_buildings: List[GhostBuilding]
    hidden_structures: List[HiddenStructure]
    osm_building_count: int
    detected_building_count: int
    coverage_ratio: float
    anomaly_candidates: List[AnomalyCandidate]
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        """Sözlük temsiline dönüştürür."""
        return {
            "osm_building_count": self.osm_building_count,
            "detected_building_count": self.detected_building_count,
            "coverage_ratio": round(self.coverage_ratio, 4),
            "num_ghost_buildings": len(self.ghost_buildings),
            "num_hidden_structures": len(self.hidden_structures),
            "num_anomaly_candidates": len(self.anomaly_candidates),
            "summary": self.summary,
            "ghost_buildings": [g.to_dict() for g in self.ghost_buildings],
            "hidden_structures": [h.to_dict() for h in self.hidden_structures],
            "anomaly_candidates": [a.to_dict() for a in self.anomaly_candidates],
        }


# ---------------------------------------------------------------------------
# Yardımcı: IoU hesaplama
# ---------------------------------------------------------------------------


def compute_iou(box_a: BBox, box_b: BBox) -> float:
    """İki sınırlayıcı kutu arasındaki IoU (Intersection over Union) hesaplar.

    Args:
        box_a: Birinci sınırlayıcı kutu.
        box_b: İkinci sınırlayıcı kutu.

    Returns:
        IoU değeri (0–1). 0 = hiç kesişim yok, 1 = tamamen örtüşüyor.
    """
    # Kesişim alanı
    inter_x1 = max(box_a.x1, box_b.x1)
    inter_y1 = max(box_a.y1, box_b.y1)
    inter_x2 = min(box_a.x2, box_b.x2)
    inter_y2 = min(box_a.y2, box_b.y2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    # Birleşim alanı
    union_area = box_a.area + box_b.area - inter_area

    if union_area <= 0:
        return 0.0

    return inter_area / union_area


def compute_iou_geo(
    geo_a: GeoBBox,
    geo_b: GeoBBox,
) -> float:
    """İki coğrafi bbox arasındaki IoU hesaplar (derece koordinatları).

    Args:
        geo_a: Birinci coğrafi bbox.
        geo_b: İkinci coğrafi bbox.

    Returns:
        IoU değeri (0–1).
    """
    inter_south = max(geo_a.south, geo_b.south)
    inter_west = max(geo_a.west, geo_b.west)
    inter_north = min(geo_a.north, geo_b.north)
    inter_east = min(geo_a.east, geo_b.east)

    inter_w = max(0.0, inter_east - inter_west)
    inter_h = max(0.0, inter_north - inter_south)
    inter_area = inter_w * inter_h

    area_a = geo_a.width_deg * geo_a.height_deg
    area_b = geo_b.width_deg * geo_b.height_deg
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0

    return inter_area / union_area


# ---------------------------------------------------------------------------
# Yardımcı: Koordinat dönüşümleri
# ---------------------------------------------------------------------------


def pixel_to_geo(
    px: float,
    py: float,
    image_width: int,
    image_height: int,
    geo_bbox: GeoBBox,
) -> Tuple[float, float]:
    """Piksel koordinatını coğrafi koordinata dönüştürür.

    Args:
        px: X piksel koordinatı.
        py: Y piksel koordinatı.
        image_width: Görüntü genişliği (piksel).
        image_height: Görüntü yüksekliği (piksel).
        geo_bbox: Görüntünün coğrafi sınırları.

    Returns:
        (lat, lng) coğrafi koordinat çifti.
    """
    # X → boylam (soldan sağa artar)
    lng = geo_bbox.west + (px / image_width) * geo_bbox.width_deg

    # Y → enlem (yukarıdan aşağıya azalır)
    lat = geo_bbox.north - (py / image_height) * geo_bbox.height_deg

    return (lat, lng)


def pixel_bbox_to_geo(
    bbox: BBox,
    image_width: int,
    image_height: int,
    geo_bbox: GeoBBox,
) -> GeoBBox:
    """Piksel bbox'ı coğrafi bbox'a dönüştürür.

    Args:
        bbox: Piksel koordinatlarında sınırlayıcı kutu.
        image_width: Görüntü genişliği (piksel).
        image_height: Görüntü yüksekliği (piksel).
        geo_bbox: Görüntünün tam coğrafi sınırları.

    Returns:
        Coğrafi sınırlayıcı kutu.
    """
    lat_top, lng_left = pixel_to_geo(
        bbox.x1, bbox.y1, image_width, image_height, geo_bbox
    )
    lat_bottom, lng_right = pixel_to_geo(
        bbox.x2, bbox.y2, image_width, image_height, geo_bbox
    )

    return GeoBBox(
        south=min(lat_top, lat_bottom),
        west=min(lng_left, lng_right),
        north=max(lat_top, lat_bottom),
        east=max(lng_left, lng_right),
    )


def osm_geometry_to_geo_bbox(geometry: Dict[str, Any]) -> Optional[GeoBBox]:
    """OSM GeoJSON Polygon geometrisinden coğrafi bbox hesaplar.

    Args:
        geometry: GeoJSON Polygon geometrisi.

    Returns:
        GeoBBox veya geçersiz geometride None.
    """
    if geometry.get("type") != "Polygon":
        return None

    coords = geometry.get("coordinates", [[]])
    if not coords or not coords[0]:
        return None

    ring = coords[0]  # Dış halka
    lngs = [c[0] for c in ring]
    lats = [c[1] for c in ring]

    return GeoBBox(
        south=min(lats),
        west=min(lngs),
        north=max(lats),
        east=max(lngs),
    )


def tile_bbox_from_center(
    lat: float,
    lng: float,
    zoom: int,
    tile_size: int = 256,
) -> GeoBBox:
    """Merkez koordinat ve zoom seviyesinden tile coğrafi bbox hesaplar.

    Slippy map tile standartına göre yaklaşık bbox hesaplar.

    Args:
        lat: Merkez enlemi.
        lng: Merkez boylamı.
        zoom: Harita zoom seviyesi.
        tile_size: Tile piksel boyutu (varsayılan 256).

    Returns:
        Tile'ın coğrafi sınırları.
    """
    # Bir piksel kaç derece (yaklaşık)
    meters_per_pixel = (
        156543.03392 * math.cos(math.radians(lat)) / (2 ** zoom)
    )
    half_size_meters = (tile_size / 2) * meters_per_pixel

    # Metre → derece dönüşümü
    lat_offset = half_size_meters / METERS_PER_DEGREE_LAT
    lng_offset = half_size_meters / (
        METERS_PER_DEGREE_LAT * math.cos(math.radians(lat))
    )

    return GeoBBox(
        south=lat - lat_offset,
        west=lng - lng_offset,
        north=lat + lat_offset,
        east=lng + lng_offset,
    )


# ---------------------------------------------------------------------------
# BuildingDetector — YOLO v8 ile bina tespiti
# ---------------------------------------------------------------------------


class BuildingDetector:
    """YOLO v8 nano modeli ile uydu görüntüsünden bina tespiti yapar.

    ultralytics YOLO("yolov8n.pt") modelini yükleyerek uydu
    görüntülerindeki bina yapılarını tespit eder. COCO dataset'te
    doğrudan "building" sınıfı olmadığından, ilgili sınıfları
    (house, building benzeri) ve genel nesne tespitini kullanır.

    Not: COCO dataset'te building doğrudan yoktur. Bu nedenle
    model, yapay ortamda fine-tune edilmişse class_id değişebilir.
    Varsayılan olarak tüm tespitler alınarak filtreleme yapılır.

    Attributes:
        _model: YOLO model objesi (lazy loading).
        _confidence_threshold: Minimum güven skoru eşiği.
        _model_name: Yüklenecek model dosyası adı.
        _target_classes: Hedef sınıf ID'leri (None ise tümü).

    Examples:
        >>> detector = BuildingDetector()
        >>> detections = detector.detect_buildings(satellite_image)
        >>> for d in detections:
        ...     print(d.class_name, d.confidence)
    """

    # COCO sınıflarından yapı ile ilişkilendirilebilecek olanlar
    # 0: person, ... tam listeden yapı ilişkili olanlar seçilir
    # Gerçek projede fine-tuned model kullanılması önerilir
    _BUILDING_RELATED_CLASSES: Dict[int, str] = {
        # COCO'da doğrudan building yok, ancak şu sınıflar
        # uydu görüntüsünde yapı göstergesi olabilir:
        # Fine-tuned modelde bu ID building'e map edilir
    }

    def __init__(
        self,
        *,
        model_name: str = YOLO_MODEL_NAME,
        confidence_threshold: float = YOLO_CONFIDENCE_THRESHOLD,
        target_classes: Optional[List[int]] = None,
    ) -> None:
        """
        Args:
            model_name: YOLO model dosyası adı (ör. "yolov8n.pt").
            confidence_threshold: Minimum tespit güven skoru (0–1).
            target_classes: Hedef sınıf ID listesi. None ise tüm
                tespitler döndürülür.
        """
        self._model = None
        self._model_name = model_name
        self._confidence_threshold = confidence_threshold
        self._target_classes = target_classes

    def load_model(self) -> None:
        """YOLO v8 modelini yükler.

        İlk çağrıda modeli indirir/yükler ve önbelleğe alır.
        Sonraki çağrılar no-op'tur.

        Raises:
            ImportError: ultralytics paketi yüklü değilse.
            RuntimeError: Model dosyası yüklenemezse.

        Examples:
            >>> detector = BuildingDetector()
            >>> detector.load_model()
        """
        if self._model is not None:
            logger.debug("YOLO modeli zaten yüklü, atlanıyor")
            return

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "YOLO v8 için 'ultralytics' paketi gerekli. "
                "Yüklemek için: pip install ultralytics"
            ) from exc

        logger.info("YOLO modeli yükleniyor: %s", self._model_name)

        try:
            self._model = YOLO(self._model_name)
            logger.info(
                "YOLO modeli başarıyla yüklendi: %s (sınıf sayısı: %d)",
                self._model_name,
                len(self._model.names) if hasattr(self._model, "names") else -1,
            )
        except Exception as exc:
            raise RuntimeError(
                f"YOLO modeli yüklenemedi: {self._model_name} — {exc}"
            ) from exc

    def _ensure_model(self) -> None:
        """Model yüklüyse geçer, değilse yükler."""
        if self._model is None:
            self.load_model()

    def detect_buildings(
        self,
        satellite_image: Image.Image,
        *,
        confidence_threshold: Optional[float] = None,
    ) -> List[Detection]:
        """Uydu görüntüsünden bina/yapı tespiti yapar.

        YOLO v8 modelini çalıştırarak görüntüdeki nesneleri tespit eder.
        Sonuçlar confidence eşiğine göre filtrelenir ve Detection listesi
        olarak döndürülür.

        Args:
            satellite_image: Analiz edilecek uydu görüntüsü (PIL Image).
            confidence_threshold: Override confidence eşiği. None ise
                varsayılan kullanılır.

        Returns:
            Detection listesi (confidence'a göre azalan sırala).

        Examples:
            >>> detector = BuildingDetector()
            >>> detections = detector.detect_buildings(sat_image)
            >>> print(f"Tespit: {len(detections)} yapı")
        """
        self._ensure_model()

        conf_thresh = confidence_threshold or self._confidence_threshold

        # RGB'ye dönüştür
        img_rgb = satellite_image.convert("RGB")
        img_array = np.array(img_rgb)

        logger.info(
            "YOLO tespiti başlatılıyor: boyut=%dx%d, eşik=%.2f",
            img_rgb.width, img_rgb.height, conf_thresh,
        )

        # YOLO çıkarımı
        results = self._model(
            img_array,
            conf=conf_thresh,
            iou=YOLO_IOU_NMS_THRESHOLD,
            verbose=False,
        )

        detections: List[Detection] = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for i in range(len(boxes)):
                # Sınıf ID ve güven skoru
                class_id = int(boxes.cls[i].item())
                confidence = float(boxes.conf[i].item())

                # Hedef sınıf filtresi
                if (
                    self._target_classes is not None
                    and class_id not in self._target_classes
                ):
                    continue

                # Bbox koordinatları (x1, y1, x2, y2)
                xyxy = boxes.xyxy[i].cpu().numpy()
                bbox = BBox(
                    x1=float(xyxy[0]),
                    y1=float(xyxy[1]),
                    x2=float(xyxy[2]),
                    y2=float(xyxy[3]),
                )

                # Sınıf adı
                class_name = (
                    self._model.names.get(class_id, f"class_{class_id}")
                    if hasattr(self._model, "names")
                    else f"class_{class_id}"
                )

                detections.append(
                    Detection(
                        bbox=bbox,
                        confidence=confidence,
                        class_id=class_id,
                        class_name=class_name,
                    )
                )

        # Confidence'a göre azalan sırala
        detections.sort(key=lambda d: d.confidence, reverse=True)

        logger.info(
            "YOLO tespiti tamamlandı: %d nesne bulundu (eşik=%.2f)",
            len(detections), conf_thresh,
        )

        return detections

    def detections_to_geojson(
        self,
        detections: List[Detection],
        geo_bbox: GeoBBox,
        image_width: int,
        image_height: int,
    ) -> Dict[str, Any]:
        """Tespit sonuçlarını GeoJSON FeatureCollection'a dönüştürür.

        Piksel koordinatlarındaki bbox'ları coğrafi koordinatlara
        dönüştürerek her tespiti GeoJSON Point Feature olarak kodlar.

        Args:
            detections: YOLO tespit listesi.
            geo_bbox: Görüntünün coğrafi sınırları.
            image_width: Görüntü genişliği (piksel).
            image_height: Görüntü yüksekliği (piksel).

        Returns:
            GeoJSON FeatureCollection sözlüğü.

        Examples:
            >>> geojson = detector.detections_to_geojson(
            ...     detections, geo_bbox, 256, 256
            ... )
            >>> geojson["type"]
            'FeatureCollection'
        """
        features: List[Dict[str, Any]] = []

        for idx, det in enumerate(detections):
            # Piksel merkez → coğrafi koordinat
            center_px = det.bbox.center
            lat, lng = pixel_to_geo(
                center_px[0], center_px[1],
                image_width, image_height,
                geo_bbox,
            )

            # Piksel bbox → coğrafi bbox
            det_geo = pixel_bbox_to_geo(
                det.bbox, image_width, image_height, geo_bbox
            )

            feature: Dict[str, Any] = {
                "type": "Feature",
                "id": f"detection_{idx}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lng, lat],
                },
                "properties": {
                    "detection_id": idx,
                    "class_id": det.class_id,
                    "class_name": det.class_name,
                    "confidence": round(det.confidence, 4),
                    "bbox_geo": det_geo.to_dict(),
                    "bbox_pixel": det.bbox.to_dict(),
                },
            }
            features.append(feature)

        return {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "total_detections": len(features),
                "geo_bbox": geo_bbox.to_dict(),
                "image_size": {
                    "width": image_width,
                    "height": image_height,
                },
            },
        }


# ---------------------------------------------------------------------------
# GeospatialAnalyzer — OSM ↔ Uydu karşılaştırması
# ---------------------------------------------------------------------------


class GeospatialAnalyzer:
    """OSM bina verilerini uydu görüntüsü tespitleriyle karşılaştırır.

    Ghost building (hayalet bina) ve hidden structure (gizli yapı)
    anomalilerini tespit eder. Kapsam oranı analizi ile sistematik
    gizleme şüphesini değerlendirir.

    Attributes:
        _building_detector: YOLO bina tespit modülü.
        _ghost_iou_threshold: Ghost building IoU eşiği.
        _hidden_iou_threshold: Hidden structure IoU eşiği.

    Examples:
        >>> analyzer = GeospatialAnalyzer()
        >>> result = analyzer.analyze(
        ...     lat=41.0082, lng=28.9784, zoom=16,
        ...     osm_buildings=osm_data, satellite_image=sat_img,
        ... )
        >>> print(f"Ghost: {len(result.ghost_buildings)}")
        >>> print(f"Hidden: {len(result.hidden_structures)}")
    """

    def __init__(
        self,
        *,
        building_detector: Optional[BuildingDetector] = None,
        ghost_iou_threshold: float = GHOST_IOU_THRESHOLD,
        hidden_iou_threshold: float = HIDDEN_IOU_THRESHOLD,
    ) -> None:
        """
        Args:
            building_detector: Kullanılacak BuildingDetector. None ise
                varsayılan oluşturulur.
            ghost_iou_threshold: Ghost building IoU eşiği. Altındaki
                OSM binaları ghost kabul edilir.
            hidden_iou_threshold: Hidden structure IoU eşiği. Altındaki
                YOLO tespitleri hidden kabul edilir.
        """
        self._building_detector = building_detector or BuildingDetector()
        self._ghost_iou_threshold = ghost_iou_threshold
        self._hidden_iou_threshold = hidden_iou_threshold

    # ------------------------------------------------------------------ #
    # analyze — Ana analiz metodu
    # ------------------------------------------------------------------ #

    def analyze(
        self,
        lat: float,
        lng: float,
        zoom: int,
        osm_buildings: List[Dict[str, Any]],
        satellite_image: Image.Image,
    ) -> GeospatialResult:
        """Tam mekansal analiz çalıştırır.

        1. YOLO ile uydu görüntüsünden bina tespit eder.
        2. OSM binaları ile karşılaştırarak ghost building bulur.
        3. YOLO tespitleri ile karşılaştırarak hidden structure bulur.
        4. Kapsam oranını hesaplar.
        5. Tüm sonuçları AnomalyCandidate listesine dönüştürür.

        Args:
            lat: Merkez enlemi.
            lng: Merkez boylamı.
            zoom: Harita zoom seviyesi.
            osm_buildings: OSM Building dataclass'larının sözlük temsilleri
                veya Building objeleri. Her eleman en az şu alanlara sahip
                olmalı: osm_id, osm_type, building_type, geometry, centroid,
                area_m2, is_sensitive.
            satellite_image: Uydu/harita tile görüntüsü (PIL Image).

        Returns:
            GeospatialResult — tam analiz sonuçları.

        Examples:
            >>> analyzer = GeospatialAnalyzer()
            >>> result = analyzer.analyze(41.0, 28.9, 16, osm_data, sat_img)
            >>> result.coverage_ratio
            0.75
        """
        img_w, img_h = satellite_image.size

        # Tile coğrafi sınırları
        geo_bbox = tile_bbox_from_center(lat, lng, zoom, tile_size=img_w)

        logger.info(
            "Mekansal analiz başlatılıyor: (%.4f, %.4f), zoom=%d, "
            "OSM bina=%d, görüntü=%dx%d",
            lat, lng, zoom, len(osm_buildings), img_w, img_h,
        )

        # --- 1. YOLO bina tespiti ---
        detected = self._building_detector.detect_buildings(satellite_image)

        logger.info(
            "YOLO tespiti: %d nesne bulundu", len(detected)
        )

        # OSM binalarının coğrafi bbox'larını hesapla
        osm_geo_bboxes = self._extract_osm_bboxes(osm_buildings)

        # YOLO tespitlerinin coğrafi bbox'larını hesapla
        detected_geo_bboxes = [
            pixel_bbox_to_geo(d.bbox, img_w, img_h, geo_bbox)
            for d in detected
        ]

        # --- 2. Ghost buildings ---
        ghosts = self.find_ghost_buildings(
            osm_buildings, osm_geo_bboxes,
            detected, detected_geo_bboxes,
        )

        # --- 3. Hidden structures ---
        hidden = self.find_hidden_structures(
            osm_buildings, osm_geo_bboxes,
            detected, detected_geo_bboxes,
            geo_bbox, img_w, img_h,
        )

        # --- 4. Kapsam oranı ---
        coverage = self.compute_coverage_ratio(
            osm_building_count=len(osm_buildings),
            detected_count=len(detected),
        )

        # --- 5. Anomali adaylarına dönüştür ---
        candidates: List[AnomalyCandidate] = []

        # Ghost building adayları
        for ghost in ghosts:
            candidates.append(
                AnomalyCandidate(
                    category=CATEGORY_GHOST_BUILDING,
                    lat=ghost.centroid[0],
                    lng=ghost.centroid[1],
                    confidence_score=ghost.ghost_score,
                    title=f"Hayalet Bina: {ghost.building_type}",
                    description=(
                        f"OSM ID {ghost.osm_id} ({ghost.osm_type}) — "
                        f"haritada kayıtlı ({ghost.area_m2:.0f} m²) ama "
                        f"uydu görüntüsünde tespit edilemedi. "
                        f"IoU: {ghost.best_iou:.3f}. {ghost.reason}"
                    ),
                    source_providers=["osm", "satellite"],
                    detection_methods=["geospatial_cross_reference", "yolo_v8"],
                    meta_data=ghost.to_dict(),
                )
            )

        # Hidden structure adayları
        for hs in hidden:
            center = hs.center_geo or (lat, lng)
            candidates.append(
                AnomalyCandidate(
                    category=CATEGORY_HIDDEN_STRUCTURE,
                    lat=center[0],
                    lng=center[1],
                    confidence_score=hs.hidden_score,
                    title=f"Gizli Yapi: {hs.detection.class_name}",
                    description=(
                        f"Uydu görüntüsünde tespit edildi "
                        f"(confidence: {hs.detection.confidence:.2f}) ama "
                        f"OSM'de kayitli degil. "
                        f"IoU: {hs.best_iou:.3f}. {hs.reason}"
                    ),
                    source_providers=["satellite"],
                    detection_methods=["yolo_v8", "geospatial_cross_reference"],
                    meta_data=hs.to_dict(),
                )
            )

        # Kapsam anomalisi adayı
        if coverage < COVERAGE_LOW_THRESHOLD and len(osm_buildings) > 0:
            cov_score = self._coverage_to_score(coverage)
            candidates.append(
                AnomalyCandidate(
                    category=CATEGORY_COVERAGE_ANOMALY,
                    lat=lat,
                    lng=lng,
                    confidence_score=cov_score,
                    title="Dusuk Kapsam Orani",
                    description=(
                        f"OSM bina sayisi ({len(osm_buildings)}) ile uydu "
                        f"tespiti ({len(detected)}) arasinda buyuk fark var. "
                        f"Kapsam orani: {coverage:.1%}. "
                        f"Sistematik gizleme suphesi."
                    ),
                    source_providers=["osm", "satellite"],
                    detection_methods=["coverage_analysis"],
                    meta_data={
                        "osm_count": len(osm_buildings),
                        "detected_count": len(detected),
                        "coverage_ratio": round(coverage, 4),
                    },
                )
            )

        # Özet oluştur
        summary = self._build_summary(
            ghosts, hidden, coverage,
            len(osm_buildings), len(detected),
        )

        result = GeospatialResult(
            ghost_buildings=ghosts,
            hidden_structures=hidden,
            osm_building_count=len(osm_buildings),
            detected_building_count=len(detected),
            coverage_ratio=coverage,
            anomaly_candidates=candidates,
            summary=summary,
        )

        logger.info(
            "Mekansal analiz tamamlandi: ghost=%d, hidden=%d, "
            "coverage=%.2f, aday=%d",
            len(ghosts), len(hidden), coverage, len(candidates),
        )

        return result

    # ------------------------------------------------------------------ #
    # find_ghost_buildings — Hayalet bina tespiti
    # ------------------------------------------------------------------ #

    def find_ghost_buildings(
        self,
        osm_buildings: List[Dict[str, Any]],
        osm_geo_bboxes: List[Optional[GeoBBox]],
        detected: List[Detection],
        detected_geo_bboxes: List[GeoBBox],
    ) -> List[GhostBuilding]:
        """OSM'de kayitli ama uydu görüntüsünde tespit edilemeyen binalari bulur.

        Her OSM binasi icin en yakin YOLO tespiti ile IoU hesaplar.
        IoU < ghost_iou_threshold olan binalar "ghost building" olarak
        isaretlenir.

        Args:
            osm_buildings: OSM bina verileri (sozluk listesi).
            osm_geo_bboxes: Her OSM binasinin cografi bbox'i.
            detected: YOLO tespit listesi.
            detected_geo_bboxes: Her tespitin cografi bbox'i.

        Returns:
            GhostBuilding listesi (ghost_score'a gore azalan sirada).

        Examples:
            >>> ghosts = analyzer.find_ghost_buildings(
            ...     osm_data, osm_bboxes, detections, det_bboxes
            ... )
            >>> for g in ghosts:
            ...     print(f"Ghost: OSM {g.osm_id}, score={g.ghost_score}")
        """
        ghosts: List[GhostBuilding] = []

        for idx, osm_b in enumerate(osm_buildings):
            osm_bbox = osm_geo_bboxes[idx] if idx < len(osm_geo_bboxes) else None

            if osm_bbox is None:
                continue

            # Bu OSM binasina en yakin YOLO tespitini bul
            best_iou = 0.0
            for det_bbox in detected_geo_bboxes:
                iou = compute_iou_geo(osm_bbox, det_bbox)
                best_iou = max(best_iou, iou)

            # Ghost esigi kontrolu
            if best_iou < self._ghost_iou_threshold:
                # Ghost building skoru hesapla
                ghost_score = self._compute_ghost_score(
                    osm_b, best_iou, len(detected)
                )

                # Bina bilgilerini cikar
                osm_id = osm_b.get("osm_id", 0)
                if hasattr(osm_b, "osm_id"):
                    osm_id = osm_b.osm_id

                osm_type = osm_b.get("osm_type", "way")
                if hasattr(osm_b, "osm_type"):
                    osm_type = osm_b.osm_type

                building_type = osm_b.get("building_type", "unknown")
                if hasattr(osm_b, "building_type"):
                    building_type = osm_b.building_type

                centroid = osm_b.get("centroid", (0.0, 0.0))
                if hasattr(osm_b, "centroid"):
                    centroid = osm_b.centroid
                elif isinstance(centroid, dict):
                    centroid = (centroid.get("lat", 0.0), centroid.get("lng", 0.0))

                area_m2 = osm_b.get("area_m2", 0.0)
                if hasattr(osm_b, "area_m2"):
                    area_m2 = osm_b.area_m2

                is_sensitive = osm_b.get("is_sensitive", False)
                if hasattr(osm_b, "is_sensitive"):
                    is_sensitive = osm_b.is_sensitive

                reason = self._ghost_reason(best_iou, is_sensitive, area_m2)

                ghosts.append(
                    GhostBuilding(
                        osm_id=osm_id,
                        osm_type=osm_type,
                        building_type=building_type,
                        centroid=centroid,
                        area_m2=area_m2,
                        best_iou=best_iou,
                        ghost_score=ghost_score,
                        is_sensitive=is_sensitive,
                        reason=reason,
                    )
                )

        # Ghost score'a gore azalan sirala
        ghosts.sort(key=lambda g: g.ghost_score, reverse=True)

        logger.info(
            "Ghost building tespiti: %d/%d OSM binasi ghost olarak isaretlendi",
            len(ghosts), len(osm_buildings),
        )

        return ghosts

    # ------------------------------------------------------------------ #
    # find_hidden_structures — Gizli yapi tespiti
    # ------------------------------------------------------------------ #

    def find_hidden_structures(
        self,
        osm_buildings: List[Dict[str, Any]],
        osm_geo_bboxes: List[Optional[GeoBBox]],
        detected: List[Detection],
        detected_geo_bboxes: List[GeoBBox],
        image_geo_bbox: GeoBBox,
        image_width: int,
        image_height: int,
    ) -> List[HiddenStructure]:
        """Uydu görüntüsünde tespit edilen ama OSM'de kayitli olmayan yapilari bulur.

        Her YOLO tespiti icin en yakin OSM binasi ile IoU hesaplar.
        IoU < hidden_iou_threshold VE confidence > HIDDEN_CONFIDENCE_MIN
        olan tespitler "hidden structure" olarak isaretlenir.

        Args:
            osm_buildings: OSM bina verileri.
            osm_geo_bboxes: Her OSM binasinin cografi bbox'i.
            detected: YOLO tespit listesi.
            detected_geo_bboxes: Her tespitin cografi bbox'i.
            image_geo_bbox: Goruntuunun cografi siniri.
            image_width: Goruntu genisligi (piksel).
            image_height: Goruntu yuksekligi (piksel).

        Returns:
            HiddenStructure listesi (hidden_score'a gore azalan sirada).
        """
        hidden: List[HiddenStructure] = []

        valid_osm_bboxes = [b for b in osm_geo_bboxes if b is not None]

        for idx, det in enumerate(detected):
            # Minimum confidence filtresi
            if det.confidence < HIDDEN_CONFIDENCE_MIN:
                continue

            det_geo = detected_geo_bboxes[idx] if idx < len(detected_geo_bboxes) else None
            if det_geo is None:
                continue

            # Bu tespite en yakin OSM binasini bul
            best_iou = 0.0
            for osm_bbox in valid_osm_bboxes:
                iou = compute_iou_geo(det_geo, osm_bbox)
                best_iou = max(best_iou, iou)

            # Hidden esigi kontrolu
            if best_iou < self._hidden_iou_threshold:
                # Merkez cografi koordinat
                center_px = det.bbox.center
                center_geo = pixel_to_geo(
                    center_px[0], center_px[1],
                    image_width, image_height,
                    image_geo_bbox,
                )

                # Hidden score hesapla
                hidden_score = self._compute_hidden_score(
                    det, best_iou, len(osm_buildings)
                )

                reason = self._hidden_reason(
                    det.confidence, best_iou, len(osm_buildings)
                )

                hidden.append(
                    HiddenStructure(
                        detection=det,
                        geo_bbox=det_geo,
                        center_geo=center_geo,
                        best_iou=best_iou,
                        hidden_score=hidden_score,
                        reason=reason,
                    )
                )

        # Hidden score'a gore azalan sirala
        hidden.sort(key=lambda h: h.hidden_score, reverse=True)

        logger.info(
            "Hidden structure tespiti: %d/%d tespit hidden olarak isaretlendi",
            len(hidden), len(detected),
        )

        return hidden

    # ------------------------------------------------------------------ #
    # compute_coverage_ratio — Kapsam orani
    # ------------------------------------------------------------------ #

    @staticmethod
    def compute_coverage_ratio(
        osm_building_count: int,
        detected_count: int,
    ) -> float:
        """OSM bina yogunlugu ile YOLO tespit yogunlugunu karsilastirir.

        Dusuk kapsam orani sistematik gizleme suphesi ia sayilir.
        Oran = min(detected, osm) / max(detected, osm).

        Args:
            osm_building_count: OSM'deki bina sayisi.
            detected_count: YOLO tespiti bina sayisi.

        Returns:
            Kapsam orani (0–1). 1 = tam uyum.

        Examples:
            >>> GeospatialAnalyzer.compute_coverage_ratio(100, 80)
            0.8
            >>> GeospatialAnalyzer.compute_coverage_ratio(100, 10)
            0.1
        """
        if osm_building_count == 0 and detected_count == 0:
            return 1.0

        max_count = max(osm_building_count, detected_count)
        if max_count == 0:
            return 1.0

        min_count = min(osm_building_count, detected_count)
        return min_count / max_count

    # ------------------------------------------------------------------ #
    # Dahili yardimcilar
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_osm_bboxes(
        osm_buildings: List[Dict[str, Any]],
    ) -> List[Optional[GeoBBox]]:
        """OSM bina listesinden cografi bbox'lari cikarir.

        Args:
            osm_buildings: OSM bina verileri.

        Returns:
            Her bina icin GeoBBox veya None listesi.
        """
        bboxes: List[Optional[GeoBBox]] = []

        for osm_b in osm_buildings:
            geometry = None

            # Dataclass veya dict desteği
            if hasattr(osm_b, "geometry"):
                geometry = osm_b.geometry
            elif isinstance(osm_b, dict):
                geometry = osm_b.get("geometry")

            if geometry is not None:
                bboxes.append(osm_geometry_to_geo_bbox(geometry))
            else:
                bboxes.append(None)

        return bboxes

    @staticmethod
    def _compute_ghost_score(
        osm_building: Dict[str, Any],
        best_iou: float,
        detected_count: int,
    ) -> float:
        """Ghost building skor hesaplar (0–100).

        Faktörler:
          - IoU düşüklüğü (IoU = 0 → maksimum puan)
          - Bina alanı (büyük binalar daha şüpheli)
          - Hassas yapı olması (askeri vb.)
          - Bölgede başka tespit varlığı

        Args:
            osm_building: OSM bina verisi.
            best_iou: En yakın tespit ile IoU.
            detected_count: Bölgedeki toplam tespit sayısı.

        Returns:
            Ghost skoru (0–100).
        """
        score: float = 0.0

        # IoU bileşeni: IoU ne kadar düşükse o kadar yüksek skor
        iou_component = (1.0 - best_iou / GHOST_IOU_THRESHOLD) * 40.0
        score += max(0.0, iou_component)

        # Alan bileşeni: büyük binalar daha dikkat çekici
        area = 0.0
        if hasattr(osm_building, "area_m2"):
            area = osm_building.area_m2
        elif isinstance(osm_building, dict):
            area = osm_building.get("area_m2", 0.0)

        if area > 500:
            score += 15.0
        elif area > 200:
            score += 10.0
        elif area > 50:
            score += 5.0

        # Hassas yapı bonusu
        is_sensitive = False
        if hasattr(osm_building, "is_sensitive"):
            is_sensitive = osm_building.is_sensitive
        elif isinstance(osm_building, dict):
            is_sensitive = osm_building.get("is_sensitive", False)

        if is_sensitive:
            score += 25.0

        # Bölgede başka tespit varsa → bu bina gerçekten yok
        if detected_count > 3:
            score += 10.0
        elif detected_count > 0:
            score += 5.0

        return min(100.0, max(0.0, score))

    @staticmethod
    def _compute_hidden_score(
        detection: Detection,
        best_iou: float,
        osm_count: int,
    ) -> float:
        """Hidden structure skor hesaplar (0–100).

        Faktörler:
          - Tespit confidence'ı (yüksek = daha güvenilir)
          - IoU düşüklüğü (IoU ≈ 0 → OSM'de hiç eşleşme yok)
          - Bölgedeki OSM bina yoğunluğu (yoğun bölgede eksik → şüpheli)
          - Tespit boyutu (büyük yapılar daha dikkat çekici)

        Args:
            detection: YOLO tespit bilgisi.
            best_iou: En yakın OSM binası ile IoU.
            osm_count: Bölgedeki OSM bina sayısı.

        Returns:
            Hidden skoru (0–100).
        """
        score: float = 0.0

        # Confidence bileşeni
        conf_component = detection.confidence * 30.0
        score += conf_component

        # IoU bileşeni
        iou_component = (1.0 - best_iou / HIDDEN_IOU_THRESHOLD) * 25.0
        score += max(0.0, iou_component)

        # OSM yoğunluğu: bölgede OSM verisi varsa eksiklik daha anlamlı
        if osm_count > 10:
            score += 20.0
        elif osm_count > 5:
            score += 15.0
        elif osm_count > 0:
            score += 10.0

        # Boyut bileşeni
        det_area = detection.bbox.area
        if det_area > 5000:
            score += 15.0
        elif det_area > 2000:
            score += 10.0
        elif det_area > 500:
            score += 5.0

        return min(100.0, max(0.0, score))

    @staticmethod
    def _coverage_to_score(coverage: float) -> float:
        """Kapsam oranını anomali skoruna dönüştürür (0–100).

        Args:
            coverage: Kapsam oranı (0–1).

        Returns:
            Anomali skoru (0–100). Düşük kapsam = yüksek skor.
        """
        if coverage < COVERAGE_CRITICAL_THRESHOLD:
            return 90.0
        elif coverage < COVERAGE_LOW_THRESHOLD:
            # 0.1–0.3 arası lineer interpolasyon: 90 → 50
            t = (coverage - COVERAGE_CRITICAL_THRESHOLD) / (
                COVERAGE_LOW_THRESHOLD - COVERAGE_CRITICAL_THRESHOLD
            )
            return 90.0 - t * 40.0
        else:
            return max(0.0, (1.0 - coverage) * 30.0)

    @staticmethod
    def _ghost_reason(
        best_iou: float,
        is_sensitive: bool,
        area_m2: float,
    ) -> str:
        """Ghost building için açıklama metni üretir.

        Args:
            best_iou: En yakın tespit ile IoU.
            is_sensitive: Hassas yapı mı.
            area_m2: Bina alanı (m²).

        Returns:
            İnsan okunabilir açıklama.
        """
        parts: List[str] = []

        if best_iou == 0.0:
            parts.append("Uydu goruntusunde hic eslesme bulunamadi")
        else:
            parts.append(
                f"En yakin eslesme IoU={best_iou:.3f} (esik: {GHOST_IOU_THRESHOLD})"
            )

        if is_sensitive:
            parts.append("Hassas/askeri yapi kategorisinde")

        if area_m2 > 500:
            parts.append(f"Buyuk yapi ({area_m2:.0f} m2)")

        return ". ".join(parts) + "."

    @staticmethod
    def _hidden_reason(
        confidence: float,
        best_iou: float,
        osm_count: int,
    ) -> str:
        """Hidden structure için açıklama metni üretir.

        Args:
            confidence: Tespit güven skoru.
            best_iou: En yakın OSM binası ile IoU.
            osm_count: Bölgedeki OSM bina sayısı.

        Returns:
            İnsan okunabilir açıklama.
        """
        parts: List[str] = []

        parts.append(f"Tespit guveni: {confidence:.2f}")

        if best_iou == 0.0:
            parts.append("OSM'de hic eslesme yok")
        else:
            parts.append(f"En yakin OSM eslesmesi IoU={best_iou:.3f}")

        if osm_count > 10:
            parts.append(
                f"Yogun OSM bolgesi ({osm_count} bina) — eksiklik dikkat cekici"
            )

        return ". ".join(parts) + "."

    @staticmethod
    def _build_summary(
        ghosts: List[GhostBuilding],
        hidden: List[HiddenStructure],
        coverage: float,
        osm_count: int,
        detected_count: int,
    ) -> str:
        """Analiz sonucu için özet metin oluşturur.

        Args:
            ghosts: Ghost building listesi.
            hidden: Hidden structure listesi.
            coverage: Kapsam oranı.
            osm_count: OSM bina sayısı.
            detected_count: YOLO tespit sayısı.

        Returns:
            İnsan okunabilir özet.
        """
        parts: List[str] = []

        parts.append(
            f"Mekansal analiz: OSM'de {osm_count} bina, "
            f"uydu tespiti {detected_count} nesne."
        )

        if ghosts:
            sensitive_ghosts = sum(1 for g in ghosts if g.is_sensitive)
            parts.append(
                f"{len(ghosts)} hayalet bina tespit edildi"
                + (f" ({sensitive_ghosts} hassas yapi)" if sensitive_ghosts else "")
                + "."
            )

        if hidden:
            parts.append(
                f"{len(hidden)} gizli yapi tespit edildi."
            )

        parts.append(f"Kapsam orani: {coverage:.1%}.")

        if coverage < COVERAGE_CRITICAL_THRESHOLD:
            parts.append("UYARI: Cok dusuk kapsam — sistematik gizleme suphesi.")
        elif coverage < COVERAGE_LOW_THRESHOLD:
            parts.append("DIKKAT: Dusuk kapsam orani.")

        total_anomalies = len(ghosts) + len(hidden)
        if total_anomalies == 0:
            parts.append("Kayda deger anomali tespit edilmedi.")

        return " ".join(parts)
