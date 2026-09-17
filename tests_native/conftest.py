"""Run native integration tests against Home Assistant, without an Immich server."""
from io import BytesIO

import pytest
from PIL import Image

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture
def jpeg():
    output = BytesIO()
    Image.new("RGB", (100, 200), "blue").save(output, "JPEG")
    return output.getvalue()


@pytest.fixture
def asset():
    return {
        "id": "portrait-a", "type": "IMAGE", "originalFileName": "a.jpg",
        "width": 100, "height": 200, "localDateTime": "2026-09-17T12:00:00Z",
        "exifInfo": {"city": "Bath"}, "people": [], "tags": [],
    }
