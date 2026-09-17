from pathlib import Path

from immich_frames.models import FrameConfig
from immich_frames.storage import Storage


def test_frame_config_survives_restart(tmp_path: Path) -> None:
    frame = FrameConfig("frame", "Living Room", mode="pairs", filter={"isFavorite": {"eq": True}})
    Storage(tmp_path).save_frame(frame)
    assert Storage(tmp_path).list_frames()[0] == frame

