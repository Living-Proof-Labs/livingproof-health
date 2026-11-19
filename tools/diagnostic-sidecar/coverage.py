# SPDX-License-Identifier: Apache-2.0
"""Evidence checks only. No scenario verdict or producer behavior lives here."""

import math


def gaps(sidecar):
    rows = sidecar["rows"]
    if not rows:
        return ["no callbacks"]
    problems = []
    dt = sidecar["timestep_s"]
    if rows[0]["index"] != 0 or rows[0]["time_s"] != 0:
        problems.append("missing initial state")
    for previous, current in zip(rows, rows[1:]):
        if current["index"] != previous["index"] + 1 or not math.isclose(
            current["time_s"] - previous["time_s"], dt, rel_tol=0, abs_tol=1e-12
        ):
            problems.append("callback cadence gap")
            break
    if rows[-1]["time_s"] != sidecar["final_time_s"]:
        problems.append("missing terminal state")
    if any(row["time_ns"] != str(round(row["time_s"] * 1e9)) for row in rows):
        problems.append("timestamp mismatch")
    if any(not math.isfinite(row[key]) for row in rows for key in ("raw_z", "fresh_z")):
        problems.append("nonfinite position")
    if any(row["raw_z"] != row["fresh_z"] for row in rows):
        problems.append("raw position stale at callback time")
    return problems
