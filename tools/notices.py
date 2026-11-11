#!/usr/bin/env python3
"""Render THIRD_PARTY_NOTICES.md from branding/notices.json.

The notices file is the single machine-readable source of third-party credit.
The same data will feed the Settings page About -> Open-source licenses, so
credit is never written by hand in two places and can never drift.

    python3 tools/notices.py --check     # CI: fail if the rendered file differs
    python3 tools/notices.py --write     # regenerate THIRD_PARTY_NOTICES.md
    python3 tools/notices.py --json      # dump the validated data (for the UI)

Nothing here invents license information. An entry whose license is still
unknown must say TODO(verify) and must reference an id that exists in
docs/UNVERIFIED.md; both rules are enforced.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iarch_brand import product, repo_root  # noqa: E402

GENERATED_BANNER = (
    "<!-- GENERATED FILE - do not edit by hand.\n"
    "     Source: branding/notices.json\n"
    "     Regenerate: python3 tools/notices.py --write\n"
    "     Verify: python3 tools/notices.py --check -->"
)

KIND_ORDER = (
    "vendored-code",
    "derived-config",
    "runtime-dependency",
    "asset",
    "infrastructure",
    "provenance",
)
KIND_HEADINGS = {
    "vendored-code": "Vendored code stored in this repository",
    "derived-config": "Configuration and colors derived from third-party projects",
    "runtime-dependency": "Third-party software this product configures or launches",
    "asset": "Artwork and audio assets stored in this repository",
    "infrastructure": "Third-party services, repositories and registries",
    "provenance": "Where this repository came from",
}
LICENSES_BANNER = (
    "GENERATED FILE - do not edit by hand. "
    "Source: branding/notices.json. Regenerate: python3 tools/notices.py --write"
)
REQUIRED_FIELDS = ("id", "name", "kind", "purpose", "license", "used_by")


def notices_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / product()["IARCH_NOTICES_SOURCE"]


def output_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / product()["IARCH_NOTICES_FILE"]


def licenses_path(root: Path | None = None) -> Path:
    """Machine-readable credit data the settings app reads for About -> Licenses."""
    return (root or repo_root()) / product()["IARCH_LICENSES_FILE"]


def render_licenses(data: Dict[str, Any], root: Path | None = None) -> str:
    values = product(root)
    payload = {
        "_generated": LICENSES_BANNER,
        "_copyright": values["IARCH_COPYRIGHT_HEADER"],
        "notices_version": data["notices_version"],
        "updated": data["updated"],
        "license_information_verified": data["verification"]["date"],
        "verification_method": data["verification"]["method"],
        "product": {
            "name": values["IARCH_PRODUCT_NAME"],
            "license": values["IARCH_LICENSE_ID"],
            "license_file": values["IARCH_LICENSE_FILE"],
            "maintainer": values["IARCH_MAINTAINER"],
            "repository": values["IARCH_REPO_URL"],
            "notices_document": values["IARCH_NOTICES_FILE"],
        },
        "components": [
            {
                "id": c["id"],
                "name": c["name"],
                "kind": c["kind"],
                "license": c["license"],
                "unverified": "TODO(verify)" in str(c["license"]),
                "purpose": c["purpose"],
                **({"copyright": c["copyright"]} if c.get("copyright") else {}),
                **({"version": c["version"]} if c.get("version") else {}),
                **({"upstream": c["upstream"]} if c.get("upstream") else {}),
                "used_by": c.get("used_by", []),
                **({"notes": c["notes"]} if c.get("notes") else {}),
                "open_items": c.get("verify_ids", []),
            }
            for c in data["components"]
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def load(root: Path | None = None) -> Dict[str, Any]:
    return json.loads(notices_path(root).read_text(encoding="utf-8"))


def validate(data: Dict[str, Any], root: Path | None = None) -> List[str]:
    """Return a list of problems with the notices data."""
    problems: List[str] = []
    root_path = root or repo_root()
    kinds = data.get("kinds", {})
    components = data.get("components", [])
    license_texts = data.get("license_texts", {})

    if not components:
        problems.append("notices.json declares no components")

    unverified_doc = root_path / "docs" / "UNVERIFIED.md"
    unverified_text = unverified_doc.read_text(encoding="utf-8") if unverified_doc.is_file() else ""

    seen: set[str] = set()
    for component in components:
        cid = component.get("id", "<missing id>")
        if cid in seen:
            problems.append(f"duplicate component id: {cid}")
        seen.add(cid)

        for field in REQUIRED_FIELDS:
            if not component.get(field):
                problems.append(f"{cid}: field {field} is missing or empty")

        kind = component.get("kind")
        if kind not in kinds:
            problems.append(f"{cid}: unknown kind {kind!r}")
        if kind not in KIND_ORDER:
            problems.append(f"{cid}: kind {kind!r} has no render order")

        license_id = str(component.get("license", ""))
        if not license_id:
            problems.append(f"{cid}: license is empty; write TODO(verify) instead")

        text_key = component.get("license_text") or ""
        if text_key and text_key not in license_texts:
            problems.append(f"{cid}: license_text {text_key!r} is not in license_texts")
        if kind == "vendored-code" and not text_key:
            problems.append(f"{cid}: vendored code must include the license text (license_text)")

        for path in component.get("used_by", []):
            target = root_path / path
            exists = target.is_dir() if path.endswith("/") else target.is_file()
            if not exists:
                problems.append(f"{cid}: used_by path does not exist: {path}")

        for verify_id in component.get("verify_ids", []):
            if "TODO(verify)" in license_id and unverified_text and verify_id not in unverified_text:
                problems.append(f"{cid}: license is TODO(verify) but {verify_id} is not in docs/UNVERIFIED.md")
            elif verify_id and unverified_text and verify_id not in unverified_text:
                problems.append(f"{cid}: verify id {verify_id} is not listed in docs/UNVERIFIED.md")
        if "TODO(verify)" in license_id and not component.get("verify_ids"):
            problems.append(f"{cid}: license is TODO(verify) but no verify_ids entry points at docs/UNVERIFIED.md")

    return problems


def render(data: Dict[str, Any], root: Path | None = None) -> str:
    values = product(root)
    components: List[Dict[str, Any]] = data["components"]
    license_texts: Dict[str, str] = data.get("license_texts", {})
    lines: List[str] = []

    lines.append(f"# Third-party notices — {values['IARCH_PRODUCT_NAME']}")
    lines.append("")
    lines.append(GENERATED_BANNER)
    lines.append("")
    lines.append(
        f"Notices version {data['notices_version']} · updated {data['updated']} · "
        f"license information verified {data['verification']['date']}"
    )
    lines.append("")

    for paragraph in data.get("intro", []):
        lines.append(paragraph)
        lines.append("")

    lines.append("## Product license")
    lines.append("")
    lines.append(
        f"{values['IARCH_PRODUCT_NAME']} is free software: you can redistribute it and/or modify it "
        f"under the terms of the {values['IARCH_LICENSE_ID']} license as published by the Free Software "
        f"Foundation. The complete text is in [`{values['IARCH_LICENSE_FILE']}`]({values['IARCH_LICENSE_FILE']}) "
        "and is not reproduced here."
    )
    lines.append("")
    lines.append(
        f"Maintained by {values['IARCH_MAINTAINER']} · {values['IARCH_REPO_URL']}"
    )
    lines.append("")

    lines.append("## What is listed here")
    lines.append("")
    for kind in KIND_ORDER:
        if kind in data.get("kinds", {}):
            lines.append(f"- **{KIND_HEADINGS[kind]}** — {data['kinds'][kind]}")
    lines.append("")

    for kind in KIND_ORDER:
        group = [c for c in components if c.get("kind") == kind]
        if not group:
            continue
        lines.append(f"## {KIND_HEADINGS[kind]}")
        lines.append("")
        for component in group:
            lines.append(f"### {component['name']}")
            lines.append("")
            lines.append(component["purpose"])
            lines.append("")
            lines.append(f"- **License:** {component['license']}")
            if component.get("copyright"):
                lines.append(f"- **Copyright:** {component['copyright']}")
            if component.get("version"):
                lines.append(f"- **Version checked:** {component['version']}")
            if component.get("upstream"):
                lines.append(f"- **Upstream:** {component['upstream']}")
            lines.append("- **Used by:**")
            for path in component.get("used_by", []):
                lines.append(f"  - `{path}`")
            if component.get("notes"):
                lines.append(f"- **Notes:** {component['notes']}")
            if component.get("verify_ids"):
                ids = ", ".join(f"`{v}`" for v in component["verify_ids"])
                lines.append(f"- **Open verification items:** {ids} in `docs/UNVERIFIED.md`")
            lines.append("")
            if component.get("license_text"):
                # The text belongs to this component, so it is printed with it
                # instead of being pooled at the end of the file.
                lines.append("<details>")
                lines.append(f"<summary>{component['license']} license text</summary>")
                lines.append("")
                if component.get("copyright"):
                    lines.append(component["copyright"])
                    lines.append("")
                for paragraph in license_texts[component["license_text"]].split("\n\n"):
                    lines.append(paragraph)
                    lines.append("")
                lines.append("</details>")
                lines.append("")

    lines.append("## Verification")
    lines.append("")
    lines.append(data["verification"]["method"])
    lines.append("")
    lines.append(
        "Items that could not be verified are listed in "
        "[`docs/UNVERIFIED.md`](docs/UNVERIFIED.md). They are never presented as working features."
    )
    lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="fail if THIRD_PARTY_NOTICES.md is out of date")
    group.add_argument("--write", action="store_true", help="regenerate THIRD_PARTY_NOTICES.md")
    group.add_argument("--json", action="store_true", help="print validated notices data as JSON")
    args = parser.parse_args(argv)

    data = load()
    problems = validate(data)
    if problems:
        for problem in problems:
            print(f"notices: {problem}", file=sys.stderr)
        return 1

    if args.json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    rendered = render(data)
    licenses_rendered = render_licenses(data)
    target = output_path()
    licenses_target = licenses_path()
    if args.write:
        target.write_text(rendered, encoding="utf-8")
        licenses_target.parent.mkdir(parents=True, exist_ok=True)
        licenses_target.write_text(licenses_rendered, encoding="utf-8")
        print(f"notices: wrote {target} and {licenses_target}")
        return 0

    stale = 0
    for path, expected in ((target, rendered), (licenses_target, licenses_rendered)):
        if not path.is_file():
            print(f"notices: {path} does not exist; run python3 tools/notices.py --write", file=sys.stderr)
            stale = 1
            continue
        if path.read_text(encoding="utf-8") != expected:
            print(
                f"notices: {path} is out of date with {notices_path()}; "
                "run python3 tools/notices.py --write",
                file=sys.stderr,
            )
            stale = 1
    if stale:
        return 1
    print(f"notices: {target} and {licenses_target} match {notices_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
