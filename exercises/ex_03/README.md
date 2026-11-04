# ex_03: The Traitor's Game

A live 1v1 Prisoner's Dilemma tournament over MQTT, with a leaderboard for
the projector. Students play from an ESP32 with two buttons (Cooperate /
Betray); this game master pairs them, runs the clock, scores, and drives the
page. Game state lives in memory only: restarting the container starts a
new game.

```
ESP32 ── bme/s04/game/<name>/join ──▶ ┌─────────────┐
ESP32 ── bme/s04/game/<name>/move ──▶ │ game master │ ──▶ http://192.168.50.1:8003/
ESP32 ◀─ bme/s04/game/<name>/result ─ └─────────────┘     (projector, live)
```

## Start, stop, reset

On the Pi (the broker from `broker/` is already running on `localhost:1883`):

```sh
cd ~/iot-kit/exercises/ex_03
ADMIN_PASSWORD=choose-one docker compose up -d --build   # start (builds the image the first time)
docker compose logs -f                                   # every MQTT message, one line each
docker compose down                                      # stop, forgets the game
```

- Page: `http://192.168.50.1:8003/` (also `http://iot-kit.lan:8003/`).
- Admin: `http://192.168.50.1:8003/admin`, HTTP basic auth, any user name,
  the `ADMIN_PASSWORD` you started with. Without a password `/admin` is off.
- **Reset scores**: the button top right of the page (with a confirm step).
  It wipes scores and history and restarts at round 1 with everyone still
  in the pool. Use it once the room has finished building to start the
  real match. The admin page has the same button.
- Settings are environment variables in `docker-compose.yml`:

| Variable | Default | |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | `localhost` / `1883` | the broker |
| `TOPIC_PREFIX` | `bme/s04/game` | all topics live under it |
| `ROUND_OPEN_SECONDS` | `30` | moves accepted |
| `ROUND_REVEAL_SECONDS` | `30` | results shown, no moves |
| `MAX_MISSED_ROUNDS` | `2` | consecutive misses before a player is dropped |
| `WEB_PORT` | `8003` | |
| `ADMIN_PASSWORD` | empty | empty = `/admin` disabled |

On a laptop without a broker: `docker network create iot-kit` once, then
`docker compose --profile broker up -d` also starts a Mosquitto with
anonymous access on 1883. Never use that profile on the Pi, its broker is
already there.

## The MQTT contract (for students)

Three topics, one subscription, no round state on the board. Press a
button, publish, wait for a number back. Everything else (round timing,
opponents, standings) is on the web page.

| Topic | Direction | Payload | Purpose |
|---|---|---|---|
| `bme/s04/game/<name>/join` | ESP32 → GM | anything, e.g. `hi` (ignored) | enter the pool, once in `setup()` |
| `bme/s04/game/<name>/move` | ESP32 → GM | `C` or `B` | play during an open round |
| `bme/s04/game/<name>/result` | GM → ESP32 | points: `0`, `1`, `3` or `5` | drive the LEDs |

- `<name>` is the student's nickname, a single `const char* NAME` at the
  top of the sketch. It is shown on the board as is and it is the only
  identity the game master has: MQTT does not carry the connect-time
  client ID in published messages, so **the topic path is how the game
  master knows who moved**. Guidelines to give the room: letters, digits,
  `-` and `_` only (`^[A-Za-z0-9_-]{1,24}$`: no spaces, no accents),
  unique in the room, and case matters (`Alan` and `alan` are two
  players). Invalid names are rejected with a red line in the log.
- Joining again while in the pool changes nothing.
- `result` carries points, not a verdict: `5` betrayed a cooperator, `3`
  mutual cooperation, `1` mutual betrayal, `0` cooperated against a traitor.
  One comparison (`points >= 3`) lights the good LED.
- Move payloads are trimmed and case-insensitive (`c`, `C`, `C\n`). Anything
  else is rejected and shown in red on the page.
- Only the first valid move per player per round counts. Moves while the
  round is closed, or from a player not paired this round, are ignored
  (shown in grey on the page, not queued).
- QoS 0 is fine for everything the boards publish (PubSubClient default).
  The game master publishes at QoS 1.
- **The broker has no authentication: anyone can publish on anyone's move
  topic.** That is deliberate, and the material for the end-of-session
  hacker demo. The game master also publishes a JSON summary of every round
  on `bme/s04/game/log` (not told to students).

`esp32-traitor/esp32-traitor.ino` is the reference sketch: about 25 lines
on top of Lab 2b, one constant (`NAME`), one subscription, one publish per
button, a four-line callback with no topic comparison.

## Game rules

| A | B | Points A | Points B |
|---|---|---|---|
| C | C | 3 | 3 |
| B | B | 1 | 1 |
| B | C | 5 | 0 |
| C | B | 0 | 5 |

Round cycle, no teacher action: **Open** (30 s, the full time even if
everyone has moved) → **Close** (a paired player with no move gets a random
C or B, flagged with a dice badge; their opponent gets a real result) →
**Reveal** (30 s, all results at once) → the next round opens.

- Odd number of players: one sits out (fewest sit-outs so far, then not
  benched last round, then random). They score nothing that round and it is
  not a miss.
- Fewer than 2 players in the pool: the game idles ("Waiting for players").
- Pairings favour opponents met least; with 2 players they meet every round.
- Player lifecycle: `waiting` (joined, paired from the next round) →
  `active` → `dropped` after `MAX_MISSED_ROUNDS` consecutive rounds paired
  without a move. Dropped players keep their score, are greyed out at the
  bottom, and come back by publishing join again. A move from an id that
  never joined does nothing except a red line in the log.
- Ranking is by total points: boards that work earlier are rewarded.

## Testing without boards

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/pytest -q tests                       # engine: scoring, pairing, lifecycle
.venv/bin/python sim.py --players 7 --strategy mixed --host 192.168.50.1
.venv/bin/python sim.py --players 3 --join-staggered 30    # late arrivals
.venv/bin/python sim.py --players 2 --strategy tit-for-tat --double-press
```

Strategies: `always-c`, `always-b`, `tit-for-tat`, `random`, `slow` (moves
24–36 s after the round opens, sometimes too late), `absent` (never moves,
gets dropped), or `mixed` (one of each, cycling). The fake players are
named `Ada`, `Linus`, `Grace`, … and only see
their own result, like a real board, and press a few seconds after each
result arrives. `--reveal` must match `ROUND_REVEAL_SECONDS` if you change
it.

To check with the command line only:

```sh
mosquitto_pub -h 192.168.50.1 -t bme/s04/game/Test/join -m hi
mosquitto_pub -h 192.168.50.1 -t bme/s04/game/Test/move -m C
mosquitto_sub -h 192.168.50.1 -t 'bme/s04/game/#' -v
curl http://192.168.50.1:8003/api/state
```

## Layout

| Path | |
|---|---|
| `gamemaster/engine.py` | the game: players, pairing, scoring; pure Python, unit-tested |
| `gamemaster/game.py` | round scheduler, live log feed, state snapshots |
| `gamemaster/mqtt.py` | paho-mqtt 2.x adapter, auto-reconnect and resubscribe |
| `gamemaster/web.py` | aiohttp: `/`, `/events` (SSE), `/api/state`, `/api/reset`, `/admin`, `/admin/log.csv` |
| `gamemaster/static/` | the projector page and the admin page, plain HTML/CSS/JS, no CDN |
| `sim.py` | simulated players |
| `tests/` | pytest |
| `examples/` | reference student sketches (two buttons; BOOT button only) |
