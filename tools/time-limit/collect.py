# SPDX-License-Identifier: Apache-2.0
"""Diagnostic consumer of the unchanged producer hook; run in its pinned container."""

import copy
import gzip
import hashlib
import json
import sys
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
        self.__call__(len(self.rows), self.live)
        self.terminal = self.rows.pop()
        self.terminal.pop("index")


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
# Public Python trial input: run_trial passes this duration to observe_route(seconds=...).
# This is a diagnostic duration, not a modified scenario lock or evaluator threshold.
parameters = {**prepared.recorded, "time_limit": 0.1}
args = (ref, "stock", plan, parameters, prepared.world)
baseline = ev.run_trial(*args, **kwargs)
hooks = []
integrations = []
pending = []


def factory(model, body):
    hook = Diagnostic(model, body)
    hooks.append(hook)
    return hook


def profile(frame, event, function):
    # Observe CPython's native-call events; no function replacement or extra stepping.
    if event in ("c_call", "c_return") and function is mujoco.mj_step2:
        data = frame.f_locals["data"]
        if event == "c_call":
            pending.append(float(data.time))
        else:
            before = pending.pop()
            integrations.append(
                {
                    "before_s": before,
                    "after_s": float(data.time),
                    "before_ns": str(round(before * 1e9)),
                    "after_ns": str(round(data.time * 1e9)),
                }
            )


assert sys.getprofile() is None
sys.setprofile(profile)
try:
    observed = ev.run_trial(*args, on_step=factory, **kwargs)
finally:
    sys.setprofile(None)
assert not pending and integrations, "native integration events were not observable"
encoded_observation = ev.observation_bytes(observed)
assert ev.observation_bytes(baseline) == encoded_observation
assert observed["end"] == "time_limit"
hook = hooks[0]
result = {
    "schema": "health-time-limit-diagnostic-v1",
    "timestep_s": hook.dt,
    "configured_duration_s": parameters["time_limit"],
    "previous_configured_duration_s": prepared.recorded["time_limit"],
    "parameters": parameters,
    "final_time_s": hook.final_time,
    "terminal": hook.terminal,
    "end": observed["end"],
    "observation_sha256": digest(encoded_observation),
    "integration_calls": integrations,
    "rows": hook.rows,
}
(OUT / "observation.json").write_bytes(encoded_observation)
encoded = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
(OUT / "sidecar.json.gz").write_bytes(gzip.compress(encoded, mtime=0))
print("hook-disabled/enabled observation bytes identical", result["observation_sha256"])
print("end", observed["end"], "callbacks", len(hook.rows), "integrations", len(integrations))
print("last callback", hook.rows[-1], "terminal", hook.terminal)
print("sidecar sha256", digest((OUT / "sidecar.json.gz").read_bytes()))
