from pathlib import Path

from immich_frames.models import FrameConfig
from immich_frames.storage import Storage


def test_frame_config_survives_restart(tmp_path: Path) -> None:
    frame = FrameConfig("frame", "Living Room", mode="pairs", source="smart", smart_query="mountains", filter={"isFavorite": {"eq": True}})
    Storage(tmp_path).save_frame(frame)
    assert Storage(tmp_path).list_frames()[0] == frame


def test_connection_secrets_are_not_listed(tmp_path: Path) -> None:
    storage = Storage(tmp_path)
    storage.save_connection("home", "Home Immich", "https://photos.example", "secret")
    assert storage.list_connections() == [{"id": "home", "name": "Home Immich", "url": "https://photos.example"}]
    assert storage.get_connection("home") == ("home", "https://photos.example", "secret")
