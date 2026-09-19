from types import SimpleNamespace

from custom_components.immich_frames.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_redact_credentials_and_omit_image_bytes() -> None:
    entry = SimpleNamespace(
        data={"url": "http://immich.test", "api_key": "secret"},
        runtime_data=SimpleNamespace(
            data=SimpleNamespace(
                connected=True,
                using_cache=False,
                status="ok",
                generation=3,
                matching_assets=12,
                layout="single",
                image=b"private image bytes",
            )
        ),
    )

    diagnostics = await async_get_config_entry_diagnostics(None, entry)

    assert diagnostics["entry"]["api_key"] == "**REDACTED**"
    assert diagnostics["runtime"] == {
        "connected": True,
        "using_cache": False,
        "status": "ok",
        "generation": 3,
        "matching_assets": 12,
        "layout": "single",
    }
    assert "image" not in str(diagnostics)
