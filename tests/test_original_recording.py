# SPDX-License-Identifier: Apache-2.0
"""Original producer bytes, not an MCAP constructed from a saved trace."""

import hashlib
import json
from pathlib import Path

from click.testing import CliRunner
from livingproof_evaluator_scenario import EVALUATE
from mcap.reader import make_reader

from livingproof_health.assessment import assess_base_height
from livingproof_health.cli import health
from livingproof_health.recording import read_mcap
from livingproof_health.snapshots import Replay

ROOT = Path(__file__).parent / "fixtures/original-recording"
MCAP = ROOT / "media/mcap/trial-01.mcap"


def document(path):
    return json.loads((ROOT / path).read_text())


def test_original_bytes_and_producer_pairing():
    provenance = document("provenance.json")
    for name, expected in provenance["files"].items():
        data = (ROOT / name).read_bytes()
        assert len(data) == expected["bytes"], name
        assert hashlib.sha256(data).hexdigest() == expected["sha256"], name
    manifest = document("evidence/manifest.json")
    run = document("evidence/run-manifest.json")
    media = document("media/media.json")
    assert manifest["run_id"] == run["run_id"] == media["run_id"] == provenance["run_id"]
    assert run["simulator"]["adapter_commit"] == provenance["producer"]["commit"]
    assert run["robot"]["commit"] == provenance["robot"]["commit"]
    assert manifest["lock"]["content"] == document("corner.lock.json")
    assert (
        manifest["lock"]["sha256"]
        == hashlib.sha256((ROOT / "corner.lock.json").read_bytes()).hexdigest()
    )
    (trial,) = manifest["trials"]["results"]
    (recording,) = media["trials"]
    digest = hashlib.sha256((ROOT / "evidence/trials/trial-01.json").read_bytes()).hexdigest()
    assert trial["sha256"] == recording["observation_sha256"] == digest
    assert digest == provenance["generation"]["observation_matches_previous_fixture_sha256"]
    assert recording["mcap"]["sha256"] == hashlib.sha256(MCAP.read_bytes()).hexdigest()
    assert recording["mcap"]["bytes"] == MCAP.stat().st_size == 214645
    assert (ROOT / "media" / recording["mcap"]["path"]) == MCAP
    assert provenance["generation"]["evidence_exit"] == provenance["generation"]["media_exit"] == 0
    assert (
        "1 MCAP recordings (214645 B), all matching their evidence"
        in (ROOT / "generation.log").read_text()
    )


def test_original_channels_and_recorded_interval():
    with MCAP.open("rb") as stream:
        reader = make_reader(stream, validate_crcs=True)
        assert reader.get_header().library == "livingproof_sim_mujoco.media"
        records = list(reader.iter_messages())
    poses = [message for _, channel, message in records if channel.topic == "/base_pose"]
    joints = [message for _, channel, message in records if channel.topic == "/joint_states"]
    assert len(poses) == len(joints) == 614
    times = [message.log_time for message in poses]
    assert times == list(range(0, 12_260_000_000 + 1, 20_000_000))
    assert times == [message.publish_time for message in poses]
    assert document("evidence/trials/trial-01.json")["duration_s"] == 12.26
    assert document("evidence/trials/trial-01.json")["end"] == "crossed_exit"
    for message in poses:
        payload = json.loads(message.data)
        assert (
            payload["timestamp"]["sec"] * 1_000_000_000 + payload["timestamp"]["nsec"]
            == message.log_time
        )
        assert payload["frame_id"] == "world"
        assert set(payload["pose"]["orientation"]) == {"x", "y", "z", "w"}


def test_original_recording_and_actual_evaluator_at_unchanged_threshold():
    run = document("evidence/run-manifest.json")
    limits = run["parameters"]
    assert limits["fall_height"] == 0.5  # Use the recorded policy, not a fitted threshold.
    oracle = EVALUATE["hallway-fall"](
        document("evidence/trials/trial-01.json"),
        {
            "fall_height": limits["fall_height"],
            "time_limit": limits["time_limit"],
            "lateral_limit": limits["lateral_limit"],
            "half_width": 0.75,
        },
        run["run_id"],
    )
    actual = assess_base_height(read_mcap(MCAP), minimum_m=limits["fall_height"], frame_id="world")
    assert oracle["status"] == actual["status"] == "PASS"
    assert actual["minimum_m"] == 0.74637
    assert oracle["details"]["observed"] == 0.7464
    assert (
        actual["minimum_m"] != oracle["details"]["observed"]
    )  # Preserve genuine precision difference.
    assert actual["time_ns"] == round(oracle["details"]["time"] * 1_000_000_000) == 4_440_000_000
    assert actual["sample_count"] == 614 and actual["unavailable_count"] == 0
    assert actual["scope"] == "recorded-samples-only"
    assert actual["whole_trial_parity"] == "not-established"


def test_original_recording_cli_and_lossless_seek(tmp_path):
    runner = CliRunner()
    result = runner.invoke(health, ["replay", str(MCAP)])
    assert result.exit_code == 0, result.output
    portable = tmp_path / "original.json"
    portable.write_text(result.output)
    replay = Replay.from_json(result.output)
    assert replay.seek(4_440_000_000)["items"]["base_pose"]["position"]["z"] == 0.74637
    result = runner.invoke(health, ["seek", str(portable), "--time-ns", "4440000000"])
    assert result.exit_code == 0, result.output
    wire = json.loads(result.output)
    assert wire["time_ns"] == wire["source"]["publish_time_ns"] == "4440000000"
    assert wire["source"]["sha256"] == hashlib.sha256(MCAP.read_bytes()).hexdigest()
    result = runner.invoke(
        health, ["assess", str(portable), "--minimum-m", "0.5", "--frame-id", "world"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["minimum_m"] == 0.74637
