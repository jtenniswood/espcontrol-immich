from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class FrameSnapshot:
    image: bytes
    generation: int
    photos: tuple[dict[str, Any], ...]
    layout: str
    created_at: datetime
    matching_assets: int
    connected: bool = True
    using_cache: bool = False
    status: str = "ready"

    @property
    def primary(self) -> dict[str, Any]:
        return self.photos[0]

    @property
    def secondary(self) -> dict[str, Any] | None:
        return self.photos[1] if len(self.photos) > 1 else None
