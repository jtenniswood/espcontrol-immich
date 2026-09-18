# Publishing to the HACS default list

The integration supports HACS custom-repository installation. Inclusion in the default list requires a separate submission to [hacs/default](https://github.com/hacs/default) after the release and validation steps below; adding the validation workflow does not automatically list the integration.

## Repository requirements

- Keep the repository public and active, with issues enabled and a description explaining the integration.
- Keep relevant GitHub topics configured, including `hacs`, `home-assistant`, `custom-component`, `immich`, and `espcontrol`. Topics are repository settings, not files in a release.
- Keep the installation and usage instructions in the root README and linked guides current.
- Ship exactly one integration under `custom_components/immich_frames`, including all its runtime files and the local `brand/icon.png` asset.
- Maintain the required fields in `custom_components/immich_frames/manifest.json`, including the version, owner, documentation, and issue tracker.
- Keep `hacs.json` at the repository root. HACS downloads the integration directory from the selected Git ref; no release ZIP or `filename` setting is needed.

## Validation and release

1. Open a pull request and require successful **HACS** and **Hassfest** checks, alongside the existing test suites. The HACS workflow deliberately has no ignored checks. It runs on pushes, pull requests, published releases, and manual dispatches; it has no scheduled trigger.
2. Test installation through HACS on a Home Assistant instance, restart, and add a frame using an Immich server. Confirm that its image and controls work. Automated tests use mocked Immich responses and do not replace this installation check.
3. Merge the reviewed changes into the repository's default branch and verify its checks pass. The current default branch is `feature/immich-frames-foundation`; do not assume `main` is the release source.
4. Update the integration's manifest version for the release and publish a full GitHub release from a checked commit with the matching version tag, for example `v0.2.14` for manifest version `0.2.14`. A tag alone does not meet the default-list requirements. Use the next available version if that example has already been used.
5. Verify **HACS validation** passes for the published release without ignored checks. The existing release workflow also publishes the optional renderer images; inspect that workflow separately.

HACS uses the latest published release when one exists. Fixes that only exist on a branch will not repair an older release used by the default-list validator.

## Submit for inclusion

Once the checks, installation test, and release are complete, the repository owner or a major contributor can submit it:

1. Fork `hacs/default` under a personal account and create a new branch from its `master` branch.
2. Add `jtenniswood/espcontrol-immich` to the `integration` JSON list in alphabetical order, preserving its formatting.
3. Open a pull request, allow maintainer edits, and complete the current template truthfully. Link the passing validation run and release where requested.
4. Address automated checks and maintainer feedback. HACS acceptance is a separate review, and the integration appears in the default list after the submission is merged and the next scan completes.

See the official [general requirements](https://www.hacs.xyz/docs/publish/start/), [integration requirements](https://www.hacs.xyz/docs/publish/integration/), and [default-list submission instructions](https://www.hacs.xyz/docs/publish/include/).
