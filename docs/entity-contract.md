# Home Assistant entity contract

Each configured frame is one native Home Assistant device. Entity IDs are generated from the config entry identifier, so renaming a frame does not break automations.

| Entity | Type | Purpose |
|---|---|---|
| Image | Image | Final rendered single image or pair |
| Date/Location/Filename/People/Tags/Rating/Camera | Sensors | Details for the selected photo: the single image, or the left/right photo in a pair |
| Slideshow | Switch | Pause or resume automatic advancement |
| Show photo details for | Select | Choose “Single photo or left photo in a pair” or “Right photo in a pair” to set which photo supplies the detail sensors |
| Slide interval | Number | 10–86,400 seconds |
| Next, Previous, Refresh, Clear cache | Buttons | Manual frame controls |

The image and metadata entities update from the same coordinator snapshot. The image is replaced only after every selected photo has been downloaded and rendered. During a temporary Immich outage the last complete cached slide remains available.

With a single image, the sensors always use that photo's details, even if the right-photo option is selected. With a pair, the selector chooses the left or right photo. It changes the detail sensors, not the displayed images. The control's details panel includes an explanation. Existing entity IDs and the `primary`/`secondary` automation values remain unchanged; the UI translates those values into the descriptive labels above.
