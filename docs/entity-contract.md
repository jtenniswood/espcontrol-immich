# Home Assistant entity contract

Each configured frame is one native Home Assistant device. Entity IDs are generated from the config entry identifier, so renaming a frame does not break automations.

| Entity | Type | Purpose |
|---|---|---|
| Image | Image | Final rendered single image or pair |
| Date/Location/Filename/People/Tags/Rating/Camera | Sensors | Details for the selected photo: the single image, or the left/right photo in a pair |
| Favourite | Sensor | Yes if the selected photo is a favourite in Immich, No if it is not; blank when the status is missing |
| Slideshow | Switch | Pause or resume automatic advancement |
| Show photo details for | Select (Configuration) | Choose “Single photo or left photo in a pair” or “Right photo in a pair” to set which photo supplies the detail sensors |
| Target display | Select (Configuration) | Choose the EspControl device and its resolution: 1280 × 800, 1024 × 600, 480 × 800, 720 × 720, 480 × 480, or 800 × 1280; saves the choice and reloads the frame |
| Slide interval | Number (Configuration) | 10–86,400 seconds |
| Next, Previous, Refresh, Clear cache | Buttons | Manual frame controls |

The image and metadata entities update from the same coordinator snapshot. The image is replaced only after every selected photo has been downloaded and rendered. During a temporary Immich outage the last complete cached slide remains available.

With a single image, the sensors always use that photo's details, even if the right-photo option is selected. With a pair, the selector chooses the left or right photo. It changes the detail sensors, not the displayed images. The control's details panel includes an explanation. Existing entity IDs and the `primary`/`secondary` automation values remain unchanged; the UI translates those values into the descriptive labels above.

Target display labels include the device model, resolution and shape. The existing entity ID and `landscape`, `portrait`, and `square` service values keep their original dimensions. New service values are `jc1060p470` (1024 × 600), `jc4880p443` (480 × 800), and `4848s040` (480 × 480). See the [display presets](native-integration.md) for the device mapping.
