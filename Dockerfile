# syntax=docker/dockerfile:1
# ---
# author: Just Deploy It
# project: Hister on Railway
# purpose: Wrap the official immutable Hister image for Railway source deployments
# used_by: Railway template IhfcxB and automated pin updater
# status: active
# verified: 2026-08-27
# ---
ARG HISTER_IMAGE=ghcr.io/asciimoo/hister@sha256:55ca3b00da9d3245cc689a7f4455be5f4a3931c29d3450d6d1f46f8c931cce35
FROM ${HISTER_IMAGE}
LABEL org.opencontainers.image.source="https://github.com/just-deploy-it/hister-railway" \
      org.opencontainers.image.url="https://github.com/asciimoo/hister" \
      org.opencontainers.image.version="v0.18.0" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
