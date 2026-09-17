# Installation

Immich Frames is distributed as a Home Assistant app and is intended for Home Assistant OS or another installation that supports apps. Add this repository to **Settings → Apps → App repositories**, install **Immich Frames**, and install/configure an MQTT broker first.

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

The app uses MQTT discovery. It does not expose the Immich API key through MQTT, image URLs, metadata, or logs. TLS verification remains enabled by default; using an `http://` URL is an explicit local-network choice.

Open the app through its ingress page and create a frame. A frame has a stable identifier, a name, a source, a slideshow interval, and either single-image or matching-pair output. The advanced filter field accepts the typed Immich 3.2 structured-search format.

