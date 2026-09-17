# Immich Frames for Home Assistant

Immich Frames is an original Home Assistant app that turns an Immich 3.2+ library into virtual photo-frame devices. It publishes image, metadata, and slideshow controls through MQTT discovery.

The add-on provides a persistent frame registry, multiple Immich connections, single-image selection, capture-date matching pairs, rendered JPEG snapshots, MQTT discovery/state publishing, cache recovery, and an ingress configuration page. A frame can use Immich structured metadata search, On This Day memories, or Smart Search. Pair mode keeps primary and companion metadata separate so automations can choose either photo.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
```

The app reads Home Assistant options from `/data/options.json`. API keys are never published to MQTT or included in image URLs.

See [installation](docs/installation.md), the [entity contract](docs/entity-contract.md), and the [compatibility matrix](docs/compatibility.md).

The ingress API exposes `GET /api/export` and `POST /api/import` for moving frame definitions between installations. Exports contain frame rules and connection identifiers only; API keys are never exported. Create the matching connection on the destination before importing.
