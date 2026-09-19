# Home Assistant Core readiness audit

Audit date: 2026-09-19  
Audited source: `origin/main` at `7c6ef8a`  
Local checkout note: the original checkout was on `main` at `ee7b9b5`, eight commits behind `origin/main`. This audit uses the newer remote-main tree where it differs.

## Executive summary

The current integration is a substantial and well-tested custom integration, but it is not ready to submit to Home Assistant Core. The biggest blockers are structural rather than cosmetic:

1. Home Assistant requires all external-service communication to live in a maintained, typed PyPI library. The current integration still owns the Immich HTTP client inside `custom_components/immich_frames` and declares no runtime requirements in its manifest.
2. Home Assistant already has a built-in `immich` integration, currently using the async `aioimmich` library and holding the Immich account connection. We need an early architecture decision about reusing that configured account/session or extending the existing integration. A second independent Immich client and credential flow would create avoidable duplication.
3. The core submission must be a Home Assistant integration under `homeassistant/components`, not the complete HACS repository. The current optional renderer app, HACS packaging, release automation, and shared application engine need to remain separate from the Core PR.
4. The current integration misses several Bronze requirements: `ConfigEntry.runtime_data`, transparent pinned dependencies, core manifest fields, Home Assistant website documentation, full config-flow coverage, and core-style error/logging behavior.
5. Reaching the highest possible quality level is feasible, but it should be staged. Home Assistant explicitly asks new integrations to start at Bronze with a small, single-platform PR rather than submitting every Gold/Platinum feature at once.

The audit began as research only. The follow-up implementation branch now contains a first readiness slice; the status below distinguishes code completed in this repository from external gates that still require a PyPI release, Home Assistant maintainer agreement, or changes in the Home Assistant Core and documentation repositories.

## Implementation status on the readiness branch

Completed in this repository:

- Extracted the async Immich transport into `src/immich_frames/client.py`, with injectable `aiohttp.ClientSession`, retries, response validation, EXIF-aware image sizing, and compatibility methods used by the optional app.
- Changed the Home Assistant integration and all platforms to use `ConfigEntry.runtime_data` instead of `hass.data`.
- Injected Home Assistant's managed web session into the coordinator and config flow; the client does not close Home Assistant's session.
- Added `ConfigEntryAuthFailed` handling, one-time unavailable/recovery logging, and a credential-only reauthentication flow with translations.
- Added redacted config-entry diagnostics that never include image bytes or the API key.
- Added manifest `integration_type`/logger metadata and focused diagnostics coverage.
- Preserved the existing rendering, pairing, cache, output-size, migration, and entity-identity contracts; the Home Assistant-native test suite passes 341 tests on the readiness branch, and the shared-client/core contract tests pass separately.

Still required before this can be proposed as a built-in integration:

- Publish the reusable client as a maintained PyPI project with an sdist, public typed API, issue tracker, documentation, and a pinned release; then add that exact requirement to the Core manifest and generated Core requirements.
- Decide with the existing Home Assistant `immich` integration maintainers whether this should depend on the existing Immich config entry or become additional functionality in that integration. The current branch is a transport/library preparation step and does not yet perform that account-ownership migration.
- Create the actual `homeassistant/components/<domain>/` and `tests/components/<domain>/` Core PR, with the final domain/name and Home Assistant website documentation.
- Complete Core-only gates: brands, CODEOWNERS, strict typing, full config-flow/error/coverage checks, translated exception text, default-disabled metadata decisions, and maintainer review.

## Important architectural decision

Home Assistant already ships an `immich` integration. Its current manifest identifies it as a local-polling service, uses `aioimmich==0.17.0`, and declares Platinum quality. Its coordinator already creates an async shared Home Assistant web session and stores its coordinator in `ConfigEntry.runtime_data`.

Before implementation, request maintainer feedback on one of these designs:

### Recommended: a small `immich_frames` integration that depends on `immich`

- Require the user to configure the existing Immich integration first.
- Let the frame flow select an existing Immich config entry/user instead of collecting the URL and API key again.
- Reuse the existing `aioimmich` connection/session or add the missing frame operations to the library.
- Keep only frame-specific state in `immich_frames`: source/filter, rendering policy, frame identity, cache, and entities.
- Add `dependencies: ["immich"]` only if the final lifecycle and runtime-data contract needs it; a dependency controls setup order but does not configure an Immich entry for the user.

This preserves the current user experience conceptually while avoiding duplicate credentials, API retry logic, SSL handling, and account ownership.

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

