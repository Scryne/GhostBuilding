<p align="center">
  <img src="https://raw.githubusercontent.com/Scryne/GhostBuilding/main/public/logo.png" alt="GhostBuilding Logo" width="120" height="120" />
</p>

<h1 align="center">👻 GhostBuilding</h1>

<p align="center">
  <strong>Global OSINT Mapping Intelligence Platform</strong><br/>
  <em>Detect censored areas, ghost buildings, and hidden structures across global map providers.</em>
</p>

<p align="center">
  <a href="https://github.com/Scryne/GhostBuilding/actions"><img src="https://img.shields.io/github/actions/workflow/status/Scryne/GhostBuilding/ci.yml?branch=main&style=flat-square" alt="Build Status" /></a>
  <a href="https://github.com/Scryne/GhostBuilding/releases"><img src="https://img.shields.io/github/v/release/Scryne/GhostBuilding?style=flat-square" alt="Version" /></a>
  <a href="https://github.com/Scryne/GhostBuilding/stargazers"><img src="https://img.shields.io/github/stars/Scryne/GhostBuilding?style=flat-square" alt="Stars" /></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square" alt="License: MIT" /></a>
</p>

<p align="center">
  <strong><a href="https://ghostbuilding.io">Live Demo</a></strong> •
  <strong><a href="docs/api.md">API Docs</a></strong> •
  <strong><a href="docs/algorithms.md">How It Works</a></strong> •
  <strong><a href="CONTRIBUTING.md">Contribute</a></strong>
</p>

---

## 🔎 Overview

GhostBuilding is an advanced open-source intelligence (OSINT) platform that systematically detects and highlights discrepancies between major map providers (Google Maps, OpenStreetMap, Bing Maps, Yandex). 

By comparing pixel architectures, geospatial metadata, and historical archives, GhostBuilding automatically identifies:
- 🏚️ **Ghost Buildings** — Structures registered in public metadata (OSM) but invisible in satellite imagery.
- 🔒 **Hidden Structures** — Classified or secret buildings visible in satellite imagery but absent from official maps.
- 🚫 **Censored Areas** — Systematically blurred, pixelated, or intentionally obscured regions.
- 🔍 **Image Discrepancies** — Significant pixel-level anomalies or manipulation between provider tiles.

<p align="center">
  <!-- Demo GIF Placeholder -->
  <img src="https://raw.githubusercontent.com/Scryne/GhostBuilding/main/public/demo.gif" alt="GhostBuilding Demo" width="800" />
</p>

---

## ✨ Features

- 🛰️ **Cross-Provider Comparison:** Simultaneously download and compare tiles from 4+ providers.
- 🧮 **Advanced Computer Vision:** Laplacian variance for blur detection and SSIM for pixel diffs.
- 🗺️ **Geospatial Cross-Referencing:** Compare OpenStreetMap building data with YOLO v8 satellite detections.
- 🌐 **Interactive Global Map:** Built with MapLibre GL JS and tailored for intense intelligence gathering.
- 👥 **Community Verification:** Weighted voting system with trust scores for anomaly confirmation.
- 🚀 **Asynchronous Scanning:** Celery-powered background grid scanning with progress tracking.

---

## ⚡ Quick Start

Get GhostBuilding running on your machine in under 3 minutes using Docker.

```bash
# 1. Clone the repository
git clone https://github.com/Scryne/GhostBuilding.git
cd GhostBuilding

# 2. Configure environment
cp .env.example .env

# 3. Start the entire stack
docker compose up -d
```

Once running, navigate to:
- **Frontend Dashboard:** [http://localhost:3000](http://localhost:3000)
- **Backend API:** [http://localhost:8000/docs](http://localhost:8000/docs)

> For manual deployment or production setup, see our [Deployment Guide](docs/deployment.md).

---

## 📚 Documentation

The technical details of the project are thoroughly documented in the `docs/` folder:

- [API Documentation](docs/api.md)
- [Detection Algorithms Explained](docs/algorithms.md)
- [Production Deployment Guide](docs/deployment.md)
- [Data Sources & Licensing](docs/data-sources.md)

---

## 🤝 Contributing

We welcome contributions from the OSINT and developer communities! Whether it's adding a new map provider, improving the computer vision models, or reporting a bug, please join us.

1. Read our [Contribution Guidelines](.github/CONTRIBUTING.md).
2. Review our [Code of Conduct](CODE_OF_CONDUCT.md).
3. Check the open issues or create a new one using our templates.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

> **Disclaimer:** This tool is for educational, research, and journalistic purposes. It relies on public APIs and open data sources. Please respect the Terms of Service of individual map providers.

<p align="center">
  <sub>Built for the truth. Uncover the hidden.</sub>
</p>