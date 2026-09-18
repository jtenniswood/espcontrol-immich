# Native Home Assistant integration

Install EspControl Immich Companion through HACS or copy `custom_components/immich_frames` into Home Assistant's configuration directory. Restart Home Assistant and add **EspControl Immich Companion** under **Settings → Devices & services**. MQTT and a separate container are not required.

## Setup and sources

Enter an Immich URL and read-only API key. The integration verifies the connection, then offers **All photos**, **Albums**, **Memories** or **Keywords**. Albums loads a searchable list, including shared albums, and allows multiple selections. Keywords asks for search text. All photos and Memories continue directly to the frame name.

New frames start at Landscape (1280 × 800), Show full image, mixed photo orientations, individual photos and a 30-second timer. Memories uses a two-day window with no fallback. Existing saved memory-window and fallback settings are retained; the current native interface does not provide a separate memory-settings editor.

To change sources, choose **Configure** on the integration entry. It opens the source selector with the current source selected. Albums and Keywords open their corresponding editor; All photos and Memories save directly. The frame name, display settings and entity identities are kept. Closing the editor without saving leaves the frame unchanged.

Add the integration again for another frame. Existing server/key combinations can be reused and are verified again. Each native frame keeps its own copy of the connection details: deleting one does not disconnect the others, and changing a key does not update other frames.

## Display controls

Use the frame device page for display and timing settings. See [the settings reference](settings-reference.md) for exact values, ordering, defaults and limits.

- **Screen shape:** Landscape is exactly 1280 × 800, Portrait 800 × 1280 and Square 720 × 720. This controls the output, independently of the orientation of selected photos.
- **Photo fit:** Crop to fit fills the screen by trimming edges. Show full image retains the photo's proportions and fills empty space with a dim colour sampled from that photo.
- **Portrait images:** Single portrait photos only; Single and Paired portrait photos; or Paired portrait photos only. Landscapes and square photos can still appear individually when permitted by the independent orientation filter.
- **Photo orientation:** Mixed includes landscapes, portraits and square photos. Portrait-only and landscape-only choices restrict the source. Older square-only saved settings remain supported, but are not offered as a new choice.
- **Pairing window:** 0–7 calendar days, default 2. Zero pairs photos captured on the same date. A pair stays side by side with a one-pixel black divider; each tile has its own fit and sampled background.
- **Time range:** All time, or a rolling month/year range. It applies to every source, both photos in pairs, and the All photos fallback for Memories. Calendar ranges are measured in UTC.
- **Slideshow Timer:** in the **Controls** panel alongside pause/resume and photo navigation; 10–86,400 seconds between slides. Changing this updates the timer without a reload.

In mixed pairing mode, an unmatched portrait is shown in full with a sampled background even if Photo fit is Crop to fit. Paired-only mode skips unmatched and undated portraits. Combine paired-only mode with portrait-only orientation for exclusively portrait pairs.

Display-rule changes save immediately and reload the frame. Reloading restarts the slideshow and clears Previous history. Incompatible cached images are rejected. The slideshow keeps the last compatible image if no eligible photos remain, or reports no matching photos if none is available.

Crop to fit requests a full-size photo only when the preview is too small for the tile. If unavailable, rendering continues with the preview. Images use high JPEG quality with full colour detail. See [image permissions and quality](installation.md#image-quality).

## Navigation and photo details

The device provides pause/resume, Next, Previous, Refresh and Clear cache controls. Metadata sensors describe the single photo or the left photo in a pair. Dates use the photo's recorded date, displayed as **14 May, 2007**. Missing details remain blank; a rating of zero remains 0.

To open a photo, expand the Image entity's Attributes and follow **Open in Immich**. Paired slides also expose **Open second photo in Immich**. Image, metadata and links follow the same displayed snapshot, including Previous navigation and cached slides. Links contain no API key. Your browser must reach the configured Immich server and may require sign-in.

## Upgrades and outages

Updates preserve frame settings and entity identities. Legacy device presets map to their corresponding screen shape: JC1060P470 to Landscape, JC4880P443 to Portrait and 4848S040 to Square. Existing aspect-ratio choices become explicit Photo fit settings.

The shared-engine upgrade changes native saved settings to version 2. Back up Home Assistant before testing it. Old image caches are regenerated because they cannot establish their source and account; **Immich must be reachable for the first image after this upgrade**. Later restarts can restore complete compatible slides during outages. Source, album, keywords, account, display settings, image dimensions and checksums are checked before reuse.

See [architecture, migration and rollback](architecture.md) and [the entity contract](entity-contract.md).
