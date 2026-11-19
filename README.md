# livingproof-health

Robot wellness and time-indexed health observation plugin for Living Proof Labs.

## Status

This repository is currently in its **bootstrap foundation** stage (issue `#2`).
It provides the Python package scaffold, pinned dependencies, Docker/Task
development workflow, continuous integration checks, and the discoverable
`health` plugin entry point for the `livingproof` host command-line tool.

Health snapshots, recording replay, and posture evaluation are not implemented
yet and are tracked in [issue #1](https://github.com/Living-Proof-Labs/livingproof-health/issues/1).

## Design boundaries

- **Time is the only universal assumption.** Individual observations are optional,
  and missing data is never treated as healthy data.
- **No external stack requirements.** The package and command-line plugin work
  without ROS, Foxglove, or paid services, and do not require any particular
  robot or telemetry field.
- **Observations stay separate from policy.** Recorded observations do not
  imply scenario verdicts, universal health thresholds, or safety certification.

## Command-line discovery and usage

`livingproof-health` registers two entry points in `pyproject.toml`:

- Standalone script: `livingproof-health`
- Host plugin under `livingproof.capability.commands`: `health`, invoked as
  `livingproof capability health`

Available bootstrap commands:

```sh
livingproof capability --help
livingproof capability health --help
livingproof capability health --version
livingproof-health --help
livingproof-health --version
```

Invoking `livingproof capability health` or `livingproof-health` without a
subcommand exits with status `1` and explains that Health functionality is not
implemented yet while pointing to `--help`, `--version`, and issue `#1`.

## Development setup and verification

### Prepared environment (Python 3.12, uv, and Task 3.54.0)

Requires Python `>=3.11` (verified on Python `3.12.12` and `3.12.16`),
[uv](https://docs.astral.sh/uv/), and [Task](https://taskfile.dev) `3.54.0`:

```sh
task setup
task check
task test
task verify
```

- `task setup` runs `uv sync --locked --no-python-downloads`.
- `task check` runs locked Ruff lint and formatting checks.
- `task test` runs locked pytest and writes `artifacts/tests.xml`.
- `task verify` runs `task check` followed by `task test`.

### Docker and development container

From a host with Docker and Docker Compose (builds the `development` target
from `Dockerfile` with Python `3.12.12`, `uv` `0.12.23`, and Task `3.54.0`):

```sh
task dev:build
task dev:verify
```

`task dev:verify` explicitly enables the online installed-host integration test
inside Compose; it requires access to the checksum-pinned GitHub releases and
package index. No host environment-variable forwarding is required.

To open an interactive shell inside the development container:

```sh
task dev:shell
```

Inside the development container (including `.devcontainer/devcontainer.json`),
run `task setup` and `task verify` directly without nested Docker.

### Isolated wheel and host plugin verification

`tests/test_host_integration.py` builds a wheel of `livingproof-health`, installs
it alongside the pinned `livingproof` (`v1.5.4`) and `livingproof-common`
(`v1.0.0`) wheels into a clean virtual environment, checks dependency
consistency with `uv pip check`, and exercises lightweight discovery, `--help`,
`--version`, bash completion, and the unimplemented response.

Run it online against the checksum-pinned GitHub releases:

```sh
LIVINGPROOF_NETWORK=1 task verify
```

Or offline against pre-downloaded, checksum-verified wheels in a local directory:

```sh
LIVINGPROOF_WHEEL_DIR=/path/to/wheels task verify
```

Continuous integration runs `LIVINGPROOF_NETWORK=1 task verify` on both
`ubuntu-24.04` (`amd64`) and `ubuntu-24.04-arm` (`arm64`) and checks workflows
with `actionlint`. These fallback jobs run Task directly; they do not build or
exercise Docker. Docker verification is a separate contributor/reviewer check.

Test reporting fails verification for missing, malformed, empty, or inconsistent
JUnit evidence and for failed check publication. Each suite must declare its
test count; declared test/failure/error/skip totals must match its cases. Fork
PRs explicitly disable check publication where write permissions are unavailable;
the job summary and retained JUnit artifact remain the evidence for those runs.

### Deferred infrastructure adoption

The development image has not been published. CI uses the Ubuntu fallback above,
and the development container builds the local Dockerfile.
[Issue #4](https://github.com/Living-Proof-Labs/livingproof-health/issues/4) tracks
image publication and migration of CI/development containers to a shared
multi-architecture digest.

The generated manual and GitHub Pages adoption are not complete.
[Issue #5](https://github.com/Living-Proof-Labs/livingproof-health/issues/5) tracks
generation, scoped deployment authorization, and live verification before adding
a README start-here link. Bootstrap #2 makes no settings or deployment changes.

## License

[Apache-2.0](LICENSE).
