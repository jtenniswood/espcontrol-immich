# EspControl Immich Companion for Home Assistant

EspControl Immich Companion is an original Home Assistant integration that turns an Immich 3.2+ library into native photo-frame devices. It creates the image, metadata, slideshow, and pair controls directly through Home Assistant's entity system; MQTT is not required.

Each config entry creates one persistent Home Assistant device. A frame can show all photos, select one or more Immich albums by name, use Memories, or use Keywords. Pair mode keeps primary and companion metadata separate so automations can choose either photo. The repository also contains the optional renderer app for supervised installations, but the native integration is the recommended user path.

The native integration offers landscape (1280 × 800), portrait (800 × 1280), or square (720 × 720) output. The optional renderer uses a fixed 16:10 frame at 1280 × 800 pixels.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
```

Native integration tests run against Home Assistant 2026.9.2 with mocked Immich responses, including setup, entity registration, image rendering, and cache recovery. In a separate Python 3.14 environment, install `-e '.[test]' -r requirements-native-test.txt` and run `pytest -q tests_native`. CI runs both suites.

The integration stores the Immich URL and API key in a Home Assistant config entry. API keys are never exposed as entity state, image URLs, or logs.

See [installation](docs/installation.md), the [native integration guide](docs/native-integration.md), the [entity contract](docs/entity-contract.md), and the [compatibility matrix](docs/compatibility.md).

The ingress API exposes `GET /api/export` and `POST /api/import` for moving frame definitions between installations. Exports contain frame rules and connection identifiers only; API keys are never exported. Create the matching connection on the destination before importing.

In the optional renderer app, choose **Albums** to load the selected connection’s album list. Search by name and tick one or more albums; their photos are combined in the frame. **Reload albums** refreshes the list after changes in Immich. Existing single-album frame definitions remain supported.
