# EspControl Immich Companion

Turn your Immich photo library into a slideshow for your EspControl display, managed through Home Assistant.

Choose **All photos**, combine **Albums**, revisit **Memories** from around this date, or use **Keywords** such as “beach at sunset”. Show photos individually or pair portrait photos side by side.

## What you need

- Home Assistant with [HACS](https://hacs.xyz/) installed.
- An Immich server running version **3.2 or later**, accessible from Home Assistant.
- Your Immich server address and a **read-only API key** — a key that lets Home Assistant access your photos. See the [required permissions](docs/installation.md#immich-connection-and-permissions).

## Get started

1. In Home Assistant, open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/jtenniswood/espcontrol-immich` and choose **Integration**.
3. Find **EspControl Immich Companion**, download it, and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration** and select **EspControl Immich Companion**.
5. Enter your Immich server address and API key, choose which photos to show, and name your frame.
6. Open the new frame’s device page. Under **Configuration → Screen shape**, choose **Landscape (1280 × 800)**, **Portrait (800 × 1280)**, or **Square (720 × 720)**.

Each frame has its own photo image and slideshow controls in Home Assistant. To create another frame, add the integration again; you can reuse your saved Immich connection.

## Make it yours

On the frame’s device page:

- **Controls:** pause or resume the slideshow, or move to the next or previous photo.
- **Photo timer:** choose how often photos change.
- **Photo fit:** choose **Show full image** to keep the whole photo with a matching background, or **Crop to fit** to fill the screen by trimming the edges.
- **Portrait images:** show one photo or pair portrait photos taken around the same date. A portrait without a matching partner is shown in full with a colour-matched background, even when paired photos use **Crop to fit**.
- **Photo orientation:** choose which photo shapes to include.

To change albums, keywords or other photo sources, open **Settings → Devices & services → EspControl Immich Companion → Configure** for your frame. This opens the photo source editor directly, with the current source selected. As in setup, Albums opens the album picker and Keywords opens the keyword field. All photos and Memories save without another source screen. Your frame name is kept. Display settings are managed on the device page.

Every photo is requested at full size before being resized for your display, in both **Show full image** and **Crop to fit**, including paired photos. Photos are saved at high JPEG quality, keeping fine colour detail. Full-size photos use more bandwidth; if one is unavailable, the slideshow continues using the preview. See [image quality and permissions](docs/installation.md#image-quality).

## Updates and help

Update through HACS, then restart Home Assistant. Your frame settings are kept. Older device presets automatically switch to the matching screen shape and use its dimensions.

See the [installation guide](docs/installation.md) for manual installation and connection help, or [report a problem](https://github.com/jtenniswood/espcontrol-immich/issues).

Development and upgrade details are in [the architecture guide](docs/architecture.md). The shared-engine upgrade regenerates old image caches; Immich must be reachable for the first image after updating. Frame settings and entity identities are preserved.
