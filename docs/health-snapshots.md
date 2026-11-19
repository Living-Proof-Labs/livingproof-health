# Health snapshots and recorded posture

The first slice implements [issue #1](https://github.com/Living-Proof-Labs/livingproof-health/issues/1).
Time is the only universal assumption. A valid observation can be just
`{"time_ns": "0"}` on the JSON wire. An empty set of observations is valid; omitting time is not.
Identity, measurements, posture, and source metadata are optional.

## Contract and adapter boundary

`livingproof_health.snapshots.snapshot` validates and copies a JSON object.
`time_ns` is a nonnegative integer in the Python API and a canonical decimal
string on the JSON wire, in nanoseconds on the producer's clock. It is not
implicitly Unix time. `items`, when present, is an object with adapter-owned
names and arbitrary JSON values. For example:

```json
{"time_ns": "20000000", "items": {"robot-specific/gripper": {"load": 3, "unit": "N"}, "temperature": null}}
```

An absent item means not reported; `null` means explicitly unavailable. Neither
is healthy. Other JSON fields are preserved, including optional robot identity
and source information. Nonfinite numbers, invalid time values, and non-JSON
values are rejected. There is no universal healthy/unhealthy snapshot field.

`ObservationAdapter.observe(time_ns, payload)` defines the small adapter boundary.
A future live source can supply timestamps and adapter-specific payloads through
this same boundary. This slice delivers one recorded source, not a live transport
or a robot-adapter discovery framework.

`BasePoseAdapter` accepts the JSON pose channel emitted by the simulation recorder:
`foxglove.PoseInFrame` / `jsonschema`, JSON messages on `/base_pose` (or an explicitly
selected topic). The schema name is a wire-format identifier; no Foxglove library,
viewer, server, ROS, or subscription is required. Choosing this adapter asserts
that positions use metres, as the referenced recorder does. It reports position
and optional quaternion components in the supplied frame, without assuming limbs,
wheels, an upright orientation, or what position is desirable. It does not
normalize quaternions, infer frames, or derive hardware signals. Missing/invalid
position or frame produces `base_pose: null`; missing orientation stays absent.
Unrelated channels are ignored. Unsupported encodings, malformed payloads, and a
selected topic with no messages fail explicitly.

## Portable representation and seek

`replay` emits one JSON document with `format: "livingproof-health/1"` and a
`snapshots` array. Each converted snapshot records the input SHA-256, topic,
publish timestamp, sequence, adapter version, and clock choice. This links the
output to the recording without embedding a local path. It does not authenticate
input provenance or prove that the source is hardware. The fixture's provenance
is documented separately below.

### Lossless timestamps across Python and JavaScript

All defined timestamps use the same **canonical nonnegative decimal string** on
the wire: snapshot `time_ns`, optional `source.publish_time_ns`, and assessment
`time_ns`. CLI `replay`, `seek`, and `assess` all follow this convention. An
assessment without an observed minimum retains `time_ns: null`; this is absence,
not a timestamp. The canonical syntax is `0` or an ASCII digit from `1` to `9`
followed by zero or more ASCII digits. JSON numbers, signs, leading zeroes,
whitespace, fractions, exponents, booleans, and non-ASCII digits are rejected.

For example, `"1800000000000000001"` and `"1800000000000000003"` remain distinct
through ordinary `JSON.parse` and `JSON.stringify`. Numeric JSON cannot guarantee
this: both would round to the same JavaScript `Number`. Never convert these
strings to `Number`, `parseInt`, or millisecond `Date` values for exact ordering.
Use `BigInt` for comparison; leave the strings in the document when serializing
because `JSON.stringify` does not accept `BigInt` values.

Python `snapshot`, adapters, `Replay.seek`, and `assess_base_height` use integer
nanoseconds internally. `Replay.to_json`, `snapshot_to_wire` (for an individual
seek result), and `assessment_to_json` emit decimal strings. `Replay.from_json`
validates wire strings and restores Python integers. Optional source timestamps
are validated when supplied; robot observations and metadata remain optional.
This convention covers the defined clock fields, not arbitrary adapter-owned
measurements. Adapters defining additional exact times must encode them losslessly.

This corrects the unreleased draft `/1` format. Numeric timestamps from earlier
PR revisions are rejected; regenerate those outputs from the original recording.
Already-rounded browser data cannot be repaired by converting it to a string.

The browser-compatible [seek reference](seek.mjs) uses validated `BigInt`
comparisons and lower-bound search over the sorted snapshots, preserving the
first duplicate. It can be used directly as an ES module:

```javascript
import { seek } from "./seek.mjs";
const recording = JSON.parse(text);
const sample = seek(recording.snapshots, "1800000000000000003");
const portableAgain = JSON.stringify(recording);
```

The regression in `tests/test_timestamp_wire.py` sends actual CLI replay, seek,
and assessment output through Node's ordinary JSON parser and serializer, imports
the result back into Python, and checks exact snapshot, publish, and assessment
times. It executes this same seek reference for duplicates, before/at/between/
after boundaries, empty input, and invalid query timestamps. Node is a development
test engine only; the Python package and CLI do not require it. A graphical
browser test is not claimed.

Replay sorts by integer MCAP **log time** and keeps duplicate timestamps in file
order. Embedded payload timestamps do not override the selected clock. Every
selected message is retained, including an unavailable sample. No interpolation,
decimation, smoothing, carry-forward, or rounding is applied. `seek(t)` returns
the first sample at or after `t`; before the beginning it returns the first
sample, and after the end (or in an empty replay) it returns `null`. There is no
implicit freshness claim for a sample returned after a gap. Reads return copies.
Replaying the same bytes gives the same JSON. This small implementation loads
recordings in memory; large-file streaming and cross-robot clock alignment remain
unsupported.

## Scenario assessment and parity limits

`assess` requires both a minimum height in metres and the expected frame. It reads
**all** snapshots, independently of any seek. A height strictly below the limit
fails; equality passes. It reports the lowest observed value and its earliest
timestamp. A recorded violation remains a failure even if other samples are
unavailable. Missing/wrong-frame/wrong-unit evidence prevents PASS. Empty input,
one instant, or duplicate samples of one instant cannot establish a trial
minimum and return `INSUFFICIENT_EVIDENCE` unless a violation is already observed.

The result always says `scope: recorded-samples-only` and
`whole_trial_parity: not-established`. PASS means every supplied sample meets
this particular expectation; it does **not** mean robot health, safety,
continuous-time success, or full-trial coverage. A file can omit the beginning,
end, or an interior interval without enough information to detect that omission.
The adapter does not invent completeness evidence.

The comparison matches the strict `<` behavior in
[scenario evaluator v1.3.8, checks.py](https://github.com/Living-Proof-Labs/livingproof-evaluator-scenario/blob/v1.3.8/src/livingproof_evaluator_scenario/checks.py)
(resolved `c1531f52f2df030d2ea85b9ce91fb5c01983cef5`). The
[MuJoCo recorder v3.6.5](https://github.com/Living-Proof-Labs/livingproof-sim-mujoco/blob/v3.6.5/src/livingproof_sim_mujoco/media.py)
records pose at 50 Hz and rounds position to five decimals. The evaluator's
existing minimum comes from simulation observation evidence, not necessarily
those same samples. A dip between recorder samples or rounding at a threshold
can differ. Therefore **existing validators remain in place**. This PR does not
establish end-to-end parity or change an evaluator dependency.

Integration should proceed through a released health package, with robot adapters
owning supported observations and scenarios owning expectations. Before routing
an existing validator through Health, compare both paths on the same original
full-trial evidence, including equality, rounding, missing evidence, and interior
dips. Either carry a trustworthy full-trial extremum/coverage record or retain the
current validator when sampled data cannot establish equivalence. Do not convert
a seek result into a whole-trial minimum.

## Fixture provenance and reproduction

`tests/fixtures/simulation-pose.mcap` is a deterministic **re-encoding of saved
simulation trace positions**, not an original recorder MCAP, new simulation run,
or hardware recording. All 614 saved positions from the G1 stock walk-corner
fixture are retained, with no fabricated orientation. The input was recorded
using MuJoCo v3.2.1 and Unitree G1 v2.2.1, according to the upstream provenance.
See [provenance.json](../tests/fixtures/provenance.json) for the released source,
resolved commit, original file checksum, transformation, and limits. Source
material is Apache-2.0; original upstream license is the same as this repository.
The saved trace has rounded samples and does not prove full-step parity.

Reproduce it offline after `task setup`:

```sh
uv run --locked --no-sync python tools/build_pose_fixture.py
uv run --locked --no-sync livingproof-health replay tests/fixtures/simulation-pose.mcap > health.json
uv run --locked --no-sync livingproof-health seek health.json --time-ns 4440000000
uv run --locked --no-sync livingproof-health assess health.json --minimum-m 0.75 --frame-id world
```

The final command returns FAIL (exit 1), with minimum `0.7464 m` at `4440000000 ns`.
Setting `--minimum-m 0.7464` returns PASS for the recorded samples (exit 0).
Insufficient evidence and invalid arguments return nonzero; assessment's
INSUFFICIENT_EVIDENCE is exit 2. Command help is generated directly by Click.

## Executable scenario inventory

Run `task verify`, or `task dev:verify` for Docker with the installed host check.
The existing CI publishes individual JUnit results and retains reports for 30 days.

| Behavior | Executable evidence |
| --- | --- |
| Time-only, robot-specific items, unavailable values, invalid contract | `tests/test_snapshots.py` |
| Stable replay, duplicate times, exact integer seek, portable round trip | `tests/test_snapshots.py` |
| Lossless Python/JavaScript/Python epoch timestamps; BigInt seek and invalid wire input | `tests/test_timestamp_wire.py`, `tests/timestamp_roundtrip.mjs` |
| Recorded position conversion, byte-identical fixture regeneration | `test_simulation_fixture_reproduces_and_preserves_every_position` |
| Below/equal/above limit, missing evidence, single instant, brief dip | `test_hallway_threshold_and_whole_recording_cases` |
| Scenario controls verdict, wrong frame does not pass | `test_scenario_controls_verdict_observation_has_no_verdict` |
| Unsupported/malformed MCAP fails; command-line replay/seek/assessment | `tests/test_posture.py` |
| Fresh wheel installed beside pinned host; conversion and assessment | `tests/test_host_integration.py` (online or cached wheels required) |

No real hardware, original recorder MCAP, live source, full-step parity,
cross-robot clock alignment, or viewer coverage is claimed by these scenarios.
