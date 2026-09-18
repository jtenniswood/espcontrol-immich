"""Image inspection and photo-derived colours for the native frame renderer."""
from io import BytesIO

from PIL import Image


def image_size(payload: bytes) -> tuple[int, int]:
    """Validate decoding and report displayed dimensions after EXIF rotation."""
    with Image.open(BytesIO(payload)) as image:
        image.load()
        width, height = image.size
        if image.getexif().get(274) in (5, 6, 7, 8):
            return height, width
        return width, height


def background_colour(image: Image.Image) -> tuple[int, int, int]:
    """Sample RGB photo content using ESPFrame's former accent-fill method.

    Reference: jtenniswood/espframe at 47ae12c, espframe_helpers.h,
    fill_accent_color. Keep its grid, saturation weighting and half brightness;
    RGB565 conversion and black-pixel border detection are device-specific and
    unnecessary here because the renderer owns the padding canvas.
    """
    step_x = max(1, image.width // 20)
    step_y = max(1, image.height // 20)
    red = green = blue = total_weight = 0
    for y in range(step_y // 2, image.height, step_y):
        for x in range(step_x // 2, image.width, step_x):
            r, g, b = image.getpixel((x, y))
            saturation = max(r, g, b) - min(r, g, b)
            weight = saturation * saturation + 1
            red += r * weight
            green += g * weight
            blue += b * weight
            total_weight += weight
    return (
        red // total_weight // 2,
        green // total_weight // 2,
        blue // total_weight // 2,
    )
