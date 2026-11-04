"""Glue between the engine, the clock, the broker and the page: the round
scheduler, the live log feed and the state snapshot the page renders.
Runs entirely on the asyncio loop; the MQTT thread hands messages over
with call_soon_threadsafe (see mqtt.py)."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import time
from collections import deque
from typing import Callable, Protocol

from .config import Config
from .engine import IDLE, OPEN, REVEAL, Engine

log = logging.getLogger("game")

LOG_LINES = 200


class Publisher(Protocol):
    def publish(self, topic: str, payload: str, qos: int = 0) -> None: ...


class Game:
    def __init__(self, cfg: Config, publisher: Publisher | None = None):
        self.cfg = cfg
        self.engine = Engine(max_missed=cfg.max_missed)
        self.publisher = publisher
        self.open_seconds = cfg.open_seconds
        self.reveal_seconds = cfg.reveal_seconds
        self.paused = False
        self.pause_pending = False
        self.phase_started = 0.0
        self.phase_ends = 0.0
        self.feed: deque[dict] = deque(maxlen=LOG_LINES)
        self.subscribers: set[asyncio.Queue] = set()
        self.wake = asyncio.Event()      # poke the scheduler out of idle/pause
        self.mqtt_connected = False
        self._task: asyncio.Task | None = None

    # -- log feed ------------------------------------------------------------

    def say(self, kind: str, text: str) -> None:
        """One line of the terminal feed. kind: join, move, result, ignored,
        rejected, round, system."""
        entry = {"ts": time.time(), "kind": kind, "text": text}
        self.feed.append(entry)
        log.info("%-8s %s", kind, text)

    # -- state for the page ---------------------------------------------------

    def snapshot(self) -> dict:
        s = self.engine.snapshot()
        s.update({
            "now": time.time(),
            "phase_started": self.phase_started,
            "phase_ends": self.phase_ends,
            "open_seconds": self.open_seconds,
            "reveal_seconds": self.reveal_seconds,
            "paused": self.paused,
            "pause_pending": self.pause_pending,
            "mqtt_connected": self.mqtt_connected,
            "topic_prefix": self.cfg.topic_prefix,
            "feed": list(self.feed),
        })
        return s

    def changed(self) -> None:
        """Push a fresh snapshot to every SSE client. Slow clients get the
        latest snapshot only: the queue holds one item."""
        snap = self.snapshot()
        for q in list(self.subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(snap)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        q.put_nowait(self.snapshot())
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    # -- incoming MQTT ----------------------------------------------------------

    def on_join(self, pid: str) -> None:
        r = self.engine.join(pid)
        if r.status == "bad_id":
            self.say("rejected", f"{pid} → join: invalid name ({r.detail})")
            self.changed()
            return
        if r.status == "rejoined":
            self.say("join", f"{pid} → join: back in the pool")
        else:
            self.say("join", f"{pid} → join")
        self.wake.set()
        self.changed()

    def on_bare_join(self, payload: str) -> None:
        self.say("rejected", f"join on {self.cfg.topic_prefix}/join ({payload!r}): "
                             f"who are you? publish on {self.cfg.topic_prefix}/<name>/join")
        self.changed()

    def on_move(self, pid: str, payload: str) -> None:
        """The move itself is never shown while the round is open: the log
        is on the wall and the opponent would just read it."""
        r = self.engine.move(pid, payload)
        shown = payload.strip()[:16] or "∅"
        match r.status:
            case "accepted":
                self.say("move", f"{pid} → move: locked in")
            case "ignored_closed":
                self.say("ignored", f"{pid} → move (ignored — round closed)")
            case "ignored_not_paired":
                self.say("ignored", f"{pid} → move (ignored — not paired this round)")
            case "ignored_duplicate":
                self.say("ignored", f"{pid} → move (ignored — already moved)")
            case "not_joined":
                self.say("rejected", f"{pid} → move: {shown} (rejected — never joined)")
            case "bad_payload":
                self.say("rejected", f"{pid} → move: {shown!r} (rejected — send C or B)")
            case "bad_id":
                self.say("rejected", f"{pid} → move: {shown} (rejected — invalid name)")
        self.changed()

    def on_other(self, topic: str, payload: str) -> None:
        self.say("rejected", f"{topic} ← {payload.strip()[:32]!r} (unknown topic)")
        self.changed()

    # -- outgoing MQTT ----------------------------------------------------------

    def _publish(self, topic: str, payload: str, qos: int = 1) -> None:
        if self.publisher is not None:
            self.publisher.publish(topic, payload, qos)

    # -- the round loop -----------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self.run(), name="scheduler")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def _set_phase_clock(self, seconds: float) -> None:
        self.phase_started = time.time()
        self.phase_ends = self.phase_started + seconds

    async def run(self) -> None:
        eng = self.engine
        while True:
            if self.pause_pending:
                self.paused, self.pause_pending = True, False
                self.say("system", "paused")
                self.changed()
            while self.paused:
                self.wake.clear()
                await self.wake.wait()

            rnd = eng.open_round()
            if rnd is None:
                if self.phase_ends:
                    self.say("system", "waiting for players (need 2)")
                self.phase_started = self.phase_ends = 0.0
                self.changed()
                # Idle until a join arrives or an admin acts, then give the
                # other boards a moment: joins often come in a burst
                self.wake.clear()
                await self.wake.wait()
                await asyncio.sleep(2)
                continue

            pairs = ", ".join(f"{m.a} vs {m.b}" for m in rnd.matches)
            bench = f" — {rnd.sit_out} sits out" if rnd.sit_out else ""
            self.say("round", f"round {rnd.number} open: {pairs}{bench}")
            self._set_phase_clock(self.open_seconds)
            self.changed()
            await asyncio.sleep(self.open_seconds)

            results = eng.close_round()
            for pid, points in results:
                self._publish(f"{self.cfg.topic_prefix}/{pid}/result", str(points))
                m = rnd.match_of(pid)
                dice = " (random)" if pid in m.random else ""
                self.say("result", f"{pid} ← result: {points}  [{m.moves[pid]}{dice} vs "
                                   f"{m.moves[m.opponent(pid)]}]")
            for m in rnd.matches:
                for pid in (m.a, m.b):
                    p = eng.players[pid]
                    if p.state == "dropped" and pid in m.random and p.misses >= eng.max_missed:
                        self.say("system", f"{pid} dropped after {p.misses} missed rounds "
                                           f"(join again to come back)")
            self._publish(f"{self.cfg.topic_prefix}/log", json.dumps(eng.round_summary()))
            self._set_phase_clock(self.reveal_seconds)
            self.changed()
            await asyncio.sleep(self.reveal_seconds)
            eng.end_reveal()

    # -- admin actions ------------------------------------------------------------

    def set_paused(self, paused: bool) -> None:
        if paused:
            if not self.paused:
                self.pause_pending = True
        else:
            self.paused = self.pause_pending = False
            self.say("system", "resumed")
            self.wake.set()
        self.changed()

    def set_durations(self, open_s: float | None, reveal_s: float | None) -> None:
        if open_s is not None and open_s > 0:
            self.open_seconds = open_s
        if reveal_s is not None and reveal_s > 0:
            self.reveal_seconds = reveal_s
        self.say("system", f"durations: open {self.open_seconds:g} s, reveal {self.reveal_seconds:g} s")
        self.changed()

    def kick(self, pid: str) -> bool:
        ok = self.engine.kick(pid)
        if ok:
            self.say("system", f"{pid} kicked by the teacher")
            self.changed()
        return ok

    def reinstate(self, pid: str) -> bool:
        ok = self.engine.reinstate(pid)
        if ok:
            self.say("system", f"{pid} reinstated by the teacher")
            self.wake.set()
            self.changed()
        return ok

    async def reset_scores(self) -> None:
        """Restart the round loop from round 1 with everyone still in."""
        await self.stop()
        self.engine.reset_scores()
        self.phase_started = self.phase_ends = 0.0
        self.feed.clear()
        self.say("system", "scores reset — the real game starts now")
        self.start()
        self.changed()

    def rows_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["round", "player", "opponent", "move", "random", "points"])
        for r in self.engine.rows:
            w.writerow([r.round, r.player, r.opponent, r.move, int(r.random), r.points])
        return buf.getvalue()
