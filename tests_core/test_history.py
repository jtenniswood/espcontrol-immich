from types import SimpleNamespace

from custom_components.immich_frames.core.history import SlideHistory


def test_history_is_bounded_and_previous_removes_current_slide():
    history = SlideHistory()
    for index in range(25):
        history.append(SimpleNamespace(photos=({"id": str(index)},)))
    assert len(history) == 20
    assert history[0].photos[0]["id"] == "5"
    assert history.recent_ids == {str(i) for i in range(15, 25)}
    assert history.previous().photos[0]["id"] == "23"
    assert history.previous().photos[0]["id"] == "22"
    assert "24" not in history.recent_ids
