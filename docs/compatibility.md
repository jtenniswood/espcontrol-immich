# Compatibility and feature coverage

The minimum supported server is Immich 3.2.0. The initial test target is Immich 3.2.x. The app checks the server version before enabling structured-search features and reports unavailable capabilities instead of silently dropping an active rule.

Implemented sources and search features:

- Structured metadata search with cursor pagination and typed operators.
- Album, person, tag, favorite, rating, date, location, camera, filename, OCR, and visibility fields where the server exposes them.
- OR branches combined with top-level AND constraints.
- Smart Search text/reference-photo requests.
- On This Day memory windows and optional fallback to the configured ordinary filter.
- Explicit image, non-trashed, non-locked safety constraints.
- Single-image and capture-date matching-pair output.

The app does not modify Immich assets. Uploading, editing, tagging, rating changes, library administration, and video playback are outside the read-only frame scope.

The add-on is built and tested for Home Assistant `amd64`, `aarch64`, `armv7`, `armhf`, and `i386` images. CI builds every declared architecture; a published release creates one multi-architecture GHCR manifest.
