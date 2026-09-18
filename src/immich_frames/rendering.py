from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps

from .models import OUTPUT_SIZE, Photo, Slide


def _fit(image: Image.Image, size: tuple[int, int], mode: str) -> Image.Image:
    if mode == "contain":
        return ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    return ImageOps.fit(image, size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def render_slide(frame_id: str, generation: int, photos: tuple[Photo, ...], payloads: tuple[bytes, ...], width: int, height: int, fit: str = "cover") -> Slide:
    # Keep accepting legacy size arguments, but always render the device frame.
    width, height = OUTPUT_SIZE
    canvas = Image.new("RGB", (width, height), "black")
    if len(photos) == 2:
        divider = width // 2
        tiles = ((0, divider), (divider + 1, width - divider - 1))
        for (left, tile_width), raw in zip(tiles, payloads):
            with Image.open(BytesIO(raw)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                canvas.paste(_fit(image, (tile_width, height), "cover"), (left, 0))
        layout = "side_by_side"
    else:
        with Image.open(BytesIO(payloads[0])) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            canvas.paste(_fit(image, (width, height), fit), (0, 0))
        layout = "single"
    output = BytesIO()
    canvas.save(output, format="JPEG", quality=95, subsampling=0, optimize=True)
    return Slide(frame_id, generation, photos, output.getvalue(), layout)
