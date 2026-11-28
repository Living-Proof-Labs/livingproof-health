# SPDX-License-Identifier: Apache-2.0
"""Resume a draft release without overwriting or duplicating assets."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


class ReleaseError(RuntimeError):
    """The release cannot be resumed safely."""


def apply_release_run(store, *, draft_created, tag, files):
    """Publish nothing when this run has no draft. Otherwise resume that draft."""
    if draft_created != "true" or not tag:
        return {"action": "no-release"}
    result = resume_draft(store, tag, files)
    result.setdefault("action", "finalized")
    return result


def _assets_by_name(release):
    assets = release.get("assets") or []
    names = [asset.get("name") for asset in assets]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ReleaseError("Draft assets must have unique names")
    return {asset["name"]: asset for asset in assets}


def _same_uploaded_bytes(store, tag, by_name, files):
    if set(by_name) != set(files):
        return False
    for name, asset in by_name.items():
        if asset.get("state") != "uploaded":
            return False
        if store.download(tag, asset) != files[name]:
            return False
    return True


def resume_draft(store, tag, files):
    """Reuse byte-identical draft assets, upload only missing ones, then publish.

    A mismatched asset is left untouched. A published release is not modified.
    A missing release is not created. A published release whose assets already
    match is left as it is.
    """
    if not tag or not files:
        raise ReleaseError("A draft tag and its assets are required")
    if len(set(files)) != len(files):
        raise ReleaseError("Duplicate asset names")
    release = store.fetch(tag)
    if release is None:
        raise ReleaseError(f"No draft release {tag}; refusing to create one")
    by_name = _assets_by_name(release)
    if release.get("draft") is not True:
        if _same_uploaded_bytes(store, tag, by_name, files):
            return {"reused": sorted(by_name), "uploaded": [], "action": "already-published"}
        raise ReleaseError(f"Refusing to modify published release {tag}")
    unexpected = sorted(set(by_name) - set(files))
    if unexpected:
        raise ReleaseError(f"Unexpected draft assets: {unexpected}")
    for name, asset in by_name.items():
        if asset.get("state") != "uploaded":
            raise ReleaseError(
                f"Draft asset {name} is not fully uploaded. "
                "Delete that incomplete draft asset and rerun; refusing to overwrite it."
            )
        remote = store.download(tag, asset)
        if remote != files[name]:
            raise ReleaseError(f"Draft asset {name} bytes do not match; refusing to overwrite")
    uploaded = []
    for name, data in files.items():
        if name in by_name:
            continue
        store.upload(tag, name, data)
        uploaded.append(name)
    store.publish(tag)
    return {"reused": sorted(by_name), "uploaded": uploaded}


class GitHubReleaseStore:
    """Read and update one GitHub release through gh. Never creates a tag."""

    def __init__(self, repository, runner=None):
        if not repository or "/" not in repository:
            raise ReleaseError("GITHUB_REPOSITORY is required")
        self.repository = repository
        self._run = runner or subprocess.run

    def _gh(self, args):
        return self._run(args, check=False, capture_output=True)

    def _list_releases(self):
        found = []
        for page in range(1, 101):
            result = self._gh(
                [
                    "gh",
                    "api",
                    f"repos/{self.repository}/releases?per_page=100&page={page}",
                ]
            )
            if result.returncode != 0:
                detail = (result.stderr or b"").decode("utf-8", "replace")
                raise ReleaseError(detail.strip() or "Unable to list releases")
            batch = json.loads(result.stdout or b"null")
            if not isinstance(batch, list):
                raise ReleaseError("Release list was not a list")
            found.extend(batch)
            if len(batch) < 100:
                return found
        raise ReleaseError("Release list did not end")

    def fetch(self, tag):
        # The tag-name endpoint returns 404 for drafts, so list releases and read by id.
        matches = [item for item in self._list_releases() if item.get("tag_name") == tag]
        if not matches:
            return None
        if len(matches) != 1:
            raise ReleaseError(f"Expected exactly one release tagged {tag}, found {len(matches)}")
        release_id = matches[0].get("id")
        if type(release_id) is not int or release_id < 1:
            raise ReleaseError(f"Release tagged {tag} has no id")
        result = self._gh(["gh", "api", f"repos/{self.repository}/releases/{release_id}"])
        if result.returncode != 0:
            detail = (result.stderr or b"").decode("utf-8", "replace")
            raise ReleaseError(detail.strip() or f"Unable to read release {release_id}")
        release = json.loads(result.stdout)
        if release.get("id") != release_id or release.get("tag_name") != tag:
            raise ReleaseError(f"Release {release_id} does not match {tag}")
        return release

    def download(self, tag, asset):
        result = self._gh(
            [
                "gh",
                "api",
                f"repos/{self.repository}/releases/assets/{asset['id']}",
                "-H",
                "Accept: application/octet-stream",
            ]
        )
        if result.returncode != 0:
            raise ReleaseError(f"Unable to read draft asset {asset.get('name')}")
        return result.stdout

    def upload(self, tag, name, data):
        if Path(name).name != name or name in {"", ".", ".."}:
            raise ReleaseError("Release asset name must be a basename")
        with tempfile.TemporaryDirectory(prefix="health-assets-") as directory:
            path = Path(directory) / name
            path.write_bytes(data)
            result = self._gh(["gh", "release", "upload", tag, str(path)])
        if result.returncode != 0:
            raise ReleaseError(f"Unable to upload {name}")

    def publish(self, tag):
        release = self.fetch(tag)
        if release is None or release.get("draft") is not True:
            raise ReleaseError(f"Refusing to modify published release {tag}")
        release_id = release["id"]
        result = self._gh(
            [
                "gh",
                "api",
                "--method",
                "PATCH",
                f"repos/{self.repository}/releases/{release_id}",
                "-F",
                "draft=false",
            ]
        )
        if result.returncode != 0:
            raise ReleaseError(f"Unable to publish draft {tag}")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    draft_created = os.environ.get("DRAFT_CREATED", "")
    tag = args[0] if args else ""
    if draft_created != "true" or not tag:
        print(json.dumps({"action": "no-release"}))
        return 0
    files = {}
    for item in args[1:]:
        path = Path(item)
        if not path.is_file():
            raise SystemExit(f"Missing release asset {item}")
        if path.name in files:
            raise SystemExit(f"Duplicate release asset {path.name}")
        files[path.name] = path.read_bytes()
    if not files:
        raise SystemExit("Release assets are required")
    store = GitHubReleaseStore(os.environ.get("GITHUB_REPOSITORY", ""))
    try:
        outcome = apply_release_run(store, draft_created=draft_created, tag=tag, files=files)
    except ReleaseError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(outcome))
    return 0


if __name__ == "__main__":
    sys.exit(main())
