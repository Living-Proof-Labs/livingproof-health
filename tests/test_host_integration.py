# SPDX-License-Identifier: Apache-2.0
"""Verify installed wheel discovery and invocation with the real livingproof host CLI.

Provide pre-downloaded checksum-verified wheels via LIVINGPROOF_WHEEL_DIR, or opt in
to downloading pinned releases with LIVINGPROOF_NETWORK=1 (run explicitly in CI).
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]

HOST_WHEEL = "livingproof-1.5.4-py3-none-any.whl"
HOST_URL = "https://github.com/Living-Proof-Labs/livingproof/releases/download/v1.5.4/" + HOST_WHEEL
HOST_SHA256 = "f01fa04a78254047a2c062478556107d036be18af98f3f8a3ddb5b0d11266639"

COMMON_WHEEL = "livingproof_common-1.0.0-py3-none-any.whl"
COMMON_URL = (
    "https://github.com/Living-Proof-Labs/livingproof-common/releases/download/v1.0.0/"
    + COMMON_WHEEL
)
COMMON_SHA256 = "8b7795748b54eeb89610f3716245f45db48ac0474465a5abbf974e7075c1476c"


def _obtain_wheel(tmp_path: Path, filename: str, url: str, expected_sha256: str) -> Path:
    wheel_dir = os.environ.get("LIVINGPROOF_WHEEL_DIR")
    if wheel_dir:
        candidate = Path(wheel_dir) / filename
        if not candidate.is_file():
            pytest.fail(f"Expected {filename} in LIVINGPROOF_WHEEL_DIR ({wheel_dir})")
        content = candidate.read_bytes()
    else:
        content = urlopen(url, timeout=60).read()
    actual_sha256 = hashlib.sha256(content).hexdigest()
    assert actual_sha256 == expected_sha256, f"{filename} checksum mismatch: {actual_sha256}"
    target = tmp_path / filename
    target.write_bytes(content)
    return target


def _has_wheels_or_network() -> bool:
    return (
        bool(os.environ.get("LIVINGPROOF_WHEEL_DIR"))
        or os.environ.get("LIVINGPROOF_NETWORK") == "1"
    )


@pytest.mark.skipif(
    not _has_wheels_or_network(),
    reason="requires LIVINGPROOF_NETWORK=1 or LIVINGPROOF_WHEEL_DIR",
)
def test_installed_wheel_discovered_and_run_by_host_cli(tmp_path):
    uv = shutil.which("uv")
    assert uv, "uv is required for isolated wheel installation verification"

    def run(*args, cwd=tmp_path, env=None, expected_exit=0):
        result = subprocess.run(
            list(map(str, args)),
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == expected_exit, (
            f"command {args} exited {result.returncode} (expected {expected_exit})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        return result

    host_wheel = _obtain_wheel(tmp_path, HOST_WHEEL, HOST_URL, HOST_SHA256)
    common_wheel = _obtain_wheel(tmp_path, COMMON_WHEEL, COMMON_URL, COMMON_SHA256)

    wheels_dir = tmp_path / "wheels"
    run(uv, "build", "--offline", "--wheel", "--out-dir", wheels_dir, cwd=ROOT)
    (health_wheel,) = wheels_dir.glob("livingproof_health-*.whl")

    env_dir = tmp_path / "environment"
    run(uv, "venv", "--python", sys.executable, "--no-python-downloads", env_dir)
    python = env_dir / "bin" / "python"
    host_bin = env_dir / "bin" / "livingproof"
    standalone_bin = env_dir / "bin" / "livingproof-health"

    # Install in one resolver transaction to verify compatible pinned dependencies.
    install_args = [uv, "pip", "install", "--python", python]
    if os.environ.get("LIVINGPROOF_WHEEL_DIR"):
        install_args.append("--offline")
    install_args.extend([host_wheel, health_wheel, common_wheel])
    run(*install_args)
    run(uv, "pip", "check", "--python", python)

    # Lightweight discovery: group help and bash completion must list `health` without importing it.
    discovery = run(host_bin, "capability", "--help")
    assert "health" in discovery.stdout
    assert "Installed plugin" in discovery.stdout

    probe = (
        "import sys, click; "
        "from livingproof.cli import capability, Plugins; "
        "ctx = click.Context(capability); "
        "names = Plugins().list_commands(ctx); "
        "assert 'health' in names, names; "
        "assert 'livingproof_health' not in sys.modules, 'discovery imported plugin module'"
    )
    run(python, "-c", probe)

    completion_env = {
        **os.environ,
        "_LIVINGPROOF_COMPLETE": "bash_complete",
        "COMP_WORDS": "livingproof capability h",
        "COMP_CWORD": "2",
    }
    completion = run(host_bin, env=completion_env)
    assert "plain,health" in completion.stdout

    # Help and version through both the host CLI and standalone entrypoint.
    host_help = run(host_bin, "capability", "health", "--help")
    standalone_help = run(standalone_bin, "--help")
    assert "Robot wellness" in host_help.stdout
    assert "issue #1" in host_help.stdout
    assert "Robot wellness" in standalone_help.stdout

    host_version = run(host_bin, "capability", "health", "--version")
    standalone_version = run(standalone_bin, "--version")
    assert host_version.stdout == standalone_version.stdout
    assert "livingproof-health, version " in host_version.stdout
    assert "identity source: recorded-build" in host_version.stdout

    # Invoking without a subcommand gives a clear, nonzero command-selection response.
    host_unimpl = run(host_bin, "capability", "health", expected_exit=1)
    assert "Choose a command" in host_unimpl.stderr
    assert "livingproof capability health --help" in host_unimpl.stderr
    assert "Traceback" not in host_unimpl.stderr

    standalone_unimpl = run(standalone_bin, expected_exit=1)
    assert "Choose a command" in standalone_unimpl.stderr
    assert "livingproof-health --help" in standalone_unimpl.stderr
    assert "Traceback" not in standalone_unimpl.stderr

    # Exercise conversion and scenario evaluation through the installed host plugin.
    converted = run(
        host_bin, "capability", "health", "replay", ROOT / "tests/fixtures/simulation-pose.mcap"
    )
    portable = tmp_path / "health.json"
    portable.write_text(converted.stdout)
    sought = run(standalone_bin, "seek", portable, "--time-ns", "4440000000")
    assert json.loads(sought.stdout)["items"]["base_pose"]["position"]["z"] == 0.7464
    verdict = run(
        host_bin,
        "capability",
        "health",
        "assess",
        portable,
        "--minimum-m",
        "0.75",
        "--frame-id",
        "world",
        expected_exit=1,
    )
    assert json.loads(verdict.stdout)["status"] == "FAIL"
