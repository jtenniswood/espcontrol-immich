# Home Assistant Core readiness audit

Audit date: 2026-09-19  
Audited source: `origin/main` at `7c6ef8a`  
Local checkout note: the original checkout was on `main` at `ee7b9b5`, eight commits behind `origin/main`. This audit uses the newer remote-main tree where it differs.

## Executive summary

The current integration remains a substantial custom integration, while a separate Home Assistant Core candidate is now submitted for upstream review. The biggest remaining issues are contribution gates and deliberately deferred follow-up scope rather than an unstructured codebase:

1. Home Assistant requires all external-service communication to live in a maintained, typed PyPI library. The original HACS integration still owns a compatibility HTTP client inside `custom_components/immich_frames`, but the submitted Core candidate reuses the built-in `immich` integration and its maintained `aioimmich` dependency.
2. Home Assistant already has a built-in `immich` integration that holds the Immich account connection. The architecture decision is now made for the initial Core contribution: reuse that configured account/session and keep only frame-specific state in `immich_frames`. A second independent Immich client and credential flow remains out of scope.
3. The core submission must be a Home Assistant integration under `homeassistant/components`, not the complete HACS repository. The current optional renderer app, HACS packaging, release automation, and shared application engine need to remain separate from the Core PR.
4. The initial Core candidate is shaped as a Bronze contribution, with the companion documentation and Brands changes submitted separately. Their automated checks are green; maintainer review/merge remains open. Silver, Gold, and Platinum follow-up work is documented and should be staged.
5. Reaching the highest possible quality level is feasible, but it should be staged. Home Assistant explicitly asks new integrations to start at Bronze with a small, single-platform PR rather than submitting every Gold/Platinum feature at once.

The audit began as research only. The follow-up implementation branch now contains a first readiness slice; the status below distinguishes code completed in this repository from external gates that still require a PyPI release, Home Assistant maintainer agreement, or changes in the Home Assistant Core and documentation repositories.

## Current upstream contribution status

The recommended architecture has now been implemented in an isolated Home Assistant Core candidate: `immich_frames` depends on the existing Core `immich` config entry and reuses its maintained `aioimmich==0.17.0` client/session. This removes the need for a new Immich transport package for the initial Core contribution. A standalone client package remains an optional product/reuse decision for the custom repository, not a blocker for this Core path.

Open upstream pull requests:

