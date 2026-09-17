# Native Home Assistant integration

The native integration is the simplest way to use EspControl Immich Companion. It creates one Home Assistant device for each config entry and does not require MQTT, a broker, or a separate app container.

Copy `custom_components/immich_frames` into the Home Assistant configuration directory as `custom_components/immich_frames`, restart Home Assistant, then choose **Settings → Devices & services → Add integration → EspControl Immich Companion**.

The setup form asks for the Immich URL, a read-only API key, a frame name, the photo source, and display mode. Add one integration entry for each frame. The integration polls Immich, renders the selected image or pair locally, and keeps the last complete image in Home Assistant's `.storage` directory for temporary upstream outages.

The created device includes the rendered image, photo metadata sensors, connection and cache binary sensors, slideshow pause/resume, next/previous/refresh/clear-cache buttons, metadata-role selection, and the interval control.

For HACS, add this repository as a custom repository of type **Integration**, then install EspControl Immich Companion and restart Home Assistant. Manual copying is also supported for development branches.
