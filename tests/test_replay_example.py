# SPDX-License-Identifier: Apache-2.0
"""Exercise the development example via installed host-plugin subprocesses."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "replay_example", ROOT / "examples/recorded-replay/demo.py"
)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_genuine_example_repeatable_and_seekable(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    report = demo.demonstrate(demo.MCAP, first)
    demo.demonstrate(demo.MCAP, second)
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()
    }
    assert report["health"]["status"] == report["scenario_from_replay_summary"]["status"] == "PASS"
    assert report["scenario_from_original_summary"]["status"] == "PASS"
    assert report["health"]["minimum_m"] == 0.74637
    assert report["original_summary"]["value"] == 0.7464
    assert report["interval"] == {
        "count": 614,
        "start_ns": "0",
        "end_ns": "12260000000",
        "sample_intervals_ns": ["20000000"],
    }
    assert report["whole_trial_parity"] == "not-established"
    exact = json.loads((first / "seek-4440000000.json").read_text())
    assert exact["time_ns"] == "4440000000"
    assert exact["items"]["base_pose"]["position"]["z"] == 0.74637
    assert json.loads((first / "seek-4440000001.json").read_text())["time_ns"] == "4460000000"
    assert json.loads((first / "seek-12260000001.json").read_text()) is None
    with pytest.raises(ValueError, match="already exists"):
        demo.demonstrate(demo.MCAP, first)


@pytest.mark.parametrize(
    "minimum,health,saved",
    [(0.74637, "PASS", "PASS"), (0.74638, "FAIL", "PASS"), (0.75, "FAIL", "FAIL")],
)
def test_example_threshold_boundaries_preserve_disagreement(tmp_path, minimum, health, saved):
    report = demo.demonstrate(demo.MCAP, tmp_path / "result", minimum)
    assert report["health"]["status"] == report["scenario_from_replay_summary"]["status"] == health
    assert report["scenario_from_original_summary"]["status"] == saved


@pytest.mark.parametrize("items", [None, {}, {"base_pose": None}])
def test_time_only_or_missing_posture_cannot_pass(tmp_path, items):
    source = tmp_path / "source.json"
    rows = [{"time_ns": str(t)} for t in [0, 20_000_000]]
    if items is not None:
        for row in rows:
            row["items"] = items
    source.write_text(json.dumps({"format": "livingproof-health/1", "snapshots": rows}))
    report = demo.demonstrate(source, tmp_path / "result", portable=True)
    assert (
        report["health"]["status"]
        == report["scenario_from_replay_summary"]["status"]
        == "INSUFFICIENT_EVIDENCE"
    )
    assert report["scenario_from_original_summary"] is None
    assert json.loads((tmp_path / "result/replay-summary.json").read_text()) == {}


def test_wrong_frame_cannot_pass(tmp_path):
    report = demo.demonstrate(demo.MCAP, tmp_path / "result", frame="unreported-frame")
    assert (
        report["health"]["status"]
        == report["scenario_from_replay_summary"]["status"]
        == "INSUFFICIENT_EVIDENCE"
    )
    assert report["scenario_from_original_summary"] is None


@pytest.mark.parametrize("portable", [True, False])
def test_malformed_input_publishes_no_report(tmp_path, portable):
    source = tmp_path / "bad"
    source.write_bytes(b"not JSON or MCAP")
    target = tmp_path / "result"
    with pytest.raises(ValueError):
        demo.demonstrate(source, target, portable=portable)
    assert not target.exists()


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CompletedProcess([], 1, '{"status":"PASS"}', "failed"),
        subprocess.CompletedProcess([], 0, "malformed", ""),
        subprocess.CompletedProcess([], 0, '{"status":"UNKNOWN"}', ""),
    ],
)
def test_command_failures_cannot_be_results(monkeypatch, result):
    monkeypatch.setattr(demo.subprocess, "run", lambda *a, **kw: result)
    with pytest.raises(ValueError):
        demo.command("assess", assessment=True)


def test_missing_command_publishes_no_report(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("livingproof unavailable")

    monkeypatch.setattr(demo.subprocess, "run", missing)
    target = tmp_path / "result"
    with pytest.raises(FileNotFoundError):
        demo.demonstrate(demo.MCAP, target)
    assert not target.exists()


def test_partial_evidence_does_not_become_minimum_only_pass(tmp_path):
    from livingproof_health.snapshots import Replay

    source = tmp_path / "partial.json"
    source.write_text(
        Replay(
            [
                {
                    "time_ns": 0,
                    "items": {
                        "base_pose": {"position": {"z": 0.4}, "unit": "m", "frame_id": "world"}
                    },
                },
                {"time_ns": 20_000_000},
            ]
        ).to_json()
    )
    report = demo.demonstrate(source, tmp_path / "result", portable=True)
    assert report["health"]["status"] == "FAIL"
    assert report["scenario_from_replay_summary"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_late_seek_failure_publishes_no_report(tmp_path, monkeypatch):
    original = demo.command

    def fail_seek(*args, **kwargs):
        if args[0] == "seek":
            raise ValueError("seek command failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(demo, "command", fail_seek)
    target = tmp_path / "result"
    with pytest.raises(ValueError, match="seek command failed"):
        demo.demonstrate(demo.MCAP, target)
    assert not target.exists()
