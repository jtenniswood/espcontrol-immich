"""Legacy render entry point backed by the shared renderer."""
from custom_components.immich_frames.core.rendering import render
from custom_components.immich_frames.core.settings import SCREEN_SIZES
from .models import Slide


def render_slide(frame_id, generation, photos, payloads, width, height, fit="cover"):
    shape = next((key for key, size in SCREEN_SIZES.items() if size == (width, height)), "landscape")
    jpeg, layout = render([p.record() for p in photos], list(payloads[:len(photos)]), shape,
                          "show_full" if fit == "contain" else "crop")
    return Slide(frame_id, generation, photos, jpeg, layout)
