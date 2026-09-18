"""Behavior contract for both hosts, without importing Home Assistant."""
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch
import base64
import hashlib
import json

import pytest
from PIL import Image

from custom_components.immich_frames.core.cache import SnapshotStore, connection_identity
from custom_components.immich_frames.core.models import FrameSnapshot
from custom_components.immich_frames.core.settings import migrate_settings, SCREEN_SIZES
from custom_components.immich_frames.core.rendering import render
from custom_components.immich_frames.core.engine import snapshot
from custom_components.immich_frames.api import ImmichApi
from immich_frames.models import FrameConfig
from immich_frames.selection import ClientAdapter
from immich_frames.immich_client import ImmichClient


def jpeg(size=(300, 600), colour="blue"):
    output = BytesIO()
    Image.new("RGB", size, colour).save(output, "JPEG")
    return output.getvalue()


def slide(asset="album-a-photo", generation=1):
    return FrameSnapshot(jpeg((1280, 800)), generation, ({"id": asset, "orientation": "landscape"},),
                         "single", datetime.now(timezone.utc), 1)


def test_source_change_never_restores_old_album(tmp_path):
    store = SnapshotStore(tmp_path / "slide.json")
    store.write(slide(), {"source": "album", "album_ids": ["a"]}, "account")
    assert store.read({"source": "album", "album_ids": ["a"]}, "account").primary["id"] == "album-a-photo"
    assert store.read({"source": "album", "album_ids": ["b"]}, "account") is None


@pytest.mark.parametrize("before,after", [
    ({"source": "smart", "smart_query": "beach"}, {"source": "smart", "smart_query": "mountain"}),
    ({}, {"source": "memories"}), ({}, {"mode": "pairs"}), ({}, {"orientation": "portrait"}),
    ({}, {"pair_window_days": 3}), ({}, {"photo_fit": "crop"}), ({}, {"screen_shape": "portrait"}),
    ({}, {"time_range": "1_year"}), ({}, {"filter": {"rating": {"gte": 4}}}),
])
def test_changed_photo_rules_reject_cache(tmp_path, before, after):
    store = SnapshotStore(tmp_path / "slide.json")
    store.write(slide(), before, "account")
    assert store.read(after, "account") is None


def test_account_identity_and_interval(tmp_path):
    identity = connection_identity("http://immich.test", "private-key")
    store = SnapshotStore(tmp_path / "slide.json")
    store.write(slide(), {}, identity)
    assert "private-key" not in store.path.read_text()
    assert "http://immich.test" not in store.path.read_text()
    assert store.read({"interval": 60}, identity)
    assert store.read({}, connection_identity("http://other.test", "private-key")) is None
    assert store.read({}, connection_identity("http://immich.test", "other-key")) is None


def test_interrupted_write_keeps_complete_previous_slide(tmp_path):
    store = SnapshotStore(tmp_path / "slide.json")
    store.write(slide(), {}, "account")
    with patch("custom_components.immich_frames.core.cache.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError):
            store.write(slide("new-photo", 2), {}, "account")
    assert store.read({}, "account").primary["id"] == "album-a-photo"
    assert list(tmp_path.iterdir()) == [store.path]


@pytest.mark.parametrize("corruption", ["checksum", "dimensions", "metadata", "truncated", "version"])
def test_corrupt_records_are_rejected(tmp_path, corruption):
    store = SnapshotStore(tmp_path / "slide.json")
    store.write(slide(), {}, "account")
    state = json.loads(store.path.read_text())
    if corruption == "checksum":
        state["image"] = base64.b64encode(jpeg((1280, 800), "red")).decode()
    if corruption == "dimensions":
        raw = jpeg((800, 1280))
        state["image"] = base64.b64encode(raw).decode()
        state["sha256"] = hashlib.sha256(raw).hexdigest()
    if corruption == "metadata":
        state["photos"] = [{"id": "different-valid-photo"}]
    if corruption == "version":
        state["render_version"] += 1
    store.path.write_text("{" if corruption == "truncated" else json.dumps(state))
    assert store.read({}, "account") is None


@pytest.mark.parametrize("shape,size", SCREEN_SIZES.items())
@pytest.mark.parametrize("fit", ["show_full", "crop"])
@pytest.mark.parametrize("paired", [False, True])
def test_rendered_dimensions_padding_and_divider(shape, size, fit, paired):
    output, layout = render([], [jpeg()] * (2 if paired else 1), shape, fit)
    with Image.open(BytesIO(output)) as image:
        assert image.size == size
        if paired:
            assert max(image.getpixel((size[0] // 2, size[1] // 2))) < 10
        assert image.getpixel((size[0] // 4, size[1] // 2))[2] > 100
    assert layout == ("side_by_side" if paired else "single")


@pytest.mark.parametrize("legacy,expected", [
    ({"screen_shape": "jc4880p443"}, {"screen_shape": "portrait"}),
    ({"album_id": "old"}, {"album_ids": ["old"]}),
    ({"mode": "pairs", "original_aspect_ratio": True}, {"photo_fit": "show_full"}),
    ({"mode": "pairs", "original_aspect_ratio": False}, {"photo_fit": "crop"}),
])
def test_version_one_upgrades_preserve_behavior(legacy, expected):
    old = {"url": "http://immich.test", "api_key": "secret", "frame_name": "Hall", **legacy}
    result = migrate_settings(old)
    assert all(result[key] == value for key, value in expected.items())
    assert result["url"] == old["url"] and result["frame_name"] == "Hall"
    assert old == {"url": "http://immich.test", "api_key": "secret", "frame_name": "Hall", **legacy}
    assert migrate_settings(result, 2) == result


def test_unknown_future_settings_version_is_not_downgraded():
    with pytest.raises(ValueError):
        migrate_settings({}, 999)


@pytest.mark.parametrize("source", ["all", "album", "smart", "memories"])
@pytest.mark.parametrize("shape", SCREEN_SIZES)
@pytest.mark.parametrize("mode", ["single", "pairs", "pairs_only"])
async def test_hosts_produce_identical_slides(source, shape, mode):
    assets = [{"id": name, "width": 300, "height": 600, "localDateTime": "2026-09-18T12:00:00Z"} for name in ("a", "b")]
    async def request(*args, **kwargs):
        path = args[-1]
        if path == "/api/memories":
            return [{"assets": assets}]
        if "/search/" in path:
            return assets if path.endswith("random") else {"assets": {"items": assets}}
        return jpeg()
    options = {"source": source, "album_ids": ["album"], "smart_query": "beach", "screen_shape": shape,
               "mode": mode, "photo_fit": "show_full", "memory_window_days": 0, "order_direction": "random"}
    native = ImmichApi("http://immich.test", "key")
    container = ImmichClient("http://immich.test", "key")
    native._request = container._request = request
    frame = FrameConfig("frame", "Hall", **options)
    first = await native.snapshot(options, 1, set())
    second = await snapshot(ClientAdapter(container), frame.settings(), 1, set())
    assert first.image == second.image
    assert first.layout == second.layout
    assert [p["id"] for p in first.photos] == [p["id"] for p in second.photos]
