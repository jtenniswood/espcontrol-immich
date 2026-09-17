# Native Home Assistant integration

The native integration is the simplest way to use EspControl Immich Companion. It creates one Home Assistant device for each config entry and does not require MQTT, a broker, or a separate app container.

Copy `custom_components/immich_frames` into the Home Assistant configuration directory as `custom_components/immich_frames`, restart Home Assistant, then choose **Settings → Devices & services → Add integration → EspControl Immich Companion**.

Setup is progressive. First enter the Immich URL and read-only API key; Home Assistant verifies the server before continuing. Next choose **All photos**, **Album**, **On This Day memories**, or **Smart Search**. Album mode loads a searchable list of albums available to the connected account, including shared albums, and lets you select by name. The API key needs `album.read` permission in addition to the photo permissions. If the list is empty or cannot be loaded, setup explains the problem and lets you retry or choose another source. Existing frames retain their saved album IDs without any migration. Finally configure the frame name and display behavior. Add one integration entry for each frame. The integration polls Immich, renders the selected image or pair locally, and keeps the last complete image in Home Assistant's `.storage` directory for temporary upstream outages.

The created device includes the rendered image, photo metadata sensors, slideshow pause/resume, next/previous/refresh/clear-cache buttons, a “Show photo details for” control that chooses the single image or the left/right photo in a pair for the detail sensors, and the interval control.

When adding another frame, setup offers existing Immich connections by server URL and frame name. Select one to reuse its URL and API key, or choose **Connect to another Immich server** to enter different details. Saved connections are verified again before continuing. Each frame has its own source and display settings, and keeps a copy of the connection details so deleting the original frame does not disconnect the others. Updating a key in one frame does not update other existing frames.

For HACS, add this repository as a custom repository of type **Integration**, then install EspControl Immich Companion and restart Home Assistant. Manual copying is also supported for development branches.

To change your mind during setup, use **Next action** on the album, memories, Smart Search or display screen. Select a **Back** option (or **Change photo source** on the display screen), then press **Submit**. The form retains your earlier selections and display settings. Choose **Save frame** on the display screen to finish. Only filters for the selected source are saved.

After setup, open **Settings → Devices & services → EspControl Immich Companion**, open the menu for the frame entry and choose **Reconfigure**. Change its source, album or display settings and save. The existing device and entities are retained. Closing the form without saving leaves the frame unchanged.
