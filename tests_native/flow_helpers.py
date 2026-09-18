"""Complete the visible settings steps through Home Assistant's flow manager."""


async def finish_settings(manager, result):
    for step in ("display", "photos", "pairing"):
        if result.get("step_id") == step:
            assert not result.get("errors")
            result = await manager.async_configure(result["flow_id"], {})
    assert result["type"] in ("create_entry", "abort")
    return result
