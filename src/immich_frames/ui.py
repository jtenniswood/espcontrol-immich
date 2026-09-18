"""Small handwritten app page with controls from the shared product contract."""
from html import escape
from importlib.resources import files

from custom_components.immich_frames.core.settings import SETTINGS


def home_page() -> str:
    controls = []
    for spec in SETTINGS:
        key = "slideshow_interval" if spec.key == "interval" else spec.key
        if spec.choices:
            options = "".join(f'<option value="{escape(value)}"{" selected" if value == spec.default else ""}>{escape(label)}</option>' for value, label in spec.choices)
            control = f'<select name="{key}">{options}</select>'
        else:
            control = f'<input name="{key}" type="number" min="{spec.minimum}" max="{spec.maximum}" value="{spec.default}">'
        controls.append(f"<label>{escape(spec.label)} {control}</label>")
    template = files("immich_frames").joinpath("web/index.html").read_text()
    return template.replace("{{display_controls}}", "".join(controls))
