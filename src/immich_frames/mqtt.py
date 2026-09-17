from __future__ import annotations

import json
from typing import Any, Callable

import paho.mqtt.client as mqtt

from .models import FrameConfig, Slide


class MqttPublisher:
    """Home Assistant MQTT discovery and state adapter for virtual frames."""

    def __init__(self, host: str, port: int, username: str | None = None, password: str | None = None) -> None:
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="immich-frames")
        self.command_handler: Callable[[str, str], None] | None = None
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        if username:
            self.client.username_pw_set(username, password)
        self.client.connect(host, port, keepalive=60)
        self.client.loop_start()

    def _on_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, _reason_code: Any, _properties: Any = None) -> None:
        client.subscribe("immich_frames/+/command")

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        if self.command_handler:
            parts = message.topic.split("/")
            if len(parts) == 3:
                self.command_handler(parts[1], message.payload.decode("utf-8", "replace"))

    def set_command_handler(self, handler: Callable[[str, str], None]) -> None:
        self.command_handler = handler

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    @staticmethod
    def _device(frame: FrameConfig) -> dict[str, Any]:
        return {"identifiers": [f"immich_frames_{frame.frame_id}"], "name": frame.name, "manufacturer": "Immich Frames", "model": "Virtual photo frame", "sw_version": "0.1.0"}

    def _discovery(self, frame: FrameConfig) -> None:
        root = f"immich_frames/{frame.frame_id}"
        device = self._device(frame)
        availability = {"availability_topic": f"{root}/availability", "payload_available": "online", "payload_not_available": "offline"}
        metadata = {"json_attributes_topic": f"{root}/metadata", "state_topic": f"{root}/metadata"}
        entities: list[tuple[str, str, str, dict[str, Any]]] = [
            ("image", "image", "Frame", {"image_topic": f"{root}/image", "content_type": "image/jpeg"}),
            ("sensor", "photo_date", "Photo date", {"value_template": "{{ value_json.primary.taken_at or 'unknown' }}", **metadata}),
            ("sensor", "photo_location", "Photo location", {"value_template": "{{ value_json.primary.location or 'unknown' }}", **metadata}),
            ("sensor", "photo_filename", "Photo filename", {"value_template": "{{ value_json.primary.filename or 'unknown' }}", **metadata}),
            ("sensor", "photo_people", "Photo people", {"value_template": "{{ (value_json.primary.people or []) | join(', ') }}", **metadata}),
            ("sensor", "photo_tags", "Photo tags", {"value_template": "{{ (value_json.primary.tags or []) | join(', ') }}", **metadata}),
            ("sensor", "photo_rating", "Photo rating", {"value_template": "{{ value_json.primary.rating if value_json.primary.rating is not none else 'unknown' }}", **metadata}),
            ("sensor", "photo_camera", "Photo camera", {"value_template": "{{ value_json.primary.camera.model or 'unknown' }}", **metadata}),
            ("sensor", "status", "Status", {"state_topic": f"{root}/status"}),
            ("sensor", "slide", "Slide", {"value_template": "{{ value_json.generation }}", "state_topic": f"{root}/state"}),
            ("sensor", "matching_assets", "Matching assets", {"state_topic": f"{root}/matching_assets", "unit_of_measurement": "assets"}),
            ("binary_sensor", "immich_connected", "Immich connected", {"state_topic": f"{root}/immich_connected", "payload_on": "on", "payload_off": "off", "device_class": "connectivity"}),
            ("binary_sensor", "using_cache", "Using cached image", {"state_topic": f"{root}/using_cache", "payload_on": "on", "payload_off": "off"}),
            ("switch", "slideshow", "Slideshow", {"command_topic": f"{root}/command", "state_topic": f"{root}/slideshow", "payload_on": "on", "payload_off": "off", "payload_turn_on": "resume", "payload_turn_off": "pause"}),
            ("select", "metadata_role", "Metadata photo", {"command_topic": f"{root}/command", "state_topic": f"{root}/metadata_role", "options": ["primary", "secondary"]}),
            ("number", "interval", "Slide interval", {"command_topic": f"{root}/command", "state_topic": f"{root}/interval", "command_template": "interval:{{ value }}", "min": 10, "max": 86400, "step": 1, "unit_of_measurement": "s"}),
            ("button", "next", "Next", {"command_topic": f"{root}/command", "payload_press": "next"}),
            ("button", "previous", "Previous", {"command_topic": f"{root}/command", "payload_press": "previous"}),
            ("button", "refresh", "Refresh", {"command_topic": f"{root}/command", "payload_press": "refresh"}),
            ("button", "clear_cache", "Clear cache", {"command_topic": f"{root}/command", "payload_press": "clear_cache"}),
        ]
        for component, key, name, extra in entities:
            config = {"name": name, "unique_id": f"{frame.frame_id}_{key}", "device": device, **availability, **extra}
            self.client.publish(f"homeassistant/{component}/{frame.frame_id}/{key}/config", json.dumps(config), retain=True)

    def publish_frame(self, frame: FrameConfig, slide: Slide, paused: bool = False, using_cache: bool = False, status: str = "ready", matching_assets: int | None = None) -> None:
        root = f"immich_frames/{frame.frame_id}"
        self._discovery(frame)
        state = slide.state()
        for item in (state["primary"], state["secondary"]):
            if item.get("available"):
                item["location"] = ", ".join(x for x in (item.get("city"), item.get("state"), item.get("country")) if x)
        self.client.publish(f"{root}/image", slide.jpeg, retain=True)
        self.client.publish(f"{root}/metadata", json.dumps(state), retain=True)
        self.client.publish(f"{root}/state", json.dumps({"generation": slide.generation, "layout": slide.layout}), retain=True)
        self.client.publish(f"{root}/status", status, retain=True)
        self.client.publish(f"{root}/availability", "online", retain=True)
        self.client.publish(f"{root}/immich_connected", "on", retain=True)
        self.client.publish(f"{root}/using_cache", "on" if using_cache else "off", retain=True)
        self.client.publish(f"{root}/slideshow", "off" if paused else "on", retain=True)
        self.client.publish(f"{root}/metadata_role", "primary", retain=True)
        self.client.publish(f"{root}/interval", str(frame.slideshow_interval), retain=True)
        if matching_assets is not None:
            self.client.publish(f"{root}/matching_assets", str(matching_assets), retain=True)

    def publish_error(self, frame: FrameConfig, status: str) -> None:
        root = f"immich_frames/{frame.frame_id}"
        self._discovery(frame)
        self.client.publish(f"{root}/availability", "online", retain=True)
        self.client.publish(f"{root}/immich_connected", "off", retain=True)
        self.client.publish(f"{root}/status", status, retain=True)

    def publish_controls(self, frame: FrameConfig, paused: bool, role: str = "primary") -> None:
        root = f"immich_frames/{frame.frame_id}"
        self.client.publish(f"{root}/slideshow", "off" if paused else "on", retain=True)
        self.client.publish(f"{root}/metadata_role", role, retain=True)
        self.client.publish(f"{root}/interval", str(frame.slideshow_interval), retain=True)

    def remove_frame(self, frame: FrameConfig) -> None:
        root = f"immich_frames/{frame.frame_id}"
        entities = [("image", "image"), ("sensor", "photo_date"), ("sensor", "photo_location"), ("sensor", "photo_filename"), ("sensor", "photo_people"), ("sensor", "photo_tags"), ("sensor", "photo_rating"), ("sensor", "photo_camera"), ("sensor", "status"), ("sensor", "slide"), ("sensor", "matching_assets"), ("binary_sensor", "immich_connected"), ("binary_sensor", "using_cache"), ("switch", "slideshow"), ("select", "metadata_role"), ("number", "interval"), ("button", "next"), ("button", "previous"), ("button", "refresh"), ("button", "clear_cache")]
        for component, key in entities:
            self.client.publish(f"homeassistant/{component}/{frame.frame_id}/{key}/config", "", retain=True)
        for topic in ("image", "metadata", "status", "availability", "state", "immich_connected", "using_cache", "slideshow", "metadata_role", "interval", "matching_assets"):
            self.client.publish(f"{root}/{topic}", "", retain=True)
