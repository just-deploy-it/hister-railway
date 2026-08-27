#!/usr/bin/env python3
# ---
# author: Just Deploy It
# project: Hister on Railway
# purpose: Fail closed unless release pins and Railway template inputs are consistent and safe
# used_by: CI, updater pre-push gate and lifecycle evidence
# status: active
# verified: 2026-08-27
# dependencies: Python standard library only
# ---
from __future__ import annotations

import json
import re
from pathlib import Path

IMAGE = "ghcr.io/asciimoo/hister"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EXPECTED_VARIABLES = {
    "HISTER__APP__ACCESS_TOKEN": "${{secret(32)}}",
    "HISTER__APP__PUBLIC": "false",
    "HISTER__APP__USER_HANDLING": "false",
    "HISTER__SERVER__ADDRESS": "0.0.0.0:4433",
    "HISTER__SERVER__BASE_URL": "https://${{RAILWAY_PUBLIC_DOMAIN}}",
    "HISTER_DATA_DIR": "/hister/data",
    "PORT": "4433",
    "RAILWAY_RUN_UID": "0",
}


def verify(root: Path) -> dict:
    upstream = json.loads((root / "upstream.json").read_text())
    template = json.loads((root / "railway-template.json").read_text())
    dockerfile = (root / "Dockerfile").read_text()
    version, digest = upstream["version"], upstream["digest"]
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version) or not DIGEST_RE.fullmatch(digest):
        raise ValueError("upstream.json contains a mutable or prerelease pin")
    if upstream.get("pinBearingFiles") != ["Dockerfile", "upstream.json", "railway-template.json"]:
        raise ValueError("pin-bearing file declaration changed")
    if dockerfile.count(f"{IMAGE}@{digest}") != 1 or dockerfile.count(f'org.opencontainers.image.version="{version}"') != 1:
        raise ValueError("Dockerfile does not build the declared candidate pin")
    if template.get("upstream") != {"version": version, "digest": digest}:
        raise ValueError("railway-template.json upstream pin is inconsistent")
    services = template.get("services", [])
    if len(services) != 1:
        raise ValueError("template must contain exactly one service")
    service = services[0]
    source = service.get("source", {})
    if source != {"type": "github", "repository": "https://github.com/just-deploy-it/hister-railway", "branch": "main", "rootDirectory": "/", "dockerfilePath": "Dockerfile"}:
        raise ValueError("template source must be the maintained main-branch wrapper")
    if service.get("variables") != EXPECTED_VARIABLES:
        raise ValueError("template variables differ from the approved zero-input contract")
    if service.get("volume", {}).get("mountPath") != "/hister/data":
        raise ValueError("Hister volume mount must be /hister/data")
    if service.get("publicNetworking", {}).get("port") != 4433 or service.get("healthcheck", {}).get("path") != "/api/config":
        raise ValueError("public port or health check changed")
    if "caddy" in dockerfile.lower():
        raise ValueError("Caddy is not part of this template")
    return {"version": version, "digest": digest, "tests": True, "configuration": True, "requiredInputs": 0, "literalSecrets": False, "pinBearingFilesConsistent": True}


if __name__ == "__main__":
    print(json.dumps(verify(Path(__file__).resolve().parents[1]), sort_keys=True))
