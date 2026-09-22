"""Reject substituted archives or commits before an image can be promoted."""

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import tarfile

import pytest

spec = importlib.util.spec_from_file_location(
    "container_artifact", Path(__file__).parents[1] / "scripts/container_artifact.py"
)
artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact)


def candidate(tmp_path):
    archive = tmp_path / "image.tar"
    with tarfile.open(archive, "w") as bundle:
        for name, value in [
            ("manifest.json", [{"Config": "config.json"}]),
            ("config.json", {"architecture": "amd64"}),
        ]:
            payload = json.dumps(value).encode()
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            bundle.addfile(info, BytesIO(payload))
    return archive, {
        "commit": "checked-commit",
        "archive_sha256": artifact.checksum(archive),
        "config_digest": artifact.config_digest(archive),
        "acceptance": "connection-create-render-image-navigation",
    }


@pytest.mark.parametrize("change", ["commit", "archive", "acceptance", "config"])
def test_promotion_rejects_unverified_candidate(tmp_path, change):
    archive, record = candidate(tmp_path)
    artifact.verify_record(record, archive, "checked-commit")
    if change == "commit":
        record["commit"] = "another-commit"
    elif change == "archive":
        archive.write_bytes(archive.read_bytes() + b"changed")
    elif change == "config":
        record["config_digest"] = "sha256:wrong"
    else:
        record["acceptance"] = "not-tested"
    with pytest.raises(ValueError):
        artifact.verify_record(record, archive, "checked-commit")
