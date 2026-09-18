# Installation

The recommended installation is the native Home Assistant integration in `custom_components/immich_frames`. It works on Home Assistant OS, Supervised, Container, and Core; MQTT is not required. The repository also contains an optional supervised renderer app for deployments that specifically want an app container.

## HACS installation

This repository can be installed through HACS as a custom repository before its default-list submission. It is not yet included in the default list.

1. Open **HACS**, select the **⋮** menu, then **Custom repositories**.
2. Enter `https://github.com/jtenniswood/espcontrol-immich` and choose **Integration**.
3. Add the repository, search for **EspControl Immich Companion**, and download it.
4. Restart Home Assistant.
5. Open **Settings → Devices & services → Add integration** and select **EspControl Immich Companion**.
6. Supply the Immich connection details and API key described below, then choose your frame's photo source and name. Change display settings on the frame's device page.

Add the integration again to create another frame. To update, download the new version in HACS and restart Home Assistant; the existing frame settings are retained.

The bundled EspControl icon is displayed by Home Assistant 2026.3 and later. Earlier versions may show a placeholder icon.

## Manual installation

Copy the entire `custom_components/immich_frames` directory from the desired release or development branch into `<config>/custom_components/immich_frames`, where `<config>` is the directory containing Home Assistant's `configuration.yaml`. Restart Home Assistant and add **EspControl Immich Companion** under **Settings → Devices & services**.

For a development build, copy this directory from the feature branch you want to test. Keep only one installed copy of the `immich_frames` integration. Back up the existing directory before replacing it, then restart Home Assistant.

## Immich connection and permissions

Enter the Immich server URL and a read-only API key with these permissions:

| Permission | Used for |
|---|---|
| `asset.read` | Search and metadata |
| `asset.view` | Preview images |
| `album.read` | Album catalog and album filters |
| `person.read` | People catalog and people filters |
| `tag.read` | Tag catalog and tag filters |
| `memory.read` | On This Day and saved memories |
| `asset.statistics` | Optional matching counts |

The integration checks `/api/server/version` for Immich 3.2 or later, then performs an authenticated metadata search to verify the API key and its `asset.read` permission before continuing. An empty library can pass this connection check. TLS verification remains enabled by default; using an `http://` URL is an explicit local-network choice.

The integration keeps the last complete rendered slide in Home Assistant's `.storage` directory. If Immich becomes unavailable, the image remains available.

For the optional renderer app, add the repository under **Settings → Apps → App store → Repositories**, install **EspControl Immich Companion**, and open its ingress page. This app path does not create native entities by itself; use the integration for Home Assistant devices and controls.
