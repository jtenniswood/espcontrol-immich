import json
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

def test_legacy_saved_dimensions_are_normalized_on_load(tmp_path):
    storage = Storage(tmp_path)
    config = {"frame_id": "old", "name": "Old frame", "output_width": 4096, "output_height": 4096}
    storage.db.execute("INSERT INTO frames VALUES (?, ?, ?)", ("old", "Old frame", json.dumps(config)))
    storage.db.commit()
    frame = storage.list_frames()[0]
    assert (frame.output_width, frame.output_height) == (1280, 800)


def test_multiple_albums_survive_restart(tmp_path: Path) -> None:
    frame = FrameConfig("frame", "Albums", source="album", album_ids=["a", "b"])
    Storage(tmp_path).save_frame(frame)
    assert Storage(tmp_path).list_frames()[0] == frame


def test_legacy_album_survives_restart(tmp_path: Path) -> None:
    import json
    storage = Storage(tmp_path)
    storage.db.execute("INSERT INTO frames VALUES (?, ?, ?)", ("frame", "Album", json.dumps({
        "frame_id": "frame", "name": "Album", "source": "album", "album_id": "old",
    })))
    storage.db.commit()
    frame = Storage(tmp_path).list_frames()[0]
    assert frame.album_id == "old"
    assert frame.album_ids is None
