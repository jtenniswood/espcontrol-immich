#!/usr/bin/env python3
"""Export the supplied EspControl artwork for Home Assistant and HACS."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = {
    "custom_components/immich_frames/brand/icon.png": 256,
    "custom_components/immich_frames/brand/icon@2x.png": 512,
    "immich_frames/icon.png": 128,
    "immich_frames/logo.png": 256,
}


def main():
    with Image.open(ROOT / "docs/branding/espcontrol.png") as source:
        artwork = source.convert("RGBA")
    if artwork.width != artwork.height:
        raise ValueError("The source icon must be square")
    for relative_path, size in EXPORTS.items():
        destination = ROOT / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        artwork.resize((size, size), Image.Resampling.LANCZOS).save(
            destination, optimize=True
        )
        print(f"{relative_path}: {size} × {size}")


if __name__ == "__main__":
    main()
