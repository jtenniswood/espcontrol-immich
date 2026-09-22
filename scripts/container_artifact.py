#!/usr/bin/env python3
"""Record or verify a tested Docker archive. Never rebuild during promotion."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile


def run(*args, input=None):
    return subprocess.run(
        args, input=input, text=True, check=True, capture_output=True
    ).stdout


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def config_digest(archive):
    # Docker's classic image store reports the config digest as image Id; the
    # containerd store can report a manifest digest. Read the archive's config
    # explicitly so registry verification works with either store.
    with tarfile.open(archive) as bundle:
        manifests = json.load(bundle.extractfile("manifest.json"))
        if len(manifests) != 1:
            raise ValueError("Expected exactly one candidate image")
        config = bundle.extractfile(manifests[0]["Config"]).read()
        return "sha256:" + hashlib.sha256(config).hexdigest()


def verify_record(record, archive, commit):
    if record["commit"] != commit:
        raise ValueError("Candidate belongs to a different source commit")
    if record["archive_sha256"] != checksum(archive):
        raise ValueError("Candidate archive checksum does not match")
    if record["config_digest"] != config_digest(archive):
        raise ValueError("Candidate image configuration does not match")
    if record.get("acceptance") != "connection-create-render-image-navigation":
        raise ValueError("Candidate has not passed image-delivery acceptance")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("record", "verify"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    manifest = args.archive.with_suffix(".json")
    if args.command == "verify":
        record = json.loads(manifest.read_text())
        verify_record(record, args.archive, args.commit)
    run("docker", "load", "--input", str(args.archive))
    reference = record["image_id"] if args.command == "verify" else args.image
    inspected = json.loads(run("docker", "image", "inspect", reference))[0]
    if (
        inspected["Config"]["Labels"].get("org.opencontainers.image.revision")
        != args.commit
    ):
        raise ValueError("Image revision does not match the checked source")
    if args.command == "record":
        smoke = (Path(__file__).parent / "check_container.py").read_text()
        result = json.loads(
            run(
                "docker",
                "run",
                "--rm",
                "-i",
                "--entrypoint",
                "python3",
                inspected["Id"],
                "-",
                input=smoke,
            )
        )
        record = {
            **result,
            "commit": args.commit,
            "image_id": inspected["Id"],
            "architecture": inspected["Architecture"],
            "archive_sha256": checksum(args.archive),
            "config_digest": config_digest(args.archive),
            "os_packages": run(
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "apk",
                inspected["Id"],
                "info",
                "-v",
            ).splitlines(),
        }
        manifest.write_text(json.dumps(record, indent=2) + "\n")
    elif (
        inspected["Id"] != record["image_id"]
        or inspected["Architecture"] != record["architecture"]
    ):
        raise ValueError("Loaded image differs from the tested candidate")
    print(
        json.dumps(
            {
                key: record[key]
                for key in ("commit", "image_id", "architecture", "archive_sha256")
            }
        )
    )


if __name__ == "__main__":
    main()
