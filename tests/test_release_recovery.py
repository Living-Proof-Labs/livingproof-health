# SPDX-License-Identifier: Apache-2.0
"""Draft asset recovery stays local and does not publish to GitHub."""

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
    try:
        resume_draft(store, TAG, FILES)
    except ReleaseError as exc:
        assert "published" in str(exc)
    else:
        raise AssertionError("published release was modified")
    assert store.assets == before
    assert store.uploads == uploads
    assert store.publishes == 1


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
    store.publish(TAG)
    assert calls[0][:3] == ["gh", "release", "upload"]
    assert "--clobber" not in calls[0]
    assert "create" not in calls[0]
    assert calls[1] == ["gh", "release", "edit", TAG, "--draft=false"]
    text = (
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath("tools/release_assets.py")
        .read_text(encoding="utf-8")
    )
    assert "--clobber" not in text
    assert "release create" not in text
    assert "git tag" not in text
