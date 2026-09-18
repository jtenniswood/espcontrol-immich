from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .models import FrameConfig


class Storage:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "frames.db")
        self.db.execute("CREATE TABLE IF NOT EXISTS frames (id TEXT PRIMARY KEY, name TEXT NOT NULL, config TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS connections (id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, api_key TEXT NOT NULL)")
        self.db.commit()

    def list_frames(self) -> list[FrameConfig]:
        rows = self.db.execute("SELECT config FROM frames ORDER BY name").fetchall()
        frames = []
        for row in rows:
            config = json.loads(row[0])
            version = config.get("settings_version", 1)
            if version > 2:
                raise ValueError("Frame settings require a newer application version")
            if version == 1:
                config.setdefault("fit", "cover")
                config["screen_shape"] = "landscape"  # The previous app always rendered this shape.
                config["photo_fit"] = "show_full" if config["fit"] == "contain" else "crop"
                config["settings_version"] = 2
            config.pop("pairs_only", None)  # Retired setting in older saved frames.
            frames.append(FrameConfig(**config))
        return frames

    def save_frame(self, frame: FrameConfig) -> None:
        data = asdict(frame)
        self.db.execute("INSERT OR REPLACE INTO frames(id,name,config) VALUES(?,?,?)", (frame.frame_id, frame.name, json.dumps(data)))
        self.db.commit()

    def delete_frame(self, frame_id: str) -> None:
        self.db.execute("DELETE FROM frames WHERE id=?", (frame_id,))
        self.db.commit()

    def save_connection(self, connection_id: str, name: str, url: str, api_key: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO connections(id,name,url,api_key) VALUES(?,?,?,?)", (connection_id, name, url.rstrip("/"), api_key))
        self.db.commit()

    def delete_connection(self, connection_id: str) -> None:
        self.db.execute("DELETE FROM connections WHERE id=?", (connection_id,))
        self.db.commit()

    def get_connection(self, connection_id: str) -> tuple[str, str, str] | None:
        return self.db.execute("SELECT id,url,api_key FROM connections WHERE id=?", (connection_id,)).fetchone()

    def list_connections(self) -> list[dict[str, str]]:
        return [{"id": row[0], "name": row[1], "url": row[2]} for row in self.db.execute("SELECT id,name,url FROM connections ORDER BY name")]
