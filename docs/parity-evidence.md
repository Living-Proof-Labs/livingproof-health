# Differential parity evidence

This is the bounded evidence slice for [issue #1](https://github.com/Living-Proof-Labs/livingproof-health/issues/1#issuecomment-7007699728).
It does not replace a validator, implement a scenario runner, or establish
whole-trial or hardware parity. Keep issue #1 open while that parity is unproven.

## Two actual paths, one declared evidence set

`tests/test_scenario_parity.py` runs the installed
`livingproof-evaluator-scenario` **v1.3.8**, through its public
`EVALUATE["hallway-fall"]` entry point and actual parameter resolution. The test
prepares a `min_base_height` observation from explicitly enumerated samples; it
does not copy the evaluator's comparison rule. The other path writes actual MCAP
JSON pose messages, reads them through `read_mcap`, and calls
`assess_base_height` with the same configured threshold. Health retains its
recorded-sample scope and `whole_trial_parity: not-established` result.

For these synthetic cases, **full resolution** means every enumerated test
sample is supplied to both paths without sampling or rounding. It does not mean
continuous-time evidence, physical safety, or simulation steps from a real run.
The generated MCAP carries synthetic-contract provenance. Cases that deliberately
remove or round samples are separate tests with explicit differing expectations.
The helper is confined to the tests, has no runner entry point, and invokes no
simulator. It does not duplicate the scenario MCAP-runner work in
[livingproof-evaluator-scenario#1](https://github.com/Living-Proof-Labs/livingproof-evaluator-scenario/issues/1).

The evaluator is in the **development dependency group only**. Its released Git
tag resolves in `uv.lock` to `c1531f52f2df030d2ea85b9ce91fb5c01983cef5`; its scenario
parameters dependency is v2.2.0 at `23bec516bda29be7b26555286cbf2e8217ac5c81`.
The test verifies installed versions, Git provenance, and the evaluator source
checksum. These development dependencies require Python 3.12; the Health runtime
requirement remains Python >=3.11 and its wheel does not depend on either package.

## Executable cases and expected outcomes

Each parameterized case has its own JUnit result in the ordinary Task/CI suite.
A successful test can assert different path outcomes; it must not be read as
successful robot behavior or established parity.

| Evidence / stable test name | Scenario evaluator | Health | Meaning |
| --- | --- | --- | --- |
| `equivalent_full_resolution_synthetic_samples[below]` | FAIL | FAIL | Same minimum below the configured limit |
| `[equal]`, `[above]` | PASS | PASS | Equality is preserved |
| `[unrounded-just-below]`, `[unrounded-just-above]` | FAIL / PASS | FAIL / PASS | No precision loss with equivalent unrounded samples |
| `[brief-interior-dip]` | FAIL | FAIL | All 1,001 supplied samples are considered, including a single-sample interior dip at 2 ms spacing |
| `equivalent_unavailable_evidence_cannot_pass` (3 cases) | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | Absent, text, or boolean height is not a healthy observation |
| `empty_mcap_is_an_input_error_not_a_pass` | INSUFFICIENT_EVIDENCE | Input error | No pose messages is an explicit conversion failure |
| `single_instant_does_not_establish_coverage` (3 cases) | PASS at/above limit; FAIL below | INSUFFICIENT_EVIDENCE at/above; FAIL below | The evaluator trusts a supplied minimum summary; Health cannot infer trial coverage from one instant |
| `expected_disagreement_when_sampling_loses_a_dip` | FAIL | PASS after sampling | A synthetic 500 Hz stream has a dip at 10 ms omitted by 50 Hz sampling; full input fails on both paths |
| `expected_disagreement_when_mcap_rounding_loses_precision` | FAIL | PASS after rounding | `0.499996` becomes `0.50000` at five decimals, against a `0.5` limit |
| `expected_disagreement_between_four_and_five_decimal_evidence` | PASS | FAIL | `0.499991` becomes `0.5000` in a four-decimal summary but `0.49999` in five-decimal MCAP |
| `expected_disagreement_when_summary_is_missing_or_malformed` (3 cases) | INSUFFICIENT_EVIDENCE | PASS | Valid multi-instant pose cannot repair absent summary value/time or malformed summary time in the other path |
| `expected_disagreement_when_recording_has_unavailable_sample` | PASS | INSUFFICIENT_EVIDENCE | A complete minimum summary does not repair a missing Health observation |
| `original_saved_summary_vs_derived_trace_not_original_mcap` (3 cases) | PASS / PASS / FAIL | PASS / PASS / FAIL | Agreement for the saved, rounded G1 fixture at limits `0.5`, `0.7464`, `0.75`; not independent original-recording parity |

The remaining case verifies dependency/source/fixture pins and the runtime
boundary. The suite has **24 differential/provenance cases**. Existing timestamp,
MCAP, CLI, installed-wheel, and other regression tests still run unchanged.

## Original evidence inspected and the precise gap

This section records the evidence available for the differential-harness slice.
A subsequent [original recorder slice](original-recording.md) successfully
regenerated the pinned G1 trial and preserved its genuine paired MCAP. The
sampling/full-step limits below remain; the absence of original media is no
longer the current fixture limitation.

The [provenance manifest](../tests/fixtures/parity/provenance.json) records tags,
resolved commits, source paths, and SHA-256 checksums. The original G1 stock
`trial-01.json` and `run-manifest.json` are copied **byte-for-byte** from the
MuJoCo repository's v3.6.5 fixture tree, at
`24c7e9b217f8dec94d3dfa5942d7edab71f6a7c4`. They are saved simulation evidence,
not synthetic cases. The run manifest identifies producer v3.2.1 commit
`f9c326f370cc3e54bf38932bfb332455dc4b5ef1`, MuJoCo 3.17.0, G1 robot commit
`68725986336c38d25a5ea421f895d9d796aed7f1`, and its world/profile identities.
Upstream material is Apache-2.0, the same license as this repository.

The saved summary minimum is `0.7464 m` at `4.44 s`. Its rounded position trace
is the source of Health's existing `simulation-pose.mcap`. The new tests compare
the *original saved summary* to that *derived MCAP*, verify the trace derivation,
and assert both value and occurrence time. Re-encoding a trace cannot restore
the information discarded by its producer, so this is deliberately not labeled
original MCAP parity.

Inspection of the producer's pinned code establishes:

- [`observations.py` at v3.2.1](https://github.com/Living-Proof-Labs/livingproof-sim-mujoco/blob/v3.2.1/src/livingproof_sim_mujoco/observations.py): both observation loops default `sample_hz` to 50 and update `min_base_height` **inside** the `i % every == 0` sampling gate. The stride is `max(1, round(1 / (sample_hz * timestep)))`. Thus the recorded summary is not a per-physics-step minimum. Stored positions/minima and sample seconds are rounded to four decimal places. A new raw height is compared against the previously rounded stored minimum, which can also affect the selected occurrence time near ties. This harness does not reimplement or modify that producer logic.
- [`media.py` at v3.2.1](https://github.com/Living-Proof-Labs/livingproof-sim-mujoco/blob/v3.2.1/src/livingproof_sim_mujoco/media.py): `MCAP_HZ = 50`, with the same stride formula by default; position uses five decimal places and time uses `round(data.time * 1e9)` nanoseconds. Media is made by replaying a run; the code checks the re-run observation hash before retaining its recording. The default nominal rates coincide, but their precision differs, and neither rate proves full-step coverage.
- The inspected v3.6.5 Git tree has the original saved observation and manifest, but **no `.mcap` files** or full-physics-step stream. No original media was downloaded or newly generated in this slice. The synthetic lost-dip test demonstrates what sampling can lose; it does not assert that this particular saved G1 run contained such a dip.

This corrects the earlier implication that the saved simulator minimum was
computed at every physics step. An original recorder MCAP paired by hash with
its source observation, and an explicit account of source coverage/rounding,
remain necessary before even recorded-path parity can be claimed for original
media. Full-trial parity additionally requires evidence that covers the desired
trial interval and resolution, or a trustworthy full-trial extremum record.
The current inputs cannot prove those properties. Existing validators stay in
place; no simulator sampling or validation policy changes are proposed here.

## Reproduction

Inside the prepared development environment (Python 3.12, uv, Task, Node):

```sh
task setup
uv run --locked --no-sync --no-python-downloads pytest tests/test_scenario_parity.py -v
LIVINGPROOF_NETWORK=1 task verify
```

On a Docker host:

```sh
task dev:build
task dev:verify
```

Initial setup fetches the two commit-locked Git sources; later harness execution
is offline. CI runs the same suite on amd64 and arm64, publishes individual case
results, and retains JUnit artifacts for 30 days. The PR evidence identifies the
exact tested Health head, environment, run, published case views, and artifacts.
