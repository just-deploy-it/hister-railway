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
TEMPLATE_ID = "27248383-1851-4556-8604-1b1f6f93f4c9"
TEMPLATE_CODE = "IhfcxB"
SERVICE_ID = "4a3812aa-2eff-4e20-a26f-f1b8a3855d51"
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


def verify_serialized_config(config: dict, version: str, digest: str) -> dict:
    del version
    expected_image = f"{IMAGE}@{digest}"
    if config.get("buckets") != {}:
        raise ValueError("template must not contain buckets")
    services = config.get("services", {})
    if set(services) != {SERVICE_ID}:
        raise ValueError("serialized template must contain only the approved Hister service")
    service = services[SERVICE_ID]
    if service.get("name") != "Hister" or service.get("source") != {"image": expected_image}:
        raise ValueError("serialized template source is not the approved direct immutable image")
    if service.get("deploy", {}).get("healthcheckPath") != "/api/config":
        raise ValueError("serialized template health check changed")
    if service.get("networking", {}).get("serviceDomains") != {"<hasDomain>:4433": {"port": 4433}}:
        raise ValueError("serialized template public port changed")
    expected_variables = {name: {"defaultValue": value} for name, value in EXPECTED_VARIABLES.items()}
    if service.get("variables") != expected_variables:
        raise ValueError("serialized template variables differ from the approved zero-input contract")
    if service.get("volumeMounts") != {SERVICE_ID: {"mountPath": "/hister/data"}}:
        raise ValueError("serialized template volume owner or mount path changed")
    return {"requiredInputs": 0, "literalSecrets": False, "serializedConfigVerified": True}


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
    if template.get("template") != {"id": TEMPLATE_ID, "code": TEMPLATE_CODE, "status": "UNPUBLISHED"}:
        raise ValueError("railway-template.json does not identify the approved unpublished template")
    if template.get("upstream") != {"version": version, "digest": digest}:
        raise ValueError("railway-template.json upstream pin is inconsistent")
    services = template.get("services", [])
    if len(services) != 1:
        raise ValueError("template must contain exactly one service")
    service = services[0]
    if service.get("id") != SERVICE_ID:
        raise ValueError("template service ID changed")
    source = service.get("source", {})
    if source != {"type": "image", "image": f"{IMAGE}@{digest}", "autoUpdates": False}:
        raise ValueError("template source must be the approved direct immutable image with auto-updates disabled")
    if service.get("variables") != EXPECTED_VARIABLES:
        raise ValueError("template variables differ from the approved zero-input contract")
    if service.get("volume", {}).get("mountPath") != "/hister/data":
        raise ValueError("Hister volume mount must be /hister/data")
    if service.get("publicNetworking", {}).get("port") != 4433 or service.get("healthcheck", {}).get("path") != "/api/config":
        raise ValueError("public port or health check changed")
    if "caddy" in dockerfile.lower():
        raise ValueError("Caddy is not part of this template")
    return {"version": version, "digest": digest, "tests": True, "configuration": True, "directImage": True, "requiredInputs": 0, "literalSecrets": False, "pinBearingFilesConsistent": True}


if __name__ == "__main__":
    print(json.dumps(verify(Path(__file__).resolve().parents[1]), sort_keys=True))
