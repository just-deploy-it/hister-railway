#!/usr/bin/env python3
# ---
# author: Just Deploy It
# project: Hister on Railway
# purpose: Advance every declared Hister release pin atomically
# used_by: .github/workflows/update-hister.yml and updater simulation
# status: active
# verified: 2026-08-27
# dependencies: Python standard library only
# safety: writes pins only after release metadata and current file consistency validate
# ---
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

IMAGE = "ghcr.io/asciimoo/hister"
VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
    )
)


def require_pin(version: str, digest: str) -> None:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"stable version required, got {version!r}")
    if not DIGEST_RE.fullmatch(digest):
        raise ValueError(f"OCI sha256 digest required, got {digest!r}")


def fetch_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "just-deploy-it-hister-updater/1", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def latest_pin() -> tuple[str, str]:
    version = fetch_json("https://api.github.com/repos/asciimoo/hister/releases/latest")["tag_name"]
    require_pin(version, "sha256:" + "0" * 64)
    scope = urllib.parse.quote("repository:asciimoo/hister:pull")
    token = fetch_json(f"https://ghcr.io/token?scope={scope}&service=ghcr.io")["token"]
    request = urllib.request.Request(
        f"https://ghcr.io/v2/asciimoo/hister/manifests/{version}",
        headers={"Authorization": f"Bearer {token}", "Accept": ACCEPT, "User-Agent": "just-deploy-it-hister-updater/1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        digest = response.headers.get("Docker-Content-Digest", "")
        response.read(1)
    require_pin(version, digest)
    return version, digest


def replace_once(content: str, old: str, new: str, path: str) -> str:
    if content.count(old) != 1:
        raise ValueError(f"expected exactly one current pin in {path}: {old}")
    return content.replace(old, new)


def apply_update(root: Path, version: str, digest: str) -> dict:
    require_pin(version, digest)
    upstream_path = root / "upstream.json"
    dockerfile_path = root / "Dockerfile"
    template_path = root / "railway-template.json"
    upstream = json.loads(upstream_path.read_text())
    template = json.loads(template_path.read_text())
    current_version = upstream["version"]
    current_digest = upstream["digest"]
    require_pin(current_version, current_digest)
    if (version, digest) == (current_version, current_digest):
        return {"changed": False, "from": {"version": current_version, "digest": current_digest}, "to": {"version": version, "digest": digest}}

    if template.get("upstream") != {"version": current_version, "digest": current_digest}:
        raise ValueError("railway-template.json does not match the current upstream pin")
    dockerfile = dockerfile_path.read_text()
    dockerfile = replace_once(dockerfile, f"{IMAGE}@{current_digest}", f"{IMAGE}@{digest}", "Dockerfile")
    dockerfile = replace_once(dockerfile, f'org.opencontainers.image.version="{current_version}"', f'org.opencontainers.image.version="{version}"', "Dockerfile")
    template["upstream"] = {"version": version, "digest": digest}
    upstream["version"] = version
    upstream["digest"] = digest

    dockerfile_path.write_text(dockerfile)
    template_path.write_text(json.dumps(template, indent=2) + "\n")
    upstream_path.write_text(json.dumps(upstream, indent=2) + "\n")
    return {"changed": True, "from": {"version": current_version, "digest": current_digest}, "to": {"version": version, "digest": digest}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--version")
    parser.add_argument("--digest")
    args = parser.parse_args()
    if bool(args.version) != bool(args.digest):
        parser.error("--version and --digest must be provided together")
    version, digest = (args.version, args.digest) if args.version else latest_pin()
    print(json.dumps(apply_update(args.root.resolve(), version, digest), sort_keys=True))


if __name__ == "__main__":
    main()
