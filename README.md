# Immich Frames for Home Assistant

Immich Frames is an original Home Assistant app that turns an Immich 3.2+ library into virtual photo-frame devices. It publishes image, metadata, and slideshow controls through MQTT discovery.

The current foundation implements a persistent frame registry, single-image selection, capture-date matching pairs, rendered JPEG snapshots, MQTT discovery/state publishing, and an ingress configuration page.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
```

The app reads Home Assistant options from `/data/options.json`. API keys are never published to MQTT or included in image URLs.
