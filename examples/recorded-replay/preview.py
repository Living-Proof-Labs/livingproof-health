# SPDX-License-Identifier: Apache-2.0
"""Build a local-only card and trusted static replay viewer from verified details."""

import argparse
import hashlib
import html
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlencode

from details import MAX_BYTES, load_details
from static_viewer import render_static_viewer


def build_preview(source, digest, run, configuration, trial, output):
    # Reuse the released local CLI validation; the browser checks again at use time.
    load_details(source, digest, run, configuration, trial)
    with source.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Details exceed the 16 MiB preview limit")
    # Bind the bytes copied below, even if the source changed after validation.
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Details changed while preparing preview")
    shell = render_static_viewer()
    query = urlencode(
        {
            "file": "data/health.json",
            "sha256": digest,
            "run": run,
            "configuration": configuration,
            "trial": trial,
        }
    )
    label = html.escape(f"{run} / {configuration} / trial {trial}")
    card = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<title>Local G1 card preview</title><style>body{{font:18px/1.5 system-ui;max-width:48rem;margin:auto;padding:24px}}article{{border:1px solid;padding:24px;border-radius:12px}}a{{display:inline-block;padding:12px}}p{{overflow-wrap:anywhere}}</style>
<h1>Local G1 card preview</h1><p>Development demonstration, not a production report. Health viewer {html.escape(version("livingproof-health"))}.</p>
<article aria-label="Health"><h2>Health</h2><p>Advisory · observations only · no grade</p><p>{label}</p>
<a href="viewer.html#{html.escape(query, quote=True)}">Open replay</a></article></html>"""
    output.mkdir()  # Never overwrite another preview.
    (output / "data").mkdir()
    (output / "data/health.json").write_bytes(raw)
    (output / "viewer.html").write_text(shell, encoding="utf-8")
    (output / "index.html").write_text(card, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("details", type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--trial-index", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        build_preview(
            args.details,
            args.sha256,
            args.run_id,
            args.configuration,
            args.trial_index,
            args.output,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot prepare preview: {exc}\n")
    print(
        f"Local preview ready: {args.output}/index.html. Serve this directory on loopback; do not publish."
    )


if __name__ == "__main__":
    main()
