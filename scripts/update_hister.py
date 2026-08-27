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
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from scripts.verify import SERVICE_ID, TEMPLATE_CODE, TEMPLATE_ID, verify, verify_serialized_config
except ModuleNotFoundError:
    from verify import SERVICE_ID, TEMPLATE_CODE, TEMPLATE_ID, verify, verify_serialized_config

IMAGE = "ghcr.io/asciimoo/hister"
RAILWAY_API = "https://backboard.railway.com/graphql/internal"
VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
    )
)
TEMPLATE_QUERY = """
query template($id: String!) {
  template(id: $id) { id code status serializedConfig }
}
"""
STAGED_QUERY = """
query templateStagedChangeSet($templateId: String!) {
  templateChangeSets(templateId: $templateId, first: 1) {
    edges { node { id status patch } }
  }
}
"""
STAGE_MUTATION = """
mutation templateChangeSetStage($templateId: String!, $patch: TemplatePatch!, $merge: Boolean) {
  templateChangeSetStage(templateId: $templateId, patch: $patch, merge: $merge) { id status }
}
"""
APPLY_MUTATION = """
mutation templateChangeSetApply($changeSetId: String!) {
  templateChangeSetApply(changeSetId: $changeSetId) { id status }
}
"""


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


def railway_graphql(token: str, operation: str, query: str, variables: dict) -> dict:
    request = urllib.request.Request(
        f"{RAILWAY_API}?q={urllib.parse.quote(operation)}",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "just-deploy-it-hister-updater/1",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(f"Railway {operation} failed: {payload['errors']}")
    return payload["data"]


def sync_template(
    root: Path,
    token: str,
    expected_current_digest: str,
    graphql=railway_graphql,
) -> dict:
    require_pin("v0.0.0", expected_current_digest)
    verified = verify(root)
    version, digest = verified["version"], verified["digest"]
    candidate_image = f"{IMAGE}@{digest}"
    current_image = f"{IMAGE}@{expected_current_digest}"
    template = graphql(token, "template", TEMPLATE_QUERY, {"id": TEMPLATE_ID})["template"]
    if (template["id"], template["code"], template["status"]) != (TEMPLATE_ID, TEMPLATE_CODE, "UNPUBLISHED"):
        raise ValueError("Railway readback does not identify the approved unpublished template")
    config = template["serializedConfig"]
    live_image = config.get("services", {}).get(SERVICE_ID, {}).get("source", {}).get("image")
    staged_edges = graphql(
        token,
        "templateStagedChangeSet",
        STAGED_QUERY,
        {"templateId": TEMPLATE_ID},
    )["templateChangeSets"]["edges"]
    patch = {"config": {"services": {SERVICE_ID: {"source": {"image": candidate_image}}}}}
    if live_image == candidate_image and not staged_edges:
        return {"changed": False, "templateId": TEMPLATE_ID, "code": TEMPLATE_CODE, "image": candidate_image, **verify_serialized_config(config, version, digest)}
    if live_image != current_image:
        raise ValueError(f"Railway template image drifted: expected {current_image}, got {live_image}")

    if staged_edges:
        staged = staged_edges[0]["node"]
        if staged.get("patch") != patch:
            raise ValueError("Railway template has unrelated staged changes")
        change_set_id = staged["id"]
    else:
        staged = graphql(
            token,
            "templateChangeSetStage",
            STAGE_MUTATION,
            {"templateId": TEMPLATE_ID, "patch": patch, "merge": True},
        )["templateChangeSetStage"]
        change_set_id = staged["id"]
    graphql(
        token,
        "templateChangeSetApply",
        APPLY_MUTATION,
        {"changeSetId": change_set_id},
    )
    for _ in range(20):
        template = graphql(token, "template", TEMPLATE_QUERY, {"id": TEMPLATE_ID})["template"]
        config = template["serializedConfig"]
        if config.get("services", {}).get(SERVICE_ID, {}).get("source", {}).get("image") == candidate_image:
            return {"changed": True, "templateId": TEMPLATE_ID, "code": TEMPLATE_CODE, "changeSetId": change_set_id, "image": candidate_image, **verify_serialized_config(config, version, digest)}
        time.sleep(1)
    raise RuntimeError("Railway template did not expose the candidate image after apply")


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
    source = template["services"][0]["source"]
    source["image"] = replace_once(source["image"], f"{IMAGE}@{current_digest}", f"{IMAGE}@{digest}", "railway-template.json")
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
    parser.add_argument("--sync-template", action="store_true")
    parser.add_argument("--expected-current-digest")
    args = parser.parse_args()
    if args.sync_template:
        if args.version or args.digest or not args.expected_current_digest:
            parser.error("--sync-template requires only --expected-current-digest")
        token = os.environ.get("RAILWAY_API_TOKEN", "")
        if not token:
            parser.error("RAILWAY_API_TOKEN is required")
        print(json.dumps(sync_template(args.root.resolve(), token, args.expected_current_digest), sort_keys=True))
        return
    if bool(args.version) != bool(args.digest):
        parser.error("--version and --digest must be provided together")
    version, digest = (args.version, args.digest) if args.version else latest_pin()
    print(json.dumps(apply_update(args.root.resolve(), version, digest), sort_keys=True))


if __name__ == "__main__":
    main()
