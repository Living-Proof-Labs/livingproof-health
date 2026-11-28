# SPDX-License-Identifier: Apache-2.0
"""Standalone viewer releases contain only deterministic owned code."""

import hashlib
import json
from pathlib import Path
import runpy
import zipfile

import pytest

from tools import package
from tools.release_assets import GitHubReleaseStore
from tools.smoke import _verify_checksums

ROOT = Path(__file__).resolve().parents[1]


def render():
    return runpy.run_path(str(ROOT / "examples/recorded-replay/static_viewer.py"))[
        "render_static_viewer"
    ]()


def test_viewer_is_reproducible_without_data_or_working_directory(tmp_path, monkeypatch):
    first = render().encode()
    monkeypatch.chdir(tmp_path)
    assert render().encode() == first
    assert b"loadDetails(location.hash, location.href)" in first
    assert b"__DATA__" not in first
    assert b'"samples":' not in first
    assert b'"run_id":' not in first
    assert b"default-src" in first


def test_package_and_smoke_require_exact_viewer_bytes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VERSION", "1.2.3")

    def build(*args, **kwargs):
        with zipfile.ZipFile("dist/livingproof_health-1.2.3-py3-none-any.whl", "w") as archive:
            archive.writestr(
                "livingproof_health/_build_provenance.json",
                json.dumps({"package_version": "1.2.3"}),
            )
        Path("dist/livingproof_health-1.2.3.tar.gz").write_bytes(b"source-fixture")

    monkeypatch.setattr(package.subprocess, "run", build)
    package.main()
    out = Path("dist")
    viewer = out / "livingproof-health-viewer.html"
    assert viewer.read_bytes() == render().encode()
    assert (
        f"{hashlib.sha256(viewer.read_bytes()).hexdigest()}  {viewer.name}\n"
        in (out / "SHA256SUMS").read_text()
    )
    _verify_checksums(out)
    viewer.write_bytes(b"modified")
    with pytest.raises(SystemExit, match="Checksum mismatch"):
        _verify_checksums(out)


def test_upload_uses_exact_filename_not_gh_label():
    names = ["livingproof-health-viewer.html", "SHA256SUMS"]
    seen = []

    def runner(command, **kwargs):
        path = Path(command[4])
        assert "#" not in str(path)
        assert path.read_bytes() == b"owned bytes"
        seen.append(path.name)
        return type("Result", (), {"returncode": 0})()

    store = GitHubReleaseStore("Living-Proof-Labs/livingproof-health", runner=runner)
    for name in names:
        store.upload("v1.2.3", name, b"owned bytes")
    assert seen == names
