# Native Home Assistant integration

The native integration is the simplest way to use EspControl Immich Companion. It creates one Home Assistant device for each config entry and does not require MQTT, a broker, or a separate app container.

Copy `custom_components/immich_frames` into the Home Assistant configuration directory as `custom_components/immich_frames`, restart Home Assistant, then choose **Settings → Devices & services → Add integration → EspControl Immich Companion**.

Setup is progressive. First enter the Immich URL and read-only API key; Home Assistant verifies the server before continuing. Next choose **All photos**, **Album by ID**, **On This Day memories**, or **Smart Search**. Album mode asks for the album ID from Immich. Finally configure the frame name and display behavior. Add one integration entry for each frame. The integration polls Immich, renders the selected image or pair locally, and keeps the last complete image in Home Assistant's `.storage` directory for temporary upstream outages.

The created device includes the rendered image, photo metadata sensors, connection and cache binary sensors, slideshow pause/resume, next/previous/refresh/clear-cache buttons, metadata-role selection, and the interval control.

When adding another frame, setup offers existing Immich connections by server URL and frame name. Select one to reuse its URL and API key, or choose **Connect to another Immich server** to enter different details. Saved connections are verified again before continuing. Each frame has its own source and display settings, and keeps a copy of the connection details so deleting the original frame does not disconnect the others. Updating a key in one frame does not update other existing frames.

For HACS, add this repository as a custom repository of type **Integration**, then install EspControl Immich Companion and restart Home Assistant. Manual copying is also supported for development branches.
