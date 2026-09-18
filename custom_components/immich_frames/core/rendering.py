"""Image inspection and photo-derived colours for the native frame renderer."""
from io import BytesIO

from PIL import Image, ImageOps


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

from .settings import DEFAULT_SCREEN_SHAPE, SCREEN_SIZES, PHOTO_FIT_FULL, PHOTO_FIT_CROP

def render(photos: list[dict], payloads: list[bytes], screen_shape: str = DEFAULT_SCREEN_SHAPE, fit: str | None = None) -> tuple[bytes, str]:
    canvas_size = SCREEN_SIZES.get(screen_shape, SCREEN_SIZES[DEFAULT_SCREEN_SHAPE])
    images: list[Image.Image] = []
    for payload in payloads:
        image = ImageOps.exif_transpose(Image.open(BytesIO(payload))).convert("RGB")
        images.append(image)
    fit = fit or (PHOTO_FIT_FULL if len(images) == 1 else PHOTO_FIT_CROP)

    def tile(image: Image.Image, size: tuple[int, int]) -> Image.Image:
        if fit == PHOTO_FIT_CROP:
            return ImageOps.fit(image, size, Image.Resampling.LANCZOS)
        contained = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
        result = Image.new("RGB", size, background_colour(image))
        result.paste(contained, ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2))
        return result

    if len(images) == 1:
        canvas = tile(images[0], canvas_size)
        layout = "single"
    else:
        # Keep one black pixel between the two independently fitted photos.
        canvas = Image.new("RGB", canvas_size, "black")
        divider = canvas.width // 2
        tiles = ((0, divider), (divider + 1, canvas.width - divider - 1))
        for image, (left, width) in zip(images[:2], tiles):
            canvas.paste(tile(image, (width, canvas.height)), (left, 0))
        layout = "side_by_side"
    output = BytesIO()
    # Preserve fine colour detail as well as the narrow divider in pairs.
    canvas.save(output, "JPEG", quality=95, subsampling=0, optimize=True)
    return output.getvalue(), layout
