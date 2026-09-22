# EspControl branding

`espcontrol.png` is the supplied 864 × 864 EspControl icon: a white touch mark inside a blue house, with a transparent background. It is the source for the current branding. Preserve its colours, proportions, and transparency when exporting it.

`espcontrol.svg` is the previous white-only artwork, retained for reference. Its source repository provides that artwork under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/). Preserve that notice unless the artwork owner explicitly licences those copies under different terms.

## Exports

Run `python scripts/export_branding.py` with the project's Pillow dependency installed to regenerate:

- `custom_components/immich_frames/brand/icon.png`: 256 × 256 pixels.
- `custom_components/immich_frames/brand/icon@2x.png`: 512 × 512 pixels.
- `immich_frames/icon.png`: 128 × 128 pixels for the optional Home Assistant add-on.
- `immich_frames/logo.png`: 256 × 256 pixels for the add-on detail page.

The integration uses the same artwork in light and dark themes, and its icon also serves as the logo fallback. The README uses an absolute image URL so it can render in GitHub and HACS; that URL reflects the repository's default branch after publication.

## Home Assistant and HACS

Home Assistant **2026.3 or later** loads the integration's bundled `brand/` assets automatically. HACS downloads these assets with the integration; no icon setting is needed in `hacs.json`. See the [Home Assistant brand image documentation](https://developers.home-assistant.io/docs/core/integration/brand_images/), [HACS brand requirements](https://www.hacs.xyz/docs/publish/integration/#brand-assets), and [add-on image requirements](https://developers.home-assistant.io/docs/apps/presentation/#app-icon--logo).

After publishing and installing the updated version, restart Home Assistant and refresh the browser to check the integration icon. Older Home Assistant versions do not load bundled branding.

HACS dashboard icons have a separate upstream limitation: [hacs/integration#5402](https://github.com/hacs/integration/issues/5402) reports a placeholder even when Home Assistant displays the bundled icon correctly. These files satisfy the documented HACS branding requirement, but cannot guarantee the dashboard thumbnail on affected HACS versions. Verify the HACS repository page and dashboard separately during release testing.
