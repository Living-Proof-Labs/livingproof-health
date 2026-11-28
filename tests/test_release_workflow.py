# SPDX-License-Identifier: Apache-2.0
"""Verify release workflow pin, main-push gating, and packaging contract."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from tools.release_check import main as release_check_main
from tools.release_check import require_verified_release
from tools.smoke import require_recorded_release

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/verify.yml"
RENOVATE = ROOT / "renovate.json"


def _job_block(text: str, job: str) -> str:
    match = re.search(rf"^  {re.escape(job)}:\n", text, re.MULTILINE)
    assert match, f"job {job} not found"
    start = match.start()
    end = len(text)
    for later in re.finditer(r"^  [A-Za-z0-9_-]+:\s*$", text[match.end() :], re.MULTILINE):
        end = match.end() + later.start()
        break
    return text[start:end]


def test_release_workflow_pins_same_guidelines_tag_as_renovate():
    renovate = json.loads(RENOVATE.read_text(encoding="utf-8"))
    (preset,) = renovate["extends"]
    preset_tag = preset.rsplit("#", 1)[1]
    text = WORKFLOW.read_text(encoding="utf-8")
    expected_uses = (
        f"Living-Proof-Labs/collaboration-guidelines/.github/workflows/"
        f"semantic-release.yml@{preset_tag}"
    )
    assert expected_uses in text


def test_release_and_publish_run_on_main_pushes_and_not_on_pull_requests():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "\npermissions:\n  contents: read\n" in text
    assert "RELEASES_ENABLED" not in text

    release = _job_block(text, "release")
    assert "needs: verify" in release
    assert "    if: github.event_name == 'push' && github.ref == 'refs/heads/main'\n" in release
    assert "pull_request" not in release
    assert "contents: write" in release
    assert "draft-release: true" in release

    publish = _job_block(text, "publish")
    assert "needs: release" in publish
    assert "    if: needs.release.outputs.draft-created == 'true'\n" in publish
    assert "pull_request" not in publish
    assert "github.event_name" not in publish
    assert "ref: ${{ needs.release.outputs.git-tag }}" in publish
    assert "workflow_dispatch" not in text
    assert "--clobber" not in text
    check = publish.index("python tools/release_check.py")
    package = publish.index("task package")
    smoke = publish.index("task smoke")
    resume = publish.index("python3 tools/release_assets.py")
    assert check < package < smoke < resume
    assert "VERIFIED_COMMIT: ${{ github.sha }}" in publish
    assert "SOURCE_COMMIT: ${{ github.sha }}" in publish
    assert "dist/*.whl dist/*.tar.gz dist/livingproof-health-viewer.html dist/SHA256SUMS" in publish
    assert "DRAFT_CREATED: ${{ needs.release.outputs.draft-created }}" in publish
    smoke_source = (ROOT / "tools/smoke.py").read_text(encoding="utf-8")
    assert "SOURCE_COMMIT" in smoke_source
    assert "require_recorded_release" in smoke_source


def _git(root, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
    )
    return subprocess.check_output(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            "-C",
            str(root),
            *args,
        ],
        text=True,
        env=env,
    ).strip()


def _repo(path, *, annotated):
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "commit", "--allow-empty", "-m", "verified")
    if annotated:
        _git(path, "tag", "-a", "v1.2.3", "-m", "release")
    else:
        _git(path, "tag", "v1.2.3")
    return path, _git(path, "rev-parse", "HEAD")


def test_peeled_tag_and_checkout_must_equal_verified_commit(tmp_path):
    root, commit = _repo(tmp_path / "annotated", annotated=True)
    assert require_verified_release(root, "1.2.3", "v1.2.3", commit) == commit
    tag_object = _git(root, "rev-parse", "refs/tags/v1.2.3")
    assert tag_object != commit
    with pytest.raises(SystemExit, match="must both equal"):
        require_verified_release(root, "1.2.3", "v1.2.3", tag_object)

    light, light_commit = _repo(tmp_path / "lightweight", annotated=False)
    assert require_verified_release(light, "1.2.3", "v1.2.3", light_commit) == light_commit

    untagged = tmp_path / "untagged"
    untagged.mkdir()
    _git(untagged, "init", "-b", "main")
    _git(untagged, "commit", "--allow-empty", "-m", "verified")
    untagged_commit = _git(untagged, "rev-parse", "HEAD")
    with pytest.raises(SystemExit, match="Missing refs/tags/v1.2.3"):
        require_verified_release(untagged, "1.2.3", "v1.2.3", untagged_commit)
    with pytest.raises(SystemExit, match="is not v1.2.3"):
        require_verified_release(root, "1.2.3", "v1.2.4", commit)
    with pytest.raises(SystemExit, match="full verified commit"):
        require_verified_release(root, "1.2.3", "v1.2.3", commit[:12])

    (root / "later.txt").write_text("later\n", encoding="utf-8")
    _git(root, "add", "later.txt")
    _git(root, "commit", "-m", "later")
    with pytest.raises(SystemExit, match="must both equal"):
        require_verified_release(root, "1.2.3", "v1.2.3", commit)
    child = _git(root, "rev-parse", "HEAD")
    with pytest.raises(SystemExit, match="must both equal"):
        require_verified_release(root, "1.2.3", "v1.2.3", child)


def test_release_check_cli_accepts_only_the_verified_tag(tmp_path, monkeypatch):
    root, commit = _repo(tmp_path / "cli", annotated=True)
    monkeypatch.setenv("VERSION", "1.2.3")
    monkeypatch.setenv("RELEASE_TAG", "v1.2.3")
    monkeypatch.setenv("VERIFIED_COMMIT", commit)
    tags_before = _git(root, "tag", "--list")
    release_check_main(root)
    monkeypatch.setenv("VERIFIED_COMMIT", "b" * 40)
    with pytest.raises(SystemExit, match="must both equal"):
        release_check_main(root)
    assert _git(root, "tag", "--list") == tags_before


def test_recorded_release_requires_matching_version_and_revision():
    commit = "a" * 40
    good = {"package_version": "1.2.3", "identity": {"commit": commit, "state": "clean"}}
    require_recorded_release(good, "1.2.3", commit)
    with pytest.raises(SystemExit, match="package_version"):
        require_recorded_release(good, "1.2.4", commit)
    with pytest.raises(SystemExit, match="revision"):
        require_recorded_release(good, "1.2.3", "b" * 40)
    dirty = {"package_version": "1.2.3", "identity": {"commit": commit, "state": "dirty"}}
    with pytest.raises(SystemExit, match="clean"):
        require_recorded_release(dirty, "1.2.3", commit)
    with pytest.raises(SystemExit, match="revision"):
        require_recorded_release({"package_version": "1.2.3"}, "1.2.3", commit)


def test_evidence_gate_keeps_strict_checks_and_exact_count():
    probes = (ROOT / "tools/review/zstd_probes.py").read_text(encoding="utf-8")
    readme = (ROOT / "tools/review/README.md").read_text(encoding="utf-8")
    match = re.search(r"len\(cases\) == (\d+)", probes)
    assert match, "evidence gate must require an exact testcase count"
    count = int(match.group(1))
    assert '"failure", "error", "skipped"' in probes
    assert 'identity["checkout_tree"] == identity["head_tree"]' in probes
    assert "len(resources) == 41" in probes
    assert '["outcome"] == "PASS"' in probes
    assert f"the existing {count} tests" in readme
    assert f"JUnit has {count} passing cases" in readme
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    collected = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    found = re.findall(r"(\d+) tests collected", collected.stdout)
    assert found, collected.stdout
    assert count == int(found[-1])
