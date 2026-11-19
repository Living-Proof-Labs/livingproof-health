# SPDX-License-Identifier: Apache-2.0
"""Differential evidence, not a scenario runner or a replacement validator.

Synthetic full-resolution means all explicitly enumerated test samples, not
continuous time or a robot simulation. EVALUATE is the actual pinned package.
"""

import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path

from livingproof_evaluator_scenario import EVALUATE
import livingproof_evaluator_scenario.checks as scenario_checks
from mcap.writer import CompressionType, Writer
import pytest

from livingproof_health.assessment import assess_base_height
from livingproof_health.recording import read_mcap

FIXTURES = Path(__file__).parent / "fixtures"
PROVENANCE = json.loads((FIXTURES / "parity/provenance.json").read_text())


def scenario(observation, threshold=0.5):
    # Use the public registered evaluator, including its real parameter resolution.
    # Other frozen hallway limits satisfy its interface; only hallway-fall is compared.
    return EVALUATE["hallway-fall"](
        observation,
        {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": threshold},
        "health-differential-test",
    )


def minimum_observation(samples):
    # Input preparation only: reduce the enumerated evidence, never implement a verdict.
    time_ns, height = min(samples, key=lambda sample: sample[1])
    return {"min_base_height": {"value": height, "time": time_ns / 1_000_000_000}}


def health(tmp_path, samples, threshold=0.5):
    path = tmp_path / "synthetic-contract.mcap"
    with path.open("wb") as stream:
        writer = Writer(stream, compression=CompressionType.NONE)
        writer.start(library="health-synthetic-parity-test/1")
        writer.add_metadata(
            "provenance",
            {
                "kind": "synthetic-contract-evidence",
                "coverage": "enumerated-samples-only",
                "robot_trial": "false",
            },
        )
        schema = writer.register_schema("foxglove.PoseInFrame", "jsonschema", b'{"type":"object"}')
        channel = writer.register_channel("/base_pose", "json", schema)
        for index, (time_ns, height) in enumerate(samples):
            payload = {"frame_id": "world", "pose": {"position": {"x": 0, "y": 0, "z": height}}}
            writer.add_message(
                channel, time_ns, json.dumps(payload).encode(), time_ns, sequence=index
            )
        writer.finish()
    replay = read_mcap(path)
    assert len(list(replay)) == len(samples)  # No adapter decimation hidden in the harness.
    result = assess_base_height(replay, minimum_m=threshold, frame_id="world")
    assert result["scope"] == "recorded-samples-only"
    assert result["whole_trial_parity"] == "not-established"
    return result


def test_actual_evaluator_and_original_evidence_pins():
    package = distribution("livingproof-evaluator-scenario")
    assert package.version == "1.3.8"
    direct = json.loads(package.read_text("direct_url.json"))
    assert direct["vcs_info"]["commit_id"] == PROVENANCE["evaluator"]["commit"]
    expected = next(p for p in PROVENANCE["inspected_code"] if p["path"].endswith("checks.py"))
    assert (
        hashlib.sha256(Path(scenario_checks.__file__).read_bytes()).hexdigest()
        == expected["sha256"]
    )
    parameters = distribution("livingproof-scenario-parameters")
    assert parameters.version == "2.2.0"
    assert (
        json.loads(parameters.read_text("direct_url.json"))["vcs_info"]["commit_id"]
        == PROVENANCE["scenario_parameters"]["commit"]
    )
    for source in PROVENANCE["files"]:
        data = (FIXTURES / "parity" / source["local_path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == source["sha256"]
    runtime_requirements = distribution("livingproof-health").requires
    assert not any(
        "evaluator-scenario" in r or "scenario-parameters" in r for r in runtime_requirements
    )


@pytest.mark.parametrize(
    "heights,expected",
    [
        pytest.param([0.8, 0.49, 0.8], "FAIL", id="below"),
        pytest.param([0.8, 0.5, 0.8], "PASS", id="equal"),
        pytest.param([0.8, 0.51, 0.8], "PASS", id="above"),
        pytest.param([0.8, 0.499996, 0.8], "FAIL", id="unrounded-just-below"),
        pytest.param([0.8, 0.500004, 0.8], "PASS", id="unrounded-just-above"),
        pytest.param([0.8] * 500 + [0.49] + [0.8] * 500, "FAIL", id="brief-interior-dip"),
    ],
)
def test_equivalent_full_resolution_synthetic_samples(tmp_path, heights, expected):
    samples = [(index * 2_000_000, height) for index, height in enumerate(heights)]
    actual = health(tmp_path, samples)
    oracle = scenario(minimum_observation(samples))
    assert actual["status"] == oracle["status"] == expected
    assert actual["minimum_m"] == oracle["details"]["observed"] == min(heights)
    assert actual["time_ns"] == round(oracle["details"]["time"] * 1_000_000_000)


@pytest.mark.parametrize(
    "value", [None, "unknown", True], ids=["absent", "malformed-text", "malformed-boolean"]
)
def test_equivalent_unavailable_evidence_cannot_pass(tmp_path, value):
    observation = {} if value is None else {"min_base_height": {"value": value, "time": 0}}
    assert scenario(observation)["status"] == "INSUFFICIENT_EVIDENCE"
    assert health(tmp_path, [(0, value), (2_000_000, value)])["status"] == "INSUFFICIENT_EVIDENCE"


def test_empty_mcap_is_an_input_error_not_a_pass(tmp_path):
    assert scenario({})["status"] == "INSUFFICIENT_EVIDENCE"
    with pytest.raises(ValueError, match="No pose messages"):
        health(tmp_path, [])


@pytest.mark.parametrize(
    "height,oracle_status,health_status",
    [
        pytest.param(0.8, "PASS", "INSUFFICIENT_EVIDENCE", id="above"),
        pytest.param(0.5, "PASS", "INSUFFICIENT_EVIDENCE", id="equal"),
        pytest.param(0.4, "FAIL", "FAIL", id="observed-violation"),
    ],
)
def test_single_instant_does_not_establish_coverage(tmp_path, height, oracle_status, health_status):
    # The oracle trusts a supplied minimum summary; it does not certify its coverage.
    samples = [(0, height)]
    assert scenario(minimum_observation(samples))["status"] == oracle_status
    assert health(tmp_path, samples)["status"] == health_status


def test_expected_disagreement_when_sampling_loses_a_dip(tmp_path):
    full = [(i * 2_000_000, 0.49 if i == 5 else 0.8) for i in range(21)]
    assert scenario(minimum_observation(full))["status"] == "FAIL"
    assert health(tmp_path, full)["status"] == "FAIL"
    sampled = full[::10]  # 20 ms period; the 10 ms dip is absent.
    assert health(tmp_path, sampled)["status"] == "PASS"


def test_expected_disagreement_when_mcap_rounding_loses_precision(tmp_path):
    full = [(0, 0.8), (2_000_000, 0.499996), (4_000_000, 0.8)]
    assert scenario(minimum_observation(full))["status"] == "FAIL"
    assert health(tmp_path, full)["status"] == "FAIL"
    rounded = [(time, round(height, 5)) for time, height in full]
    assert health(tmp_path, rounded)["status"] == "PASS"


def test_expected_disagreement_between_four_and_five_decimal_evidence(tmp_path):
    full = [(0, 0.8), (20_000_000, 0.499991), (40_000_000, 0.8)]
    summary = minimum_observation(full)
    summary["min_base_height"]["value"] = round(summary["min_base_height"]["value"], 4)
    assert scenario(summary)["status"] == "PASS"
    assert health(tmp_path, [(t, round(z, 5)) for t, z in full])["status"] == "FAIL"


@pytest.mark.parametrize(
    "minimum",
    [None, {"value": 0.8}, {"value": 0.8, "time": "unknown"}],
    ids=["absent-summary", "absent-time", "malformed-time"],
)
def test_expected_disagreement_when_summary_is_missing_or_malformed(tmp_path, minimum):
    assert scenario({"min_base_height": minimum})["status"] == "INSUFFICIENT_EVIDENCE"
    assert health(tmp_path, [(0, 0.8), (20_000_000, 0.8)])["status"] == "PASS"


def test_expected_disagreement_when_recording_has_unavailable_sample(tmp_path):
    summary = minimum_observation([(0, 0.8), (20_000_000, 0.8), (40_000_000, 0.8)])
    assert scenario(summary)["status"] == "PASS"
    assert (
        health(tmp_path, [(0, 0.8), (20_000_000, None), (40_000_000, 0.8)])["status"]
        == "INSUFFICIENT_EVIDENCE"
    )


@pytest.mark.parametrize(
    "threshold,expected",
    [(0.5, "PASS"), (0.7464, "PASS"), (0.75, "FAIL")],
    ids=["recorded-threshold", "equality", "below"],
)
def test_original_saved_summary_vs_derived_trace_not_original_mcap(threshold, expected):
    original = json.loads((FIXTURES / "parity/original-trial-01.json").read_text())
    manifest = json.loads((FIXTURES / "parity/original-run-manifest.json").read_text())
    assert manifest["parameters"]["fall_height"] == 0.5
    trace = json.loads((FIXTURES / "simulation-trace.json").read_text())
    assert trace["samples"] == [sample[:4] for sample in original["trace"]["samples"]]
    # This MCAP is re-encoded from those rounded samples, NOT an original recorder file.
    replay = read_mcap(FIXTURES / "simulation-pose.mcap")
    oracle = scenario(original, threshold)
    actual = assess_base_height(replay, minimum_m=threshold, frame_id="world")
    assert oracle["status"] == actual["status"] == expected
    assert actual["minimum_m"] == oracle["details"]["observed"] == 0.7464
    assert actual["time_ns"] == round(oracle["details"]["time"] * 1_000_000_000) == 4_440_000_000
