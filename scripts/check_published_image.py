"""Prove the registry manifest references the tested image configuration."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys

root = Path(sys.argv[1])
record = json.loads((root / "image.json").read_text())
raw = (root / "registry.json").read_bytes()
manifest = json.loads(raw)
if manifest.get("config", {}).get("digest") != record["config_digest"]:
    raise SystemExit("Published image differs from the tested image")
# imagetools emits the raw manifest followed by a newline; registry digests hash
# the manifest itself. Obtain the canonical digest from the descriptor instead.
image = os.environ["IMAGE"]
tag = os.environ["RELEASE_TAG"]
arch = os.environ["ARCH"]
descriptor = json.loads(
    subprocess.check_output(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            f"{image}:{tag}-{arch}",
            "--format",
            "{{json .Manifest}}",
        ],
        text=True,
    )
)
digest = descriptor["digest"]
if digest not in {
    "sha256:" + hashlib.sha256(raw).hexdigest(),
    "sha256:" + hashlib.sha256(raw.rstrip(b"\n")).hexdigest(),
}:
    raise SystemExit("Registry descriptor changed during verification")
(root / "digest.txt").write_text(digest + "\n")
record["registry_digest"] = digest
(root / "image.json").write_text(json.dumps(record, indent=2) + "\n")
