#!/usr/bin/env python3
"""Smoke-test the actual wheel or HACS directory outside the checkout."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd):
    subprocess.run([sys.executable, *args], cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("wheel", "hacs"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="immich-installation-") as directory:
        root = Path(directory)
        installed = root / "installed"
        installed.mkdir()
        if args.kind == "wheel":
            source = root / "source"
            source.mkdir()
            for name in ("pyproject.toml", "README.md", "LICENSE"):
                shutil.copy(ROOT / name, source / name)
            for name in ("src", "custom_components"):
                shutil.copytree(
                    ROOT / name,
                    source / name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
                )
            run(
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(root / "wheels"),
                str(source),
                cwd=root,
            )
            wheel = next((root / "wheels").glob("immich_frames-*.whl"))
            run(
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(installed),
                str(wheel),
                cwd=root,
            )
        else:
            shutil.copytree(
                ROOT / "custom_components/immich_frames",
                installed / "custom_components/immich_frames",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        code = """
import importlib, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
root = Path(sys.argv[1])
kind = sys.argv[2]
if kind == "wheel":
    class NoHomeAssistant:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "homeassistant" or fullname.startswith("homeassistant."):
                raise AssertionError("The standalone engine imported Home Assistant")
    sys.meta_path.insert(0, NoHomeAssistant())
modules = ["custom_components.immich_frames.core." + name for name in
           ("client", "engine", "cache", "history", "models", "settings", "rendering")]
modules += ["immich_frames.app"] if kind == "wheel" else ["custom_components.immich_frames." + name for name in
           ("config_flow", "coordinator", "image", "select", "number", "button", "sensor", "switch")]
if kind == "wheel":
    from immich_frames.ui import home_page
    page = home_page()
    assert "Landscape (1280 × 800)" in page and "{{display_controls}}" not in page
for name in modules:
    module = importlib.import_module(name)
    assert Path(module.__file__).is_relative_to(root), module.__file__
from custom_components.immich_frames.core.rendering import render
from PIL import Image
from io import BytesIO
raw = BytesIO()
Image.new("RGB", (100, 200), "blue").save(raw, "JPEG")
for shape, size in (("landscape", (1280,800)), ("portrait", (800,1280)), ("square", (720,720))):
    rendered, _ = render([], [raw.getvalue()], shape, "show_full")
    assert Image.open(BytesIO(rendered)).size == size
print(kind + " isolated installation and rendering passed")
"""
        run("-I", "-c", code, str(installed), args.kind, cwd=root)


if __name__ == "__main__":
    main()
