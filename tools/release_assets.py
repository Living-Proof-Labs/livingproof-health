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
    result["action"] = "finalized"
    return result


def resume_draft(store, tag, files):
    """Reuse byte-identical draft assets, upload only missing ones, then publish.

    A mismatched asset is left untouched. A published release is not modified.
    A missing release is not created.
    """
    if not tag or not files:
        raise ReleaseError("A draft tag and its assets are required")
    if len(set(files)) != len(files):
        raise ReleaseError("Duplicate asset names")
    release = store.fetch(tag)
    if release is None:
        raise ReleaseError(f"No draft release {tag}; refusing to create one")
    if release.get("draft") is not True:
        raise ReleaseError(f"Refusing to modify published release {tag}")
    assets = release.get("assets") or []
    names = [asset.get("name") for asset in assets]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ReleaseError("Draft assets must have unique names")
    by_name = {asset["name"]: asset for asset in assets}
    unexpected = sorted(set(by_name) - set(files))
    if unexpected:
        raise ReleaseError(f"Unexpected draft assets: {unexpected}")
    for name, asset in by_name.items():
        if asset.get("state") != "uploaded":
            raise ReleaseError(f"Draft asset {name} is not fully uploaded")
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

    def fetch(self, tag):
        result = self._gh(["gh", "api", f"repos/{self.repository}/releases/tags/{tag}"])
        if result.returncode != 0:
            detail = (result.stderr or b"").decode("utf-8", "replace")
            if "Not Found" in detail or "HTTP 404" in detail:
                return None
            raise ReleaseError(detail.strip() or f"Unable to read release {tag}")
        return json.loads(result.stdout)

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
        descriptor, path = tempfile.mkstemp(prefix="health-asset-")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
            result = self._gh(["gh", "release", "upload", tag, f"{path}#{name}"])
        finally:
            os.unlink(path)
        if result.returncode != 0:
            raise ReleaseError(f"Unable to upload {name}")

    def publish(self, tag):
        result = self._gh(["gh", "release", "edit", tag, "--draft=false"])
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
