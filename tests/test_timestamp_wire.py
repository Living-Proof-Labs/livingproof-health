# SPDX-License-Identifier: Apache-2.0
"""Exercise actual package JSON in ordinary JavaScript, then import it in Python."""

import json
from pathlib import Path
import shutil
import subprocess

from click.testing import CliRunner
from mcap.writer import CompressionType, Writer
import pytest

from livingproof_health.assessment import assessment_to_json
from livingproof_health.cli import health
from livingproof_health.snapshots import Replay, snapshot, timestamp_from_wire

ROOT = Path(__file__).resolve().parents[1]
INVALID = [0, 1.0, True, None, "", "-1", "+1", "01", "1.0", "1e9", " 1", "1\n", "١", [], {}]


def javascript_roundtrip(payload):
    node = shutil.which("node")
    assert node, "Node.js is required for timestamp wire regressions; use task dev:verify"
    result = subprocess.run(
        [node, str(ROOT / "tests" / "timestamp_roundtrip.mjs")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def test_epoch_times_survive_actual_cli_javascript_round_trip_and_seek(tmp_path):
    t = 1_800_000_000_000_000_001
    path = tmp_path / "epoch.mcap"
    # Deliberately unsorted file order and a duplicate. The first duplicate wins seek.
    with path.open("wb") as stream:
        writer = Writer(stream, compression=CompressionType.NONE)
        writer.start()
        schema = writer.register_schema("foxglove.PoseInFrame", "jsonschema", b"{}")
        channel = writer.register_channel("/base_pose", "json", schema)
        for index, (time, height) in enumerate([(t + 2, 0.4), (t + 2, 0.6), (t, 0.8)]):
            writer.add_message(
                channel,
                time,
                json.dumps(
                    {"frame_id": "world", "pose": {"position": {"x": 0, "y": 0, "z": height}}}
                ).encode(),
                time + 7,
                sequence=index,
            )
        writer.finish()
    runner = CliRunner()
    converted = runner.invoke(health, ["replay", str(path)])
    assert converted.exit_code == 0, converted.output
    portable = tmp_path / "health.json"
    portable.write_text(converted.output)
    assessed = runner.invoke(
        health, ["assess", str(portable), "--minimum-m", "0.5", "--frame-id", "world"]
    )
    assert assessed.exit_code == 1, assessed.output
    sought = runner.invoke(health, ["seek", str(portable), "--time-ns", str(t + 2)])
    assert sought.exit_code == 0, sought.output
    queries = [0, t - 1, t, t + 1, t + 2, t + 3]
    result = javascript_roundtrip(
        {
            "replay": converted.output,
            "assessment": assessed.output,
            "sought": sought.output,
            "queries": [str(time) for time in queries],
            "invalid": INVALID,
        }
    )
    restored = Replay.from_json(json.dumps(result["replay"]))
    original = Replay.from_json(converted.output)
    assert list(restored) == list(original)
    assert [s["time_ns"] for s in restored] == [t, t + 2, t + 2]
    assert [s["source"]["publish_time_ns"] for s in restored] == [t + 7, t + 9, t + 9]
    assert result["assessment"] == json.loads(assessed.output)
    assert timestamp_from_wire(result["assessment"]["time_ns"]) == t + 2
    assert result["sought"] == json.loads(sought.output)
    assert result["sought"]["time_ns"] == str(t + 2)
    assert result["sought"]["source"]["publish_time_ns"] == str(t + 9)
    assert [s["source"]["sequence"] if s else None for s in result["selections"]] == [
        2,
        2,
        2,
        0,
        0,
        None,
    ]
    for time, selection in zip(queries, result["selections"], strict=True):
        assert selection == (
            json.loads(Replay([original.seek(time)]).to_json())["snapshots"][0]
            if original.seek(time) is not None
            else None
        )
    assert result["empty"] is None
    assert result["invalid_rejected"] == len(INVALID)


@pytest.mark.parametrize("value", INVALID)
@pytest.mark.parametrize("field", ["time_ns", "publish_time_ns"])
def test_wire_rejects_noncanonical_timestamps(value, field):
    sample = {"time_ns": "0", "source": {"publish_time_ns": "1"}}
    target = sample if field == "time_ns" else sample["source"]
    target[field] = value
    with pytest.raises(ValueError, match="canonical nonnegative decimal string"):
        Replay.from_json(json.dumps({"format": "livingproof-health/1", "snapshots": [sample]}))


@pytest.mark.parametrize("value", [-1, True, 1.5, "1", None])
def test_in_memory_source_and_assessment_reject_invalid_times(value):
    with pytest.raises(ValueError, match="nonnegative integer"):
        snapshot({"time_ns": 0, "source": {"publish_time_ns": value}})
    if value is not None:  # Assessment null explicitly means no observed minimum.
        with pytest.raises(ValueError, match="nonnegative integer"):
            assessment_to_json({"time_ns": value})


def test_missing_assessment_time_stays_null():
    assert json.loads(assessment_to_json({"time_ns": None}))["time_ns"] is None


def test_cli_explains_invalid_wire_time(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text(
        '{"format":"livingproof-health/1","snapshots":[{"time_ns":1800000000000000001}]}'
    )
    result = CliRunner().invoke(health, ["seek", str(path), "--time-ns", "0"])
    assert result.exit_code != 0
    assert "canonical nonnegative decimal string" in result.output
    assert "Traceback" not in result.output
