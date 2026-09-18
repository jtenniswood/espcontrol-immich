from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal

Mode = Literal["single", "pairs", "pairs_only"]
from custom_components.immich_frames.core.settings import SCREEN_SIZES, FrameSettings
OUTPUT_SIZE = SCREEN_SIZES["landscape"]


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(slots=True, frozen=True)
class Photo:
    id: str
    width: int | None
    height: int | None
    file_created_at: datetime | None
    local_date_time: datetime | None
    original_file_name: str
    original_mime_type: str | None = None
    is_favorite: bool = False
    is_archived: bool = False
    is_trashed: bool = False
    visibility: str = "timeline"
    exif: dict[str, Any] = field(default_factory=dict)
    people: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    checksum: str | None = None
    thumbhash: str | None = None

    @classmethod
    def from_api(cls, value: dict[str, Any]) -> "Photo":
        exif = value.get("exifInfo") or {}
        people = tuple(name.strip() for person in value.get("people") or []
                       if isinstance(name := person.get("name"), str) and name.strip())
        tags = tuple(t.get("name") or t.get("id", "") for t in value.get("tags") or [])
        return cls(
            id=value["id"], width=value.get("width"), height=value.get("height"),
            file_created_at=parse_datetime(value.get("fileCreatedAt")),
            local_date_time=parse_datetime(value.get("localDateTime")),
            original_file_name=value.get("originalFileName", value["id"]),
            original_mime_type=value.get("originalMimeType"),
            is_favorite=bool(value.get("isFavorite")), is_archived=bool(value.get("isArchived")),
            is_trashed=bool(value.get("isTrashed")), visibility=value.get("visibility", "timeline"),
            exif=exif, people=people, tags=tags, checksum=value.get("checksum"), thumbhash=value.get("thumbhash"),
        )

    def record(self) -> dict:
        capture = self.capture_time
        return {"id": self.id, "filename": self.original_file_name, "width": self.width,
                "height": self.height, "orientation": self.orientation, "captured": capture.isoformat() if capture else None,
                "capture_dt": capture, "exif": self.exif, "people": list(self.people), "tags": list(self.tags),
                "favorite": self.is_favorite, "rating": self.exif.get("rating"), "checksum": self.checksum}

    @classmethod
    def from_record(cls, photo):
        return cls(photo["id"], photo.get("width"), photo.get("height"),
                   parse_datetime(photo.get("captured")), parse_datetime(photo.get("captured")),
                   photo.get("filename", photo["id"]), is_favorite=photo.get("favorite"),
                   exif=photo.get("exif", {}), people=tuple(photo.get("people", ())), tags=tuple(photo.get("tags", ())), checksum=photo.get("checksum"))

    @property
    def capture_time(self) -> datetime | None:
        return self.local_date_time or self.file_created_at

    @property
    def orientation(self) -> str:
        if not self.width or not self.height:
            return "unknown"
        if self.width == self.height:
            return "square"
        return "landscape" if self.width > self.height else "portrait"

    @classmethod
    def from_cache(cls, value: dict[str, Any]) -> "Photo":
        return cls(
            id=value.get("asset_id", "unknown"), width=(value.get("dimensions") or {}).get("width"), height=(value.get("dimensions") or {}).get("height"),
            file_created_at=parse_datetime(value.get("taken_at")), local_date_time=parse_datetime(value.get("taken_at")),
            original_file_name=value.get("filename", "unknown"), exif={"city": value.get("city"), "state": value.get("state"), "country": value.get("country"), "description": value.get("description"), "rating": value.get("rating"), **(value.get("camera") or {})},
            people=tuple(value.get("people") or ()), tags=tuple(value.get("tags") or ()), is_favorite=bool(value.get("favorite")),
        )


