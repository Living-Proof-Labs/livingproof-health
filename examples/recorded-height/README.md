<!-- SPDX-License-Identifier: Apache-2.0 -->
# Sampled base-height indicator

This local Health demonstration compares recorded simulator base heights with an
**explicit scenario criterion**. It does not measure orientation or decide that a
robot is upright, healthy, safe, or successful over the whole trial. No report
grade or existing Scenario result changes.

The primary source for the hallway rule is
[robot-capability-specs v2.3.0, walk-hallway.feature](https://github.com/Living-Proof-Labs/robot-capability-specs/blob/v2.3.0/specs/scenarios/walk-hallway/walk-hallway.feature):
`hallway-fall` fails when `min_base_height` **is less than** `fall_height`.
The threshold is resolved from the selected configuration, not a Health constant.
For the verified G1 stock recording used here,
[stock configuration 1.1.1 in livingproof-unitree-g1 v2.3.40](https://github.com/Living-Proof-Labs/livingproof-unitree-g1/blob/v2.3.40/configurations/stock.json)
sets `locomotion.fall_base_height.value` to **0.50 m**. That file's SHA-256 is
`8baf584eb025fa4408aad20a81521b73bc068a3a7e613dfeeb8f03d24eb02b5e`, matching the
recording's report configuration pin. The scenario's parameter rule is defined in
[parameters.json](https://github.com/Living-Proof-Labs/robot-capability-specs/blob/v2.3.0/specs/scenarios/walk-hallway/parameters.json).
This is an absolute base-position z value in the recording's `world` frame, not a
height reduction from the nominal pose. Equality is not below the threshold.

## Run the demo

Use the repository's prepared development container (`task setup`). Obtain an
unchanged `health.json`, its **report-published** checksum and the selected trial
identity using the [released replay procedure](../recorded-replay/README.md#open-existing-evaluator-details-locally).
Do not use a self-computed hash as provenance. Verify that your selected scenario
and configuration actually use this criterion before supplying the example flags.
Other scenarios may use a different criterion or none.

```sh
uv run --locked --no-sync python examples/recorded-height/demo.py health.json \
  --sha256 "$REPORT_SHA256" \
  --run-id '<run_id from the verified file>' \
  --configuration '<configuration from that trial>' --trial-index '<index>' \
  --minimum-m 0.50 --frame-id world \
  --criterion-source 'robot-capability-specs@v2.3.0 walk-hallway; livingproof-unitree-g1@v2.3.40 stock 1.1.1' \
  --output height-demo
python3 -m http.server 8000 --bind 127.0.0.1 --directory height-demo
```

Open <http://127.0.0.1:8000/>. The page shows the minimum recorded height, its exact
nanosecond timestamp/frame, configured threshold, sample availability and source.
**Inspect recorded replay** opens the existing viewer for the same verified input.
The command also writes `indicator.json` and prints the indicator. Choose a new
output directory each time; existing output is refused. Keep generated files local.

To demonstrate a scenario with **no declared height requirement**, omit all three
of `--minimum-m`, `--frame-id`, and `--criterion-source`, and choose a new output
directory. The indicator says **Not applicable**. A somersault or backflip gets no
implied upright requirement: applicability comes from the caller's explicit
scenario declaration, never the scenario's name. A partial set of criterion flags
is an input error, not a guessed default. The source label records the caller's
citation; this demo does not automatically verify that citation or resolve a
scenario configuration for the caller.

## Meaning and limits

- **Not applicable:** no criterion supplied; no height comparison is attempted.
- **Unevaluated:** criterion supplied, but no matching heights, missing samples,
  wrong frame/unit, or fewer than two distinct sample times prevent a complete
  sampled comparison. A malformed or digest-invalid input file is refused.
- **Recorded height below configured threshold:** at least one observed sample
  is below it. Missing samples cannot erase that observed violation.
- **Recorded heights at or above configured threshold:** all available snapshot
  slots are measured in the selected frame/unit and at least two distinct times
  were recorded. This is not a whole-trial PASS; between-sample motion is unknown.

The first minimum in replay order supplies the displayed time. Quaternion values
are not interpreted. Missing robot telemetry is not filled by simulator evidence.
The module reuses `assess_base_height`; it only presents that sampled result with
explicit applicability and neutral labels. No universal threshold is installed.

Historical test evidence (2026-11-28): the reused 574-sample G1 recording, digest
`9e6e7bfe280966e37072c938f4d30ac4f09782bca2dec676900b3db41169f2ec`, has minimum
**0.74814 m at 8460000000 ns in world**, compared with the explicitly supplied
0.50 m criterion. These are that recording's values, not expected values for a new
run. The broader whole-trial parity work in #1 and static-card preview in #38 are
separate; this slice closes only #39.
