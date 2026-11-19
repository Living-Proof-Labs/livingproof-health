# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from livingproof_health.snapshots import Replay, snapshot


def test_time_only_and_arbitrary_robot_items_round_trip():
    samples = [
        {"time_ns": 0},
        {"time_ns": 1, "items": {"tentacle/load": {"unit": "N", "value": 7}, "camera": None}},
        {"time_ns": 2, "robot": "unspecified-shape", "items": {}},
    ]
    replay = Replay(samples)
    assert list(Replay.from_json(replay.to_json())) == samples
    assert "items" not in list(replay)[0]
    assert list(replay)[1]["items"]["camera"] is None


def test_replay_seek_stable_duplicates_and_large_nanosecond_times():
    t = 1_800_000_000_000_000_001
    samples = [{"time_ns": t + 2}, {"time_ns": t, "items": {"a": 1}}, {"time_ns": t}]
    replay = Replay(samples)
    assert list(replay) == [samples[1], samples[2], samples[0]]
    assert replay.seek(t) == samples[1]
    assert replay.seek(0) == samples[1]
    assert replay.seek(t + 1) == samples[0]
    assert replay.seek(t + 3) is None
    assert Replay([]).seek(0) is None
    replay.seek(t)["items"]["a"] = 2
    samples[1]["items"]["a"] = 3
    assert replay.seek(t)["items"]["a"] == 1
    assert Replay.from_json(replay.to_json()).to_json() == replay.to_json()


@pytest.mark.parametrize(
    "value",
    [
        {},
        [],
        {"time_ns": -1},
        {"time_ns": True},
        {"time_ns": 1.0},
        {"time_ns": 0, "items": []},
        {"time_ns": 0, "items": {"x": float("nan")}},
        {"time_ns": 0, "items": {"x": float("inf")}},
        {"time_ns": 0, "items": {1: "x"}},
        {"time_ns": 0, "items": {"x": (1, 2)}},
    ],
)
def test_snapshot_rejects_invalid_contract(value):
    with pytest.raises(ValueError):
        snapshot(value)


@pytest.mark.parametrize(
    "doc",
    [
        {},
        [],
        {"format": "unknown", "snapshots": []},
        {"format": "livingproof-health/1", "snapshots": {}},
    ],
)
def test_portable_format_is_validated(doc):
    with pytest.raises(ValueError):
        Replay.from_json(json.dumps(doc))