@dataclass(slots=True, frozen=True)
class FrameConfig:
    frame_id: str
    name: str
    connection_id: str = "default"
    mode: Mode = "single"
    pair_window_days: int = 2
    slideshow_interval: int = 30
    filter: dict[str, Any] = field(default_factory=dict)
    source: Literal["all", "album", "filter", "memories", "smart"] = "all"
    album_id: str | None = None
    memory_window_days: int = 2
    fallback_to_all: bool = False
    smart_query: str | None = None
    smart_reference_asset_id: str | None = None
    order_field: Literal["fileCreatedAt", "localDateTime", "fileSizeInBytes", "rating"] = "fileCreatedAt"
    order_direction: Literal["asc", "desc"] = "desc"
    output_width: int = OUTPUT_SIZE[0]
    output_height: int = OUTPUT_SIZE[1]
    fit: Literal["cover", "contain"] = "contain"
    orientation: Literal["any", "portrait", "landscape", "square"] = "any"
    album_ids: list[str] | None = None

    screen_shape: str = "landscape"
    photo_fit: str | None = None
    time_range: str = "all_time"
    settings_version: int = 2

    def settings(self) -> dict:
        data = asdict(self)
        data["interval"] = self.slideshow_interval
        # Legacy app cover/contain preferences migrate to the common fit policy.
        data["photo_fit"] = self.photo_fit or ("show_full" if self.fit == "contain" else "crop")
        data["smart_query"] = self.smart_query or ""
        if self.album_ids is None:
            data.pop("album_ids")
        return FrameSettings.from_options(data).options()

    def __post_init__(self) -> None:
        if self.settings_version != 2:
            raise ValueError("Unsupported frame settings version")
        if self.screen_shape not in SCREEN_SIZES:
            raise ValueError("Unsupported screen_shape")
        # Explicit shapes use the common dimensions; old size arguments remain ignored.
        object.__setattr__(self, "output_width", SCREEN_SIZES[self.screen_shape][0])
        object.__setattr__(self, "output_height", SCREEN_SIZES[self.screen_shape][1])


@dataclass(slots=True, frozen=True)
class Slide:
    frame_id: str
    generation: int
    photos: tuple[Photo, ...]
    jpeg: bytes
    layout: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def primary(self) -> Photo:
        return self.photos[0]

    @property
    def secondary(self) -> Photo | None:
        return self.photos[1] if len(self.photos) > 1 else None

    def metadata(self, role: Literal["primary", "secondary"] = "primary") -> dict[str, Any]:
        photo = self.secondary if role == "secondary" else self.primary
        if photo is None:
            return {"slide_id": f"{self.frame_id}:{self.generation}", "role": role, "available": False}
        return {
            "slide_id": f"{self.frame_id}:{self.generation}", "role": role, "available": True,
            "asset_id": photo.id, "filename": photo.original_file_name,
            "taken_at": photo.capture_time.isoformat() if photo.capture_time else None,
            "orientation": photo.orientation, "favorite": photo.is_favorite,
            "rating": photo.exif.get("rating"), "city": photo.exif.get("city"),
            "state": photo.exif.get("state"), "country": photo.exif.get("country"),
            "description": photo.exif.get("description"), "people": list(photo.people), "tags": list(photo.tags),
            "camera": {k: photo.exif.get(k) for k in ("make", "model", "lensModel", "fNumber", "focalLength", "iso") if photo.exif.get(k) is not None},
            "dimensions": {"width": photo.width, "height": photo.height},
            "latitude": photo.exif.get("latitude"), "longitude": photo.exif.get("longitude"),
        }

    def state(self, role: Literal["primary", "secondary"] = "primary") -> dict[str, Any]:
        primary = self.metadata("primary")
        secondary = self.metadata("secondary")
        return {
            "slide_id": primary["slide_id"], "generation": self.generation, "layout": self.layout, "selected_role": role,
            "asset_ids": [photo.id for photo in self.photos], "primary": primary, "secondary": secondary, "selected": secondary if role == "secondary" else primary,
            "created_at": self.created_at.isoformat(),
        }
