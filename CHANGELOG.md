# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.1.0] - 2026-04-13
### Added (Initial Release Core Features)
- **MapLibre GL Interface**: High-performance interactive map with multi-provider tile layering.
- **FastAPI Backend**: Asynchronous core engine for fast data retrieval and routing.
- **Celery Scan Orchestration**: Grid-based background scanning queue for continuous intelligence gathering.
- **Computer Vision Pipelines**: Basic implementation of `BlurDetector` and `PixelDiffAnalyzer`.
- **Authentication System**: Secure JWT-based registration and login protocols.
- **Trust Scoring System**: Gamified user evaluation system for anomaly verification.
- **Automated Alerts**: Email and dashboard notification architecture for critical anomalies.
- **Production Monitoring Stack**: Complete Prometheus + Grafana Sentry observability ecosystem.

### Known Limitations
- High-density urban areas with heavy 3D building data may currently trigger false positive `GHOST_BUILDING` returns.
- Apple Maps tile parsing is currently experimental and not fully integrated into SSIM comparisons.
- NASA GIBS historical time-series alignment has a ±15 meter geometric shift that needs algorithmic correction.

### Future Roadmap
- Complete YOLOv8 integration for automated object detection inside bounding boxes.
- Edge-based processing for anomaly detection running on the client.
- Mobile responsive optimizations for the exploration grid.
