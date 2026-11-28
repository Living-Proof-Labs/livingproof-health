# SPDX-License-Identifier: Apache-2.0
"""Draft asset recovery stays local and does not publish to GitHub."""

import json
from pathlib import Path

from tools.release_assets import GitHubReleaseStore, ReleaseError, apply_release_run, resume_draft

FILES = {"wheel.whl": b"wheel", "pkg.tar.gz": b"sdist", "SHA256SUMS": b"sums\n"}
TAG = "v1.2.3"


class MemoryStore:
    def __init__(self, *, draft, assets, tag=TAG):
        self.tag = tag
        self.draft = draft
        self.assets = dict(assets)
        self.uploads = []
        self.publishes = 0
        self.fetches = 0

    def fetch(self, tag):
        self.fetches += 1
        if tag != self.tag:
            return None
        return {
            "tag_name": tag,
            "draft": self.draft,
            "assets": [{"id": name, "name": name, "state": "uploaded"} for name in self.assets],
        }

    def download(self, tag, asset):
        return self.assets[asset["name"]]

    def upload(self, tag, name, data):
        if self.draft is not True:
            raise AssertionError("upload touched a published release")
        if name in self.assets:
            raise AssertionError(f"duplicate upload {name}")
        self.assets[name] = data
        self.uploads.append(name)

    def publish(self, tag):
        if self.draft is not True:
            raise AssertionError("published release edited again")
        self.draft = False
        self.publishes += 1


def test_interrupted_draft_reuses_matching_assets_then_publishes():
    partial = MemoryStore(draft=True, assets={"wheel.whl": FILES["wheel.whl"]})
    result = apply_release_run(partial, draft_created="true", tag=TAG, files=FILES)
    assert result["action"] == "finalized"
    assert result["reused"] == ["wheel.whl"]
    assert result["uploaded"] == ["pkg.tar.gz", "SHA256SUMS"]
    assert partial.draft is False
    assert partial.assets == FILES
    assert partial.publishes == 1
    _refuse_published_retry(partial)

    complete = MemoryStore(draft=True, assets=dict(FILES))
    finished = resume_draft(complete, TAG, FILES)
    assert finished["uploaded"] == []
    assert complete.uploads == []
    assert complete.draft is False
    assert complete.assets == FILES


def _refuse_published_retry(store):
    before = dict(store.assets)
    uploads = list(store.uploads)
    publishes = store.publishes
    result = resume_draft(store, TAG, FILES)
    assert result["uploaded"] == []
    assert result["action"] == "already-published"
    assert store.assets == before
    assert store.uploads == uploads
    assert store.publishes == publishes


def test_mismatched_draft_bytes_are_rejected():
    store = MemoryStore(
        draft=True,
        assets={"wheel.whl": b"other", "pkg.tar.gz": FILES["pkg.tar.gz"]},
    )
    try:
        resume_draft(store, TAG, FILES)
    except ReleaseError as exc:
        assert "bytes do not match" in str(exc)
    else:
        raise AssertionError("mismatched bytes were accepted")
    assert store.draft is True
    assert store.assets["wheel.whl"] == b"other"
    assert store.uploads == []
    assert store.publishes == 0

    extra = MemoryStore(draft=True, assets={"wheel.whl": FILES["wheel.whl"], "extra.bin": b"x"})
    try:
        resume_draft(extra, TAG, FILES)
    except ReleaseError as exc:
        assert "Unexpected" in str(exc)
    else:
        raise AssertionError("unexpected draft asset was published")
    assert extra.draft is True
    assert extra.assets["extra.bin"] == b"x"
    assert extra.uploads == []


def test_published_release_is_not_overwritten_or_duplicated():
    store = MemoryStore(draft=False, assets=dict(FILES))
    changed = dict(FILES)
    changed["wheel.whl"] = b"replacement"
    try:
        resume_draft(store, TAG, changed)
    except ReleaseError as exc:
        assert "published" in str(exc)
    else:
        raise AssertionError("published release was overwritten")
    assert store.assets == FILES
    assert store.uploads == []
    assert store.publishes == 0

    missing = MemoryStore(draft=True, assets={})
    missing.tag = "absent"

    def fetch(tag):
        missing.fetches += 1
        return None

    missing.fetch = fetch
    try:
        apply_release_run(missing, draft_created="true", tag=TAG, files=FILES)
    except ReleaseError as exc:
        assert "refusing to create" in str(exc)
    else:
        raise AssertionError("missing release was created")
    assert missing.uploads == []
    assert missing.publishes == 0


