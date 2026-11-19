# SPDX-License-Identifier: Apache-2.0
"""Diagnostic consumer of the unchanged producer hook; run in its pinned container."""

import copy
import gzip
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
from livingproof_sim_mujoco import evidence as ev

ROOT = Path("/health/tests/fixtures/original-recording")
OUT = Path("/output")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def state(data):
    # Every exposed ndarray, plus scalar time: includes integration and derived state.
    return (
        data.time,
        {
            k: getattr(data, k).tobytes()
            for k in dir(data)
            if isinstance(getattr(data, k), np.ndarray)
        },
    )


class Diagnostic:
    def __init__(self, model, body):
        self.model = copy.copy(model)
        for name in dir(model):
            a, b = getattr(model, name), getattr(self.model, name)
            if isinstance(a, np.ndarray):
                assert not np.shares_memory(a, b), name
        self.body = model.body(body).id
        self.rows = []
        self.dt = model.opt.timestep
        self.live = None

    def __call__(self, index, data):
        before = state(data)
        isolated = copy.copy(data)
        for name in dir(data):
            a, b = getattr(data, name), getattr(isolated, name)
            if isinstance(a, np.ndarray):
                assert not np.shares_memory(a, b), name
        # Position-only freshness diagnostic. Never forward/step the producer data.
        mujoco.mj_kinematics(self.model, isolated)
        assert before == state(data)
        self.rows.append(
            {
                "index": index,
                "time_s": float(data.time),
                "time_ns": str(round(data.time * 1e9)),
                "raw_z": float(data.xpos[self.body, 2]),
                "fresh_z": float(isolated.xpos[self.body, 2]),
            }
        )
        self.live = data

    def close(self):
        self.final_time = float(self.live.time)


ref = "lpl_g1.adapter:ROBOT"
robot = ev.adapter(ref)
plan, prepared = ev.recording(robot, json.loads((ROOT / "corner.lock.json").read_text()), "stock")
geometry = ev.sc.route_geometry(prepared.world, prepared.document)
route, exit_place = geometry if geometry else (None, None)
kwargs = dict(
    start_offset=ev.declared_offset(plan),
    command=prepared.command,
    route=route,
    exit_place=exit_place,
    places=ev.sc.scenario_places(prepared.world, prepared.document)
    if prepared.command is None
    else None,
)
args = (ref, "stock", plan, prepared.recorded, prepared.world)
baseline = ev.run_trial(*args, **kwargs)
hooks = []


def factory(model, body):
    hook = Diagnostic(model, body)
    hooks.append(hook)
    return hook


observed = ev.run_trial(*args, on_step=factory, **kwargs)
expected = (ROOT / "evidence/trials/trial-01.json").read_bytes()
assert ev.observation_bytes(baseline) == ev.observation_bytes(observed) == expected
hook = hooks[0]
result = {
    "schema": "health-diagnostic-sidecar-v1",
    "timestep_s": hook.dt,
    "final_time_s": hook.final_time,
    "end": observed["end"],
    "observation_sha256": digest(expected),
    "mcap_sha256": digest((ROOT / "media/mcap/trial-01.mcap").read_bytes()),
    "isolation": "copy.copy model/data; no shared data arrays; all exposed live arrays and time unchanged at every callback",
    "rows": hook.rows,
}
encoded = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
(OUT / "sidecar.json.gz").write_bytes(gzip.compress(encoded, mtime=0))
print(json.dumps({k: v for k, v in result.items() if k != "rows"}))
print("callbacks", len(hook.rows), "sha256", digest((OUT / "sidecar.json.gz").read_bytes()))