Why it matters: This is an explicit Home Assistant Core eligibility requirement and the current code fails it. The Home Assistant layer should work with typed library objects, not build request paths, headers, retries, response validation, and API error messages itself.

Development needed:

- Extend `aioimmich` if its public API can cleanly support the required searches, albums, memories, thumbnails/full-size images, and metadata.
- If the frame-specific engine needs a separate library, publish and maintain an async package on PyPI with source distributions, an issue tracker, documentation, tests, and a stable API. It must be reusable outside Home Assistant.
- Keep Pillow-based rendering separate from Immich transport. Rendering is not external communication, but it should have a clear package boundary and must not leak Immich HTTP details into Home Assistant entities.
- Add a pinned manifest requirement and the corresponding Home Assistant `requirements_all.txt` update through the normal generator.
- Ensure the library accepts a Home Assistant-provided `aiohttp.ClientSession` and does not create its own session.

User experience impact: None intended. Keep the current retry, preview/full-size fallback, cache, pairing, and rendering behavior as characterization-tested contracts.

Risk management: Start with a transport adapter that maps the new library objects to the current `FrameSnapshot`. Compare mocked request sequences and rendered bytes before deleting the old client.

### 3. Reduce the first Core contribution to a reviewable Bronze slice

Importance: Critical  
Recommendation strength: Strong  
Work required: Medium after the library decision

Home Assistant asks new integrations to begin at Bronze, keep the PR small, and limit the first contribution to a single platform. The current submission would include image, sensor, select, switch, number, and button platforms plus cache/rendering infrastructure and an optional app. That is appropriate product scope for the custom integration, but too broad for the first Core PR.

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

The current manifest is custom-integration oriented:

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

For Core, development must:

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

Concrete gaps:

- Replace the current `hass.data[DOMAIN][entry_id]` runtime store with a typed `ConfigEntry.runtime_data` object.
- Separate connection/account identity from frame options. The current options flow rewrites `entry.data`; it does not use `ConfigEntry.options` as Home Assistant expects.
- Use Home Assistant constants such as `CONF_URL` and `CONF_API_KEY`, or use the existing Immich entry so the frame flow does not own those fields.
- Use current `probatio` schemas/selectors, including URL and password selectors, field defaults in the schema, and `data_description` for every field that needs context.
- Use typed config-entry aliases and `ConfigEntryState`/standard exceptions where appropriate.
- Keep the existing versioned migration in the remote-main branch and expand it for the custom-to-Core account association. The older local `main` checkout did not yet contain the migration.

Migration approach: Keep entry IDs, unique IDs, device IDs, entity IDs, source filters, display settings, and cache compatibility rules stable. Add migration tests for every released custom-entry shape, including entries that are offline during startup.

### 6. Implement Core error, authentication, and availability behavior

Importance: High  
Recommendation strength: Strong  
Work required: Medium

The current coordinator turns many upstream failures into a cached snapshot with a status string. That is useful product behavior, but it is not enough for Core lifecycle semantics.

Development needed:

- Raise `ConfigEntryAuthFailed` with translated exception text when the API key is rejected, so Home Assistant opens reauthentication instead of silently keeping an apparently healthy entry.
- Add `async_step_reauth` and preserve the configured frame/account relationship during key replacement.
- Complete reconfiguration so a changed server URL/account can be tested and saved without deleting the frame.
- Raise translated `UpdateFailed` errors for connection failures and no-matching-photo conditions where the entity should remain cached but the service status must be clear.
- Log one meaningful message when unavailable and one when connectivity returns; avoid logging the same failure every polling cycle.
- Decide and test entity availability semantics: the cached image can remain available while Immich is offline, but the integration must not hide authentication failures or make every metadata/control entity look healthy indefinitely.

### 7. Complete translations and entity metadata

Importance: High  
Recommendation strength: Strong  
Work required: Medium

The current strings cover the image and select entities, but several entities use hard-coded `_attr_name` values. The remaining gaps are:

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

The repository documentation is unusually detailed and is a useful source, but Core requires documentation on `home-assistant.io`. Create the page after the architecture/domain decision and cover:

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