def test_ordinary_no_release_rerun_does_not_upload_or_publish():
    published = MemoryStore(draft=False, assets=dict(FILES))
    outcome = apply_release_run(
        published,
        draft_created="false",
        tag=TAG,
        files={"wheel.whl": b"new"},
    )
    assert outcome == {"action": "no-release"}
    assert published.fetches == 0
    assert published.assets == FILES
    assert published.uploads == []
    assert published.publishes == 0

    absent = MemoryStore(draft=True, assets={})
    outcome = apply_release_run(absent, draft_created="false", tag="", files=FILES)
    assert outcome == {"action": "no-release"}
    assert absent.fetches == 0
    assert absent.uploads == []
    assert absent.publishes == 0


def _result(returncode=0, stdout=b"", stderr=b""):
    class Result:
        pass

    result = Result()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _fake_github(releases, full_by_id, asset_bytes):
    """Model GitHub: the tag endpoint 404s for every release, including drafts."""
    calls = []
    uploads = []
    patches = []

    def runner(command, check, capture_output):
        calls.append(list(command))
        if command[:3] == ["gh", "release", "upload"]:
            path = command[4]
            name = Path(path).name
            uploads.append((name, Path(path).read_bytes()))
            return _result()
        if "--method" in command and "PATCH" in command:
            patches.append(list(command))
            return _result(stdout=b'{"draft":false}')
        url = command[2]
        if "/releases/tags/" in url:
            return _result(returncode=1, stderr=b"gh: Not Found (HTTP 404)\n")
        if "per_page=100&page=" in url:
            page = int(url.rsplit("page=", 1)[1])
            batch = releases[(page - 1) * 100 : page * 100]
            return _result(stdout=json.dumps(batch).encode())
        if "/releases/assets/" in url:
            asset_id = int(url.split("/releases/assets/")[1].split("?")[0])
            return _result(stdout=asset_bytes[asset_id])
        if "/releases/" in url:
            release_id = int(url.rstrip("/").split("/")[-1])
            return _result(stdout=json.dumps(full_by_id[release_id]).encode())
        return _result(returncode=1, stderr=b"unexpected request\n")

    return runner, calls, uploads, patches


def _summary(release_id, tag, draft):
    return {"id": release_id, "tag_name": tag, "draft": draft}


def test_tag_endpoint_404_still_resumes_the_listed_draft():
    release_id = 431143709
    summaries = [_summary(1000 + index, f"v0.0.{index}", False) for index in range(100)]
    summaries.append(_summary(release_id, TAG, True))
    full = {
        "id": release_id,
        "tag_name": TAG,
        "draft": True,
        "assets": [{"id": 11, "name": "wheel.whl", "state": "uploaded"}],
    }
    runner, calls, uploads, patches = _fake_github(
        summaries, {release_id: full}, {11: FILES["wheel.whl"]}
    )
    store = GitHubReleaseStore("Living-Proof-Labs/livingproof-health", runner=runner)
    result = resume_draft(store, TAG, FILES)
    assert result["reused"] == ["wheel.whl"]
    assert result["uploaded"] == ["pkg.tar.gz", "SHA256SUMS"]
    assert [name for name, _ in uploads] == ["pkg.tar.gz", "SHA256SUMS"]
    assert uploads[0][1] == FILES["pkg.tar.gz"]
    assert any("page=2" in part for command in calls for part in command)
    assert any(
        f"/releases/{release_id}" in part and "PATCH" not in command
        for command in calls
        for part in command
    )
    assert patches and any(f"/releases/{release_id}" in part for part in patches[0])
    assert "draft=false" in patches[0]
    assert all("--clobber" not in command for command in calls)
    assert not any("/releases/tags/" in part for command in calls for part in command)


