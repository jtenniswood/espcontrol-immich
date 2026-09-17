# Compatibility and feature coverage

The minimum supported server is Immich 3.2.0. The initial test target is Immich 3.2.x. The integration checks the server version before setup and reports unavailable capabilities instead of silently dropping an active rule.

Implemented sources and search features:

- All photos source with the safe image/timeline constraints applied automatically.
- Albums source with multiple selections by name using Immich's `albumIds` metadata filter.
- Keywords text/reference-photo requests.
- On This Day memory windows and optional fallback to All photos when no memories are available.
- Explicit image, non-trashed, non-locked safety constraints.
- Single-image and capture-date matching-pair output.
- Local orientation selection (`any`, portrait, landscape, or square) applied after Immich metadata retrieval.

The integration does not modify Immich assets. Uploading, editing, tagging, rating changes, library administration, and video playback are outside the read-only frame scope.

The optional renderer app is built and tested for Home Assistant `amd64` and `aarch64` images. These are the architectures supported by the current official Home Assistant base images. CI builds both declared architectures; a published release creates one multi-architecture GHCR manifest.
