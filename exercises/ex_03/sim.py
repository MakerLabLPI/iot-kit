#!/usr/bin/env python3
"""Fake ESP32s for testing the game master without boards.

  python sim.py --players 7 --strategy mixed
  python sim.py --players 3 --strategy tit-for-tat --join-staggered 30
  python sim.py --host 192.168.50.1 --players 2

Each player joins, subscribes to its result topic and plays according to
its strategy. They only see their own result (points), like a real board,
so tit-for-tat infers the opponent's move from the points it got.
Needs paho-mqtt: pip install paho-mqtt"""
import argparse
import random
import signal
import sys
import threading
import time

import paho.mqtt.client as mqtt

STRATEGIES = ["always-c", "always-b", "tit-for-tat", "random", "slow", "absent"]
NAMES = ["Ada", "Linus", "Grace", "Alan", "Margaret", "Dennis", "Barbara", "Ken",
         "Radia", "Tim", "Hedy", "Claude", "Frances", "Edsger", "Joan", "Niklaus"]


class Player(threading.Thread):
    def __init__(self, idx, strategy, args):
        super().__init__(daemon=True, name=f"p{idx}")
        # The nickname is the id
        self.pid = NAMES[idx % len(NAMES)] + (str(idx // len(NAMES) + 1) if idx >= len(NAMES) else "")
        self.strategy = strategy
        self.prefix = args.prefix
        self.args = args
        self.last_points = None
        self.last_move = None
        self.stop = threading.Event()
        self.got_result = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.pid)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def log(self, msg):
        print(f"{time.strftime('%H:%M:%S')} {self.pid:<12} {self.strategy:<12} {msg}", flush=True)

    def on_connect(self, client, userdata, flags, rc, props):
        client.subscribe(f"{self.prefix}/{self.pid}/result")
        client.publish(f"{self.prefix}/{self.pid}/join", "hi")
        self.log("joined")

    def on_message(self, client, userdata, msg):
        pts = msg.payload.decode().strip()
        self.last_points = int(pts) if pts.isdigit() else None
        led = "GOOD" if (self.last_points or 0) >= 3 else "bad"
        self.log(f"result {pts} -> LED {led}")
        self.got_result.set()

    def next_move(self):
        s = self.strategy
        if s == "always-c":
            return "C"
        if s == "always-b":
            return "B"
        if s == "random":
            return random.choice("CB")
        if s == "tit-for-tat":
            # 3 or 0 points: the opponent cooperated; 5 or 1: they betrayed
            if self.last_points is None:
                return "C"
            return "C" if self.last_points in (3, 0) else "B"
        return random.choice("CB")  # slow

    def run(self):
        self.client.connect(self.args.host, self.args.port, keepalive=30)
        self.client.loop_start()
        a = self.args
        # A real board does not know the round clock either. The sim presses
        # a few seconds after each result (that is when the next round opens),
        # and every --period seconds when no result comes (not paired yet).
        delay = random.uniform(2, 4)
        while not self.stop.is_set():
            if self.strategy == "absent":
                time.sleep(1)
                continue
            self.got_result.wait(timeout=delay)
            synced = self.got_result.is_set()
            self.got_result.clear()
            if synced:
                time.sleep(a.reveal)          # the reveal, then the next round opens
            if self.strategy == "slow":
                time.sleep(random.uniform(a.slow_min, a.slow_max))
            else:
                time.sleep(random.uniform(0.5, 4))
            mv = self.next_move()
            self.last_move = mv
            self.client.publish(f"{self.prefix}/{self.pid}/move", mv)
            self.log(f"move {mv}")
            if a.double_press and random.random() < 0.3:
                time.sleep(0.3)
                self.client.publish(f"{self.prefix}/{self.pid}/move", mv)
                self.log("move again (should be ignored)")
            delay = a.period
        self.client.loop_stop()
        self.client.disconnect()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--prefix", default="bme/s04/game")
    ap.add_argument("--players", type=int, default=2)
    ap.add_argument("--strategy", default="mixed", help="one of %s, or mixed" % ", ".join(STRATEGIES))
    ap.add_argument("--join-staggered", type=float, default=0, metavar="SECONDS",
                    help="join the players one by one every N seconds")
    ap.add_argument("--period", type=float, default=60, help="seconds between presses while no result arrives")
    ap.add_argument("--reveal", type=float, default=30, help="the game master's ROUND_REVEAL_SECONDS")
    ap.add_argument("--slow-min", type=float, default=24, help="'slow' players press this long after the round opens...")
    ap.add_argument("--slow-max", type=float, default=36, help="...at most this long (past ROUND_OPEN_SECONDS = a miss)")
    ap.add_argument("--double-press", action="store_true", help="sometimes press twice, to see the duplicate ignored")
    ap.add_argument("--seed", type=int)
    args = ap.parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    if args.strategy == "mixed":
        pool = ["always-c", "always-b", "tit-for-tat", "tit-for-tat", "random", "slow", "absent"]
        strategies = [pool[i % len(pool)] for i in range(args.players)]
    elif args.strategy in STRATEGIES:
        strategies = [args.strategy] * args.players
    else:
        ap.error(f"unknown strategy {args.strategy!r}")

    players = [Player(i, s, args) for i, s in enumerate(strategies)]
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    for i, p in enumerate(players):
        p.start()
        if args.join_staggered and i < len(players) - 1:
            time.sleep(args.join_staggered)
    print(f"{len(players)} players on {args.host}:{args.port} under {args.prefix}/ — Ctrl-C to stop", flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
