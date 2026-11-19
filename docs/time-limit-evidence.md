# Empirical time-limit terminal coverage

This Health diagnostic follows [issue #1's handoff](https://github.com/Living-Proof-Labs/livingproof-health/issues/1#issuecomment-7010557208).
The unchanged pinned producer advances to **102 ms after its last callback at
100 ms** in the measured time-limit case. This confirms the earlier
[source-backed hypothesis](diagnostic-sidecar.md), without a producer fix.

## Trial configuration and scope

The diagnostic uses the public Python `evidence.run_trial` API with the same G1
stock adapter, corner world, initial placement, route controller and prepared
parameters as the original recording. The sole input difference is a copy of
`p` with `time_limit=0.1` instead of `27.0` seconds. The original corner trial
stopped at the exit after 12.26 s; this new trial exhausts its shorter duration.

This duration is an execution argument: pinned
[run_trial](https://github.com/Living-Proof-Labs/livingproof-sim-mujoco/blob/f9c326f370cc3e54bf38932bfb332455dc4b5ef1/src/livingproof_sim_mujoco/evidence.py#L317)
passes `p["time_limit"]` directly to the observer's `seconds` argument.
[observe_route](https://github.com/Living-Proof-Labs/livingproof-sim-mujoco/blob/f9c326f370cc3e54bf38932bfb332455dc4b5ef1/src/livingproof_sim_mujoco/observations.py#L518)
accepts that duration. This is a supported Python trial input, **not** a claim
that the evidence CLI accepts a duration override. The frozen scenario lock,
parameter expressions, validation thresholds, producer and robot files remain
unchanged. The fixture is a diagnostic execution, not a scenario-certified run.
No evaluator verdict or overall task success is inferred from its short duration.

The actual observation says `end="time_limit"`, `exit_time=null`,
`left_world=null`, `duration_s=0.1`; its minimum sampled height is 0.7835 m.
The observer has no fall-triggered termination branch. The complete measured
integration sequence also corroborates loop exhaustion rather than an early stop.

## Three distinct measurements

| Measurement | Count | First time | Last time |
| --- | ---: | ---: | ---: |
| Producer hook callbacks | 51, indices 0–50 | 0 ms | 100 ms |
| Actual `mj_step2` calls | 51 | 0 → 2 ms | 100 → 102 ms |
| Saved observation samples, unchanged 50 Hz | 6 | 0 ms | 100 ms |
| Final live state inspected at hook close | 1 | — | 102 ms |

Integration calls are measured using CPython `sys.setprofile` native-call and
return events, filtering by identity of `mujoco.mj_step2`. The diagnostic retains
its caller's live `data.time` before and after each call. It does not replace
functions, invoke extra stepping or infer call counts solely from elapsed time.
The original profiler is required to be absent and profiling is removed in a
`finally` block. If these bindings do not expose native events, collection fails
rather than presenting a guessed count. Only the hook-enabled run is profiled.

The hook retains a reference to live data. On `close`, after the observer returns,
it reads final time and captures a separate terminal diagnostic, excluded from
the callback rows. The final integration begins at the final callback time and
returns at 102 ms; there is no callback at 102 ms. Thus the measured callback
coverage gap is one integration interval, **(100 ms, 102 ms]**. There are no
missing interior callback indices. The producer's returned observation duration
is its last sampled time, not this final state time.

Derived-position freshness is separate:

| State | Raw base height (m) | Fresh isolated height (m) |
| --- | ---: | ---: |
| Last callback, 100 ms | 0.7835220292121794 | 0.7834523406132797 |
| Final state, 102 ms | 0.7834523406132797 | 0.7833679996747301 |

At initialization raw and fresh heights agree. Every subsequent raw height
exactly equals the preceding callback's fresh height; the final raw height equals
the last callback's fresh height. This matches the pinned
[split-step policy](https://github.com/Living-Proof-Labs/livingproof-sim-mujoco/blob/f9c326f370cc3e54bf38932bfb332455dc4b5ef1/src/livingproof_sim_mujoco/policy.py#L425),
which updates kinematics before integration. The terminal gap and this 2 ms lag
are both empirical here. Neither is the same as the 20 ms sampling interval.

The six saved observation positions are checked against every tenth raw callback,
rounded to four decimals by the unchanged observer. **No recording is generated
or compared in this slice.** The earlier genuine MCAP remains evidence for its
own different trial; it is not relabeled as a recording of this new case.

## Isolation, precision and reproducibility

Kinematics run only on copied model/data objects. No exposed ndarray may share
memory with its source; all exposed live data arrays and time are compared
byte-for-byte before and after each isolated recomputation, including terminal
inspection. This is the same bounded isolation method as the prior diagnostic;
it is not a guarantee about arbitrary native plugins or future bindings.

Values retain Python binary64 precision with no position rounding. Floating
simulation time is preserved too: last callback `0.10000000000000007`, terminal
`0.10200000000000008`. Canonical string nanoseconds `"100000000"` and
`"102000000"` use nearest-nanosecond conversion; they do not claim the floating
clock is exact decimal time. Health Replay round-trip tests preserve the integer
times and unrounded height values without changing the time-only core.

Each of two fresh Docker containers runs the hook-disabled baseline and the
hook-enabled/profiled trial. Their observation bytes must match exactly:
SHA-256 `b451850eca78bdfdae94fda407bb79159a8c15b28759c89b8c7251d27cc323d5`.
This deliberately differs from the original long corner trial. The two retained
sidecars and observations also byte-match across containers. Logs, unrounded
gzip JSON, observation bytes and source/tool checksums live in
[tests/fixtures/time-limit](../tests/fixtures/time-limit).
The tests consume those authentic outputs; the earlier synthetic terminal-gap
injection test remains separately labeled and is not the basis of this result.

Pins: producer v3.2.1 `f9c326f370cc3e54bf38932bfb332455dc4b5ef1`, G1 v2.2.1
`68725986336c38d25a5ea421f895d9d796aed7f1`, Linux amd64, Python 3.11.14,
MuJoCo 3.17.0. The producer image is
`sha256:ef93be6981f33e2e925c3da9d4aa594fd77af498982ca3006f9097b31701ef23`.
See [original recording setup](original-recording.md#reproduce-generation-linux-amd64-docker)
for its unchanged Docker build and pinned G1 checkout. Exact managed proxy/CA
mounts are retained in [docker.sh](../tools/time-limit/docker.sh); it expects
`/workspace/health-g1-producer`. From the Health repository root:

```sh
bash tools/time-limit/docker.sh artifacts/time-limit > artifacts/time-limit-generation.log 2>&1
bash tools/time-limit/docker.sh artifacts/time-limit-repeat > artifacts/time-limit-repeat.log 2>&1
cmp artifacts/time-limit/sidecar.json.gz artifacts/time-limit-repeat/sidecar.json.gz
cmp artifacts/time-limit/observation.json artifacts/time-limit-repeat/observation.json
```

Both containers install fresh locked dependencies; the ignored model/policy cache
is reused. Existing producer warnings remain in the logs. Hosted tests consume
retained evidence on amd64/arm64; simulation generation was amd64 only. No general
whole-trial, continuous-time or hardware parity is established. Keep #1 open and
existing validators in place. Any producer contract change remains separate work.
