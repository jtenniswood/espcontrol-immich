from io import BytesIO

from PIL import Image
import pytest

from immich_frames.models import Photo
from immich_frames.rendering import render_slide


def jpeg(width: int, height: int, colour: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), colour).save(output, "JPEG")
    return output.getvalue()


@pytest.mark.parametrize("requested", [(1200, 800), (1920, 1080), (800, 1280), (4096, 4096)])
@pytest.mark.parametrize("paired", [False, True])
def test_render_enforces_fixed_frame(requested, paired) -> None:
    photos = (Photo("a", 500, 700, None, None, "a.jpg"), Photo("b", 500, 700, None, None, "b.jpg"))
    if not paired:
        photos = photos[:1]
    slide = render_slide("frame", 1, photos, (jpeg(500, 700, "red"), jpeg(500, 700, "blue")), *requested)
    with Image.open(BytesIO(slide.jpeg)) as image:
        assert image.size == (1280, 800)
    assert slide.layout == ("side_by_side" if paired else "single")

