# SPDX-License-Identifier: Apache-2.0
"""Local sampled-height indicator beside the released recorded-data viewer."""

import argparse
import html
import json
from pathlib import Path
import sys

from livingproof_health.indicator import sampled_height_indicator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "recorded-replay"))
from details import load_details  # noqa: E402
from demo import write_viewer  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("details", type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--trial-index", required=True, type=int)
    parser.add_argument("--minimum-m", type=float, help="Explicit scenario threshold; no default")
    parser.add_argument("--frame-id")
    parser.add_argument("--criterion-source", help="Versioned scenario/configuration citation")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        supplied = [
            args.minimum_m is not None,
            args.frame_id is not None,
            args.criterion_source is not None,
        ]
        if any(supplied) and not all(supplied):
            raise ValueError(
                "Supply --minimum-m, --frame-id and --criterion-source together, or omit all three"
            )
        criterion = (
            {
                "minimum_m": args.minimum_m,
                "frame_id": args.frame_id,
                "source": args.criterion_source,
            }
            if all(supplied)
            else None
        )
        replay, provenance = load_details(
            args.details, args.sha256, args.run_id, args.configuration, args.trial_index
        )
        indicator = sampled_height_indicator(replay, criterion=criterion)
        labels = {
            "not-applicable": "Not applicable — no scenario height criterion",
            "unevaluated": "Unevaluated — insufficient matching recorded evidence",
            "below-threshold": "Recorded height below configured threshold",
            "at-or-above-threshold": "Recorded heights at or above configured threshold",
        }
        esc = lambda value: html.escape(str(value))  # noqa: E731

        def measured(value, unit):
            return "Not reported" if value is None else f"{esc(value)} {unit}"

        title = labels[indicator["state"]]
        page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<title>Health · sampled base height</title><style>body{{font:18px/1.5 system-ui;max-width:50rem;margin:auto;padding:24px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}a{{display:inline-block;padding:12px}}p{{overflow-wrap:anywhere}}</style>
<h1>Health · sampled base height</h1><p>Local advisory demonstration · no grade</p><h2>{esc(title)}</h2>
<p>Minimum recorded height: <strong>{measured(indicator["minimum_m"], "m")}</strong> at {measured(indicator["time_ns"], "ns")}; frame: {esc(indicator["frame_id"] or "Not selected")}.</p>
<p>Configured threshold: {measured(args.minimum_m, "m")}. Below is a recorded violation; equality is not below.</p>
<p>Unavailable samples: {esc(indicator["unavailable_count"])}; total samples: {esc(indicator["sample_count"])}.</p>
<p>Sampled simulator base height is not orientation. No between-sample, whole-trial, physical robot or safety conclusion. Missing telemetry is not healthy telemetry. A flip scenario without this criterion receives no implied upright requirement.</p>
<a href="viewer.html">Inspect recorded replay</a><details><summary>Criterion and indicator</summary><pre>{esc(json.dumps(indicator, indent=2))}</pre></details>
<details><summary>Verified input identity</summary><pre>{esc(json.dumps(provenance["input"], indent=2))}</pre></details></html>"""
        args.output.mkdir()
        write_viewer(args.output / "viewer.html", replay, provenance, exclusive=True)
        (args.output / "indicator.json").write_text(
            json.dumps(indicator, indent=2, allow_nan=False) + "\n"
        )
        (args.output / "index.html").write_text(page)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot prepare height demo: {exc}\n")
    print(json.dumps(indicator, allow_nan=False))
    print(f"Open {args.output}/index.html using a loopback server. Keep this demo local.")


if __name__ == "__main__":
    main()
