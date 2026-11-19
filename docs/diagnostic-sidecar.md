# Diagnostic callback coverage and state freshness

This Health-only evidence slice follows [the #1 handoff](https://github.com/Living-Proof-Labs/livingproof-health/issues/1#issuecomment-7009363446).
The existing hook covers the tested G1 early-stop trial's callback times, but
**raw `data.xpos` is stale at those times**. Do not label the raw sidecar full-step
state evidence. No producer, threshold, sampling, validator or Health runtime code
has changed. Issue #1 remains open.

## Measured contract and disagreement

The unchanged stock corner trial produces 6,131 callbacks: indices 0–6130 at
2 ms intervals, timestamped 0–12.260 s. The callback at zero agrees with fresh
kinematics. Every subsequent callback's raw base height equals the preceding
callback's fresh base height exactly. The isolated kinematics calculation uses
current `qpos`, without stepping time or running a controller.

| Evidence | Minimum height (m) | Time (s) | Maximum (m), time (s) |
| --- | --- | --- | --- |
| Saved producer summary | 0.7464 | 4.44 | Not reported |
| Genuine MCAP → Health | 0.74637 | 4.440 | 0.785, 0 |
| Unrounded hook `xpos` | 0.7463695705647768 | 4.440 | 0.785, 0 |
| Isolated fresh kinematics | 0.7463695705647768 | 4.438 | 0.785, 0 |

All four height assessments PASS at the recorded **0.5 m** threshold using the
actual pinned scenario evaluator v1.3.8 and Health's existing assessment. The
sidecar-to-evaluator adapter only reduces samples to the evaluator's expected
minimum-summary input. It implements no verdict rule. The original MCAP goes
through Health's actual MCAP reader; the sidecar uses Health Replay directly,
never a re-encoded file presented as original media. Values and timestamps differ
as shown; matching PASS is not general verdict parity.

The MCAP has every tenth callback (614 poses), rounded to five position decimals;
the summary uses four. Tests compare every retained MCAP height with its raw
callback and preserve the two-millisecond freshness discrepancy. Sidecar JSON
keeps Python binary64 values unrounded; decimal serialization round-trips those
values. `time_s` retains accumulated floating-point time (terminal value
12.260000000000764). `time_ns` is a canonical decimal string produced with the
normal recorder's nearest-nanosecond conversion. It preserves that integer,
not an assertion that the floating simulation clock has exact decimal seconds.

## Why the gap occurs; what coverage was established

Pinned producer **v3.2.1 / f9c326f370cc3e54bf38932bfb332455dc4b5ef1**:

- [run_trial](https://github.com/Living-Proof-Labs/livingproof-sim-mujoco/blob/f9c326f370cc3e54bf38932bfb332455dc4b5ef1/src/livingproof_sim_mujoco/evidence.py#L317)
  constructs the hook and uses the same observer as ordinary evidence.
- [observe_route](https://github.com/Living-Proof-Labs/livingproof-sim-mujoco/blob/f9c326f370cc3e54bf38932bfb332455dc4b5ef1/src/livingproof_sim_mujoco/observations.py#L557)
  invokes the hook before sampling and before `step(data)`. On `crossed_exit`, it
  breaks before the next step. Retaining a read-only reference to the last data
  object confirms final time equals the final callback time for this trial.
- [Policy.step](https://github.com/Living-Proof-Labs/livingproof-sim-mujoco/blob/f9c326f370cc3e54bf38932bfb332455dc4b5ef1/src/livingproof_sim_mujoco/policy.py#L425)
  calls `mj_step1` then `mj_step2` once. The first updates positions; the second
  integrates. G1's [route driver](https://github.com/Living-Proof-Labs/livingproof-unitree-g1/blob/68725986336c38d25a5ea421f895d9d796aed7f1/src/lpl_g1/route.py#L69)
  calls that step once. Source ordering plus measured cadence establishes one
  callback per integration boundary in this execution, not merely a nominal rate.
- On time-limit exhaustion, the inclusive observer loop executes a final
  `step(data)` after its last callback. That terminal state would be absent from
  the sidecar. This is a **source-backed gap, not a tested time-limit trial**.
  Regression tests inject a later terminal time and require detection. Other
  termination modes, continuous time, other robots and hardware remain unproven.

MuJoCo's [API documentation](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-kinematics)
describes `mj_kinematics` as forward kinematics. This diagnostic copies both model
and data with the Python bindings, verifies no exposed ndarray shares memory with
its source, and invokes kinematics only on the copies. At every callback all
exposed live data arrays and `time` are byte-compared before/after. This is a
bounded check for the pinned model; it is not proof for arbitrary native plugin
state or future bindings. No live `mj_forward`, kinematics, controller or step
call is added by the hook.

## Retained provenance and reproduction

[Fixtures](../tests/fixtures/diagnostic-sidecar) contain deterministic gzip JSON,
two fresh-container logs and a checksum/source manifest. The original paired
observation, run manifest and MCAP remain in
[original-recording](../tests/fixtures/original-recording); no MCAP bytes are
manufactured for this slice. Each fresh container runs hook-disabled and
a hook-enabled trial, requires both observation byte streams equal the retained
SHA-256 `8337886b0509110df270dc34c6a78d6c3632dad46c05aac733f55a2e813f5424`,
then invokes the **normal media command**, which enforces observation pairing.
Its MCAP must byte-match SHA-256
`0acbf1037b64f4b3aceaac6a1fcd83fd5b8599943a10c2815a8e09ac636bbef4`.
The two sidecars must also byte-match. Logs retain existing producer warnings.

Use the producer Docker build and pinned G1 setup in
[original-recording.md](original-recording.md#reproduce-generation-linux-amd64-docker).
The exact managed-environment invocation is retained in
[tools/diagnostic-sidecar/docker.sh](../tools/diagnostic-sidecar/docker.sh).
It expects the G1 v2.2.1 checkout at `/workspace/health-g1-producer`; adjust this
mount for another machine. It forwards the managed proxy and mounts its CA;
ordinary environments can use their normal Docker network/CA configuration.
The robot checkout's ignored model cache is reused, but both containers create
fresh Python environments. Run from the Health checkout:

```sh
bash tools/diagnostic-sidecar/docker.sh artifacts/diagnostic-sidecar > artifacts/diagnostic-generation.log 2>&1
bash tools/diagnostic-sidecar/docker.sh artifacts/diagnostic-repeat > artifacts/diagnostic-repeat.log 2>&1
cmp artifacts/diagnostic-sidecar/sidecar.json.gz artifacts/diagnostic-repeat/sidecar.json.gz
```

Generation is Linux amd64, Python 3.11.14, MuJoCo 3.17.0, the unchanged producer
image `sha256:ef93be6981f33e2e925c3da9d4aa594fd77af498982ca3006f9097b31701ef23`.
G1 v2.2.1 resolves to `68725986336c38d25a5ea421f895d9d796aed7f1`;
its locked runtime inventory is retained with the original recording. Normal
Health tests replay retained evidence without adding MuJoCo dependencies.
Hosted amd64/arm64 checks test consumption, **not cross-architecture simulation**.

The smallest next decision is independent review of this freshness/terminal-gap
report. A corrected producer recording contract would be separate producer work,
not permission to modify it here. Existing validators stay in place.
