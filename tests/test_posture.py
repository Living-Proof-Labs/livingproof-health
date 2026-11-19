# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import runpy

import pytest
from click.testing import CliRunner
from mcap.writer import CompressionType, Writer

from livingproof_health.assessment import assess_base_height
from livingproof_health.cli import health
from livingproof_health.recording import BasePoseAdapter, read_mcap
from livingproof_health.snapshots import Replay

FIXTURES = Path(__file__).parent / "fixtures"


def pose(z, frame="world"):
    return {"frame_id": frame, "pose": {"position": {"x": 0, "y": 0, "z": z}}}


def series(values):
    adapter = BasePoseAdapter()
    return Replay(adapter.observe(i * 20_000_000, pose(z)) for i, z in enumerate(values))


def assess(values, threshold=0.5):
    return assess_base_height(series(values), minimum_m=threshold, frame_id="world")


@pytest.mark.parametrize(
    "values,status,minimum",
    [
        ([0.49, 0.8], "FAIL", 0.49),
        ([0.5, 0.8], "PASS", 0.5),
        ([0.51, 0.8], "PASS", 0.51),
        ([None, None], "INSUFFICIENT_EVIDENCE", None),
        ([0.8, None, 0.8], "INSUFFICIENT_EVIDENCE", 0.8),
        ([0.8] * 500 + [0.49] + [0.8] * 500, "FAIL", 0.49),
        ([0.8], "INSUFFICIENT_EVIDENCE", 0.8),
        ([], "INSUFFICIENT_EVIDENCE", None),
        ([None, 0.49], "FAIL", 0.49),
    ],
)
def test_hallway_threshold_and_whole_recording_cases(values, status, minimum):
    result = assess(values)
    assert result["status"] == status
    assert result["minimum_m"] == minimum
    assert result["scope"] == "recorded-samples-only"
    assert result["whole_trial_parity"] == "not-established"
    if len(values) == 1001:
        assert result["time_ns"] == 10_000_000_000


def test_scenario_controls_verdict_observation_has_no_verdict():
    observations = series([0.5, 0.8])
    assert assess_base_height(observations, minimum_m=0.5, frame_id="world")["status"] == "PASS"
    assert assess_base_height(observations, minimum_m=0.6, frame_id="world")["status"] == "FAIL"
    assert (
        assess_base_height(observations, minimum_m=0.1, frame_id="map")["status"]
        == "INSUFFICIENT_EVIDENCE"
    )
    assert "status" not in observations.to_json()
    assert (
        assess_base_height(
            Replay([{"time_ns": 0}, {"time_ns": 1}]), minimum_m=0.5, frame_id="world"
        )["status"]
        == "INSUFFICIENT_EVIDENCE"
    )


@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf"), "0.5"])
def test_invalid_threshold(value):
    with pytest.raises(ValueError):
        assess([0.8, 0.9], value)


@pytest.mark.parametrize("payload", [{}, pose(None), pose(True), pose(float("nan")), pose(1, "")])
def test_unavailable_pose_is_explicit(payload):
    assert BasePoseAdapter().observe(0, payload)["items"] == {"base_pose": None}


def test_duplicate_instants_do_not_prove_trial():
    s = BasePoseAdapter().observe(0, pose(0.8))
    assert (
        assess_base_height(Replay([s, s]), minimum_m=0.5, frame_id="world")["status"]
        == "INSUFFICIENT_EVIDENCE"
    )


def test_simulation_fixture_reproduces_and_preserves_every_position(tmp_path):
    build = runpy.run_path(str(FIXTURES.parents[1] / "tools" / "build_pose_fixture.py"))["build"]
    generated = tmp_path / "pose.mcap"
    build(generated)
    assert generated.read_bytes() == (FIXTURES / "simulation-pose.mcap").read_bytes()
    trace = json.loads((FIXTURES / "simulation-trace.json").read_text())["samples"]
    replay = read_mcap(generated)
    assert len(list(replay)) == len(trace)
    for sample, (time, x, y, z) in zip(replay, trace, strict=True):
        assert sample["time_ns"] == round(time * 1_000_000_000)
        assert sample["items"]["base_pose"]["position"] == {"x": x, "y": y, "z": z}
        assert "orientation" not in sample["items"]["base_pose"]
    result = assess_base_height(replay, minimum_m=0.75, frame_id="world")
    assert result["status"] == "FAIL"
    assert result["minimum_m"] == 0.7464
    assert result["time_ns"] == 4_440_000_000


