import json
import os
from pathlib import Path

from immich_frames.app import FrameApp
from immich_frames.models import FrameConfig, Photo, Slide


def test_cached_slide_is_restored(tmp_path: Path) -> None:
    app = FrameApp({"immich_url": "http://immich.test", "immich_api_key": "secret"}, tmp_path)
    frame = FrameConfig("frame", "Living room")
    slide = Slide("frame", 4, (Photo("asset", 100, 100, None, None, "photo.jpg"),), b"jpeg", "single")
    (app.cache_dir / "frame.jpg").write_bytes(slide.jpeg)
    (app.cache_dir / "frame.json").write_text(json.dumps(slide.state()))
    app.restore_cached(frame)
    assert app.generation["frame"] == 4
    assert app.slides["frame"].primary.id == "asset"


def test_cache_limit_evicts_old_files(tmp_path: Path) -> None:
    app = FrameApp({"immich_url": "http://immich.test", "immich_api_key": "secret", "cache_limit_mb": 16}, tmp_path)
    app.cache_limit_bytes = 8
    old = app.cache_dir / "old.jpg"
    new = app.cache_dir / "new.jpg"
    old.write_bytes(b"old-data")
    new.write_bytes(b"new-data")
    os.utime(old, (1, 1))
    size = app.enforce_cache_limit()
    assert size <= 8
    assert not old.exists()
