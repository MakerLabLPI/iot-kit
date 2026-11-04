import random
from collections import Counter

import pytest

from gamemaster.engine import (ACTIVE, DROPPED, IDLE, OPEN, REVEAL, WAITING,
                               Engine, pair_players, parse_move, score)


def engine(n=0, seed=1, **kw):
    e = Engine(rng=random.Random(seed), **kw)
    for i in range(n):
        e.join(f"p{i}")
    return e


def play_round(e, moves=None):
    """Open a round, play the given moves (default: everyone cooperates),
    close it, end the reveal. Returns the published results."""
    r = e.open_round()
    if r is None:
        return None
    for m in r.matches:
        for pid in (m.a, m.b):
            mv = (moves or {}).get(pid, "C")
            if mv is not None:
                e.move(pid, mv)
    results = e.close_round()
    e.end_reveal()
    return results


# --- scoring -------------------------------------------------------------------

@pytest.mark.parametrize("a,b,pa,pb", [
    ("C", "C", 3, 3), ("B", "B", 1, 1), ("B", "C", 5, 0), ("C", "B", 0, 5),
])
def test_payoff_table(a, b, pa, pb):
    assert score(a, b) == (pa, pb)


@pytest.mark.parametrize("payload,expected", [
    ("C", "C"), ("c", "C"), ("C\n", "C"), ("  b ", "B"), ("B", "B"),
    ("", None), ("X", None), ("CC", None), ("cooperate", None),
])
def test_parse_move(payload, expected):
    assert parse_move(payload) == expected


def test_points_add_up_over_a_round():
    e = engine(2)
    results = play_round(e, {"p0": "B", "p1": "C"})
    assert dict(results) == {"p0": 5, "p1": 0}
    assert e.players["p0"].points == 5
    assert e.players["p1"].points == 0
    assert e.players["p0"].rounds_played == e.players["p1"].rounds_played == 1


# --- pairing -------------------------------------------------------------------

def pairing(ids, meetings=None, last=None, sit_outs=None, sat_last=None, seed=0):
    return pair_players(ids, meetings or {}, last or {}, sit_outs or {},
                        sat_last or {}, random.Random(seed))


def test_two_players_meet_every_round():
    pairs, sit_out = pairing(["a", "b"])
    assert pairs == [("a", "b")] or pairs == [("b", "a")]
    assert sit_out is None


def test_three_players_one_sits_out():
    pairs, sit_out = pairing(["a", "b", "c"])
    assert len(pairs) == 1
    assert sit_out is not None
    assert set(pairs[0]) | {sit_out} == {"a", "b", "c"}


def test_four_players_two_pairs_everyone_once():
    pairs, sit_out = pairing(["a", "b", "c", "d"])
    assert sit_out is None
    assert len(pairs) == 2
    assert Counter(p for pair in pairs for p in pair) == Counter("abcd")


def test_fifteen_players_seven_pairs_and_a_bench():
    ids = [f"p{i}" for i in range(15)]
    pairs, sit_out = pairing(ids)
    assert len(pairs) == 7
    assert sit_out in ids
    assert Counter(p for pair in pairs for p in pair) + Counter([sit_out]) == Counter(ids)


def test_pairing_is_deterministic_for_a_seed():
    ids = [f"p{i}" for i in range(9)]
    assert pairing(ids, seed=42) == pairing(ids, seed=42)


def test_no_repeat_pairing_when_avoidable():
    # 4 players: 3 rounds of a round-robin never repeat a pair
    e = engine(4)
    seen = set()
    for _ in range(3):
        r = e.open_round()
        for m in r.matches:
            key = frozenset((m.a, m.b))
            assert key not in seen, "pair repeated while an unmet one existed"
            seen.add(key)
            e.move(m.a, "C")
            e.move(m.b, "C")
        e.close_round()
        e.end_reveal()
    assert len(seen) == 6  # every pair met exactly once


def test_meetings_stay_balanced_over_many_rounds():
    e = engine(6)
    for _ in range(30):
        play_round(e)
    counts = list(e.meetings.values())
    assert len(counts) == 15          # every pair has met
    assert max(counts) - min(counts) <= 2


