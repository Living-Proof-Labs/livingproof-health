# SPDX-License-Identifier: Apache-2.0
"""Verify release workflow pin, gating, and packaging contract."""

import json
from pathlib import Path
import re

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


def test_release_and_publish_require_verified_main_and_explicit_activation():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "\npermissions:\n  contents: read\n" in text

    release = _job_block(text, "release")
    assert "needs: verify" in release
    assert "github.event_name == 'push'" in release
    assert "github.ref == 'refs/heads/main'" in release
    assert "vars.RELEASES_ENABLED == 'true'" in release
    assert "contents: write" in release
    assert "draft-release: true" in release

    publish = _job_block(text, "publish")
    assert "needs: release" in publish
    assert "needs.release.outputs.draft-created == 'true'" in publish
    assert "ref: ${{ needs.release.outputs.git-tag }}" in publish
    assert "task package && task smoke" in publish
    assert "gh release upload" in publish
    assert "dist/*.whl dist/*.tar.gz dist/SHA256SUMS" in publish
    assert 'gh release edit "$RELEASE_TAG" --draft=false' in publish
    assert publish.index("gh release upload") < publish.index("gh release edit")
