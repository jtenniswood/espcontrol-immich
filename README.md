# EspControl Immich Companion for Home Assistant

Licensed under the [MIT License](LICENSE).

EspControl Immich Companion is an original Home Assistant integration that turns an Immich 3.2+ library into native photo-frame devices. It creates the image, metadata, slideshow, and pair controls directly through Home Assistant's entity system; MQTT is not required.

Each config entry creates one persistent Home Assistant device. A frame can show all photos, select one or more Immich albums by name, use Memories, or use Keywords. Photo detail sensors always describe the single photo, or the left photo in a pair. The repository also contains the optional renderer app for supervised installations, but the native integration is the recommended user path.

The native integration offers device-labelled output presets for EspControl displays: 1280 × 800 and 1024 × 600 landscape, 480 × 800 and 800 × 1280 portrait, and 480 × 480 or 720 × 720 square. Choose **Target display** during setup or change it later on the frame’s device page. The optional renderer uses a fixed 16:10 frame at 1280 × 800 pixels.

## Install with HACS

Until this repository is accepted into the HACS default list, add it as a custom repository:

1. Open **HACS → ⋮ → Custom repositories** in Home Assistant.
2. Add `https://github.com/jtenniswood/espcontrol-immich` with type **Integration**.
3. Find **EspControl Immich Companion** in HACS and download it, then restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → EspControl Immich Companion**.
5. Enter your Immich 3.2+ server URL and a read-only API key, then choose the photo source and display settings.

See the [installation guide](docs/installation.md) for API-key permissions, manual installation, and updates. Each frame becomes a Home Assistant device with its own image and controls.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
```

Native integration tests run against Home Assistant 2026.9.2 with mocked Immich responses, including setup, entity registration, image rendering, and cache recovery. In a separate Python 3.14 environment, install `-e '.[test]' -r requirements-native-test.txt` and run `pytest -q tests_native`. CI runs both suites.

The **HACS validation** workflow runs HACS and Hassfest on pushes, pull requests, and published releases, and can be run manually. See [HACS publishing](docs/hacs-publishing.md) for the remaining release and default-list submission steps.

The integration stores the Immich URL and API key in a Home Assistant config entry. API keys are never exposed as entity state, image URLs, or logs.

See [installation](docs/installation.md), the [native integration guide](docs/native-integration.md), the [entity contract](docs/entity-contract.md), and the [compatibility matrix](docs/compatibility.md).

The ingress API exposes `GET /api/export` and `POST /api/import` for moving frame definitions between installations. Exports contain frame rules and connection identifiers only; API keys are never exported. Create the matching connection on the destination before importing.

In the optional renderer app, choose **Albums** to load the selected connection’s album list. Search by name and tick one or more albums; their photos are combined in the frame. **Reload albums** refreshes the list after changes in Immich. Existing single-album frame definitions remain supported.
