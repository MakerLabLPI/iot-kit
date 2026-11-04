#!/usr/bin/env python3
"""Heartbeat and breath: the clocks of exercise 2, running on the Pi so that
the boards keep beating when the teacher's laptop sleeps or shows something
else. The web page (../index.html) is only a view and a remote control.

Per beat / breath (what the boards follow, unchanged):
    <prefix>/heartbeat   "72"   one message per beat, payload the tempo in BPM
    <prefix>/breath      "12"   one message per breath, payload the rate per minute
Retained state (what any page shows when it opens):
    <prefix>/heartbeat/rate     "72"      <prefix>/heartbeat/running  "1" or "0"
    <prefix>/breath/rate        "12"      <prefix>/breath/running     "1" or "0"
Control (what the page's sliders and buttons send):
    <prefix>/heartbeat/set      "80" (a rate), "pause" or "start"
    <prefix>/breath/set         idem

The page itself is served on WEB_PORT (default 8002), from the index.html
next to this file in the container, or opened as a local file.
"""
import asyncio
import logging
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
PREFIX = os.environ.get("TOPIC_PREFIX", "bme/s04").strip("/")
WEB_PORT = int(os.environ.get("WEB_PORT", "8002"))
PAGE = Path(__file__).with_name("index.html")

log = logging.getLogger("rhythms")


class PageHandler(BaseHTTPRequestHandler):
    """Serves the one page; the page talks to the broker directly."""

    def do_GET(self):
        if self.path.split("?")[0] not in ("/", "/index.html"):
            self.send_error(404)
            return
        body = PAGE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.info("page: %s %s", self.address_string(), fmt % args)


def serve_page() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", WEB_PORT), PageHandler)
    threading.Thread(target=server.serve_forever, daemon=True, name="web").start()
    log.info("page on http://0.0.0.0:%d/", WEB_PORT)


class Rhythm:
    """Something that happens `rate` times per minute, at fixed times: a late
    wake-up delays one tick without shifting the following ones."""

    def __init__(self, name: str, rate: int, lo: int, hi: int, client: mqtt.Client):
        self.name, self.lo, self.hi = name, lo, hi
        self.rate = rate
        self.running = True
        self.client = client
        self.topic = f"{PREFIX}/{name}"
        self.sent = 0
        self.changed = asyncio.Event()   # a control message arrived

    @property
    def period(self) -> float:
        return 60.0 / self.rate

    def publish_state(self) -> None:
        self.client.publish(f"{self.topic}/rate", str(self.rate), qos=1, retain=True)
        self.client.publish(f"{self.topic}/running", "1" if self.running else "0", qos=1, retain=True)

    def control(self, payload: str) -> None:
        """A message on <topic>/set, from the page (any thread: only sets
        fields and pokes the loop)."""
        p = payload.strip().lower()
        if p in ("pause", "stop", "0"):
            self.running = False
        elif p in ("start", "resume", "run"):
            self.running = True
        else:
            try:
                self.rate = max(self.lo, min(self.hi, round(float(p))))
            except ValueError:
                log.warning("%s: ignored control %r", self.name, payload)
                return
        log.info("%s: %s -> %d/min, %s", self.name, p, self.rate, "running" if self.running else "paused")
        self.changed.set()

    def tick(self) -> None:
        self.client.publish(self.topic, str(self.rate), qos=0)
        self.sent += 1

    async def run(self) -> None:
        self.publish_state()
        last = None                      # when the last tick was due
        while True:
            if not self.running:
                self.changed.clear()
                await self.changed.wait()
                self.publish_state()
                last = None
                continue
            if last is None:             # (re)start: tick at once
                self.tick()
                last = time.monotonic()
            due = last + self.period
            try:
                await asyncio.wait_for(self.changed.wait(), max(0.0, due - time.monotonic()))
                # A control message: the next tick is one (new) period after
                # the last one, so dragging the slider does not spam beats
                self.changed.clear()
                self.publish_state()
                continue
            except asyncio.TimeoutError:
                pass
            self.tick()
            # Far too late (broker gone, machine suspended): start over
            last = due if time.monotonic() - due < self.period else time.monotonic()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    loop = asyncio.get_running_loop()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="rhythms", clean_session=True)
    heart = Rhythm("heartbeat", int(os.environ.get("HEART_BPM", "60")), 30, 180, client)
    breath = Rhythm("breath", int(os.environ.get("BREATH_RATE", "12")), 4, 30, client)
    rhythms = {r.topic: r for r in (heart, breath)}

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code != 0:
            log.warning("connect refused: %s", reason_code)
            return
        c.subscribe([(f"{r.topic}/set", 0) for r in rhythms.values()])
        log.info("connected to %s:%d, publishing under %s/", HOST, PORT, PREFIX)
        loop.call_soon_threadsafe(lambda: [r.publish_state() for r in rhythms.values()])

    def on_message(c, userdata, msg):
        r = rhythms.get(msg.topic[: -len("/set")])
        if r is not None:
            loop.call_soon_threadsafe(r.control, msg.payload.decode("utf-8", "replace"))

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = lambda *a: log.warning("disconnected from the broker, reconnecting")
    client.reconnect_delay_set(1, 10)
    client.connect_async(HOST, PORT, keepalive=30)
    client.loop_start()
    if PAGE.exists():
        serve_page()

    tasks = [asyncio.create_task(r.run()) for r in rhythms.values()]
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    for t in tasks:
        t.cancel()
    client.disconnect()
    client.loop_stop()


if __name__ == "__main__":
    asyncio.run(main())