def write_recording(path, messages, *, encoding="json", schema_name="foxglove.PoseInFrame"):
    with path.open("wb") as stream:
        writer = Writer(stream, compression=CompressionType.NONE)
        writer.start()
        schema = writer.register_schema(schema_name, "jsonschema", b"{}")
        channel = writer.register_channel("/base_pose", encoding, schema)
        for time, data in messages:
            writer.add_message(channel, time, data, time)
        writer.finish()


def test_mcap_out_of_order_and_duplicates_are_not_decimated(tmp_path):
    path = tmp_path / "test.mcap"
    write_recording(
        path,
        [
            (10, json.dumps(pose(1)).encode()),
            (0, json.dumps(pose(0.4)).encode()),
            (0, json.dumps(pose(0.7)).encode()),
        ],
    )
    replay = read_mcap(path)
    assert [s["time_ns"] for s in replay] == [0, 0, 10]
    assert replay.seek(0)["items"]["base_pose"]["position"]["z"] == 0.4
    assert assess_base_height(replay, minimum_m=0.5, frame_id="world")["status"] == "FAIL"


@pytest.mark.parametrize(
    "messages,options",
    [
        ([], {}),
        ([(0, b"{")], {}),
        ([(0, b"[]")], {}),
        ([(0, b"{}")], {"encoding": "protobuf"}),
        ([(0, b"{}")], {"schema_name": "other"}),
    ],
)
def test_malformed_or_unsupported_mcap_fails_cleanly(tmp_path, messages, options):
    path = tmp_path / "bad.mcap"
    write_recording(path, messages, **options)
    result = CliRunner().invoke(health, ["replay", str(path)])
    assert result.exit_code == 1
    assert "See 'replay --help'" in result.output
    assert "Traceback" not in result.output


def test_cli_end_to_end_and_invalid_input(tmp_path):
    runner = CliRunner()
    converted = runner.invoke(health, ["replay", str(FIXTURES / "simulation-pose.mcap")])
    assert converted.exit_code == 0, converted.output
    path = tmp_path / "health.json"
    path.write_text(converted.output)
    found = runner.invoke(health, ["seek", str(path), "--time-ns", "4440000000"])
    assert json.loads(found.output)["items"]["base_pose"]["position"]["z"] == 0.7464
    for threshold, code, status in [(0.75, 1, "FAIL"), (0.7464, 0, "PASS"), (0.7, 0, "PASS")]:
        result = runner.invoke(
            health, ["assess", str(path), "--minimum-m", str(threshold), "--frame-id", "world"]
        )
        assert result.exit_code == code
        assert json.loads(result.output)["status"] == status
    path.write_text(series([None, None]).to_json())
    assert (
        runner.invoke(
            health, ["assess", str(path), "--minimum-m", "0.5", "--frame-id", "world"]
        ).exit_code
        == 2
    )
    path.write_text("[]")
    result = runner.invoke(health, ["seek", str(path), "--time-ns", "0"])
    assert result.exit_code != 0
    assert "Expected health JSON" in result.output


@pytest.mark.parametrize("size", [0, 1, 7, 8, 20, 50])
def test_truncated_mcap_fails_cleanly(tmp_path, size):
    path = tmp_path / "truncated.mcap"
    path.write_bytes((FIXTURES / "simulation-pose.mcap").read_bytes()[:size])
    result = CliRunner().invoke(health, ["replay", str(path)])
    assert result.exit_code == 1
    assert "Cannot read pose recording" in result.output
    assert "replay --help" in result.output
