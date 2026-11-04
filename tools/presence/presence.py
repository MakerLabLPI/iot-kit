#!/usr/bin/env python3
"""Who is on the kit LAN right now. Runs on the Pi (tools/docker-compose.yml,
host networking: ARP lives on eth0).

Every client got its address from the Pi's dnsmasq, so the lease file
lists every candidate. Ping them all at once (which forces an ARP exchange,
even with devices that ignore ping), then read the kernel's neighbour table
for the ones that answered. Publishes on MQTT:

    <topic>/present   {"count": 2, "devices": [{"ip", "mac", "name"}, ...]}  retained
    <topic>/joined    {"ip", "mac", "name"}      one message per arrival
    <topic>/left      {"ip", "mac", "name"}      one message per departure

    python3 presence.py            # every PERIOD s, forever
    python3 presence.py --once     # one sweep, list who is present
"""
import json
import os
import subprocess
import sys
import time

import paho.mqtt.client as mqtt

LEASES = os.environ.get("LEASES", "/var/lib/misc/dnsmasq.leases")
IFACE = os.environ.get("IFACE", "eth0")
PERIOD = float(os.environ.get("PERIOD", "5"))      # seconds between sweeps
MISSES = int(os.environ.get("MISSES", "3"))        # sweeps without an answer before "left"
TOPIC = os.environ.get("TOPIC", "bme/s04/net")
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))


def leases() -> dict[str, dict]:
    """ip -> {mac, name} for every current lease (the AP included)."""
    out = {}
    for line in open(LEASES):
        parts = line.split()
        if len(parts) >= 4:
            out[parts[2]] = {"mac": parts[1], "name": parts[3] if parts[3] != "*" else ""}
    return out


def sweep(ips) -> set[str]:
    """Ping everything in parallel, then keep whoever the kernel now knows
    the MAC of. Entries in FAILED state did not answer the ARP request."""
    procs = [subprocess.Popen(["ping", "-c", "1", "-W", "1", ip],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for ip in ips]
    for p in procs:
        p.wait()
    neigh = subprocess.run(["ip", "neigh", "show", "dev", IFACE], capture_output=True, text=True).stdout
    present = set()
    for line in neigh.splitlines():
        parts = line.split()
        if "lladdr" in parts and parts[-1] in ("REACHABLE", "STALE", "DELAY", "PROBE"):
            present.add(parts[0])
    return present & set(ips)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="presence")


def publish(event: str, ip: str, info: dict) -> None:
    msg = json.dumps({"ip": ip, **info})
    print(time.strftime("%H:%M:%S"), event, msg, flush=True)
    client.publish(f"{TOPIC}/{event}", msg, qos=1)


def publish_present(present: set[str], known: dict) -> None:
    devices = [{"ip": ip, **known.get(ip, {})}
               for ip in sorted(present, key=lambda s: int(s.split(".")[-1]))]
    client.publish(f"{TOPIC}/present", json.dumps({"count": len(devices), "devices": devices}),
                   qos=1, retain=True)


def main() -> None:
    known = leases()
    if "--once" in sys.argv:
        for ip in sorted(sweep(known), key=lambda s: int(s.split(".")[-1])):
            print(f"{ip:16} {known[ip]['mac']}  {known[ip]['name']}")
        return

    client.reconnect_delay_set(1, 10)
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    print(f"sweeping the leases of {LEASES} on {IFACE} every {PERIOD:g} s, "
          f"publishing under {TOPIC}/", flush=True)

    missed: dict[str, int] = {}      # ip -> consecutive sweeps without an answer
    present: set[str] = set()
    first = True
    while True:
        known = leases()
        seen = sweep(known)
        for ip in seen - present:
            publish("joined", ip, known[ip])
        for ip in seen:
            missed[ip] = 0
        for ip in present - seen:
            missed[ip] = missed.get(ip, 0) + 1
        gone = {ip for ip in present - seen if missed[ip] >= MISSES}
        for ip in gone:
            publish("left", ip, known.get(ip, {}))
        changed = bool(seen - present) or bool(gone)
        present = (present | seen) - gone
        if changed or first:
            publish_present(present, known)
            first = False
        time.sleep(PERIOD)


if __name__ == "__main__":
    main()
