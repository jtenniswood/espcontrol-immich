import json
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