The existing `tests_native` suite provides valuable behavior coverage, especially for setup, config flow, migrations, cache compatibility, output sizes, photo fitting, albums, memories, and navigation. It is not yet a Home Assistant Core test suite or evidence of the Silver >95% integration-module coverage rule.

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
| External communication in a PyPI library | **Partial** | The transport now lives in `src/immich_frames/client.py`; publish it as the maintained dependency and remove the remaining repository-local compatibility dependency before the Core PR. |
| Source distribution available | **Gap** | The release process must publish and verify an sdist, not only wheels. |
| Issue tracker for external library | **Gap/verify** | Maintain an issue tracker and link it in the library project; do not use the custom integration repository as a substitute for library ownership. |
| Requirements in `manifest.json` | **Gap** | Add the exact published client requirement and update HA's generated `requirements_all.txt`; it is intentionally not pinned to an unpublished package in this branch. |
| Code owners | **Partial** | The custom manifest names `@jtenniswood`; add the appropriate Core `CODEOWNERS` entry and confirm sustainable ownership. |
| `.strict-typing` | **Gap** | Type the Core integration/library boundary and add it once it passes strict checks. |
| Ruff formatting | **Verify** | Run Home Assistant's actual pre-commit/Ruff checks in a Core checkout; the repository CI check is not equivalent. |
| Deprecation process | **Gap to plan** | Document migration from the custom integration and use Core config-entry migrations for saved data. |
| `home-assistant.io` documentation | **Gap** | Add the complete integration page and link it from the Core manifest. |

## Integration Quality Scale matrix

Status meanings: **Pass** means evidence exists in the current tree; **Partial** means the idea exists but Core requirements or coverage are incomplete; **Gap** means development is required; **N/A/decision** means it should be justified in the Core PR rather than implemented mechanically.

### Bronze (minimum required for a new Core integration)

| Rule | Status | Evidence and required development |
|---|---|---|
| `action-setup` | N/A/decision | No custom service actions are currently defined. If custom actions are added later, register them in `async_setup`, not per entry. |
| `appropriate-polling` | Partial | `DataUpdateCoordinator` polls using the configured interval. Add a documented rationale, safe bounds/backoff, and tests for the Immich request/render cost. |
| `brands` | Partial | The custom integration has local brand images. Core assets must be submitted to the Home Assistant brands repository. |
| `common-modules` | Pass/verify | `coordinator.py` and `entity.py` already centralize common patterns. Rework them around `runtime_data` and the shared client without duplicating logic. |
| `config-flow-test-coverage` | Partial | There is broad native flow testing, but it must move to Core layout and cover every branch, including migration, reauth, translations, and cancellation. |
| `config-flow` | Partial | UI setup exists and uses some descriptions, but the flow uses `vol.Schema`, stores settings in `data`, and duplicates Immich credentials. Adopt current selectors/probatio and the selected architecture. |
| `dependency-transparency` | Gap | Empty `requirements` hides the direct `aiohttp`/Pillow/API dependency boundary. Use a maintained pinned PyPI library and expose it correctly. |
| `docs-actions`, `docs-triggers`, `docs-conditions` | N/A/decision | No custom actions, triggers, or conditions exist. Document entity controls and add these features only when they are truly needed. |
| `docs-high-level-description` | Partial | README/repo docs cover the product, but the Core website page does not exist and must explain the relationship with built-in Immich. |
| `docs-installation-instructions` | Partial | Custom/HACS instructions exist; replace them with the standard Home Assistant website setup page for a built-in integration. |
| `docs-removal-instructions` | Gap | Add explicit removal instructions, including what happens to frame entries, cached images, and the separate Immich account entry. |
| `entity-event-setup` | N/A/decision | No entity event listeners are currently used. Reassess if the integration starts listening to Home Assistant events. |
| `entity-unique-id` | Pass/verify | Entities use stable entry-ID/key IDs. Preserve them through custom-to-Core migration and test registry continuity. |
| `has-entity-name` | Pass | The base entity sets `_attr_has_entity_name = True`. Keep this pattern. |
| `runtime-data` | Pass locally / Core typing gap | The coordinator is assigned to `entry.runtime_data` and all platforms read it. Add the typed Core config-entry alias in the eventual Core layout. |
| `test-before-configure` | Pass/partial | The flow validates Immich before advancing. Expand validation to the selected existing account/client and test all failure types. |
| `test-before-setup` | Partial | First refresh tests setup, but Core should use translated `ConfigEntryAuthFailed`/`UpdateFailed` semantics and standard retry behavior. |
| `unique-config-entry` | Partial | The current `url|frame_name` identity prevents duplicate names, but the final identity must be based on the selected Immich account plus frame identity and be tested across migrations. |

### Silver