def test_zero_matching_releases_are_not_created():
    summaries = [_summary(1000 + index, f"v0.0.{index}", False) for index in range(100)]
    summaries.append(_summary(9, "v9.9.9", True))
    runner, calls, uploads, patches = _fake_github(summaries, {}, {})
    store = GitHubReleaseStore("Living-Proof-Labs/livingproof-health", runner=runner)
    try:
        resume_draft(store, TAG, FILES)
    except ReleaseError as exc:
        assert "refusing to create" in str(exc)
    else:
        raise AssertionError("missing release was created")
    assert uploads == [] and patches == []
    assert any("page=2" in part for command in calls for part in command)


def test_multiple_matching_releases_fail_closed():
    summaries = [_summary(1000 + index, f"v0.0.{index}", False) for index in range(99)]
    summaries.append(_summary(21, TAG, True))
    summaries.append(_summary(22, TAG, False))
    runner, calls, uploads, patches = _fake_github(summaries, {}, {})
    store = GitHubReleaseStore("Living-Proof-Labs/livingproof-health", runner=runner)
    try:
        resume_draft(store, TAG, FILES)
    except ReleaseError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("duplicate tag was accepted")
    assert uploads == [] and patches == []
    assert any("page=2" in part for command in calls for part in command)
    assert not any(
        "/releases/21" in part or "/releases/22" in part for command in calls for part in command
    )


def test_incomplete_draft_asset_tells_the_operator_to_delete_it():
    release_id = 77
    full = {
        "id": release_id,
        "tag_name": TAG,
        "draft": True,
        "assets": [{"id": 3, "name": "wheel.whl", "state": "starter"}],
    }
    runner, calls, uploads, patches = _fake_github(
        [_summary(release_id, TAG, True)], {release_id: full}, {}
    )
    store = GitHubReleaseStore("Living-Proof-Labs/livingproof-health", runner=runner)
    try:
        resume_draft(store, TAG, FILES)
    except ReleaseError as exc:
        message = str(exc)
    else:
        raise AssertionError("incomplete asset was overwritten")
    assert "wheel.whl" in message
    assert "Delete that incomplete draft asset" in message
    assert uploads == [] and patches == []


def test_matching_published_release_is_not_published_again():
    release_id = 88
    assets = [
        {"id": 1, "name": "wheel.whl", "state": "uploaded"},
        {"id": 2, "name": "pkg.tar.gz", "state": "uploaded"},
        {"id": 3, "name": "SHA256SUMS", "state": "uploaded"},
    ]
    full = {"id": release_id, "tag_name": TAG, "draft": False, "assets": assets}
    runner, calls, uploads, patches = _fake_github(
        [_summary(release_id, TAG, False)],
        {release_id: full},
        {1: FILES["wheel.whl"], 2: FILES["pkg.tar.gz"], 3: FILES["SHA256SUMS"]},
    )
    store = GitHubReleaseStore("Living-Proof-Labs/livingproof-health", runner=runner)
    result = resume_draft(store, TAG, FILES)
    assert result["uploaded"] == []
    assert result["action"] == "already-published"
    assert uploads == [] and patches == []
    changed = dict(FILES)
    changed["wheel.whl"] = b"replacement"
    try:
        resume_draft(store, TAG, changed)
    except ReleaseError as exc:
        assert "published" in str(exc)
    else:
        raise AssertionError("published bytes were replaced")
    assert uploads == [] and patches == []


def test_github_commands_do_not_clobber_or_create_releases():
    calls = []

    def runner(command, check, capture_output):
        calls.append(list(command))

        class Result:
            returncode = 0
            stdout = b""
            stderr = b""

        return Result()

    store = GitHubReleaseStore("Living-Proof-Labs/livingproof-health", runner=runner)
    store.upload(TAG, "SHA256SUMS", b"abc")
    assert calls[0][:3] == ["gh", "release", "upload"]
    assert "--clobber" not in calls[0]
    assert "create" not in calls[0]
    text = (
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath("tools/release_assets.py")
        .read_text(encoding="utf-8")
    )
    assert "--clobber" not in text
    assert "releases/tags/" not in text
    assert "release create" not in text
    assert "git tag" not in text
