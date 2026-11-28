# SPDX-License-Identifier: Apache-2.0
"""Build standard Python release artifacts and SHA256SUMS for livingproof-health."""

import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import zipfile

SEMVER_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def main() -> None:
    version = os.environ.get("VERSION", "0.0.0")
    if not SEMVER_RE.fullmatch(version):
        raise SystemExit("Expected VERSION=X.Y.Z for release package metadata")

    out = Path("dist")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    env = {**os.environ, "SETUPTOOLS_SCM_PRETEND_VERSION": version}
    subprocess.run(["uv", "build", "--offline", "--out-dir", str(out)], check=True, env=env)

    wheel = out / f"livingproof_health-{version}-py3-none-any.whl"
    sdist = out / f"livingproof_health-{version}.tar.gz"
    if not wheel.is_file() or not sdist.is_file():
        raise SystemExit(f"Expected {wheel.name} and {sdist.name} in {out}")

    expected_roots = {"livingproof_health", f"livingproof_health-{version}.dist-info"}
    provenance = None
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            path = Path(entry.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0] not in expected_roots
            ):
                raise ValueError(f"Unexpected wheel path: {entry.filename}")
            data = archive.read(entry)
            if data.startswith(b"\x7fELF") or path.suffix in {".so", ".dll", ".dylib", ".pyc"}:
                raise ValueError(f"Pure Python wheel cannot include native/bytecode file: {path}")
            if entry.filename == "livingproof_health/_build_provenance.json":
                provenance = json.loads(data.decode("utf-8"))

    if not provenance or provenance.get("package_version") != version:
        raise ValueError(f"Wheel provenance package_version does not match {version}: {provenance}")

    renderer = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "examples/recorded-replay/static_viewer.py")
    )
    viewer = out / "livingproof-health-viewer.html"
    viewer.write_text(renderer["render_static_viewer"](), encoding="utf-8")
    files = [wheel, sdist, viewer]
    (out / "SHA256SUMS").write_text(
        "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
