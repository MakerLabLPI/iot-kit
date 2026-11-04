"""The game itself: players, rounds, pairing, scoring. Pure Python, no I/O,
no clock. The scheduler decides *when* to call open_round / close_round /
end_reveal; the MQTT adapter decides *what* join / move mean on the wire.
Everything here is unit-tested in tests/test_engine.py."""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

# The nickname is the id: letters, digits, dash, underscore. Topics are
# case-sensitive, so "Alan" and "alan" are two players.
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,24}$")

# (move A, move B) -> (points A, points B)
PAYOFF = {
    ("C", "C"): (3, 3),
    ("B", "B"): (1, 1),
    ("B", "C"): (5, 0),
    ("C", "B"): (0, 5),
}

WAITING, ACTIVE, DROPPED = "waiting", "active", "dropped"
IDLE, OPEN, REVEAL = "idle", "open", "reveal"


def score(move_a: str, move_b: str) -> tuple[int, int]:
    return PAYOFF[(move_a, move_b)]


def parse_move(payload: str) -> str | None:
    """'c', 'C', 'C\\n' -> 'C'; anything else -> None."""
    p = payload.strip().upper()
    return p if p in ("C", "B") else None


def valid_id(pid: str) -> bool:
    return bool(ID_RE.match(pid))


@dataclass
class Player:
    id: str
    state: str = WAITING
    points: int = 0
    rounds_played: int = 0
    coop_streak: int = 0
    misses: int = 0            # consecutive rounds paired without a move
    sit_outs: int = 0
    sat_out_last: bool = False
    last_opponent: str | None = None
    joined_round: int = 0      # round number at which they were promoted

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "state": self.state,
            "points": self.points,
            "rounds_played": self.rounds_played,
            "avg": round(self.points / self.rounds_played, 2) if self.rounds_played else 0.0,
            "coop_streak": self.coop_streak,
            "misses": self.misses,
            "sit_outs": self.sit_outs,
        }


@dataclass
class Match:
    a: str
    b: str
    moves: dict[str, str | None] = field(default_factory=dict)
    random: set[str] = field(default_factory=set)   # who got a timeout move
    points: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        self.moves = {self.a: None, self.b: None}

    def has(self, pid: str) -> bool:
        return pid in self.moves

    def opponent(self, pid: str) -> str:
        return self.b if pid == self.a else self.a

    def as_dict(self, revealed: bool) -> dict:
        """Moves and points leave the engine only once the round is closed:
        the snapshot is public (SSE, /api/state)."""
        d = {"a": self.a, "b": self.b,
             "locked": {p: m is not None for p, m in self.moves.items()}}
        if revealed:
            d.update({"moves": dict(self.moves), "random": sorted(self.random),
                      "points": dict(self.points)})
        else:
            d.update({"moves": {}, "random": [], "points": {}})
        return d


@dataclass
class Round:
    number: int
    matches: list[Match]
    sit_out: str | None
    phase: str = OPEN

    def match_of(self, pid: str) -> Match | None:
        for m in self.matches:
            if m.has(pid):
                return m
        return None


# One row of the CSV round log: round, player, opponent, move, random?, points
@dataclass
class LogRow:
    round: int
    player: str
    opponent: str
    move: str
    random: bool
    points: int


@dataclass
class Result:
    """What the engine made of an incoming message. `status` is one of
    accepted, rejoined, ignored_closed, ignored_not_paired,
    ignored_duplicate, ignored_dropped, not_joined, bad_id, bad_payload."""
    status: str
    player: str | None = None
    detail: str = ""

    @property
    def accepted(self) -> bool:
        return self.status in ("accepted", "rejoined")


# --- pairing -----------------------------------------------------------------

def choose_sit_out(players: list[str], sit_outs: Mapping[str, int],
                   sat_out_last: Mapping[str, bool], rng: random.Random) -> str:
    """Fewest sit-outs so far, then not benched last round, then random."""
    candidates = list(players)
    rng.shuffle(candidates)
    return min(candidates, key=lambda p: (sit_outs.get(p, 0), sat_out_last.get(p, False)))