def test_sit_out_rotates():
    e = engine(7)
    benched = []
    for _ in range(14):
        r = e.open_round()
        assert len(r.matches) == 3
        benched.append(r.sit_out)
        for m in r.matches:
            e.move(m.a, "C")
            e.move(m.b, "B")
        e.close_round()
        e.end_reveal()
    assert len(set(benched[:7])) == 7, "the first 7 rounds bench 7 different players"
    assert all(x != y for x, y in zip(benched, benched[1:])), "nobody benches twice in a row"
    assert max(Counter(benched).values()) == 2


def test_three_players_cycle_through_the_bench():
    e = engine(3)
    benched = []
    for _ in range(3):
        r = e.open_round()
        benched.append(r.sit_out)
        e.move(r.matches[0].a, "C")
        e.move(r.matches[0].b, "C")
        e.close_round()
        e.end_reveal()
    assert set(benched) == {"p0", "p1", "p2"}


def test_sitting_out_scores_nothing_and_is_not_a_miss():
    e = engine(3)
    r = e.open_round()
    bench = e.players[r.sit_out]
    e.close_round()
    assert bench.points == 0 and bench.rounds_played == 0 and bench.misses == 0


# --- lifecycle -------------------------------------------------------------------

def test_join_makes_waiting_then_active_on_next_open():
    e = engine()
    assert e.join("Sev").status == "accepted"
    assert e.players["Sev"].state == WAITING
    e.join("Alan")
    e.open_round()
    assert e.players["Sev"].state == ACTIVE


def test_join_is_idempotent():
    e = engine()
    e.join("a")
    assert e.join("a").status == "accepted"
    assert e.players["a"].state == WAITING
    assert len(e.players) == 1


def test_names_are_case_sensitive_like_topics():
    e = engine()
    e.join("Alan")
    e.join("alan")
    assert set(e.players) == {"Alan", "alan"}


def test_join_during_round_waits_for_next_round():
    e = engine(2)
    r = e.open_round()
    e.join("late")
    assert e.players["late"].state == WAITING
    assert r.match_of("late") is None
    assert e.move("late", "C").status == "ignored_not_paired"
    e.close_round()
    e.end_reveal()
    r2 = e.open_round()
    assert e.players["late"].state == ACTIVE
    assert r2.sit_out is not None  # 3 players now


def test_invalid_names_rejected():
    e = engine()
    for bad in ("", "a" * 25, "Sev Ferard", "Séverin", "sev.f", "a/b", "#", "+"):
        assert e.join(bad).status == "bad_id"
        assert e.move(bad, "C").status == "bad_id"
    assert e.players == {}
    for ok in ("Sev", "s04-pair07", "team_7", "A"):
        assert e.join(ok).status == "accepted"


def test_move_without_join_does_nothing():
    e = engine(2)
    e.open_round()
    assert e.move("ghost", "C").status == "not_joined"
    assert "ghost" not in e.players
    e.close_round()
    e.end_reveal()
    e.open_round()
    assert e.round.match_of("ghost") is None


def test_two_misses_drop_the_player_and_the_opponent_still_scores():
    e = engine(2)
    play_round(e, {"p1": None})
    assert e.players["p1"].misses == 1
    assert e.players["p1"].state == ACTIVE
    assert e.players["p0"].rounds_played == 1
    results = play_round(e, {"p1": None})
    assert e.players["p1"].state == DROPPED
    assert dict(results).keys() == {"p0", "p1"}
    assert e.players["p0"].rounds_played == 2
    assert e.players["p0"].points in (0, 3, 6)  # p1's random moves decided it
    # p1 is out of the pool: only one eligible player, the game idles
    assert e.open_round() is None
    assert e.phase == IDLE


def test_random_fallback_is_flagged():
    e = engine(2)
    r = e.open_round()
    e.move("p0", "C")
    e.close_round()
    m = r.matches[0]
    assert m.moves["p1"] in ("C", "B")
    assert m.random == {"p1"}
    assert e.rows[-1].random is True or e.rows[-2].random is True


def test_a_move_resets_the_miss_count():
    e = engine(2)
    play_round(e, {"p1": None})
    play_round(e)
    play_round(e, {"p1": None})
    assert e.players["p1"].misses == 1
    assert e.players["p1"].state == ACTIVE


def test_missed_threshold_is_configurable():
    e = engine(2, max_missed=3)
    play_round(e, {"p1": None})
    play_round(e, {"p1": None})
    assert e.players["p1"].state == ACTIVE
    play_round(e, {"p1": None})
    assert e.players["p1"].state == DROPPED


