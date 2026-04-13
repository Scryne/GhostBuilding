# Contributing to GhostBuilding

First off, thank you for considering contributing to GhostBuilding! It's people like you that make open-source and OSINT tools powerful.

## How Can I Contribute?

### Reporting Bugs & Anomalies
- Use the **Bug Report** template for technical issues.
- Use the **Anomaly Report** template if you've found a geospatial discrepancy you want added to our seed database or analyzed.

### Making Code Changes
1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes (`pytest` and `npm run lint`).
5. Make sure your code adheres to standard styling constraints (Prettier for TS, Black/Flake8 for Python).
6. Issue that pull request!

### Setting Up for Development
Please read our [README.md](../README.md) for detailed instructions on how to use `docker-compose` or local environments to spin up the GhostBuilding stack.
