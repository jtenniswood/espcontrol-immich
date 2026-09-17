# Home Assistant entity contract

Each configured frame is one native Home Assistant device. Entity IDs are generated from the config entry identifier, so renaming a frame does not break automations.

| Entity | Type | Purpose |
|---|---|---|
| Frame | Image | Final rendered single image or pair |
| Photo date/location/filename/people/tags/rating/camera/latitude/longitude | Sensors | Metadata for the selected primary or secondary photo |
| Status, slide, matching assets | Sensors | Runtime and selection diagnostics |
| Immich connected, using cached image | Binary sensors | Upstream and cache state |
| Slideshow | Switch | Pause or resume automatic advancement |
| Metadata photo | Select | Primary or secondary metadata source |
| Slide interval | Number | 10–86,400 seconds |
| Next, Previous, Refresh, Clear cache | Buttons | Manual frame controls |

The image and metadata entities update from the same coordinator snapshot. The image is replaced only after every selected photo has been downloaded and rendered. During a temporary Immich outage the last complete cached slide remains available; the connectivity binary sensor is off and the status identifies the failure class.

The selected metadata object becomes unavailable when a secondary photo does not exist; metadata from the preceding slide is never retained as if it belonged to the current slide.
