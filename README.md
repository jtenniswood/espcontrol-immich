# EspControl Immich Companion for Home Assistant

EspControl Immich Companion is an original Home Assistant integration that turns an Immich 3.2+ library into native photo-frame devices. It creates the image, metadata, slideshow, and pair controls directly through Home Assistant's entity system; MQTT is not required.

Each config entry creates one persistent Home Assistant device. A frame can show all photos, use a specific Immich album ID, use On This Day memories, or use Smart Search. Pair mode keeps primary and companion metadata separate so automations can choose either photo. The repository also contains the optional renderer app for supervised installations, but the native integration is the recommended user path.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
```

The integration stores the Immich URL and API key in a Home Assistant config entry. API keys are never exposed as entity state, image URLs, or logs.

See [installation](docs/installation.md), the [native integration guide](docs/native-integration.md), the [entity contract](docs/entity-contract.md), and the [compatibility matrix](docs/compatibility.md).

The ingress API exposes `GET /api/export` and `POST /api/import` for moving frame definitions between installations. Exports contain frame rules and connection identifiers only; API keys are never exported. Create the matching connection on the destination before importing.
