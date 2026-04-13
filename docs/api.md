# GhostBuilding API Documentation

The REST API is built with FastAPI and runs from `/api/v1`. 
Authentication uses JWT Bearer tokens.

## Endpoints

### 1. `POST /api/v1/auth/login`
Authenticate a user and return a JWT.
- **Payload:** `OAuth2PasswordRequestForm` (username, password)
- **Response:** `{ "access_token": "eyJ...", "token_type": "bearer" }`

### 2. `POST /api/v1/scan/coordinate`
Trigger a background Celery scan on a specific 1km radius zone.
- **Auth:** Requires JWT Bearer.
- **Payload:** `{ "lat": 37.235, "lng": -115.811, "radius_km": 1.0 }`
- **Response:** `{ "task_id": "c1f2-...", "status": "processing" }`

### 3. `GET /api/v1/anomalies/`
Fetch discovered anomalies globally or within a bounding box.
- **Query Params:** `bbox (min_lng,min_lat,max_lng,max_lat)`, `status (VERIFIED|PENDING)`, `category`
- **Response:** List of GeoJSON-style feature points.

### 4. `GET /api/v1/anomalies/{id}`
Fetch detailed metadata, associated provider images, and vote history for a single anomaly.

### 5. `POST /api/v1/verifications/`
Submit a community vote for an anomaly.
- **Auth:** Requires JWT Bearer.
- **Payload:** `{ "anomaly_id": "a1b2-...", "vote": "CONFIRM" }`
- **Response:** Automatically updates user trust score and anomaly confidence ratio.
