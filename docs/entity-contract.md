# Home Assistant entity contract

Each configured frame is one native Home Assistant device. Entity IDs are generated from the config entry identifier, so renaming a frame does not break automations.

| Entity | Type | Purpose |
|---|---|---|
| Image | Image | Final rendered single image or pair; clickable Immich links in its attributes |
| Date/Location/People/Tags/Rating/Camera | Sensors | Details for the single photo, or the left photo in a pair |
| Favourite | Sensor | Yes if the single photo (or left photo in a pair) is a favourite in Immich, No if it is not; blank when the status is missing |
| Slideshow | Switch | Pause or resume automatic advancement |
| Screen shape | Select (Configuration) | Choose Landscape (1280 × 800), Portrait (800 × 1280), or Square (720 × 720); saves the choice and reloads the frame |
| Photo fit | Select (Configuration) | Crop to fit or Show full image |
| Display mode | Select (Configuration) | Single image or Pair portrait photos |
| Time range | Select (Configuration) | All time, or the last 1, 3 or 6 months; 1, 2, 3, 4, 5 or 10 years |
| Photo orientation | Select (Configuration) | Mixed, portrait, landscape or square photos |
| Pairing window | Number (Configuration) | 0–7 days between paired portraits; default 2 days; 0 means the same date |
| Slide interval | Number (Configuration) | 10–86,400 seconds |
| Next, Previous, Refresh, Clear cache | Buttons | Manual frame controls |

The Image entity exposes `open_in_immich` for the single/left photo and `open_second_photo_in_immich` only when a right photo exists. Each is an Immich web URL (`/photos/<asset-id>`) without the API key. Links use the same snapshot as the image, including cached slides and Previous navigation.

The image and metadata entities update from the same coordinator snapshot. The image is replaced only after every selected photo has been downloaded and rendered. During a temporary Immich outage the last complete cached slide remains available.

Photo detail sensors always use the single photo or the left photo in a pair. Existing frames have the old photo-details selector removed automatically when the integration loads, including when Immich is offline.

Screen shape offers the service values `landscape`, `portrait`, and `square`. The existing entity ID is preserved. Saved device presets migrate automatically: `jc1060p470` becomes `landscape`, `jc4880p443` becomes `portrait`, and `4848s040` becomes `square`. Automations that select a retired device value must use its corresponding shape value. See the [screen shapes](native-integration.md) for output dimensions.

Photo and pairing settings save immediately and reload the frame. The interval updates the slideshow timer directly. All settings share the same saved values as Configure and survive Home Assistant restarts. Cached photos are restored only when their photo rules and rendering settings still match.
