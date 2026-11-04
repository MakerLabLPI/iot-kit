# Exercises

Exercises for the workshop, one folder per exercise. Each one runs on the Pi as its own Docker stack, started by hand for the session; the students only need an ESP32 and the kit WiFi.

## ex_01: Secret

`exercises/ex_01/` is a small HTTP server (Python, Docker) on port 8001 that
answers `Hello World` on `/secret` and 404 everywhere else. The students
make their ESP32 fetch it. It runs on the Pi, started by hand:

```sh
cd ~/iot-kit/exercises/ex_01
docker compose up -d      # start (builds the image the first time)
docker compose logs -f    # one line per request, with the client's address
docker compose down       # stop
```

- Check without a board: `curl http://iot-kit.lan:8001/secret`

## ex_02: Heartbeat and breath

A heart beats and lungs breathe, each with its own tempo, and every beat
and every breath is published. The students make two LEDs on their ESP32
follow both (Lab 2 of the session 04 slides): first with `delay()`, and see
the heart stop while the breath LED is on, then with `millis()`.

The clocks run on the Pi (`exercises/ex_02/rhythms.py`, Python, Docker), so
the boards keep beating whatever the teacher's laptop does. Started by hand,
then it stays up across reboots:

```sh
cd ~/iot-kit/exercises/ex_02
docker compose up -d --build   # start (builds the image the first time)
docker compose logs -f         # every rate change
docker compose down            # stop: the boards stop beating
```

The page at `http://192.168.50.1:8002/` (served by the same container;
`exercises/ex_02/index.html` also works opened as a file) shows the rhythms
and remote-controls them. Nothing to install, it speaks MQTT over WebSockets
(port 9001) and works offline. Several laptops can show it at once, they all
see the same clocks.

| Topic | Payload | When |
|---|---|---|
| `bme/s04/heartbeat` | the tempo in BPM, as text (`72`) | one message per beat |
| `bme/s04/breath` | the rate per minute, as text (`12`) | one message per breath |
| `bme/s04/heartbeat/rate`, `.../running` | `72`, `1` or `0` | retained state, same under `bme/s04/breath/` |
| `bme/s04/heartbeat/set`, `bme/s04/breath/set` | a rate, `pause` or `start` | what the page's slider and button send |

The boards only need the first two: QoS 0, not retained. On the board:
heartbeat = LED 1 for 100 ms, breath = LED 2 for 2 s.

- Each side has its own Pause button and slider. Keyboard: Space pauses the
  heart, B the breath; arrow up / down change the heart tempo, right / left
  the breath rate (with shift: by 10). A new rate takes effect at the next
  beat; the page shows what the Pi confirms, not what was asked.
- The bottom left corner shows whether the broker is reached. The page
  reconnects by itself and picks up the current rates.
- Without the page: `mosquitto_pub -h broker.lan -t bme/s04/heartbeat/set -m 90`
  (`HEART_BPM` and `BREATH_RATE` in `docker-compose.yml` are the values at start).
- `exercises/ex_02/esp32-heartbeat/` is the reference solution of Lab 2b
  (two LEDs, no `delay()`). What makes the boards beat together is
  `WiFi.setSleep(false)`, and no `delay()` in the message callback.
- Check without a board: `mosquitto_sub -h broker.lan -t 'bme/s04/#' -v`
- Other broker or topics:
  `index.html?broker=ws://localhost:9001&heartbeat=test/heartbeat&breath=test/breath`

## ex_03: The Traitor's Game

`exercises/ex_03/` is the game master of Lab 3: a Prisoner's Dilemma
tournament over MQTT (Python, Docker) with a live
leaderboard for the projector at `http://192.168.50.1:8003/`. Students
publish `join` and `move` on `bme/s04/game/<name>/...` and get their points
back on `.../result`; the game master pairs, times, scores. Started by hand:

```sh
cd ~/iot-kit/exercises/ex_03
ADMIN_PASSWORD=choose-one docker compose up -d --build
docker compose logs -f
docker compose down
```

- Rules, MQTT contract, admin page and the simulator (`sim.py`, plays
  without boards): see [`ex_03/README.md`](ex_03/README.md).
