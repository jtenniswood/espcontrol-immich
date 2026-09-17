# Installation

The recommended installation is the native Home Assistant integration in `custom_components/immich_frames`. It works on Home Assistant OS, Supervised, Container, and Core; MQTT is not required. The repository also contains an optional supervised renderer app for deployments that specifically want an app container.

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

The integration verifies the server against `/api/server/version` before creating the device. TLS verification remains enabled by default; using an `http://` URL is an explicit local-network choice.

The integration keeps the last complete rendered slide in Home Assistant's `.storage` directory. If Immich becomes unavailable, the image remains available and the device reports its cached and connection state.

For the optional renderer app, add the repository under **Settings → Apps → App store → Repositories**, install **Immich Frames**, and open its ingress page. This app path does not create native entities by itself; use the integration for Home Assistant devices and controls.