| Rule | Status | Evidence and required development |
|---|---|---|
| `action-exceptions` | N/A/decision | No custom service actions exist. Entity button failures still need normal HA exception handling and tests. |
| `config-entry-unloading` | Pass/verify | `async_unload_entry` unloads platforms and closes the client. Rework the close path for the shared client/runtime data. |
| `docs-configuration-parameters` | Partial | Repository docs are detailed; the required Core website page is missing and must separate installation parameters from runtime configuration. |
| `docs-installation-parameters` | Partial | The current API-key permission and URL guidance is useful, but needs to be moved and aligned with the existing Immich account setup. |
| `entity-unavailable` | Partial | Cached image behavior is intentional, but authentication and non-cache entities need explicit availability semantics. |
| `integration-owner` | Partial | A custom code owner is present; Core needs confirmed maintainers and an appropriate `CODEOWNERS` entry. |
| `log-when-unavailable` | Pass locally / verify in Core | The coordinator logs one warning per outage and one info message on recovery; verify the final exception paths against Core's logging tests. |
| `parallel-updates` | Gap | No explicit `PARALLEL_UPDATES` declarations were found in the platform modules. Choose and document safe values per platform. |
| `reauthentication-flow` | Pass locally / verify in Core | Invalid API keys raise `ConfigEntryAuthFailed`; the new reauth flow updates only the key and preserves the frame entry. Add full Core flow coverage. |
| `test-coverage` | Gap/unverified | Existing tests are extensive but there is no evidence of the Core >95% integration-module threshold. Add coverage measurement and fill lifecycle/error/metadata gaps. |

### Gold

| Rule | Status | Evidence and required development |
|---|---|---|
| `devices` | Pass/verify | The base entity creates one device per frame. Preserve device identity and decide whether the final design has one or many devices per Immich account. |
| `diagnostics` | Pass locally / verify in Core | Added diagnostics that redact the API key and expose safe runtime state without image bytes; add the final Core diagnostics test and ensure URLs/account identifiers follow maintainer guidance. |
| `discovery-update-info` | N/A/verify | No supported Immich discovery mechanism has been established. Investigate Zeroconf/SSDP/DHCP before declaring this N/A. |
| `discovery` | N/A/verify | Current setup is manual by URL/account. Implement only if Immich exposes a stable, safe discovery protocol. |
| `docs-data-update` | Partial | Polling/cache behavior is documented in repo files; move it to the website and state the final interval/backoff. |
| `docs-examples` | Gap | Add tested automation examples for pause/resume, next/previous, refresh/clear-cache where those entities remain in scope. |
| `docs-known-limitations` | Partial | Repo docs describe many limitations; publish them on the website and keep them distinct from bugs. |
| `docs-supported-devices` | Partial | Screen resolutions are documented, but the Core page needs an explicit supported/unsupported display/device matrix. |
| `docs-supported-functions` | Partial | Entity contract exists; publish the final Core platform/entity list and supported behavior. |
| `docs-troubleshooting` | Gap/partial | Add a dedicated website troubleshooting section with debug logging and diagnostics instructions. |
| `docs-use-cases` | Gap | Add clear use cases, such as a wall display, rotating family photos, album-based display, and offline cache behavior. |
| `dynamic-devices` | N/A/decision | Explicitly configured frame entries are not automatically discovered. Only implement dynamic devices if the selected architecture requires adding frames under an existing Immich account. |
| `entity-category` | Partial | Configuration selects/numbers already use `CONFIG`; audit buttons and metadata against Core conventions. |
| `entity-device-class` | Partial/N/A | Text photo metadata has no obvious standard class; numeric/date entities should be audited and justified. |
| `entity-disabled-by-default` | Gap | Metadata sensors are all enabled by default today; disable low-value/noisy sensors unless the Core design intentionally keeps them enabled. |
| `entity-translations` | Pass locally / verify in Core | Buttons, switch, number, sensor, image, and select entities now expose translation keys; add the final Core translation validation. |
| `exception-translations` | Gap | Raw `ImmichApiError` messages are not Core exception translations. Add translated exception keys/placeholders. |
| `icon-translations` | Gap/verify | Icons are hard-coded in platform code and there is no icon translation resource. Add translated dynamic icons where applicable or document why only static defaults are needed. |
| `reconfiguration-flow` | Partial | A source/frame reconfigure flow exists, but server/account changes are not reconfigurable without relying on the original credentials. Complete the connection path. |
| `repair-issues` | Gap/decision | Add repairs for actionable migration/auth conditions only; avoid repair spam for normal empty libraries. |
| `stale-devices` | N/A/decision | No service-side dynamic frame discovery currently exists. Revisit if frames become dynamic children of an Immich account. |

### Platinum

