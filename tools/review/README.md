# Hosted reconstructed review probes

This is implementor-authored reconstruction of the independent reviewer's
specification recovered from recorded tool-call history, posted in
[issue #13 comment 7021500386](https://github.com/Living-Proof-Labs/livingproof-health/issues/13#issuecomment-7021500386).
It is **not** byte-for-byte recovery of the private script and is **not independent
verification**. An independent reviewer must inspect this code and actual artifacts
before resolving the P2. The original finding is in comment 7017492431.

The Verify workflow prepares locked dependencies and checksum-verified integration
wheels in a constrained Docker container. A second container reuses that cache
and runs offline setup, the existing 273 tests, including four visual replay cases, and these probes with
`--network=none` and a 300-second timeout (forced termination after five more
seconds). Do not run these scripts on the host. Before setup or test collection,
verification fails closed without Docker, loopback-only networking and readable
cgroup v2 limits: exactly 512 MiB memory, zero additional swap, two CPUs and 128 PIDs.
Each of 16 children checks containment before creating fixtures, applies 256 MiB
address-space and 8 CPU-second limits, and has a 12-second parent timeout. Installed
CLI subprocesses inherit these limits and have four-second individual timeouts.
No CI credential is passed to Docker or to the sanitized child environment.
Local constrained verification must pass before pushing workflow changes; hosted
CI is a subsequent check. Dependency preparation invokes no fixtures or probes.

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
The job also checks the separate existing JUnit has 273 passing cases and the
existing bounds directory has 41 passing records; those tests are not rewritten.

Reproduce only in a Docker environment that enforces the stated ceilings, from a
fresh checkout/evidence directory, with the existing development image:

```sh
mkdir -p /tmp/health-review-deps
docker -H unix:///var/run/docker.sock run --rm \
  --memory=512m --memory-swap=512m --cpus=2 --pids-limit=128 \
  --user "$(id -u):$(id -g)" -v "$PWD:/workspace/health" \
  -v /tmp/health-review-deps:/tmp health-test \
  timeout --kill-after=5 300 bash tools/review/prepare.sh
docker -H unix:///var/run/docker.sock run --rm --network=none \
  --memory=512m --memory-swap=512m --cpus=2 --pids-limit=128 \
  --user "$(id -u):$(id -g)" -e REVIEW_HEAD="$(git rev-parse HEAD)" \
  -v "$PWD:/workspace/health" -v /tmp/health-review-deps:/tmp health-test \
  timeout --kill-after=5 300 bash tools/review/verify.sh
```

Use a fresh cache directory for preparation. In a managed environment, preserve
the configured Docker proxy and existing CA trust. If required, supply the
Dockerfile's `ca` BuildKit secret and mount the existing CA bundle read-only in
the preparation container for curl, Git and uv. Use `BUILDX_CONFIG` for writable
Buildx state without replacing `DOCKER_CONFIG`. Offline verification needs no
CA mount or network credentials. Report publication runs separately in Docker;
only that container receives the CI token, after tests have completed.

Hosted artifacts `reconstructed-review-<architecture>-<head>` are separate from
`junit-report-<architecture>-<head>`, both retained for 30 days. The workflow logs
retain the enclosing command. `summary.json` and every case JSON label provenance.
Failure, missing evidence or timeout fails the job; artifact upload still runs.
The original probe handoff kept #14 draft and #13/#1 open. The
[viewer evidence](../../docs/evidence/visual-replay/status.json) for #12 is
separate and does not close the broader parity work in #1.
