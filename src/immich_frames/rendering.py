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
        if width >= height:
            tile_size = (width // 2, height)
            positions = ((0, 0), (width // 2, 0))
        else:
            tile_size = (width, height // 2)
            positions = ((0, 0), (0, height // 2))
        for position, raw in zip(positions, payloads):
            with Image.open(BytesIO(raw)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                canvas.paste(_fit(image, tile_size, fit), position)
        layout = "side_by_side" if width >= height else "stacked"
    else:
        with Image.open(BytesIO(payloads[0])) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            canvas.paste(_fit(image, (width, height), fit), (0, 0))
        layout = "single"
    output = BytesIO()
    canvas.save(output, format="JPEG", quality=85, optimize=True)
    return Slide(frame_id, generation, photos, output.getvalue(), layout)