| Rule | Status | Required development |
|---|---|---|
| `async-dependency` | Partial | The transport is now async and package-isolated, but the package must be published and maintained externally before it meets Core's dependency rule. |
| `inject-websession` | Pass locally / verify in Core | The coordinator and config flow inject Home Assistant's managed session; the client only owns a session when used standalone by the optional app. |
| `strict-typing` | Gap | Type the integration, runtime data, client models, config flow, entities, and exception boundary; add `.strict-typing` and pass Core checks. |

## Core packaging and repository boundaries

The following should be separated before opening a Home Assistant Core PR:

- Core integration files move to `homeassistant/components/<domain>/`.
- Core tests move to `tests/components/<domain>/` and use Home Assistant's standard fixtures.
- The HACS manifest version, `hacs.json`, `repository.yaml`, HACS publishing instructions, custom brand directory, optional app/Docker files, and this repository's release automation stay outside the Core PR.
- The reusable Immich client/rendering package lives on PyPI and is versioned independently from Home Assistant Core.
- Core brand assets go to the Home Assistant brands repository, not only `custom_components/<domain>/brand/`.
- The custom integration needs a documented migration/retirement path so existing users are not left with duplicate `immich` and `immich_frames` accounts or broken entity IDs.

## Recommended delivery plan

### Phase 0 — maintainer alignment

- Confirm separate integration versus extension of `immich`.
- Confirm domain/name, integration type, config-entry relationship, and initial platform.
- Open a design discussion with the Immich integration owners before extracting a library.

### Phase 1 — reusable library

- Implement the async API and rendering boundaries.
- Inject the Home Assistant web session.
- Publish a pinned PyPI release with sdist, tests, issue tracker, and typed public models.
- Add characterization tests for current output dimensions, pairing, fit, cache identity, and failure behavior.

### Phase 2 — Bronze Core integration

- Add Core manifest and file layout.
- Add typed `runtime_data`, config-entry migration, UI flow, unique identity, setup/unload, translated errors, and one platform.
- Add the Home Assistant website page and Core tests.
- Run Hassfest, Ruff/pre-commit, mypy/strict typing as applicable, targeted tests, and the full Core test suite relevant to the change.

### Phase 3 — user-facing expansion

- Add remaining entities one platform at a time.
- Add reauth/reconfigure, availability/recovery logs, default-disabled metadata, translations, and automation examples.
- Preserve entity IDs and frame settings through each step.

### Phase 4 — Gold/Platinum

- Add diagnostics, actionable repairs, discovery if a real protocol exists, complete documentation, >95% coverage, and strict typing.
- Raise `quality_scale` only after every rule at that tier is complete and linked in the PR checklist.

## What is already in good shape

- The integration has a real UI config flow and tests connection details before continuing.
- It creates a Home Assistant device per configured frame and uses stable entity IDs.
- The base entity already uses `has_entity_name = True`.
- Setup, unloading, cache fallback, output-size contracts, photo fitting, pairing, albums, memories, and config-flow navigation have meaningful tests.
- The shared-engine branch has already separated much of the framework-independent behavior from Home Assistant-specific entities, which is a useful starting point for a real PyPI boundary.
- The repository documentation records detailed current behavior and compatibility contracts; it can be converted into Core website documentation after the architecture decision.

## Checks and evidence reviewed

- Read the current Home Assistant [creating an integration](https://developers.home-assistant.io/docs/creating_component_index/), [development checklist](https://developers.home-assistant.io/docs/development_checklist/), [component checklist](https://developers.home-assistant.io/docs/creating_component_code_review/), [manifest reference](https://developers.home-assistant.io/docs/creating_integration_manifest/), [Core contribution guidance](https://developers.home-assistant.io/docs/core/integration/contributing_to_core/), and [Integration Quality Scale checklist](https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/).
- Compared the repository with the live Home Assistant [Immich integration](https://www.home-assistant.io/integrations/immich) and its current Core manifest/coordinator/config flow.
- Inspected the repository status, local `main` and `origin/main` ancestry, manifest, config flow, coordinator, API/client, platform modules, translations, tests, architecture docs, and CI/release workflows.
- The implementation follow-up was run in the isolated readiness worktree. `tests_native`: 341 passed. Shared client/core tests: 82 passed. The full repository run also contains one aiohttp test that needs socket permission under the Home Assistant test plugin; it passes with that test runner override. Ruff reports pre-existing repository-wide style findings, and the managed worktree prevents Ruff/Python cache writes, so Core linting still needs to be run in a normal writable Home Assistant Core checkout.

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
