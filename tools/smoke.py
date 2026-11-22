# SPDX-License-Identifier: Apache-2.0
"""Verify dist/ release artifacts, checksums, isolated installation, and host CLI replay."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

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
            raise SystemExit(f"Expected {filename} in LIVINGPROOF_WHEEL_DIR ({wheel_dir})")
        content = candidate.read_bytes()
    else:
        content = urlopen(url, timeout=60).read()
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise SystemExit(f"{filename} checksum mismatch: {actual_sha256}")
    target = tmp_path / filename
    target.write_bytes(content)
    return target


def require_recorded_release(provenance, version, commit):
    """The installed package must record this release version and source revision."""
    if not isinstance(provenance, dict):
        raise SystemExit("Installed package provenance is missing")
    if provenance.get("package_version") != version:
        raise SystemExit(
            f"Expected package_version {version}, got {provenance.get('package_version')}"
        )
    identity = provenance.get("identity") if isinstance(provenance.get("identity"), dict) else {}
    if identity.get("commit") != commit:
        raise SystemExit(f"Expected revision {commit}, got {identity.get('commit')}")
    if identity.get("state") != "clean":
        raise SystemExit(f"Release provenance must be clean, got {identity.get('state')}")


INSTALLED_PROVENANCE = """
import json
from pathlib import Path
import livingproof_health
from livingproof_common.versioning import PROVENANCE, read_provenance
path = Path(livingproof_health.__file__).resolve().parent / PROVENANCE
saved = read_provenance(path, "livingproof-health")
if saved is None:
    raise SystemExit("Installed package has no valid provenance")
print(json.dumps(saved))
"""


def _verify_checksums(dist_dir: Path) -> tuple[Path, Path]:
    sums_path = dist_dir / "SHA256SUMS"
    if not sums_path.is_file():
        raise SystemExit(f"Missing {sums_path}")
    recorded = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        recorded[name] = digest

    wheels = sorted(dist_dir.glob("livingproof_health-*.whl"))
    sdists = sorted(dist_dir.glob("livingproof_health-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(f"Expected exactly one wheel and one sdist in {dist_dir}")
    wheel, sdist = wheels[0], sdists[0]
    if set(recorded) != {wheel.name, sdist.name}:
        raise SystemExit(f"SHA256SUMS entries {sorted(recorded)} do not match dist artifacts")
    for artifact in (wheel, sdist):
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual != recorded[artifact.name]:
            raise SystemExit(f"Checksum mismatch for {artifact.name}")
    return wheel, sdist


def main() -> None:
    dist_dir = ROOT / "dist"
    wheel, sdist = _verify_checksums(dist_dir)
    expected_version = os.environ.get("VERSION") or None
    expected_commit = os.environ.get("SOURCE_COMMIT") or None
    if (expected_version is None) != (expected_commit is None):
        raise SystemExit("VERSION and SOURCE_COMMIT must both be set for release smoke")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Verify source archive rebuilds cleanly with identical provenance.
        with tarfile.open(sdist) as archive:
            archive.extractall(tmp_path / "sdist", filter="data")
        source_dir = next((tmp_path / "sdist").iterdir())
        rebuilt_dir = tmp_path / "rebuilt"
        env = {k: v for k, v in os.environ.items() if not k.startswith("SETUPTOOLS_SCM_")}
        subprocess.run(
            ["uv", "build", "--offline", "--wheel", "--out-dir", str(rebuilt_dir)],
            cwd=source_dir,
            env=env,
            check=True,
            capture_output=True,
        )
        rebuilt_wheel = next(rebuilt_dir.glob("livingproof_health-*.whl"))
        with zipfile.ZipFile(wheel) as orig, zipfile.ZipFile(rebuilt_wheel) as rebuilt:
            orig_prov = json.loads(orig.read("livingproof_health/_build_provenance.json"))
            rebuilt_prov = json.loads(rebuilt.read("livingproof_health/_build_provenance.json"))
            if orig_prov != rebuilt_prov:
                raise SystemExit("Rebuilt sdist wheel provenance does not match dist wheel")
            if expected_version:
                require_recorded_release(orig_prov, expected_version, expected_commit)

        # Install the built wheel + pinned host CLI in an isolated environment and replay fixture.
        uv = shutil.which("uv")
        if not uv:
            raise SystemExit("uv is required for isolated package smoke verification")
        host_wheel = _obtain_wheel(tmp_path, HOST_WHEEL, HOST_URL, HOST_SHA256)
        common_wheel = _obtain_wheel(tmp_path, COMMON_WHEEL, COMMON_URL, COMMON_SHA256)

        env_dir = tmp_path / "venv"
        subprocess.run(
            [uv, "venv", "--python", sys.executable, "--no-python-downloads", str(env_dir)],
            check=True,
            capture_output=True,
        )
        python = env_dir / "bin" / "python"
        host_bin = env_dir / "bin" / "livingproof"
        standalone_bin = env_dir / "bin" / "livingproof-health"

        install_cmd = [uv, "pip", "install", "--python", str(python)]
        if os.environ.get("LIVINGPROOF_WHEEL_DIR"):
            install_cmd.append("--offline")
        install_cmd.extend([str(host_wheel), str(wheel), str(common_wheel)])
        subprocess.run(install_cmd, check=True, capture_output=True)
        subprocess.run([uv, "pip", "check", "--python", str(python)], check=True)

        discovery = subprocess.run(
            [str(host_bin), "capability", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        if "health" not in discovery.stdout:
            raise SystemExit("livingproof capability --help did not discover health plugin")

        version_out = subprocess.run(
            [str(host_bin), "capability", "health", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        if "identity source: recorded-build" not in version_out.stdout:
            raise SystemExit(f"Unexpected version output: {version_out.stdout}")
        if expected_version and f"Package: {expected_version};" not in version_out.stdout:
            raise SystemExit(
                f"Expected Package: {expected_version} in version output: {version_out.stdout}"
            )
        if expected_version:
            recorded = subprocess.run(
                [str(python), "-c", INSTALLED_PROVENANCE],
                check=False,
                capture_output=True,
                text=True,
            )
            if recorded.returncode != 0:
                raise SystemExit(
                    recorded.stderr.strip() or "Installed package provenance check failed"
                )
            require_recorded_release(json.loads(recorded.stdout), expected_version, expected_commit)

        replayed = subprocess.run(
            [
                str(host_bin),
                "capability",
                "health",
                "replay",
                str(ROOT / "tests/fixtures/simulation-pose.mcap"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        portable = tmp_path / "health.json"
        portable.write_text(replayed.stdout, encoding="utf-8")
        sought = subprocess.run(
            [str(standalone_bin), "seek", str(portable), "--time-ns", "4440000000"],
            check=True,
            capture_output=True,
            text=True,
        )
        if json.loads(sought.stdout)["items"]["base_pose"]["position"]["z"] != 0.7464:
            raise SystemExit(f"Unexpected seek output: {sought.stdout}")
        assessed = subprocess.run(
            [
                str(host_bin),
                "capability",
                "health",
                "assess",
                str(portable),
                "--minimum-m",
                "0.75",
                "--frame-id",
                "world",
            ],
            capture_output=True,
            text=True,
        )
        if assessed.returncode != 1 or json.loads(assessed.stdout)["status"] != "FAIL":
            raise SystemExit(f"Unexpected assess output ({assessed.returncode}): {assessed.stdout}")


if __name__ == "__main__":
    main()