def pair_players(players: Iterable[str], meetings: Mapping[frozenset, int],
                 last_opponent: Mapping[str, str | None], sit_outs: Mapping[str, int],
                 sat_out_last: Mapping[str, bool], rng: random.Random
                 ) -> tuple[list[tuple[str, str]], str | None]:
    """Pure function of (players, history, rng): returns (pairs, sit_out).
    Greedy: each unpaired player (random order) takes the unpaired opponent
    met the fewest times; ties go to whoever was not last round's opponent,
    then random."""
    pool = sorted(set(players))
    sit_out = None
    if len(pool) % 2 == 1:
        sit_out = choose_sit_out(pool, sit_outs, sat_out_last, rng)
        pool.remove(sit_out)
    rng.shuffle(pool)
    pairs: list[tuple[str, str]] = []
    unpaired = list(pool)
    while unpaired:
        p = unpaired.pop(0)
        others = list(unpaired)
        rng.shuffle(others)
        q = min(others, key=lambda o: (meetings.get(frozenset((p, o)), 0),
                                       last_opponent.get(p) == o))
        unpaired.remove(q)
        pairs.append((p, q))
    return pairs, sit_out


# --- the engine --------------------------------------------------------------

class Engine:
    def __init__(self, max_missed: int = 2, rng: random.Random | None = None):
        self.max_missed = max_missed
        self.rng = rng or random.Random()
        self.players: dict[str, Player] = {}
        self.round: Round | None = None
        self.round_number = 0
        self.meetings: dict[frozenset, int] = {}
        self.rows: list[LogRow] = []

    # -- players ------------------------------------------------------------

    def join(self, pid: str) -> Result:
        """The join payload is ignored: the nickname is the id in the topic."""
        if not valid_id(pid):
            return Result("bad_id", pid, "must match ^[A-Za-z0-9_-]{1,24}$")
        p = self.players.get(pid)
        if p is None:
            self.players[pid] = Player(pid)
            return Result("accepted", pid)
        if p.state == DROPPED:
            p.state = WAITING
            p.misses = 0
            return Result("rejoined", pid)
        return Result("accepted", pid)  # idempotent

    def kick(self, pid: str) -> bool:
        p = self.players.get(pid)
        if p is None or p.state == DROPPED:
            return False
        p.state = DROPPED
        return True

    def reinstate(self, pid: str) -> bool:
        p = self.players.get(pid)
        if p is None or p.state != DROPPED:
            return False
        p.state = WAITING
        p.misses = 0
        return True

    def eligible(self) -> list[str]:
        """Who plays the next round: active players and waiting ones."""
        return [p.id for p in self.players.values() if p.state in (ACTIVE, WAITING)]

    # -- moves ----------------------------------------------------------------

    def move(self, pid: str, payload: str) -> Result:
        if not valid_id(pid):
            return Result("bad_id", pid, "must match ^[A-Za-z0-9_-]{1,24}$")
        p = self.players.get(pid)
        if p is None:
            return Result("not_joined", pid, "no join received for this id")
        mv = parse_move(payload)
        if mv is None:
            return Result("bad_payload", pid, "payload must be C or B")
        r = self.round
        if r is None or r.phase != OPEN:
            return Result("ignored_closed", pid, mv)
        m = r.match_of(pid)
        if m is None:
            return Result("ignored_not_paired", pid, mv)
        if m.moves[pid] is not None:
            return Result("ignored_duplicate", pid, mv)
        m.moves[pid] = mv
        return Result("accepted", pid, mv)

    # -- rounds ---------------------------------------------------------------

    def open_round(self) -> Round | None:
        """Promote waiting players, pair everyone, open the round.
        Returns None (and stays idle) with fewer than 2 players."""
        assert self.round is None or self.round.phase != OPEN, "round already open"
        ids = self.eligible()
        if len(ids) < 2:
            self.round = None
            return None
        self.round_number += 1
        for pid in ids:
            p = self.players[pid]
            if p.state == WAITING:
                p.state = ACTIVE
                p.joined_round = self.round_number
        pairs, sit_out = pair_players(
            ids, self.meetings,
            {pid: self.players[pid].last_opponent for pid in ids},
            {pid: self.players[pid].sit_outs for pid in ids},
            {pid: self.players[pid].sat_out_last for pid in ids},
            self.rng,
        )
        for pid in ids:
            self.players[pid].sat_out_last = pid == sit_out
        if sit_out:
            self.players[sit_out].sit_outs += 1
        self.round = Round(self.round_number, [Match(a, b) for a, b in pairs], sit_out)
        return self.round

    def close_round(self) -> list[tuple[str, int]]:
        """Fill in random moves, score, count misses, drop. Returns the
        (player, points) results to publish, in match order."""
        r = self.round
        assert r is not None and r.phase == OPEN, "no open round"
        results: list[tuple[str, int]] = []
        for m in r.matches:
            for pid in (m.a, m.b):
                p = self.players[pid]
                if m.moves[pid] is None:
                    m.moves[pid] = self.rng.choice(("C", "B"))
                    m.random.add(pid)
                    p.misses += 1
                    if p.misses >= self.max_missed and p.state != DROPPED:
                        p.state = DROPPED
                else:
                    p.misses = 0
            pa, pb = score(m.moves[m.a], m.moves[m.b])
            m.points = {m.a: pa, m.b: pb}
            key = frozenset((m.a, m.b))
            self.meetings[key] = self.meetings.get(key, 0) + 1
            for pid in (m.a, m.b):
                p = self.players[pid]
                p.points += m.points[pid]
                p.rounds_played += 1
                p.last_opponent = m.opponent(pid)
                real_c = m.moves[pid] == "C" and pid not in m.random
                p.coop_streak = p.coop_streak + 1 if real_c else 0
                self.rows.append(LogRow(r.number, pid, m.opponent(pid), m.moves[pid],
                                        pid in m.random, m.points[pid]))
                results.append((pid, m.points[pid]))
        r.phase = REVEAL
        return results

    def end_reveal(self) -> None:
        if self.round is not None:
            self.round.phase = IDLE

    def reset_scores(self) -> None:
        """Start the real match: scores and history go, the pool stays."""
        for p in self.players.values():
            p.points = p.rounds_played = p.coop_streak = 0
            p.misses = p.sit_outs = 0
            p.sat_out_last = False
            p.last_opponent = None
            p.joined_round = 0
        self.round = None
        self.round_number = 0
        self.meetings = {}
        self.rows = []

    # -- views --------------------------------------------------------------

    @property
    def phase(self) -> str:
        return self.round.phase if self.round else IDLE

    def leaderboard(self) -> list[dict]:
        """Ranked: dropped players last, then by points, then rounds played
        (fewer rounds for the same points is better), then id."""
        def key(p: Player):
            return (p.state == DROPPED, -p.points, p.rounds_played, p.id.lower(), p.id)
        rows = []
        for rank, p in enumerate(sorted(self.players.values(), key=key), 1):
            d = p.as_dict()
            d["rank"] = rank
            rows.append(d)
        return rows

    def snapshot(self) -> dict:
        r = self.round
        return {
            "round": r.number if r else self.round_number,
            "phase": self.phase,
            "matches": [m.as_dict(r.phase != OPEN) for m in r.matches] if r else [],
            "sit_out": r.sit_out if r else None,
            "players": {pid: p.as_dict() for pid, p in self.players.items()},
            "leaderboard": self.leaderboard(),
            "eligible": len(self.eligible()),
        }

    def round_summary(self) -> dict:
        """The JSON published on <prefix>/log after each round."""
        r = self.round
        if r is None:
            return {}
        return {
            "round": r.number,
            "matches": [
                {"a": m.a, "b": m.b, "moves": dict(m.moves), "points": dict(m.points),
                 "random": sorted(m.random)}
                for m in r.matches
            ],
            "sit_out": r.sit_out,
            "standings": [{"id": p["id"], "points": p["points"]} for p in self.leaderboard()],
        }
