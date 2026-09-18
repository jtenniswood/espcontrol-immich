#!/usr/bin/env python3
"""Render a repeatable visual acceptance sheet using synthetic source images."""
import argparse
from io import BytesIO
from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from custom_components.immich_frames.core.rendering import render


def source(colour):
    image = Image.new("RGB", (400, 700), colour)
    draw = ImageDraw.Draw(image)
    draw.rectangle((5, 5, 394, 694), outline="white", width=12)
    draw.ellipse((60, 180, 340, 460), fill="white")
    draw.rectangle((190, 40, 210, 660), fill="black")
    raw = BytesIO()
    image.save(raw, "JPEG", quality=95)
    return raw.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sheet = Image.new("RGB", (960, 1040), "#252525")
    draw = ImageDraw.Draw(sheet)
    row = 0
    for fit in ("show_full", "crop"):
        for paired in (False, True):
            for column, shape in enumerate(("landscape", "portrait", "square")):
                payloads = [source("#2178b6")]
                if paired:
                    payloads.append(source("#b64c21"))
                output, _ = render([], payloads, shape, fit)
                image = Image.open(BytesIO(output))
                image.thumbnail((300, 225))
                x, y = column * 320, row * 260
                draw.text((x + 10, y + 8), f"{shape} / {fit} / {'pair' if paired else 'single'}", fill="white")
                sheet.paste(image, (x + (320-image.width)//2, y + 28))
            row += 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
