"""paho-mqtt 2.x adapter. paho runs its own network thread (loop_start);
every message is handed to the asyncio loop with call_soon_threadsafe so
the Game never sees two threads. Reconnects and resubscribes by itself."""
from __future__ import annotations

import asyncio
import logging

import paho.mqtt.client as mqtt

from .config import Config
from .game import Game

log = logging.getLogger("mqtt")


class MqttAdapter:
    def __init__(self, cfg: Config, game: Game, loop: asyncio.AbstractEventLoop):
        self.cfg = cfg
        self.game = game
        self.loop = loop
        self.prefix = cfg.topic_prefix
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=cfg.client_id, clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        game.publisher = self

    def start(self) -> None:
        # connect_async + loop_start: keeps retrying if the broker is not up yet
        self.client.connect_async(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()

    def publish(self, topic: str, payload: str, qos: int = 1) -> None:
        self.client.publish(topic, payload, qos=qos, retain=False)

    # -- paho callbacks, on paho's thread --------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            log.warning("connect refused: %s", reason_code)
            return
        client.subscribe([(f"{self.prefix}/+/join", 0), (f"{self.prefix}/+/move", 0),
                          (f"{self.prefix}/join", 0)])
        log.info("connected to %s:%s, subscribed to %s/+/{join,move}",
                 self.cfg.mqtt_host, self.cfg.mqtt_port, self.prefix)
        self.loop.call_soon_threadsafe(self._connected, True)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        log.warning("disconnected from the broker (%s), reconnecting", reason_code)
        self.loop.call_soon_threadsafe(self._connected, False)

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace")
        self.loop.call_soon_threadsafe(self._dispatch, msg.topic, payload)

    # -- on the asyncio loop ----------------------------------------------------

    def _connected(self, up: bool) -> None:
        self.game.mqtt_connected = up
        self.game.say("system", "broker connected" if up else "broker connection lost")
        self.game.changed()

    def _dispatch(self, topic: str, payload: str) -> None:
        rest = topic[len(self.prefix) + 1:] if topic.startswith(self.prefix + "/") else None
        parts = rest.split("/") if rest else []
        if parts == ["join"]:
            self.game.on_bare_join(payload)
        elif len(parts) == 2 and parts[1] == "join":
            self.game.on_join(parts[0])
        elif len(parts) == 2 and parts[1] == "move":
            self.game.on_move(parts[0], payload)
        else:
            self.game.on_other(topic, payload)
