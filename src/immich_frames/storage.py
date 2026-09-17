from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import FrameConfig


class Storage:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "frames.db")
        self.db.execute("CREATE TABLE IF NOT EXISTS frames (id TEXT PRIMARY KEY, name TEXT NOT NULL, config TEXT NOT NULL)")
        self.db.commit()

    def list_frames(self) -> list[FrameConfig]:
        rows = self.db.execute("SELECT config FROM frames ORDER BY name").fetchall()
        return [FrameConfig(**json.loads(row[0])) for row in rows]

    def save_frame(self, frame: FrameConfig) -> None:
        data = {
            "frame_id": frame.frame_id, "name": frame.name, "mode": frame.mode, "pair_window_days": frame.pair_window_days,
            "pairs_only": frame.pairs_only, "slideshow_interval": frame.slideshow_interval, "filter": frame.filter,
            "source": frame.source, "memory_window_days": frame.memory_window_days, "fallback_to_all": frame.fallback_to_all,
            "smart_query": frame.smart_query, "smart_reference_asset_id": frame.smart_reference_asset_id,
            "order_field": frame.order_field, "order_direction": frame.order_direction,
            "output_width": frame.output_width, "output_height": frame.output_height, "fit": frame.fit,
        }
        self.db.execute("INSERT OR REPLACE INTO frames(id,name,config) VALUES(?,?,?)", (frame.frame_id, frame.name, json.dumps(data)))
        self.db.commit()

    def delete_frame(self, frame_id: str) -> None:
        self.db.execute("DELETE FROM frames WHERE id=?", (frame_id,))
        self.db.commit()
