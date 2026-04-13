import asyncio
import json
import uuid
import sys
import os
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add the parent directory to sys.path so we can import app
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from app.config import settings

# 20 Real-World OSINT Examples
SEED_DATA = [
    {
        "lat": 37.2350, "lng": -115.8111,
        "category": "IMAGE_DISCREPANCY",
        "confidence_score": 98.5,
        "description": "Area 51, Nevada. Significant resolution mismatch and historical imagery inconsistencies across public providers.",
        "source_providers": ["google", "bing", "yandex"],
        "detection_methods": ["pixel_diff", "time_series"],
    },
    {
        "lat": 39.0302, "lng": 125.7538,
        "category": "HIDDEN_STRUCTURE",
        "confidence_score": 94.2,
        "description": "East Pyongyang, North Korea. Unmapped subterranean facility entrances visible in satellite view but absent from OSM.",
        "source_providers": ["google", "osm"],
        "detection_methods": ["geospatial_mismatch"],
    },
    {
        "lat": 73.3500, "lng": 54.8000,
        "category": "CENSORED_AREA",
        "confidence_score": 100.0,
        "description": "Novaya Zemlya, Russia. Former nuclear testing site heavily pixelated in Yandex and Bing Maps.",
        "source_providers": ["yandex", "bing"],
        "detection_methods": ["blur_detection", "fft_analysis"],
    },
    {
        "lat": 31.9166, "lng": 34.8000,
        "category": "CENSORED_AREA",
        "confidence_score": 91.0,
        "description": "Central Israel region. Aerial imagery artificially degraded to 2m/pixel resolution legally mandated limits.",
        "source_providers": ["google", "bing"],
        "detection_methods": ["resolution_degradation"],
    },
    {
        "lat": 39.9042, "lng": 116.4074,
        "category": "IMAGE_DISCREPANCY",
        "confidence_score": 87.5,
        "description": "Beijing, China. GCJ-02 coordinate system shift creating artificial misalignment (50-500m) with WGS-84 satellite imagery.",
        "source_providers": ["osm", "google"],
        "detection_methods": ["geospatial_shift"],
    },
    {
        "lat": 52.1229, "lng": 5.2813,
        "category": "GHOST_BUILDING",
        "confidence_score": 89.1,
        "description": "Soesterberg, Netherlands. Polygons present in OSM routing but camouflaged/removed in aerial view.",
        "source_providers": ["osm", "google"],
        "detection_methods": ["camouflage_detection"],
    },
    {
        "lat": -22.8122, "lng": -43.2505,
        "category": "HIDDEN_STRUCTURE",
        "confidence_score": 76.5,
        "description": "Rio de Janeiro, Brazil. Undocumented structural additions in dense urban favela not matching official city registers.",
        "source_providers": ["google", "osm"],
        "detection_methods": ["yolo_building_detection"],
    },
    {
        "lat": 48.8703, "lng": 2.3168,
        "category": "CENSORED_AREA",
        "confidence_score": 100.0,
        "description": "Élysée Palace, Paris, France. High-priority government facility heavily pixelated on domestic providers.",
        "source_providers": ["bing", "apple"],
        "detection_methods": ["pixel_block_detection"],
    },
    {
        "lat": 38.6428, "lng": 35.4853,
        "category": "IMAGE_DISCREPANCY",
        "confidence_score": 83.4,
        "description": "Central Anatolia, Turkey. Sudden topological mismatch between summer/winter satellite passes indicating subterranean excavation.",
        "source_providers": ["google"],
        "detection_methods": ["time_series"],
    },
    {
        "lat": 34.5221, "lng": 69.1765,
        "category": "GHOST_BUILDING",
        "confidence_score": 92.0,
        "description": "Kabul, Afghanistan. Ghost outlines of former compounds visible in older OSM tiles but completely absent in recent imagery.",
        "source_providers": ["osm", "bing"],
        "detection_methods": ["historical_mismatch"],
    },
    {
        "lat": 50.1109, "lng": 8.6821,
        "category": "CENSORED_AREA",
        "confidence_score": 88.3,
        "description": "Frankfurt, Germany. Financial district datacenter roof structures artificially obscured.",
        "source_providers": ["google"],
        "detection_methods": ["blur_detection"],
    },
    {
        "lat": 35.5308, "lng": 139.7371,
        "category": "HIDDEN_STRUCTURE",
        "confidence_score": 81.2,
        "description": "Kawasaki, Japan. Industrial zone anomaly with unaccounted thermal/heat exhaust signatures not mapping to known buildings.",
        "source_providers": ["bing", "osm"],
        "detection_methods": ["thermal_proxy_detection"],
    },
    {
        "lat": 55.7512, "lng": 37.6184,
        "category": "CENSORED_AREA",
        "confidence_score": 99.5,
        "description": "Kremlin, Moscow, Russia. Complete GIS offset and GPS spoofing zone causing extreme tile tearing.",
        "source_providers": ["yandex", "google", "bing"],
        "detection_methods": ["coordinate_spoofing"],
    },
    {
        "lat": 40.7128, "lng": -74.0060,
        "category": "IMAGE_DISCREPANCY",
        "confidence_score": 72.1,
        "description": "New York City, USA. Deep shadow discrepancies in high-rise corridors hiding street-level mobile structures.",
        "source_providers": ["google", "apple"],
        "detection_methods": ["shadow_analysis"],
    },
    {
        "lat": 24.7136, "lng": 46.6753,
        "category": "HIDDEN_STRUCTURE",
        "confidence_score": 96.7,
        "description": "Riyadh, Saudi Arabia. Desert facility expansion captured by Yandex but severely outdated/hidden on Google.",
        "source_providers": ["yandex", "google"],
        "detection_methods": ["temporal_lag"],
    },
    {
        "lat": 33.5138, "lng": 36.2765,
        "category": "GHOST_BUILDING",
        "confidence_score": 85.0,
        "description": "Damascus, Syria. Flattened neighborhoods still routing active traffic paths in local maps despite total structural loss.",
        "source_providers": ["osm", "bing"],
        "detection_methods": ["routing_vs_visual"],
    },
    {
        "lat": -33.8688, "lng": 151.2093,
        "category": "CENSORED_AREA",
        "confidence_score": 68.4,
        "description": "Sydney, Australia. Naval base dockyards obscured entirely by low-poly clouds strictly on certain zoom levels.",
        "source_providers": ["google", "bing"],
        "detection_methods": ["cloud_anomaly"],
    },
    {
        "lat": 23.1291, "lng": 113.2644,
        "category": "IMAGE_DISCREPANCY",
        "confidence_score": 79.9,
        "description": "Guangzhou, China. Large scale map splicing detected across major grid coordinates; 15-pixel alignment error.",
        "source_providers": ["bing", "yandex"],
        "detection_methods": ["grid_splicing"],
    },
    {
        "lat": 51.5074, "lng": -0.1278,
        "category": "HIDDEN_STRUCTURE",
        "confidence_score": 91.5,
        "description": "London, UK. Subterranean crossrail ventilation shafts appearing as generic commercial properties in public records.",
        "source_providers": ["osm", "google"],
        "detection_methods": ["zoning_mismatch"],
    },
    {
        "lat": 37.7749, "lng": -122.4194,
        "category": "GHOST_BUILDING",
        "confidence_score": 74.2,
        "description": "San Francisco, USA. Presidio private estate registered on tax maps but heavily obscured by artificial tree canopies in 3D views.",
        "source_providers": ["apple", "google"],
        "detection_methods": ["3d_render_anomaly"],
    }
]

