# Home Assistant entity contract

Each configured frame is one native Home Assistant device. Entity IDs are generated from the config entry identifier, so renaming a frame does not break automations.

| Entity | Type | Purpose |
|---|---|---|
| Image | Image | Final rendered single image or pair |
| Date/Location/People/Tags/Rating/Camera | Sensors | Details for the single photo, or the left photo in a pair |
| Favourite | Sensor | Yes if the single photo (or left photo in a pair) is a favourite in Immich, No if it is not; blank when the status is missing |
| Slideshow | Switch | Pause or resume automatic advancement |
| Target display | Select (Configuration) | Choose the EspControl device and its resolution: 1280 × 800, 1024 × 600, 480 × 800, 720 × 720, 480 × 480, or 800 × 1280; saves the choice and reloads the frame |
| Photo fit | Select (Configuration) | Crop to fit or Show full image |
| Display mode | Select (Configuration) | Single image or Pair portrait photos |
| Photo orientation | Select (Configuration) | Mixed, portrait, landscape or square photos |
| Pairing window | Number (Configuration) | 0–7 days between paired portraits; 0 means the same date |
| Slide interval | Number (Configuration) | 10–86,400 seconds |
| Next, Previous, Refresh, Clear cache | Buttons | Manual frame controls |

The image and metadata entities update from the same coordinator snapshot. The image is replaced only after every selected photo has been downloaded and rendered. During a temporary Immich outage the last complete cached slide remains available.

Photo detail sensors always use the single photo or the left photo in a pair. Existing frames have the old photo-details selector removed automatically when the integration loads, including when Immich is offline.

Target display labels include the device model, resolution and shape. The existing entity ID and `landscape`, `portrait`, and `square` service values keep their original dimensions. New service values are `jc1060p470` (1024 × 600), `jc4880p443` (480 × 800), and `4848s040` (480 × 480). See the [display presets](native-integration.md) for the device mapping.

Photo and pairing settings save immediately and reload the frame. The interval updates the slideshow timer directly. All settings share the same saved values as Configure and survive Home Assistant restarts. Cached photos are restored only when their photo rules and rendering settings still match.
