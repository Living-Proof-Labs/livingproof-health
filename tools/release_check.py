# SPDX-License-Identifier: Apache-2.0
"""Require the release tag and checkout to be the verified main commit."""

import os
from pathlib import Path
import re
import subprocess

SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _git(root, *args):
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _full_commit(value, label):
    text = (value or "").strip().lower()
    if not COMMIT.fullmatch(text):
        raise SystemExit(f"{label} must be the full verified commit")
    return text


def require_verified_release(root, version, release_tag, verified_commit):
    """Fail before packaging unless refs/tags/v$VERSION and HEAD match the commit."""
    if not SEMVER.fullmatch(version or ""):
        raise SystemExit("VERSION must be X.Y.Z before packaging")
    expected_tag = f"v{version}"
    if release_tag != expected_tag:
        raise SystemExit(f"Release tag {release_tag} is not {expected_tag}")
    verified = _full_commit(verified_commit, "VERIFIED_COMMIT")
    peeled = _git(root, "rev-parse", "--verify", f"refs/tags/{expected_tag}^{{commit}}")
    if peeled is None:
        raise SystemExit(f"Missing refs/tags/{expected_tag}")
    peeled = _full_commit(peeled, f"refs/tags/{expected_tag}")
    checkout = _git(root, "rev-parse", "--verify", "HEAD")
    if checkout is None:
        raise SystemExit("Checkout has no commit")
    checkout = _full_commit(checkout, "checkout")
    if peeled != verified or checkout != verified:
        raise SystemExit(f"Peeled tag {peeled} and checkout {checkout} must both equal {verified}")
    return verified


def main(root=None):
    require_verified_release(
        Path(root) if root is not None else Path(__file__).resolve().parents[1],
        os.environ["VERSION"],
        os.environ["RELEASE_TAG"],
        os.environ["VERIFIED_COMMIT"],
    )


if __name__ == "__main__":
    main()
