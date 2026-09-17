from immich_frames.models import Photo, Slide


def test_photo_parses_metadata() -> None:
    photo = Photo.from_api({"id": "a", "width": 100, "height": 200, "fileCreatedAt": "2026-09-17T12:00:00Z", "originalFileName": "a.jpg", "exifInfo": {"city": "Bath", "rating": 4}, "people": [{"name": "Alex"}], "tags": [{"name": "holiday"}]})
    assert photo.orientation == "portrait"
    assert photo.exif["city"] == "Bath"
    assert photo.people == ("Alex",)


def test_missing_secondary_is_explicit() -> None:
    photo = Photo("a", 100, 100, None, None, "a.jpg")
    slide = Slide("frame", 1, (photo,), b"jpeg", "single")
    assert slide.metadata("secondary")["available"] is False