- Home Assistant Core: [#182693](https://github.com/home-assistant/core/pull/182693) — initial image-only integration contribution.
- Home Assistant documentation: [home-assistant.io #48258](https://github.com/home-assistant/home-assistant.io/pull/48258) — setup, options, entity, cache, troubleshooting, and removal documentation.
- Home Assistant brands: [#11193](https://github.com/home-assistant/brands/pull/11193) — Immich Frames icon and logo assets.
- Maintained `aioimmich`: [#73](https://github.com/mib1185/aioimmich/pull/73) — backward-compatible `max_pages=None` support for following all search pages.

The Core maintainer requested a single platform for the first contribution. The Core candidate therefore ships only the `image` platform; buttons, sensors, and the slideshow switch remain in the custom product and are documented as follow-up Core work. This keeps the first reviewable contribution small without discarding the product implementation.

The Brands PR checks are green, and the contributor CLA check is now passing. The documentation PR is based on the required `next` branch; its new installation/configuration, automation, supported-client, use-case, and limitations documentation is pushed as `43d2a23b`, and its Markdown, text, Astro, header, redirect, and deploy-preview checks all pass. Core deterministic validation (`35477858220`) and the required full CI run (`35477858237`) both passed for the recovery-coverage head. Current non-code blockers are maintainer review/approval and eventual merge of the submitted PRs. These are external workflow gates, not missing implementation in the candidate.

The latest Core candidate head is `6a36b074`. Its focused suite has 76 collected tests with 98% overall branch-aware coverage; config-flow execution coverage is broad, while the contribution remains declared Bronze for the initial review scope. The documented Silver and Gold rules now have evidence: installation/configuration parameters, data updates, examples, known limitations, supported clients, supported functionality, troubleshooting, and use cases are documented; non-applicable entity metadata and repairs are explicitly exempted. Recovery assertions cover corrected retries across user, options, and reconfiguration source-preflight paths, including authentication, connection, upstream, album, and Smart Search branches. The candidate independently tracks the parent account identity, clears the previous account's persistent frame cache in the executor when that identity changes or the parent disappears, prevents stale account-bound fallback after those transitions, hides stale bytes and links after a valid empty refresh or unavailable parent, preserves existing display settings during source reconfiguration, stores user-adjustable frame settings in `ConfigEntry.options` with a v3 migration, allows a valid frame with no currently matching photos to load as unavailable, classifies render/decode failures separately from transport failures, logs upstream-error outages once with recovery, redacts account/frame/album/query identifiers from diagnostics, returns safe diagnostics before a frame has rendered, retries cleanly when the parent is not loaded, routes manual entity refreshes through candidate-cache invalidation, preserves album API errors during setup and options flows, applies rotated EXIF orientation consistently, treats Immich local capture times as wall-clock values for filtering, ordering, and pairing, identifies the logical frame as a service device, rate-limits successful and failed persistent cache writes, and cleans up test-created cache files. Local Ruff, focused behavior assertions, and integration-specific mypy checks are clean; the repository-wide mypy command still reports unrelated baseline errors, and the full local test module is affected by unrelated existing translation fixtures in Core's `immich`, `image`, and `homeassistant` integrations. The preceding deterministic run `35477858220` and full CI run `35477858237` both passed; fresh deterministic run `35478779892` and full CI run `35478779891` also passed for `6a36b074`, and maintainer review remains.

Current development gaps identified during the latest Core review pass are tracked explicitly rather than hidden by the Bronze target:

- The current Core source search path is intentionally bounded to 2,000 matching assets per source because the pinned `aioimmich==0.17.0` client stops after 20 pages. The maintained client now has an upstream patch for backward-compatible `max_pages=None` pagination in [aioimmich #73](https://github.com/mib1185/aioimmich/pull/73), currently at head `ad4e5a8`; its pre-commit checks pass and the new unlimited-pagination test passes. Core adoption still requires that PR to merge, a released version, a Core requirements update, and a follow-up change to opt into unbounded paging. The website documentation correctly states the current limit until that dependency path is released and validated.
- The setup, options, and reconfiguration flows now perform a small source preflight for All photos, albums, and Smart Search, and album setup loads and validates the available album list. They map transport and upstream API failures to translated flow errors. The current source-specific recovery branches are covered; future platforms and migrations need their own branch coverage.
- Diagnostics handle a frame that has no rendered data yet and redact account, frame, album, and query identifiers; corrected-value retries cover user, options, and reconfiguration source-preflight branches. Remaining coverage work is limited to any future platform/migration branches, while the initial image-only flow now has explicit recovery assertions.
- Pairs-only mode now rejects incompatible landscape and square orientation settings, and the image coordinator now honors the configured crop/full fitting choice for an unpaired portrait.
- The cache now persists the rendered timestamp and invalidates the previous cache schema safely; pairs-only candidate filtering uses indexed timestamp ranges rather than rescanning all candidates for every primary.
- Cache signatures now include a non-secret fingerprint of the parent Immich endpoint and API key, preventing an image from the previous server/account being served after parent reconfiguration. In-memory image attributes and payloads are also hidden until the replacement account has produced current data.
- Recent-photo history is bounded and resets after the candidate pool is exhausted, preserving rotation behavior without unbounded memory growth or permanent immediate repeats.
- Candidate retrieval is cached for five minutes and explicitly invalidated for manual refreshes or parent-account identity changes, avoiding a full 2,000-asset request on every 30-second rotation while retaining a predictable refresh path. Parent-account changes also clear in-memory rendered/candidate state so an old account's image cannot be used as fallback. First unavailable transitions are logged at info level and recovery is logged once.
- The image entity now requires a current `ready` coordinator result; cached bytes remain available for connection recovery, while empty, unsupported, render-failed, and upstream-failed updates no longer present an old image as a current healthy frame. A successful empty-source update also hides the old image bytes and asset link.
- The persistent frame cache is still a deliberately small, integration-owned JSON file because it stores rendered image bytes and needs the frame-specific cache signature; a maintainer may still request migration to Home Assistant's `Store` helper, which would require preserving atomic writes, account isolation, timestamp recovery, and deletion semantics.
- Older Immich servers need an explicit compatibility decision for album searches: the pinned `aioimmich` path can ignore the page bound on pre-v3 servers. The Core contribution should either require/document a supported server version or land an upstream pagination strategy before claiming bounded retrieval for those servers.
- A released-HACS-to-Core config-entry migration remains follow-up work; the initial image-only flow has explicit recovery coverage for its current source branches.
- Metadata/control platforms, dynamic discovery, and higher-tier feature follow-ups remain intentionally outside the image-only first contribution. The documented Silver/Gold checklist rules are now represented in `quality_scale.yaml`; the manifest remains Bronze for the maintainers' requested initial contribution scope.
- The latest automated Core review also needs human thread closure. The parent-removal and executor-cache findings are implemented and covered at `94d3245e`; the new `7996a84b` tests now cover successful retries across authentication, connection, and upstream failures for user, options, and reconfiguration flows. The remaining review topics are mapped as follows: sources over 2,000 assets still depend on the released `aioimmich` pagination change, entity availability/strict typing/upstream outage logging and version-1 migration coverage have implementation and CI evidence but await review-thread resolution, and the documentation/PR-template threads need final maintainer confirmation.

## Implementation status on the readiness branch

Completed in this repository:

- Extracted the async Immich transport into `src/immich_frames/client.py`, with injectable `aiohttp.ClientSession`, retries, response validation, EXIF-aware image sizing, and compatibility methods used by the optional app.
- Changed the Home Assistant integration and all platforms to use `ConfigEntry.runtime_data` instead of `hass.data`.
- Injected Home Assistant's managed web session into the coordinator and config flow; the client does not close Home Assistant's session.
- Added `ConfigEntryAuthFailed` handling, one-time unavailable/recovery logging, and a credential-only reauthentication flow with translations.
- Added redacted config-entry diagnostics that never include image bytes or the API key.
- Added manifest `integration_type`/logger metadata and focused diagnostics coverage.
- Preserved the existing rendering, pairing, cache, output-size, migration, and entity-identity contracts; the Home Assistant-native test suite passes 343 tests on the readiness branch, and the shared-client/core contract tests pass separately.
- Built an isolated Home Assistant Core candidate on branch `feature/immich-frames-core` through commit `6a36b074`. It depends on the existing Core `immich` config entry, reuses its `aioimmich` client/session, uses typed `runtime_data`, and includes one image platform with config/options/reconfigure flows, source preflight, exact-size rendering, source filtering, portrait pairing, bounded recent-photo history, bounded candidate retrieval caching, atomic persistent cache with account-identity protection and timestamped recovery, migration, diagnostics, translated selectors, fixed polling, parent reauthentication, parent-reload recovery, cache cleanup, manual-refresh invalidation, EXIF-aware orientation filtering, service-device metadata, rate-limited persistent cache writes, options-error preservation, stale-account fallback protection, current-frame availability semantics, empty-library setup handling, render-error classification, unavailable diagnostics, setup retry handling, settings-in-options migration, corrected config-flow recovery tests, parent-unload guards, redacted diagnostics, local capture-clock handling, isolated test-cache cleanup, unknown-source rejection, in-flight parent-client refresh protection, empty-album safety, executor-based persistent cache cleanup on account identity changes, stale-image endpoint protection when the parent is unavailable, parent-removal invalidation coverage, and documented Silver/Gold quality-scale evidence.
- The Core candidate has 76 collected focused tests covering setup, migration behavior, config-flow branches, source preflight and API errors, corrected retry paths, duplicate-entry handling, image behavior, exact output sizes, pairing, source API calls, cache integrity/timestamps/identity/cleanup, error/recovery paths, upstream outage logging, diagnostics redaction, translated setup errors, fitting behavior, recent-history behavior, candidate cache invalidation, EXIF orientation, service-device metadata, cache-write throttling, reconfiguration persistence, empty-library setup, stale-account image isolation, unavailable-frame diagnostics, parent-unload safety, settings migration, and local capture-clock handling. The measured branch-aware coverage is 98% overall for the integration modules; Ruff, focused behavior checks, and integration-specific mypy configuration are clean; a repository-wide mypy run still reports unrelated baseline errors outside this integration, and the local test module has unrelated existing translation fixture failures outside this integration. Previous deterministic run `35477858220` and full CI run `35477858237` both passed; fresh validation for `6a36b074` is in progress.

Still required before this can be proposed as a built-in integration:

- Complete the external Core PR gates: obtain maintainer review and merge of the Core, documentation, and Brands pull requests. Brands, documentation, and Core automated checks are green, including the latest full Core CI run for the quality-scale update head.
- Keep the existing custom integration and the Core image-only contribution clearly separated. If the custom repository continues to maintain a standalone transport/library, publish and support that package independently; it is not required by the current Core design.
- Complete the remaining feature and migration decisions: the custom integration still covers album/keyword selection, time/orientation filtering, pairing, rendering/output-size contracts, persistent cache, next/previous/refresh/clear controls, slideshow state, metadata/status entities, and its existing migration behavior. The Core candidate intentionally starts with the image platform only. Migration from released HACS entries still needs a maintained mapping to an existing Core `immich` account, and the current `aioimmich` API does not expose the memories operation used by the custom integration.
- Complete the upstream gates: maintainer review and eventual merge of the Core, documentation, Brands, and `aioimmich` PRs. After the pagination dependency is released, update the Core requirement and add a bounded/unbounded integration test before removing the documented source limit. Strict typing and the Silver coverage threshold are evidenced locally and in Core CI for the candidate; higher-tier work remains documented below, including unsupported memories until the shared client has a supported API.

## Important architectural decision

Home Assistant already ships an `immich` integration. Its current manifest identifies it as a local-polling service, uses `aioimmich==0.17.0`, and declares Platinum quality. Its coordinator already creates an async shared Home Assistant web session and stores its coordinator in `ConfigEntry.runtime_data`.

Before implementation, request maintainer feedback on one of these designs:

### Selected for the initial Core contribution: a small `immich_frames` integration that depends on `immich`

- Require the user to configure the existing Immich integration first.
- Let the frame flow select an existing Immich config entry/user instead of collecting the URL and API key again.
- Reuse the existing `aioimmich` connection/session or add the missing frame operations to the library.
- Keep only frame-specific state in `immich_frames`: source/filter, rendering policy, frame identity, cache, and entities.
- Add `dependencies: ["immich"]` only if the final lifecycle and runtime-data contract needs it; a dependency controls setup order but does not configure an Immich entry for the user.

This preserves the current user experience conceptually while avoiding duplicate credentials, API retry logic, SSL handling, and account ownership. It is the architecture used by Core PR #182693 and remains subject to maintainer approval.

### Alternative: add frame support to the existing `immich` integration

This avoids a second integration but requires a design for multiple independently configured frames under one Immich user entry. The existing integration is account/service oriented, while this repository currently treats each frame as its own config entry and device. This option is only attractive if Home Assistant maintainers prefer one Immich integration and accept the additional dynamic-device/configuration work.

Do not implement both designs. The decision affects config-entry identity, migration, ownership of the client, the manifest, and the eventual documentation URL.

## Ranked recommendations

### 1. Resolve the existing-Immich integration boundary

Importance: Critical  
Recommendation strength: Strong  
Work required: Large

Why it matters: A new Core integration must be maintainable for years. Reimplementing Immich authentication, URL parsing, SSL behavior, retries, API models, and account identity beside the existing `immich` integration would make that harder and would likely draw review objections.

Evidence:

- The current custom layer creates its own `aiohttp.ClientSession` and sends raw Immich HTTP requests in `custom_components/immich_frames/api.py`.
- The shared-engine branch still keeps the external client under `custom_components/immich_frames/core/client.py`; moving code into a subdirectory does not satisfy the external-library requirement.
- The Core Immich integration already uses `aioimmich`, `async_get_clientsession`, `ConfigEntry.runtime_data`, reauthentication, and reconfiguration.

User experience impact: No intended change to the frame controls or rendering. The setup experience should become clearer by selecting an existing Immich account rather than asking for the same server credentials again.

Migration approach: Preserve the current `immich_frames` config-entry IDs and frame settings. Add an explicit migration that associates each frame with an existing Immich config entry, with a clear one-time setup path when no matching account exists. Do not silently discard credentials or cached images.

Risk management: First produce a short design issue/PR against Home Assistant Core, including the proposed config-entry relationship and a diagram of one Immich account with multiple frames. Add characterization tests for current settings and cache signatures before changing ownership of the client.

Suggested first step: Ask the Immich integration owners whether they prefer a dependent integration or an extension of `immich`, and confirm what frame/search/thumbnail operations should be added to `aioimmich`.

### 2. Move all Immich communication into an async PyPI library

Importance: Critical  
Recommendation strength: Strong  
Work required: Large

Why it matters: This is an explicit Home Assistant Core eligibility requirement. The initial Core candidate satisfies it by reusing the existing Core `immich` integration and its maintained `aioimmich` dependency. The custom repository's optional standalone client remains a separate packaging decision.

Development needed:

- Extend `aioimmich` if its public API can cleanly support the required searches, albums, memories, thumbnails/full-size images, and metadata.
- If the frame-specific engine later needs API operations that `aioimmich` does not provide, extend `aioimmich` or publish a separate maintained async package on PyPI with source distributions, an issue tracker, documentation, tests, and a stable API. Do not add an unpublished repository-local requirement to Core.
- Keep Pillow-based rendering separate from Immich transport. Rendering is not external communication, but it should have a clear package boundary and must not leak Immich HTTP details into Home Assistant entities.
- Add a pinned manifest requirement and the corresponding Home Assistant `requirements_all.txt` update through the normal generator.
- Ensure the library accepts a Home Assistant-provided `aiohttp.ClientSession` and does not create its own session.

User experience impact: None intended. Keep the current retry, preview/full-size fallback, cache, pairing, and rendering behavior as characterization-tested contracts.

Risk management: Start with a transport adapter that maps the new library objects to the current `FrameSnapshot`. Compare mocked request sequences and rendered bytes before deleting the old client.

### 3. Reduce the first Core contribution to a reviewable Bronze slice

Importance: Critical  
Recommendation strength: Strong  
Work required: Medium after the library decision

Home Assistant asks new integrations to begin at Bronze, keep the PR small, and limit the first contribution to a single platform. The current Core submission follows that guidance with the image platform plus the minimum shared cache/rendering/configuration infrastructure. The custom product can continue to expose buttons, sensors, and switches separately.

Suggested sequence:

1. Core library/client and minimal integration skeleton.
2. One useful first platform, most likely the rendered `image` entity, with UI setup, runtime data, migration, tests, and website documentation.
3. Follow-up PRs for frame controls and metadata entities.
4. Follow-up Silver/Gold/Platinum improvements after the base integration is accepted.

Do not include the Docker/app path, HACS files, release workflows, or unrelated renderer compatibility adapters in the Core PR.

### 4. Make the manifest a real Core manifest

Importance: Critical  
Recommendation strength: Strong  
Work required: Small once the architecture is decided

The original custom manifest is custom-integration oriented:

```json
{
  "domain": "immich_frames",
  "name": "EspControl Immich Companion",
  "codeowners": ["@jtenniswood"],
  "config_flow": true,
  "documentation": "https://github.com/jtenniswood/espcontrol-immich",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/jtenniswood/espcontrol-immich/issues",
  "requirements": [],
  "version": "0.2.13"
}
```

The Core candidate now has the corresponding Core manifest fields (`documentation`, `integration_type`, `quality_scale`, `requirements`, and `loggers`). For Core, development must:

- Change `documentation` to the eventual `https://www.home-assistant.io/integrations/<domain>` page.
- Remove `version`; Core integrations do not carry a custom-component version.
- Remove `issue_tracker`; Core generates the correct issue link.
- Add the correct `integration_type` after the architecture decision.
- Add `quality_scale` once the achieved tier is real.
- Declare exact, transparent requirements and any built-in integration dependencies.
- Add `loggers` for third-party libraries that should be included in debug logging.
- Confirm the final domain/name with Home Assistant maintainers. The existing name describes the EspControl product, while the integration depends on the established Immich service and the existing domain is already used for the separate Core Immich integration.

### 5. Adopt modern Home Assistant config-entry patterns

Importance: High  
Recommendation strength: Strong  
Work required: Large

The Core candidate now addresses the main patterns below. The remaining gap is preserving/migrating released HACS entries if a future Core migration is approved.

Concrete requirements and follow-up gaps:

- Replace the current custom `hass.data[DOMAIN][entry_id]` runtime store with a typed `ConfigEntry.runtime_data` object. **Done in the Core candidate.**
- Separate connection/account identity from frame options. **Done in the Core candidate;** the existing Immich entry owns connection/account data and the frame options flow owns frame settings.
- Use Home Assistant constants such as `CONF_URL` and `CONF_API_KEY`, or use the existing Immich entry so the frame flow does not own those fields.
- Use current `probatio` schemas/selectors, including URL and password selectors, field defaults in the schema, and `data_description` for every field that needs context.
- Use typed config-entry aliases and `ConfigEntryState`/standard exceptions where appropriate.
- Keep the existing versioned migration in the remote-main branch and expand it for the custom-to-Core account association. The older local `main` checkout did not yet contain the migration.

Migration approach: Keep entry IDs, unique IDs, device IDs, entity IDs, source filters, display settings, and cache compatibility rules stable. Add migration tests for every released custom-entry shape, including entries that are offline during startup.

### 6. Implement Core error, authentication, and availability behavior

Importance: High  
Recommendation strength: Strong  
Work required: Medium

The Core candidate now separates connection failures from empty/unsupported/render failures, starts reauthentication on the parent Immich entry, retries when the parent is not loaded, and reports cached connection failures through entity availability. The custom integration still has additional platform-specific error behavior that must be kept aligned if it is maintained separately.

Development needed:

- Let the parent `immich` entry own `ConfigEntryAuthFailed` and reauthentication; the frame integration calls the parent's reauth flow when `aioimmich` rejects credentials and preserves the frame/account relationship.
- Complete reconfiguration tests for changed parent-account associations if maintainers decide that relationship should be mutable from the frame flow. The initial candidate intentionally keeps server URL/API-key changes in the parent Immich entry.
- Raise translated `UpdateFailed` errors for connection failures and no-matching-photo conditions where the entity should remain cached but the service status must be clear.
- Log one meaningful message when unavailable and one when connectivity returns; avoid logging the same failure every polling cycle.
- Decide and test entity availability semantics: the cached image can remain available while Immich is offline, but the integration must not hide authentication failures or make every metadata/control entity look healthy indefinitely.

### 7. Complete translations and entity metadata

Importance: High  
Recommendation strength: Strong  
Work required: Medium

The initial Core candidate covers the image entity and translated setup selectors. The remaining gaps are follow-up platform work:

- Add translation keys for all sensors, buttons, the slideshow switch, and the interval number.
- Add translated exception messages and placeholders rather than exposing raw API exception strings.
- Add icon translations where dynamic icons are needed; otherwise use standard integration icon conventions consistently.
- Audit each entity's `EntityCategory`, `device_class`, units, native value type, and default-enabled state.
- Disable lower-value metadata sensors by default, especially location, people, tags, camera, rating, and favourite, unless a maintainer decides they are all core use cases.
- Keep `has_entity_name = True` and stable unique IDs; these are already present and should not be regressed.

User experience impact: Entity names become more consistent and localizable. Existing entity IDs should remain unchanged.

### 8. Build the Home Assistant website documentation

Importance: High  
Recommendation strength: Strong  
Work required: Medium

The repository documentation is unusually detailed and is a useful source, but Core requires documentation on `home-assistant.io`. The page is now proposed in [home-assistant.io PR #48258](https://github.com/home-assistant/home-assistant.io/pull/48258); keep the following requirements as the review checklist:

- What Immich Frames does and how it relates to the built-in Immich integration.
- Prerequisites, supported Immich versions, required API permissions, and whether an Immich config entry must already exist.
- Complete setup, installation parameters, configuration parameters, reauthentication, reconfiguration, removal, and update behavior.
- Supported entities and controls, data-update cadence, cache/offline behavior, image dimensions, pairing rules, and full-size image fallback.
- Supported and unsupported device/display shapes and known limitations.
- Troubleshooting, debug logging, cache reset behavior, API-key errors, no matching photos, unsupported image formats, and TLS/network failures.
- Automation examples using the entity controls that are actually shipped. Do not invent custom actions, triggers, or conditions unless they are implemented.

The current repo covers high-level description and much of the behavior, but it does not substitute for the Core website page and does not provide a dedicated removal section.

### 9. Add Core tests and measurable coverage

Importance: High  
Recommendation strength: Strong  
Work required: Large

The existing `tests_native` suite provides valuable behavior coverage, especially for setup, config flow, migrations, cache compatibility, output sizes, photo fitting, albums, memories, and navigation. The Core candidate now has a dedicated `tests/components/immich_frames/` suite with 76 collected tests and 98% branch-aware integration-module coverage; current config-flow recovery and local capture-clock assertions cover the initial image-only path, with follow-up platform/migration behavior still requiring its own tests.

Development needed:

- Move/adapt tests to Home Assistant Core's `tests/components/<domain>/` layout.
- Add full config-flow coverage for every branch, validation failure, retry, cancellation, duplicate, reconfigure, reauth, migration, and translation path.
- Test `runtime_data`, unload/reload, `ConfigEntryAuthFailed`, `ConfigEntryNotReady`/`UpdateFailed`, availability, recovery logging, and cache fallback.
- Test all platform entities through Home Assistant services, including entity registry metadata and default-enabled flags.
- Test that credentials never appear in logs, diagnostics, cache files, or flow results.
- Add coverage measurement and reach the documented threshold before claiming Silver.
- Keep rendering tests separate from HA integration tests and continue to use deterministic fixtures.

### 10. Add diagnostics, repairs, and discovery only where they are meaningful

Importance: Medium  
Recommendation strength: Moderate  
Work required: Medium

For Gold/Platinum readiness:

- Add diagnostics that redact API keys and sensitive URLs while showing safe server version, selected source, output shape, cache state, and last error.
- Add repair issues only for conditions that genuinely require user intervention, such as an invalid credential or an incompatible migrated configuration. Do not turn normal empty libraries into noisy repairs.
- Investigate whether Immich exposes a stable Zeroconf/SSDP/DHCP discovery mechanism. If it does, implement discovery and update network information. If it does not, document why the discovery rules are not applicable rather than adding broad unsafe network probes.
- Treat frame devices created explicitly by the user as static config-entry devices unless the final architecture introduces a service that dynamically discovers frames. Do not add dynamic/stale-device machinery just to satisfy a checkbox.

### 11. Reach Platinum deliberately, not in the first PR

Importance: Medium  
Recommendation strength: Strong  
Work required: Medium after Bronze

Platinum-specific work is clear:

- `async-dependency`: use an async PyPI dependency for Immich communication.
- `inject-websession`: accept Home Assistant's managed web session, including SSL verification behavior.
- `strict-typing`: fully type the integration and library boundary, add the relevant `.strict-typing` entry, and pass Home Assistant's typing checks.

The first Core PR should not wait for every Gold/Platinum feature if Bronze is complete and the maintainers agree with the architecture. Follow-up PRs can raise the declared quality scale one tier at a time.

## Development checklist mapping

| Home Assistant development checklist item | Current status | Gap/action |
|---|---|---|
| External communication in a PyPI library | **Pass for the initial Core path** | Core reuses the existing maintained `aioimmich` dependency through the built-in `immich` entry. A separate PyPI package is only required if future frame operations cannot be added to/reused from `aioimmich`. |
| Source distribution available | **Gap** | The release process must publish and verify an sdist, not only wheels. |
| Issue tracker for external library | **Gap/verify** | Maintain an issue tracker and link it in the library project; do not use the custom integration repository as a substitute for library ownership. |
| Requirements in `manifest.json` | **Pass for the initial Core path** | The Core manifest uses the existing exact `aioimmich==0.17.0` requirement and the generated Core requirements file was regenerated and validated. |
| Code owners | **Partial** | The custom manifest names `@jtenniswood`; add the appropriate Core `CODEOWNERS` entry and confirm sustainable ownership. |
| `.strict-typing` | **Pass locally / verify in CI** | The candidate is listed in Core's `.strict-typing`, generated `mypy.ini` is committed, and integration-specific mypy reports no findings; re-run the full Core typing gate in CI. |
| Ruff formatting | **Verify** | Run Home Assistant's actual pre-commit/Ruff checks in a Core checkout; the repository CI check is not equivalent. |
| Deprecation process | **Gap to plan** | Document migration from the custom integration and use Core config-entry migrations for saved data. |
| `home-assistant.io` documentation | **In review** | Companion PR #48258 adds the integration page and links to the Core domain; merge remains an external gate. |

## Integration Quality Scale matrix

Status meanings: **Pass** means evidence exists in the current tree; **Partial** means the idea exists but Core requirements or coverage are incomplete; **Gap** means development is required; **N/A/decision** means it should be justified in the Core PR rather than implemented mechanically.

### Bronze (minimum required for a new Core integration)

| Rule | Status | Evidence and required development |
|---|---|---|
| `action-setup` | N/A/decision | No custom service actions are currently defined. If custom actions are added later, register them in `async_setup`, not per entry. |
| `appropriate-polling` | Pass/verify | The Core candidate uses a fixed 30-second `DataUpdateCoordinator` interval, independent of user options; the website PR documents the cadence and request/render cost. |
| `brands` | Partial | The custom integration has local brand images. Core assets must be submitted to the Home Assistant brands repository. |
| `common-modules` | Pass | `coordinator.py`, `entity.py`, `selection.py`, `rendering.py`, and `cache.py` centralize shared behavior in the Core candidate. |
| `config-flow-test-coverage` | Pass for the initial slice | Core flow tests cover setup, parent availability, source-specific validation/errors, options, reconfigure, and translation paths. HACS-to-Core migration remains a future design because the initial PR does not migrate custom entries. |
| `config-flow` | Pass for the initial slice | The candidate uses `probatio`, translated selectors, descriptions, options/reconfigure flows, and an existing Immich account. HACS migration remains out of scope for the initial PR. |
| `dependency-transparency` | Pass for the initial slice | The candidate declares the existing pinned `aioimmich` dependency through the Core Immich path. Memories remain deliberately unsupported because the maintained client does not expose that API. |
| `docs-actions`, `docs-triggers`, `docs-conditions` | N/A/decision | No custom actions, triggers, or conditions exist. Document entity controls and add these features only when they are truly needed. |
| `docs-high-level-description` | In review | Companion PR #48258 supplies the Core website description and relationship with built-in Immich. |
| `docs-installation-instructions` | In review | Companion PR #48258 supplies standard Home Assistant setup instructions. |
| `docs-removal-instructions` | In review | Companion PR #48258 documents frame removal, cache handling, and preservation of the separate Immich account entry. |
| `entity-event-setup` | N/A/decision | No entity event listeners are currently used. Reassess if the integration starts listening to Home Assistant events. |
| `entity-unique-id` | Pass/verify | Entities use stable entry-ID/key IDs. Preserve them through custom-to-Core migration and test registry continuity. |
| `has-entity-name` | Pass | The base entity sets `_attr_has_entity_name = True`. Keep this pattern. |
| `runtime-data` | Pass | The coordinator is assigned to `entry.runtime_data` and all platforms read it through a typed Core config-entry alias. |
| `test-before-configure` | Pass/partial | The flow validates a loaded Immich account before advancing and validates selected albums. Add full tests for all upstream failure types. |
| `test-before-setup` | Pass/partial | First refresh tests setup and translated update/auth failures are present; add standard Core retry/auth association coverage. |
| `unique-config-entry` | Pass for the initial slice | The candidate uses the selected Immich entry plus a generated stable frame ID, avoiding mutable names as config-entry unique IDs. HACS mapping is future work. |

### Silver

| Rule | Status | Evidence and required development |
|---|---|---|
| `action-exceptions` | N/A/decision | No custom service actions exist. Entity button failures still need normal HA exception handling and tests. |
| `config-entry-unloading` | Pass for the initial slice | `async_unload_entry` unloads the image platform; the shared `aioimmich` client remains owned by the parent `immich` entry and must not be closed by the frame integration. |
| `docs-configuration-parameters` | Partial | Repository docs are detailed; the required Core website page is missing and must separate installation parameters from runtime configuration. |
| `docs-installation-parameters` | Partial | The current API-key permission and URL guidance is useful, but needs to be moved and aligned with the existing Immich account setup. |
| `entity-unavailable` | Pass for the initial slice | The image entity is unavailable unless the coordinator has a current `ready` frame; verified cached bytes remain available internally for recovery and diagnostics. |
| `integration-owner` | Partial | A custom code owner is present; Core needs confirmed maintainers and an appropriate `CODEOWNERS` entry. |
| `log-when-unavailable` | Pass locally / verify in Core | The coordinator logs the first unavailable transition at info level and one info message on recovery; verify the final exception paths against Core's logging tests. |
| `parallel-updates` | Pass | Each candidate platform declares `PARALLEL_UPDATES = 1`; validate the final value against the shared-client concurrency behavior. |
| `reauthentication-flow` | N/A for the initial slice | Authentication is owned by the parent `immich` entry; the frame coordinator starts that parent reauth flow on an unauthorized response. Add full parent/child lifecycle coverage if maintainers keep this boundary. |
| `test-coverage` | Pass locally / verify in CI | The 76-test focused Core suite measures 98% branch-aware coverage across the initial integration modules. Preserve this threshold as follow-up platforms and migrations are added. |

### Gold

| Rule | Status | Evidence and required development |
|---|---|---|
| `devices` | Pass/verify | The base entity creates one device per frame. Preserve device identity and decide whether the final design has one or many devices per Immich account. |
| `diagnostics` | Pass locally / verify in Core | Added diagnostics that expose safe runtime state without image bytes; add the final Core diagnostics test and ensure URLs/account identifiers follow maintainer guidance. |
| `discovery-update-info` | N/A/verify | No supported Immich discovery mechanism has been established. Investigate Zeroconf/SSDP/DHCP before declaring this N/A. |
| `discovery` | N/A/verify | Current setup is manual by URL/account. Implement only if Immich exposes a stable, safe discovery protocol. |
| `docs-data-update` | In review | Companion PR #48258 documents the fixed 30-second polling and cache behavior. |
| `docs-examples` | N/A for the initial slice | The image-only contribution has no custom actions or automation controls; examples belong with follow-up button/switch platforms. |
| `docs-known-limitations` | In review | Companion PR #48258 documents preview-only rendering, unsupported memories, and cache/auth limitations. |
| `docs-supported-devices` | In review | Companion PR #48258 documents the exact supported output dimensions. |
| `docs-supported-functions` | In review | Companion PR #48258 documents the initial image-platform contract. |
| `docs-troubleshooting` | In review | Companion PR #48258 includes debug logging, diagnostics, authentication, connectivity, and no-photo guidance. |
| `docs-use-cases` | In review | Companion PR #48258 describes wall-display and rotating-photo use cases. |
| `dynamic-devices` | N/A/decision | Explicitly configured frame entries are not automatically discovered. Only implement dynamic devices if the selected architecture requires adding frames under an existing Immich account. |
| `entity-category` | N/A for the initial slice | The initial image entity has no configuration-only or diagnostic category. Follow-up platforms need a separate audit. |
| `entity-device-class` | Partial/N/A | Text photo metadata has no obvious standard class; numeric/date entities should be audited and justified. |
| `entity-disabled-by-default` | N/A for the initial slice | The initial image entity is enabled by default. Follow-up metadata sensors need explicit default-enabled decisions. |
| `entity-translations` | Pass locally / verify in Core | The initial image entity and all shipped config/options selectors expose translation keys; follow-up platform entities need their own translations. |
| `exception-translations` | Pass for the initial slice | The Core candidate uses translated coordinator exceptions for setup, connection, image, empty-selection, and unsupported-source failures. |
| `icon-translations` | N/A for the initial slice | The initial Core contribution has only the image platform and no dynamic icon translations. Button/sensor/switch icon work belongs to follow-up platform PRs. |
| `reconfiguration-flow` | Pass for the initial slice | Source/frame reconfiguration is covered; server/account changes remain intentionally owned by the parent Immich entry. HACS account association is future work. |
| `repair-issues` | Gap/decision | Add repairs for actionable migration/auth conditions only; avoid repair spam for normal empty libraries. |
| `stale-devices` | N/A/decision | No service-side dynamic frame discovery currently exists. Revisit if frames become dynamic children of an Immich account. |

### Platinum

| Rule | Status | Required development |
|---|---|---|
| `async-dependency` | Pass for the initial Core path | The candidate reuses the existing asynchronous `aioimmich` dependency through the built-in Immich integration. |
| `inject-websession` | Pass locally / verify in Core | The coordinator and config flow inject Home Assistant's managed session; the client only owns a session when used standalone by the optional app. |
| `strict-typing` | Pass locally / verify in Core | The candidate is listed in Core's `.strict-typing`, uses typed config-entry/runtime-data aliases, and passes focused mypy. Re-run the full Core typing gate in the eventual PR. |

## Core packaging and repository boundaries

The following boundaries are now in place for the open Home Assistant Core PR:

- Core integration files move to `homeassistant/components/<domain>/`.
- Core tests move to `tests/components/<domain>/` and use Home Assistant's standard fixtures.
- The HACS manifest version, `hacs.json`, `repository.yaml`, HACS publishing instructions, custom brand directory, optional app/Docker files, and this repository's release automation stay outside the Core PR.
- Any future standalone Immich client/rendering package remains versioned independently from Home Assistant Core; it is not an unpublished Core requirement.
- Core brand assets go to the Home Assistant brands repository, not only `custom_components/<domain>/brand/`.
- The custom integration needs a documented migration/retirement path so existing users are not left with duplicate `immich` and `immich_frames` accounts or broken entity IDs.

## Recommended delivery plan

### Phase 0 — maintainer alignment (in progress)

- The dependent-integration architecture is implemented in Core PR #182693 and awaits maintainer approval.
- The initial platform has been reduced to `image` per maintainer feedback, and the follow-up review feedback is addressed in the latest pushed commit.
- CLA signature, CI completion, and final reviewer approval remain.

### Phase 1 — reusable library (complete for the initial Core path)

- Implement the async API and rendering boundaries.
- Inject the Home Assistant web session.
- The initial Core path reuses the existing pinned `aioimmich` release. The maintained client’s unbounded-pagination PR is prepared separately; once released, Core can adopt it without introducing a second transport package.
- Add characterization tests for current output dimensions, pairing, fit, cache identity, and failure behavior.

### Phase 2 — Bronze Core integration (submitted)

- Core manifest/file layout, typed `runtime_data`, UI flow, stable generated identity, setup/unload, translated errors, image platform, website page, Brands assets, generated metadata, and Core tests are in the open PR set.
- Run Hassfest, Ruff/pre-commit, mypy/strict typing as applicable, targeted tests, and the full Core test suite relevant to the change.

### Phase 3 — user-facing expansion (future follow-up PRs)

- Add buttons, sensors, and the slideshow switch one platform at a time.
- Add reauth/reconfigure, availability/recovery logs, default-disabled metadata, translations, and automation examples.
- Preserve entity IDs and frame settings through each step.

### Phase 4 — Gold/Platinum

- Add diagnostics, actionable repairs, discovery if a real protocol exists, complete documentation, >95% coverage, and strict typing.
- Raise `quality_scale` only after every rule at that tier is complete and linked in the PR checklist.

## What is already in good shape

- The integration has a real UI config flow and tests connection details before continuing.
- It creates a Home Assistant device per configured frame and uses stable entity IDs.
- The base entity already uses `has_entity_name = True`.
- Setup, unloading, cache fallback, output-size contracts, photo fitting, pairing, albums, and config-flow navigation have meaningful tests. Memories remain unsupported in the Core candidate because `aioimmich` does not expose that operation.
- The shared-engine branch has already separated much of the framework-independent behavior from Home Assistant-specific entities, which is a useful starting point for a real PyPI boundary.
- The repository documentation records detailed current behavior and compatibility contracts; the Core website documentation is now proposed in PR #48258 and documents the image-only first slice and its known limits.

## Checks and evidence reviewed

- Read the current Home Assistant [creating an integration](https://developers.home-assistant.io/docs/creating_component_index/), [development checklist](https://developers.home-assistant.io/docs/development_checklist/), [component checklist](https://developers.home-assistant.io/docs/creating_component_code_review/), [manifest reference](https://developers.home-assistant.io/docs/creating_integration_manifest/), [Core contribution guidance](https://developers.home-assistant.io/docs/core/integration/contributing_to_core/), and [Integration Quality Scale checklist](https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/).
- Compared the repository with the live Home Assistant [Immich integration](https://www.home-assistant.io/integrations/immich) and its current Core manifest/coordinator/config flow.
- Inspected the repository status, local `main` and `origin/main` ancestry, manifest, config flow, coordinator, API/client, platform modules, translations, tests, architecture docs, and CI/release workflows.
- The implementation follow-up was run in isolated worktrees. The custom repository's existing native/client suites remain separate from the Core evidence. In the Home Assistant Core candidate at `6a36b074`, 76 tests are collected, branch-aware integration coverage is 98% overall, Ruff passes, generated `mypy.ini` validates, and deterministic requirements checks pass. A direct repository-wide mypy run reports unrelated baseline/import errors outside `immich_frames`; the Core CI typing gate is the final authority. The focused local assertions pass, while the checkout-wide translation fixture reports unrelated missing keys outside this integration. Full CI run `35477858237` passed all required test, lint, type, hassfest, requirements, and coverage jobs for the recovery-coverage head; deterministic run `35478779892` and full CI run `35478779891` also passed for the quality-scale update.

## References

- [Home Assistant: Creating your first integration](https://developers.home-assistant.io/docs/creating_component_index/)
- [Home Assistant: Development checklist](https://developers.home-assistant.io/docs/development_checklist/)
- [Home Assistant: Component checklist](https://developers.home-assistant.io/docs/creating_component_code_review/)
- [Home Assistant: Integration manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [Home Assistant: Contributing an integration to Core](https://developers.home-assistant.io/docs/core/integration/contributing_to_core/)
- [Home Assistant: Integration Quality Scale checklist](https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/)
- [Home Assistant: Integration Quality Scale rules](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/)
- [Home Assistant: Brand images](https://developers.home-assistant.io/docs/core/integration/brand_images/)
- [Home Assistant Core Immich manifest](https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/components/immich/manifest.json)
- [Home Assistant Core Immich coordinator](https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/components/immich/coordinator.py)
