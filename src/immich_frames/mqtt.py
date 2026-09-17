from __future__ import annotations

import json
from typing import Any, Callable

import paho.mqtt.client as mqtt

from .models import FrameConfig, Slide


class MqttPublisher:
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

    def publish_frame(self, frame: FrameConfig, slide: Slide) -> None:
        root = f"immich_frames/{frame.frame_id}"
        device = {"identifiers": [f"immich_frames_{frame.frame_id}"], "name": frame.name, "manufacturer": "Immich Frames", "model": "Virtual photo frame"}
        entities = [
            ("image", "image", "Frame", {"image_topic": f"{root}/image", "content_type": "image/jpeg"}),
            ("sensor", "photo_date", "Photo date", {"value_template": "{{ value_json.taken_at or 'unknown' }}", "json_attributes_topic": f"{root}/metadata"}),
            ("sensor", "photo_location", "Photo location", {"value_template": "{{ value_json.location or 'unknown' }}", "json_attributes_topic": f"{root}/metadata"}),
            ("sensor", "status", "Status", {"state_topic": f"{root}/status"}),
            ("button", "next", "Next", {"command_topic": f"{root}/command", "payload_press": "next"}),
        ]
        for component, key, name, extra in entities:
            config = {"name": name, "unique_id": f"{frame.frame_id}_{key}", "device": device, "availability_topic": f"{root}/availability", "state_topic": f"{root}/state", **extra}
            self.client.publish(f"homeassistant/{component}/{frame.frame_id}/{key}/config", json.dumps(config), retain=True)
        metadata = slide.metadata()
        metadata["location"] = ", ".join(x for x in (metadata.get("city"), metadata.get("state"), metadata.get("country")) if x)
        self.client.publish(f"{root}/image", slide.jpeg, retain=True)
        self.client.publish(f"{root}/metadata", json.dumps(metadata), retain=True)
        self.client.publish(f"{root}/status", "ready", retain=True)
        self.client.publish(f"{root}/availability", "online", retain=True)
        self.client.publish(f"{root}/state", json.dumps({"generation": slide.generation, "layout": slide.layout}), retain=True)

    def remove_frame(self, frame: FrameConfig) -> None:
        root = f"immich_frames/{frame.frame_id}"
        for component, key in (("image", "image"), ("sensor", "photo_date"), ("sensor", "photo_location"), ("sensor", "status"), ("button", "next")):
            self.client.publish(f"homeassistant/{component}/{frame.frame_id}/{key}/config", "", retain=True)
        for topic in ("image", "metadata", "status", "availability", "state"):
            self.client.publish(f"{root}/{topic}", "", retain=True)
