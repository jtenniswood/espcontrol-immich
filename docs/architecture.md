# Architecture and compatibility

Home Assistant is the primary interface. The optional container uses the same photo engine, while retaining its own storage and HTTP interface. No firmware or display-specific rules live here.

## Ownership

| Location | Owns |
|---|---|
| `custom_components/immich_frames/core/settings.py` | Valid settings, default values, control descriptions, screen dimensions and native settings migration |
| `core/client.py` | Immich requests, validated responses, retries, previews and full-size downloads |
| `core/engine.py` and `core/filtering.py` | Source queries, date/orientation filtering, pairing and complete-slide creation |
| `core/rendering.py` | EXIF rotation, crop/full-image layout, sampled backgrounds and JPEG encoding |
| `core/history.py` | Bounded history, recent-photo exclusion and Previous navigation |
| `core/cache.py` | Atomic, checksummed, source-aware slide storage |
| Home Assistant platform modules | Forms, entities, timers, native lifecycle and stable identifiers |
| `src/immich_frames` | Container HTTP interface, handwritten web page, SQLite configuration and compatibility adapters for its existing Photo/Slide objects |
| `scripts/product_contract.py` | Generated English control descriptions and settings reference |
| `scripts/check_installation.py` | Isolated HACS-directory and wheel installation smoke tests |

The shared engine has no Home Assistant dependency. It lives inside the integration directory so a HACS download is self-contained. The Python wheel packages those same source files; there is no second editable copy. Compatibility adapters translate the container's old data objects without implementing a second renderer, source selector or HTTP client.

## Product rules

The native controls and their order are listed in [the generated reference](settings-reference.md). Settings remain on the device page; setup and Configure edit the source. Frame and entity identities are unchanged.

The container now uses the native renderer: exact screen dimensions, centred full images, sampled colour padding, independent fit for each paired tile, the one-pixel divider, and full-size fallback for undersized crops. Unmatched portraits in mixed pairing mode are shown in full. These are deliberate changes from the old container's black, top-left padding and forced cropping of pairs.

Legacy container records keep their landscape size and saved cover/contain preference. New frames default to Show full image; `screen_shape`, `photo_fit` and `time_range` are available through its existing frame API and its creation form. Explicit sort order and legacy square-only orientation remain supported. Display firmware and the native Home Assistant experience are unaffected by these container-specific migration changes.

## Settings upgrades and rollback

Native config entries move from version 1 to 2 through `async_migrate_entry`. This maps old device presets to screen shapes, single-album IDs to album lists, and the old aspect-ratio flag to explicit photo fit. Connection credentials, config-entry identifiers, device identifiers and entity identifiers are retained. Future versions are rejected instead of being silently downgraded.

Container SQLite records are normalized from version 1 when read and saved as version 2 when edited. Their old field names remain supported at the HTTP boundary. Each frame still owns or references its connection as before; this change does not merge credentials across existing native frames.

Back up Home Assistant configuration (including `.storage`) or the container data directory before installing a development branch. To roll back a version-2 native entry to code that only understands version 1, restore the backup and the previous integration together. Do not manually lower the version field. Cache files are disposable; frame settings and identities are not.

## Complete slide records

A single JSON record contains the JPEG, photo metadata, generation, timestamp, exact output size, image checksum, whole-record checksum and settings signature. Credentials are never written into these records. An account-sensitive hash contributes to the signature so changing a server or key invalidates old images.

The signature covers active photo-source rules, display rules and rendering version. Changing only the timer preserves the cache. An atomic replacement publishes the record only after the complete file has been flushed. An interrupted write leaves the previous complete slide available.

Old two-file caches cannot prove their source or account and are discarded. The first image after this upgrade requires Immich to be reachable. Subsequent outages retain a compatible image. Memories caches expire when the calendar date changes, and time-limited photos must still lie inside the current rolling date range. A completed search with no eligible photos has a distinct internal `no_matching_photos` status; it is not classified as a connection outage.

## Development and release checks

Run app/core tests with `pytest -q`; run the Home Assistant suite separately with `pytest -q tests_native` using `requirements-native-test.txt` and Python 3.14. CI also checks generated references, isolated wheel and HACS installation contents, Hassfest, HACS publishing requirements, and both container architectures.

Run `python scripts/product_contract.py --check` to check generated content, or omit `--check` to regenerate it after a settings change. Run `python scripts/check_release.py` to verify package/container versions. Native integration and container versions are separate; a release tag must match the native manifest and identifies the exact source commit used for both container images.

The release workflow reuses validation before publishing container images. Publish a GitHub release only after the intended commit's PR and default-branch checks pass: a published release is already visible to HACS while release-triggered checks run. This automation does not undo or hide a GitHub release that someone publishes manually.

Hassfest copies the integration into its validation container. It does not bind-mount a runner path, which may be invisible to the Docker daemon on a self-hosted runner.

## Device acceptance

Use an isolated worktree and a ready-for-review feature PR. Install that branch on a test Home Assistant instance, keeping production unchanged. Verify all three screen shapes, individual and paired portraits, an unmatched portrait, both fit settings, Next/Previous, pause/resume, source changes and a restart with Immich offline. Confirm images, metadata and links describe the same photo on the physical display. Record the tested commit, Home Assistant/Immich versions and display in the PR. Automated pixel and package tests do not replace that check.