async def seed_db():
    print("🌱 Starting database seeding process...")
    
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Check if anomalies already exist
            result = await session.execute(text("SELECT COUNT(*) FROM anomalies"))
            count = result.scalar()
            
            if count > 0:
                print(f"⚠️ Database already contains {count} anomalies. Clearing table...")
                await session.execute(text("DELETE FROM anomaly_images"))
                await session.execute(text("DELETE FROM verifications"))
                await session.execute(text("DELETE FROM anomalies"))
                await session.commit()
            
            print(f"Inserting {len(SEED_DATA)} anomalies...")
            
            for item in SEED_DATA:
                anomaly_id = str(uuid.uuid4())
                stmt = text("""
                    INSERT INTO anomalies 
                    (id, lat, lng, geom, category, confidence_score, description, status, source_providers, detection_methods, created_at, updated_at) 
                    VALUES 
                    (:id, :lat, :lng, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), :category, :confidence_score, :description, :status, :source_providers, :detection_methods, :created_at, :updated_at)
                """)
                
                await session.execute(stmt, {
                    "id": anomaly_id,
                    "lat": item["lat"],
                    "lng": item["lng"],
                    "category": item["category"],
                    "confidence_score": item["confidence_score"],
                    "description": item["description"],
                    "status": "VERIFIED",
                    "source_providers": json.dumps(item["source_providers"]),
                    "detection_methods": json.dumps(item["detection_methods"]),
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                })

                # Insert 2 fake satellite images per anomaly
                for provider in item["source_providers"][:2]:
                    image_id = str(uuid.uuid4())
                    img_stmt = text("""
                        INSERT INTO anomaly_images 
                        (id, anomaly_id, provider, image_url, image_type, captured_at, resolution, metadata_json) 
                        VALUES 
                        (:id, :anomaly_id, :provider, :image_url, :image_type, :captured_at, :resolution, :metadata_json)
                    """)
                    await session.execute(img_stmt, {
                        "id": image_id,
                        "anomaly_id": anomaly_id,
                        "provider": provider,
                        "image_url": f"https://api.ghostbuilding.io/images/mock_{provider}_{anomaly_id[:8]}.jpg",
                        "image_type": "SATELLITE",
                        "captured_at": datetime.now(timezone.utc),
                        "resolution": 0.5,
                        "metadata_json": '{"mock": true}'
                    })

            await session.commit()
            print("✅ Seeding completed successfully!")
            
    except Exception as e:
        print(f"❌ Error during seeding: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_db())
