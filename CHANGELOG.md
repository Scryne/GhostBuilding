# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- SMTP e-posta gönderimi (`SMTP_*`, `FRONTEND_URL`); yapılandırılmamışsa uygulama çalışır ve "e-posta kapalı" der.
- E-posta doğrulama sayfası (`/auth/verify-email`): doğrulandı, zaten doğrulanmış, süresi dolmuş, geçersiz, yeniden gönder.
- Şifre sıfırlama: `/auth/forgot-password`, `/auth/reset-password`; tek kullanımlık, 30 dakikalık bağlantı;
  hesap varlığını sızdırmayan yanıt; IP ve adres başına hız sınırı; sıfırlamada tüm eski oturumlar geçersiz.
- API: `POST /auth/verify-email`, `POST /auth/resend-verification`, `POST /auth/forgot-password`, `POST /auth/reset-password`.

### Changed
- Doğrulama bağlantısı artık `APP_NAME` yerine `FRONTEND_URL` kökünden kurulur; token URL parçasında taşınır.
- Kayıt/giriş/doğrulama log'larına e-posta adresi ve token yazılmaz.
- `GET /auth/verify-email` hata kodları: `token_expired` ve `invalid_token` (eskiden ortak `invalid_or_expired_token`).

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
