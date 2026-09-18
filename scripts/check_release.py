#!/usr/bin/env python3
"""Verify the version of each explicitly versioned deliverable at this commit."""
import json
import os
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
integration = json.loads((ROOT / "custom_components/immich_frames/manifest.json").read_text())["version"]
package = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
match = re.search(r'^version: "([^"]+)"$', (ROOT / "immich_frames/config.yaml").read_text(), re.M)
assert match, "Missing container version"
assert package == match[1], "Python package and container versions disagree"
# Separate package versions are supported deliberately. The release tag is the
# native integration version; containers are tagged with the same release ref.
tag = os.environ.get("RELEASE_TAG")
if tag:
    assert tag == f"v{integration}", f"Release tag {tag!r} must match manifest v{integration}"
print(f"Native integration {integration}; container/package {package}; release tag matches" if tag else f"Native integration {integration}; container/package {package}")
