#!/usr/bin/env python3
"""Generate the small product reference; --check never changes files."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from custom_components.immich_frames.core.settings import SETTINGS


def outputs():
    component = ROOT / "custom_components/immich_frames"
    strings = json.loads((component / "strings.json").read_text())
    for spec in SETTINGS:
        if spec.choices:
            # Retained translations for a saved legacy value are intentional.
            old = strings["entity"]["select"].get(spec.entity_key or spec.key, {})
            states = dict(spec.choices)
            if spec.key == "orientation":
                states["square"] = "Square photos only"
            strings["entity"]["select"][spec.entity_key or spec.key] = {
                **old,
                "name": spec.label,
                "state": states,
            }
        elif spec.key == "pair_window_days":
            strings["entity"]["number"][spec.key] = {"name": spec.label}
    encoded = json.dumps(strings, indent=2, ensure_ascii=False) + "\n"
    yield component / "strings.json", encoded
    yield component / "translations/en.json", encoded
    rows = [
        "# Frame settings reference",
        "",
        "Generated from `core/settings.py`. Run `python scripts/product_contract.py` after changing the contract.",
        "",
        "| Control | Service values, in order | Default |",
        "|---|---|---|",
    ]
    for spec in SETTINGS:
        values = (
            "; ".join(f"`{value}` — {label}" for value, label in spec.choices)
            if spec.choices
            else f"{spec.minimum}–{spec.maximum}"
        )
        rows.append(f"| {spec.label} | {values} | `{spec.default}` |")
    rows += [
        "",
        "Screen outputs are exactly Landscape 1280 × 800, Portrait 800 × 1280, and Square 720 × 720.",
        "",
        "Square-only photo selection is retained for old saved configurations, but is not offered as a new native control choice. Square photos remain included in Mixed.",
        "",
        "Setup and Configure edit the photo source; the device page owns these display and timing controls.",
        "",
    ]
    yield ROOT / "docs/settings-reference.md", "\n".join(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, content in outputs():
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(content)
    if stale:
        raise SystemExit("Product reference is out of date: " + ", ".join(stale))


if __name__ == "__main__":
    main()
