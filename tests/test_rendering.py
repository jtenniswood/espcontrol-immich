from io import BytesIO

from PIL import Image

from immich_frames.models import Photo
from immich_frames.rendering import render_slide


def jpeg(width: int, height: int, colour: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), colour).save(output, "JPEG")
    return output.getvalue()


def test_pair_render_has_requested_dimensions() -> None:
    photos = (Photo("a", 500, 700, None, None, "a.jpg"), Photo("b", 500, 700, None, None, "b.jpg"))
    slide = render_slide("frame", 1, photos, (jpeg(500, 700, "red"), jpeg(500, 700, "blue")), 1200, 800)
    with Image.open(BytesIO(slide.jpeg)) as image:
        assert image.size == (1200, 800)
    assert slide.layout == "side_by_side"

