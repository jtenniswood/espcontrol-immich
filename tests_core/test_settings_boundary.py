"""Historical expectations are authored independently of the migration code."""

import json
from pathlib import Path

import pytest

from custom_components.immich_frames.core.settings import FrameSettings
from custom_components.immich_frames.settings import migrate_settings, native_settings
from immich_frames.compatibility import saved_frame, frame_from_body

CASES = json.loads(
    (Path(__file__).parent / "fixtures/historical-settings.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_historical_settings(case):
    saved = case["saved"]
    original = json.dumps(saved, sort_keys=True)
    if case["host"] == "native":
        migrated = migrate_settings(saved)
        assert migrate_settings(migrated, 2) == migrated
        settings = native_settings(migrated)
    else:
        migrated = saved_frame(saved)
        settings = migrated.settings()
        assert (migrated.frame_id, migrated.name) == (saved["frame_id"], saved["name"])
    assert {key: settings.options()[key] for key in case["expected"]} == case[
        "expected"
    ]
    assert json.dumps(saved, sort_keys=True) == original


@pytest.mark.parametrize(
    "values",
    [
        {"interval": 9},
        {"pair_window_days": 8},
        {"fallback_to_all": "false"},
        {"source": "album", "album_ids": []},
        {"source": "smart", "smart_query": " "},
        {"photo_fit": "invalid"},
    ],
)
def test_both_boundaries_reject_invalid_product_values(values):
    with pytest.raises(ValueError):
        native_settings(values)
    body = {"name": "Hall", **values}
    if "interval" in body:
        body["slideshow_interval"] = body.pop("interval")
    with pytest.raises(ValueError):
        frame_from_body(body)


def test_validated_settings_are_passed_through_without_retranslation():
    settings = FrameSettings(source="album", album_ids=("family",))
    assert FrameSettings.from_options(settings) is settings
