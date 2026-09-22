# Architecture and compatibility

Home Assistant is the primary interface. The optional container uses the same photo engine, while retaining its own storage and HTTP interface. No firmware or display-specific rules live here.

## Ownership

| Location | Owns |
|---|---|
| `custom_components/immich_frames/core/settings.py` | Valid settings, default values, control/source descriptions, screen dimensions and update effects |
| `core/client.py` | Immich requests, validated responses, retries, previews and full-size downloads |
| `core/engine.py` and `core/filtering.py` | Source queries, date/orientation filtering, pairing and complete-slide creation |
| `core/rendering.py` | EXIF rotation, crop/full-image layout, sampled backgrounds and JPEG encoding |
| `core/history.py` | Bounded history, recent-photo exclusion and Previous navigation |
| `core/cache.py` | Atomic, checksummed, source-aware slide storage |
| `core/session.py` | Playback, complete snapshot publication, refresh ordering and recovery |
| Native `settings.py` and container `compatibility.py` | Historical saved-format translation |
| Home Assistant platform modules | Forms, entities, timers, native lifecycle and stable identifiers |
| `src/immich_frames` | Container HTTP interface, handwritten web page, SQLite configuration and compatibility adapters for its existing Photo/Slide objects |
| `scripts/product_contract.py` | Generated English control descriptions and settings reference |
| `scripts/check_installation.py` | Isolated HACS-directory and wheel installation smoke tests |

The shared engine has no Home Assistant dependency. It lives inside the integration directory so a HACS download is self-contained. The Python wheel packages those same source files; there is no second editable copy. Compatibility adapters translate the container's old data objects without implementing a second renderer, source selector or HTTP client.

## Product rules

The native controls and their order are listed in [the generated reference](settings-reference.md). Settings remain on the device page; setup and Configure edit the source. Frame and entity identities are unchanged.

The container now uses the native renderer: exact screen dimensions, centred full images, sampled colour padding, independent fit for each paired tile, and the one-pixel divider. Both interfaces request full-size photos for every layout, with preview fallback. Unmatched portraits in mixed pairing mode are shown in full. These are deliberate changes from the old container's black, top-left padding and forced cropping of pairs.

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

Install test dependencies with `python -m pip install '.[test]'` (plus `-r requirements-native-test.txt` for native tests). Use a normal package installation: editable namespace hooks are incompatible with Home Assistant’s filesystem integration scanner. Pytest explicitly loads the checkout’s `src` and integration directories so tests still exercise the current source.

Run app/core tests with `pytest -q`; run the Home Assistant suite separately with `pytest -q tests_native` using `requirements-native-test.txt` and Python 3.14. CI also checks generated references, isolated wheel and HACS installation contents, Hassfest, HACS publishing requirements, and both container architectures.

Generate a repeatable visual acceptance sheet with `python scripts/render_examples.py /tmp/immich-examples.png`.

Run `python scripts/product_contract.py --check` to check generated content, or omit `--check` to regenerate it after a settings change. Run `python scripts/check_release.py` to verify package/container versions. Native integration and container versions are separate; a release tag must match the native manifest and identifies the exact source commit used for both container images.

The supported release path is **Actions → Publish Immich Frames → Run workflow**: select the reviewed ref and supply its matching version tag. It validates the exact commit, checks for conflicting tags/releases, publishes both container architectures and their manifest, and only then creates the public GitHub release. No public release is created if a prerequisite fails. Container images are published in the same workflow because releases created with the workflow token do not start a second release-triggered run.

The existing `release: published` trigger remains for releases created outside that path; it validates before publishing container images. A manually published GitHub release is already visible to HACS while those checks run. This automation cannot prevent a repository administrator from bypassing the supported release path.

Hassfest copies the integration into its validation container. It does not bind-mount a runner path, which may be invisible to the Docker daemon on a self-hosted runner.

## Device acceptance

Use an isolated worktree and a ready-for-review feature PR. Install that branch on a test Home Assistant instance, keeping production unchanged. Verify all three screen shapes, individual and paired portraits, an unmatched portrait, both fit settings, Next/Previous, pause/resume, source changes and a restart with Immich offline. Confirm images, metadata and links describe the same photo on the physical display. Record the tested commit, Home Assistant/Immich versions and display in the PR. Automated pixel and package tests do not replace that check.

## Runtime consolidation

`core/session.py` owns a frame's current snapshot, history, pause state,
monotonic generation, refresh serialization and cache recovery. Home Assistant
retains its `DataUpdateCoordinator` and scheduling; the container retains its
HTTP server, task timers and SQLite storage. Neither adapter implements its own
slide publication policy.

The engine and session receive validated `FrameSettings` values. Native saved
entries are translated in `custom_components/immich_frames/settings.py`;
container HTTP and stored records are translated in
`src/immich_frames/compatibility.py`. The older container `FrameConfig`, `Photo`
and `Slide` shapes remain serialization/compatibility interfaces, not a second
runtime. New invalid ranges and booleans are rejected instead of silently
clamped or converted. Historical container cover/contain and native fit rules
remain distinct in their translators.

The control registry also describes source fields and update effects. Timer
changes preserve the current image and history; selection/render changes reject
incompatible snapshots. Labels and reference tables are generated, while the
native setup interaction and lightweight container page remain handwritten.

Playback contract:

- Pause retains the current snapshot and invalidates an in-flight refresh.
- Next resumes playback and requests a new complete slide in both adapters.
- Previous changes image and metadata together and wins over an older in-flight
  refresh. History remains bounded and does not persist across restarts.
- Restart restores the last successfully generated compatible slide, as before;
  Previous does not rewrite the cache. Playback starts unpaused.
- Source/account changes invalidate running and queued work before replacement.
- Cache writes finish before cancellation releases the refresh lock. An older
  source's record cannot restore under the replacement source's signature.
- Authentication failure opens Home Assistant's reauthentication flow. A valid
  cached image remains visible while the key is replaced; the new key keeps the
  config entry and entity identities and requires a newly compatible image.

The deterministic playback scenarios in `tests_native/test_playback_scenarios.py`
run through both adapters. Historical expected settings live in
`tests_core/fixtures/historical-settings.json`. Session clock tests cover cache
date expiry without waiting for the wall clock. These complement the existing
upgrade-identity, cancellation, pixel, package and device acceptance checks.

## Tested release artifacts

CI exports one Docker archive per architecture, runs the installed application's
connection → frame creation → JPEG delivery → navigation acceptance check, and
records the archive checksum, image/config digests, source commit, architecture,
Python packages and OS packages. Artifacts are retained for seven days.

The release workflow downloads those same archives from its validation run,
checks their provenance, and publishes them without a second build. It verifies
that each registry manifest references the tested configuration, then assembles
the multi-architecture manifest from the verified registry digests. Provenance
files are attached to a draft GitHub release before it becomes public. HACS
continues to install the integration from the release's checked source commit.

Mutable dependency ranges may resolve differently in a later run; that does
not change the bytes promoted from this run. For local rehearsal, build an
archive with `SOURCE_COMMIT` set to a clearly identified local candidate, then
run `scripts/container_artifact.py record` and `verify`. Public publication is a
separate release operation.
