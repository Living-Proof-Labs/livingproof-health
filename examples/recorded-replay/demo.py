# SPDX-License-Identifier: Apache-2.0
"""Bounded development example, not a general binding runner or production grade."""

import argparse
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from livingproof_evaluator_scenario import EVALUATE
from livingproof_health.snapshots import Replay

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/original-recording"
MCAP = FIXTURE / "media/mcap/trial-01.mcap"
LIMIT = (
    "Recorded samples only; no whole-trial parity. The original recorder samples at 50 Hz "
    "and rounds positions to five decimals; the original summary uses four. "
    "Physics states between samples, a measured 2 ms raw-position lag, and terminal "
    "coverage limits remain. Simulation evidence only, not hardware health or safety certification."
)


def command(*args, assessment=False):
    result = subprocess.run(
        ["livingproof", "capability", "health", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if not assessment and result.returncode != 0:
        raise ValueError(
            f"Health command {args[0]} failed ({result.returncode}): {result.stderr.strip()}"
        )
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError(
            f"Health command {args[0]} did not return JSON: {result.stderr.strip()}"
        ) from exc
    if assessment:
        expected = {"PASS": 0, "FAIL": 1, "INSUFFICIENT_EVIDENCE": 2}
        if not isinstance(payload, dict) or payload.get("status") not in expected:
            raise ValueError("Health assessment did not return a recognized result")
        if result.returncode != expected[payload["status"]]:
            raise ValueError("Health assessment command exit disagrees with its result")
    return payload


def evaluator(observation, minimum):
    # Frozen non-height parameters satisfy the actual evaluator interface.
    return EVALUATE["hallway-fall"](
        observation,
        {"time_limit": 27.0, "lateral_limit": 0.49, "half_width": 0.75, "fall_height": minimum},
        "health-development-example",
    )


def summary_bridge(assessment):
    """Example-only bridge. Never turn incomplete evidence into a minimum-only PASS."""
    if (
        assessment["unavailable_count"]
        or assessment["sample_count"] < 2
        or assessment["time_ns"] is None
    ):
        return {}
    if assessment["status"] == "INSUFFICIENT_EVIDENCE":
        return {}
    return {
        "min_base_height": {
            "value": assessment["minimum_m"],
            "time": int(assessment["time_ns"]) / 1_000_000_000,
        }
    }


def write_viewer(path, replay, report):
    """Single local artifact; robot text is JSON data, never executable markup."""
    directory = Path(__file__).parent
    payload = json.dumps(
        {"replay": json.loads(replay.to_json()), "report": report}, allow_nan=False
    )
    # Protect the HTML raw-text script boundary, including hostile </script> text.
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = (directory / "viewer.html").read_text()
    template = template.replace("__PRESENTATION__", (directory / "presentation.js").read_text())
    path.write_text(template.replace("__DATA__", payload))


def describe_summary(summary):
    if not summary:
        return "Unavailable"
    return f"{summary['value']} m at {summary['time']} s"


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")


def demonstrate(source, output, minimum=0.5, frame="world", portable=False):
    if not math.isfinite(minimum):
        raise ValueError("minimum must be finite")
    if output.exists():
        raise ValueError("Output already exists; choose a new directory to avoid stale reports")
    original = not portable and source.resolve() == MCAP.resolve()
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if original:
        manifest = json.loads((FIXTURE / "media/media.json").read_text())
        if source_digest != manifest["trials"][0]["mcap"]["sha256"]:
            raise ValueError("Genuine fixture digest does not match its producer media manifest")
        observation_digest = hashlib.sha256(
            (FIXTURE / "evidence/trials/trial-01.json").read_bytes()
        ).hexdigest()
        if observation_digest != manifest["trials"][0]["observation_sha256"]:
            raise ValueError("Original summary does not match the paired observation hash")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".replay-demo-", dir=output.parent))
    try:
        wire = json.loads(source.read_text()) if portable else command("replay", source)
        replay = Replay.from_json(json.dumps(wire))
        replay_path = staging / "replay.json"
        replay_path.write_text(replay.to_json())
        health = command(
            "assess", replay_path, "--minimum-m", minimum, "--frame-id", frame, assessment=True
        )
        bridge = summary_bridge(health)
        derived = evaluator(bridge, minimum)
        write_json(staging / "replay-summary.json", bridge)
        seek_results = {}
        for when in ["4440000000", "4440000001", "12260000001"]:
            seek_results[when] = command("seek", replay_path, "--time-ns", when)
            write_json(staging / f"seek-{when}.json", seek_results[when])
        saved = (
            json.loads((FIXTURE / "evidence/trials/trial-01.json").read_text())
            if original
            else None
        )
        # Saved summary has world-frame semantics; do not compare it in another frame.
        saved_result = evaluator(saved, minimum) if saved is not None and frame == "world" else None
        times = [row["time_ns"] for row in replay]
        intervals = sorted({b - a for a, b in zip(times, times[1:])})
        report = {
            "kind": "development-example-comparison",
            "development_tools": {
                "livingproof": version("livingproof"),
                "scenario_evaluator": version("livingproof-evaluator-scenario"),
            },
            "whole_trial_parity": "not-established",
            "input": {
                "sha256": source_digest,
                "kind": "portable-json" if portable else "mcap",
                "provenance": "genuine pinned G1 simulation recording"
                if original
                else "user-supplied; not authenticated",
                "run_id": manifest["run_id"] if original else None,
                "source_pins": {
                    k: json.loads((FIXTURE / "provenance.json").read_text())[k]
                    for k in ("producer", "robot")
                }
                if original
                else None,
                "original_observation_sha256": observation_digest if original else None,
            },
            "expectation": {"minimum_m": minimum, "frame_id": frame},
            "interval": {
                "count": len(times),
                "start_ns": str(times[0]) if times else None,
                "end_ns": str(times[-1]) if times else None,
                "sample_intervals_ns": list(map(str, intervals)),
            },
            "health": health,
            "scenario_from_replay_summary": derived,
            "original_summary": saved["min_base_height"] if saved else None,
            "scenario_from_original_summary": saved_result,
            "bridge": "Only a complete recorded height assessment supplies a minimum summary; otherwise the evaluator receives {}.",
            "limitations": LIMIT,
        }
        write_json(staging / "comparison.json", report)
        write_viewer(staging / "viewer.html", replay, report)
        original_status = (
            saved_result["status"]
            if saved_result
            else "NOT COMPARED (no paired world-frame summary)"
        )
        original_min = saved["min_base_height"] if saved else None
        markdown = f"""# Recorded replay / scenario example

Input SHA-256: `{source_digest}`  
Provenance: {report["input"]["provenance"]}  
Expectation: base height >= **{minimum} m**, frame **{frame}**. Equality passes.

{len(times)} snapshots; interval {report["interval"]["start_ns"]}–{report["interval"]["end_ns"]} ns;
observed spacing {", ".join(report["interval"]["sample_intervals_ns"]) or "unavailable"} ns.

| Path | Result | Observed minimum and time |
| --- | --- | --- |
| Installed Health host plugin | {health["status"]} | {health["minimum_m"]} m at {health["time_ns"]} ns |
| Actual scenario evaluator, replay-derived summary | {derived["status"]} | {describe_summary(bridge.get("min_base_height"))} |
| Actual scenario evaluator, original saved summary | {original_status} | {describe_summary(original_min)} |

The original summary is retained separately, never substituted for the replay-derived summary.
The example bridge is not a general MCAP binding or a production evaluator result.
Missing required height evidence yields an empty summary for the evaluator, never an inferred PASS.

{LIMIT}

Seek artifacts: `seek-4440000000.json`, `seek-4440000001.json`, `seek-12260000001.json`.
The first snapshot at or after the requested time is returned; there is no interpolation.
See `comparison.json`, `replay.json`, and `replay-summary.json` for inspectable values.
"""
        (staging / "comparison.md").write_text(markdown)
        staging.rename(output)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=MCAP)
    parser.add_argument(
        "--portable-json", action="store_true", help="Use portable Health JSON instead of MCAP"
    )
    parser.add_argument("--output", type=Path, required=True, help="New directory for artifacts")
    parser.add_argument("--minimum-m", type=float, default=0.5)
    parser.add_argument("--frame-id", default="world")
    args = parser.parse_args()
    try:
        demonstrate(args.input, args.output, args.minimum_m, args.frame_id, args.portable_json)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Demonstration failed: {exc}\nNo comparison report was published.\n")
    print((args.output / "comparison.md").read_text())


if __name__ == "__main__":
    main()