def test_rejoin_keeps_score_and_history():
    e = engine(2)
    play_round(e)
    play_round(e, {"p1": None})
    play_round(e, {"p1": None})
    assert e.players["p1"].state == DROPPED
    pts, played = e.players["p1"].points, e.players["p1"].rounds_played
    assert pts > 0
    assert e.join("p1").status == "rejoined"
    assert e.players["p1"].state == WAITING
    assert e.players["p1"].misses == 0
    assert e.players["p1"].points == pts
    assert e.players["p1"].rounds_played == played
    assert e.open_round() is not None
    assert e.players["p1"].state == ACTIVE


def test_duplicate_move_ignored_first_one_counts():
    e = engine(2)
    e.open_round()
    assert e.move("p0", "C").status == "accepted"
    assert e.move("p0", "B").status == "ignored_duplicate"
    assert e.move("p0", "C").status == "ignored_duplicate"
    assert e.round.matches[0].moves["p0"] == "C"


def test_late_and_early_moves_ignored():
    e = engine(2)
    assert e.move("p0", "C").status == "ignored_closed"   # nothing open yet
    e.open_round()
    e.close_round()
    assert e.move("p0", "C").status == "ignored_closed"   # reveal
    e.end_reveal()
    assert e.move("p0", "C").status == "ignored_closed"   # between rounds
    assert "p0" in e.round.matches[0].random  # never got a real move in


def test_bad_payload_rejected():
    e = engine(2)
    e.open_round()
    assert e.move("p0", "x").status == "bad_payload"
    assert e.move("p0", "").status == "bad_payload"
    assert e.round.matches[0].moves["p0"] is None
    assert e.move("p0", "c\n").status == "accepted"


def test_coop_streak():
    e = engine(2)
    play_round(e, {"p0": "C"})
    play_round(e, {"p0": "C"})
    assert e.players["p0"].coop_streak == 2
    play_round(e, {"p0": "B"})
    assert e.players["p0"].coop_streak == 0
    play_round(e, {"p0": "C"})
    play_round(e, {"p0": None})  # a random C does not count
    assert e.players["p0"].coop_streak == 0


def test_kick_and_reinstate():
    e = engine(3)
    assert e.kick("p2")
    assert e.players["p2"].state == DROPPED
    assert not e.kick("p2")
    r = e.open_round()
    assert r.sit_out is None and r.match_of("p2") is None
    assert e.reinstate("p2")
    assert e.players["p2"].state == WAITING
    assert not e.reinstate("p2")


def test_reset_scores_keeps_the_pool():
    e = engine(3)
    for _ in range(4):
        play_round(e)
    e.reset_scores()
    assert e.round_number == 0 and e.round is None and e.rows == [] and e.meetings == {}
    assert set(e.players) == {"p0", "p1", "p2"}
    for p in e.players.values():
        assert p.points == 0 and p.rounds_played == 0 and p.sit_outs == 0
        assert p.state == ACTIVE
    assert e.open_round().number == 1


def test_fewer_than_two_players_idles():
    e = engine(1)
    assert e.open_round() is None
    assert e.phase == IDLE
    assert e.round_number == 0


def test_leaderboard_order_and_snapshot():
    e = engine(3)
    play_round(e, {"p0": "B", "p1": "C", "p2": "C"})
    board = e.leaderboard()
    assert [row["rank"] for row in board] == [1, 2, 3]
    assert board[0]["points"] >= board[1]["points"] >= board[2]["points"]
    e.kick("p0")
    assert e.leaderboard()[-1]["id"] == "p0"  # dropped go last, score kept
    s = e.snapshot()
    assert s["phase"] == IDLE and s["round"] == 1 and len(s["players"]) == 3
    r = e.open_round()
    assert e.snapshot()["phase"] == OPEN
    e.move("p1", "C")
    m = e.snapshot()["matches"][0]
    assert m["locked"]["p1"] is True
    assert m["moves"] == {} and m["points"] == {}  # the snapshot is public: no moves while open
    e.close_round()
    assert e.snapshot()["phase"] == REVEAL
    m = e.snapshot()["matches"][0]
    assert m["moves"]["p1"] == "C" and m["points"]["p1"] in (0, 3)
    summary = e.round_summary()
    assert summary["round"] == r.number and len(summary["standings"]) == 3
