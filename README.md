# Hister on Railway

One-click Railway packaging and maintenance automation for [Hister](https://github.com/asciimoo/hister), a self-hosted search engine for browser history and personal documents.

Railway deploys the official Hister image directly by immutable OCI digest. This repository adds no application code. Its Dockerfile is only a clean-build gate for candidate image pins and is not a template source. Railway provides HTTPS, a generated access token and persistent storage at `/hister/data`.

## Architecture

- One public Hister service on port 4433
- Railway HTTPS with `/api/config` health checks
- Token authentication enabled by default
- One volume mounted at `/hister/data`

## Updates

`.github/workflows/update-hister.yml` resolves the latest stable upstream release, updates every declared pin, runs the full tests and configuration gate, clean-builds the exact candidate image, updates Railway template `IhfcxB` through Railway's API and reads it back before any commit or push to `main`. See `UPDATE_POLICY.md`.

## Upstream and license

Hister is maintained by asciimoo and licensed under AGPL-3.0-only. This packaging is not affiliated with the upstream project. See `THIRD_PARTY_NOTICES.md`.
