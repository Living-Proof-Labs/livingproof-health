# Hosted reconstructed review probes

This is implementor-authored reconstruction of the independent reviewer's
specification recovered from recorded tool-call history, posted in
[issue #13 comment 7021500386](https://github.com/Living-Proof-Labs/livingproof-health/issues/13#issuecomment-7021500386).
It is **not** byte-for-byte recovery of the private script and is **not independent
verification**. An independent reviewer must inspect this code and actual artifacts
before resolving the P2. The original finding is in comment 7017492431.

The existing Verify workflow runs this path after the unchanged 229 tests in the
same Docker image/container and 300-second timeout. Do not run the script on the
host. It fails closed without Docker and readable cgroup v2 ceilings: memory at
most 512 MiB, zero additional swap, CPU quota at most two CPUs and at most 128 PIDs.
Each of 16 children checks containment before creating fixtures, applies 256 MiB
address-space and 8 CPU-second limits, and has a 12-second parent timeout. Installed
CLI subprocesses inherit these limits and have four-second individual timeouts.
No CI credential is passed to Docker or to the sanitized child environment.
No local adversarial run is needed or authorized by this recovery path.

Each revision (candidate and old `6f6527aad72684fb68d9271bc58149d6617c7fba`)
is exercised with known/unknown content sizes and truncated-prefix, empty,
skippable and valid single-frame inputs. Malformed inputs retain default Limits;
valid inputs use exact expansion-budget equality. Both stdout and atomic `--output`
are exercised. Old unknown-size malformed acceptance is an **expected reproduction**,
not a passing validity verdict; candidate rejects all malformed cases. Known-size
malformed cases reject on both. The recovered unknown/prefix fixture must be 246
bytes with raw CRC 572566889. Old source is read from Git objects only inside the
constrained child and selected through an explicit temporary PYTHONPATH; unavailable
old source fails the run. No checkout or runtime code is modified.

The candidate source tree must equal the requested PR head tree. Artifacts record
both the tested checkout/merge commit/tree and the PR head, old commit/tree, probe
and reader digests, exact input MCAPs, CLI commands/stdout/stderr/exit codes,
target bytes and temporary-file assertions, cgroup values and memory/time measures.
The recorded descendant RSS includes CLI and Git children (not an isolated CLI
allocation delta). Complete expected case coverage and all assertions are required.
The job also checks the separate existing JUnit has 229 passing cases and the
existing bounds directory has 41 passing records; those tests are not rewritten.

Reproduce only in a Docker environment that enforces the stated ceilings, from a
fresh checkout/evidence directory, with the existing development image:

```sh
docker run --rm --memory=512m --memory-swap=512m --cpus=2 --pids-limit=128 \
  --user "$(id -u):$(id -g)" -e LIVINGPROOF_NETWORK=1 -e HEALTH_BOUNDED_TESTS=1 \
  -e REVIEW_HEAD="$(git rev-parse HEAD)" -v "$PWD:/workspace/health" health-test \
  timeout 300 bash -o pipefail -c 'task setup && task verify && uv run --locked --no-sync python tools/review/zstd_probes.py 2>&1 | tee artifacts/review-zstd-command.log'
```

Hosted artifacts `reconstructed-review-<architecture>-<head>` are separate from
`junit-report-<architecture>-<head>`, both retained for 30 days. The workflow logs
retain the enclosing command. `summary.json` and every case JSON label provenance.
Failure, missing evidence or timeout fails the job; artifact upload still runs.
Keep #14 draft, #13/#1 open and visual #12 unchanged/browser-blocked.
