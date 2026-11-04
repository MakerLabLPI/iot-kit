"""Settings from the environment, with the defaults of the spec."""
import os
from dataclasses import dataclass


def _float(name: str, default: float) -> float:
    v = float(os.environ.get(name, default))
    if v <= 0:
        raise ValueError(f"{name} must be > 0")
    return v


@dataclass
class Config:
    mqtt_host: str = os.environ.get("MQTT_HOST", "localhost")
    mqtt_port: int = int(os.environ.get("MQTT_PORT", "1883"))
    topic_prefix: str = os.environ.get("TOPIC_PREFIX", "bme/s04/game").strip("/")
    open_seconds: float = _float("ROUND_OPEN_SECONDS", 30)
    reveal_seconds: float = _float("ROUND_REVEAL_SECONDS", 30)
    max_missed: int = int(os.environ.get("MAX_MISSED_ROUNDS", "2"))
    web_port: int = int(os.environ.get("WEB_PORT", "8003"))
    # Admin page disabled when empty
    admin_password: str = os.environ.get("ADMIN_PASSWORD", "")
    client_id: str = os.environ.get("MQTT_CLIENT_ID", "game-master")
