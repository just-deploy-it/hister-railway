# Hister on Railway

One-click Railway packaging for [Hister](https://github.com/asciimoo/hister), a self-hosted search engine for browser history and personal documents.

This repository adds no application code. Its Dockerfile inherits the official Hister image by immutable OCI digest. Railway provides HTTPS, a generated access token and persistent storage at `/hister/data`.

## Architecture

- One public Hister service on port 4433
- Railway HTTPS with `/api/config` health checks
- Token authentication enabled by default
- One volume mounted at `/hister/data`

## Updates

`.github/workflows/update-hister.yml` resolves the latest stable upstream release, updates every declared pin, runs the full tests and configuration gate, then clean-builds the exact candidate image before any commit or push to `main`. See `UPDATE_POLICY.md`.

## Upstream and license

Hister is maintained by asciimoo and licensed under AGPL-3.0-only. This packaging is not affiliated with the upstream project. See `THIRD_PARTY_NOTICES.md`.
