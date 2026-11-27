# SPDX-License-Identifier: Apache-2.0
"""Open existing evaluator details in the trusted, local Health viewer."""

import argparse
import hashlib
import json
from pathlib import Path
import re

from livingproof_health.snapshots import Replay
from demo import write_viewer

FORMAT = "livingproof-evaluator-health/1"
MAX_BYTES = 16 * 1024 * 1024


def load_details(path, expected_sha256, run_id, configuration, trial_index):
    """Check original bytes before adapting one explicitly selected trial.

    The expected digest must come from the caller's trusted result. This verifies
    byte identity, not the truth of the producer's observations or hardware origin.
    """
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ValueError("Expected a lowercase SHA-256 from the trusted result")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Details exceed the local demo's 16 MiB limit")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Details SHA-256 does not match the trusted result")
    doc = json.loads(raw)
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ValueError("Unsupported Health details format")
    trials = doc.get("trials")
    if not isinstance(trials, list) or any(not isinstance(t, dict) for t in trials):
        raise ValueError("Expected a trials array")
    matches = [
        t
        for t in trials
        if isinstance(t.get("trial"), dict)
        and t["trial"].get("run_id") == run_id
        and t["trial"].get("configuration") == configuration
        and type(t["trial"].get("index")) is int
        and t["trial"]["index"] == trial_index
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one matching trial")
    selected = matches[0]
    simulator = selected.get("simulator")
    if not isinstance(simulator, dict) or simulator.get("provenance") != "simulator":
        raise ValueError("Simulator observations or provenance missing")
    rows = simulator.get("snapshots")
    if not isinstance(rows, list):
        raise ValueError("Simulator snapshots missing; absence is not an empty recording")
    if type(simulator.get("sample_count")) is not int or simulator["sample_count"] != len(rows):
        raise ValueError("Simulator sample count does not match snapshots")
    replay = Replay.from_json(json.dumps({"format": "livingproof-health/1", "snapshots": rows}))
    identity = {k: v for k, v in selected.items() if k != "simulator"}
    identity["simulator"] = {k: v for k, v in simulator.items() if k != "snapshots"}
    robot = selected.get("robot")
    robot_status = (
        robot.get("status", "Not reported") if isinstance(robot, dict) else "Not reported"
    )
    report = {
        "input": {
            "provenance": "Simulator observations; robot telemetry: " + str(robot_status),
            "details_sha256": expected_sha256,
            "identity": identity,
        },
        "limitations": (
            "Recorded simulator samples only. No interpolation, health verdict, grade, "
            "or hardware health proof. Missing robot telemetry is not healthy telemetry. "
            "Digest verifies supplied bytes against the caller's expected value, not producer authenticity."
        ),
        "observations_only": True,
    }
    return replay, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("details", type=Path)
    parser.add_argument("--sha256", required=True, help="Digest from the trusted evaluator result")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--trial-index", required=True, type=int)
    parser.add_argument(
        "--output", type=Path, required=True, help="New local HTML file; do not publish"
    )
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output already exists; choose a new file")
        replay, report = load_details(
            args.details, args.sha256, args.run_id, args.configuration, args.trial_index
        )
        write_viewer(args.output, replay, report)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot open Health details: {exc}\n")
    print(f"Open {args.output} locally. Observations only; do not publish this demo.")


if __name__ == "__main__":
    main()
