# SPDX-License-Identifier: Apache-2.0
"""Exercise generated file:// viewers in offline Chromium; retain screenshots and results."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--python", default=str(ROOT / ".venv/bin/python"), help="Prepared Health dev Python"
)
parser.add_argument("--browser", default="/usr/bin/chromium")
parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
output = args.output.resolve()
checks = []


def generate(name, rows=None):
    target = output / name
    command = [args.python, str(ROOT / "examples/recorded-replay/demo.py"), "--output", str(target)]
    if rows is not None:
        source = output / f"{name}-synthetic.json"
        source.write_text(json.dumps({"format": "livingproof-health/1", "snapshots": rows}))
        command += ["--portable-json", "--input", str(source)]
    # The prepared environment is sufficient; no uv invocation or dependency fetch here.
    env = os.environ.copy()
    env["PATH"] = str(Path(args.python).resolve().parent) + ":" + env["PATH"]
    # Keep the venv bin path even when its python is a symlink.
    env["PATH"] = str(Path(args.python).absolute().parent) + ":" + env["PATH"]
    subprocess.run(command, check=True, capture_output=True, text=True, env=env, timeout=90)
    if rows is not None:
        # Synthetic browser fixtures remain clearly labeled in the generated page.
        relabel = """
import json, runpy, sys
from pathlib import Path
api = runpy.run_path(sys.argv[1])
target = Path(sys.argv[2])
report = json.loads((target / 'comparison.json').read_text())
report['input']['provenance'] += ' — synthetic browser contract fixture, not a robot trial'
api['write_json'](target / 'comparison.json', report)
api['write_viewer'](target / 'viewer.html', api['Replay'].from_json((target / 'replay.json').read_text()), report)
"""
        subprocess.run(
            [
                args.python,
                "-c",
                relabel,
                str(ROOT / "examples/recorded-replay/demo.py"),
                str(target),
            ],
            check=True,
            env=env,
        )
    return target / "viewer.html"


normal = generate("genuine")
epoch = 1700000000000000000
attack = '</script><script>window.robotInjected=true</script><img src="https://invalid.example/x" onerror="window.robotInjected=true">'
synthetic = generate(
    "synthetic",
    [
        {
            "time_ns": str(epoch),
            "items": {"base_pose": {"frame_id": "world", "unit": "m", "position": {"z": 0.8}}},
        },
        {"time_ns": str(epoch + 1), "items": {"duplicate": "earlier", "posture": "standing"}},
        {
            "time_ns": str(epoch + 1),
            "items": {"duplicate": "last", "robot": attack, "base_pose": {"frame_id": attack}},
        },
        {"time_ns": str(epoch + 100)},
        {"time_ns": str(epoch + 200), "items": {"base_pose": None}},
    ],
)
empty = generate("empty", [])
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.browser, headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        offline=True, viewport={"width": 1280, "height": 1000}, device_scale_factor=1
    )
    network, errors = [], []
    context.route(
        "**/*",
        lambda route: (network.append(route.request.url), route.abort())
        if route.request.url.startswith(("http:", "https:"))
        else route.continue_(),
    )
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))

    def text(id):
        return page.locator("#" + id).inner_text()

    def go(time):
        page.locator("#exact").fill(str(time))
        page.locator("#exact").press("Enter")
        assert text("playhead") == str(time)

    page.goto(normal.as_uri())
    assert "genuine pinned" in text("provenance")
    go(4_440_000_000)
    assert text("height") == "0.74637" and text("age") == "0"
    page.screenshot(path=str(output / "normal-desktop.png"), full_page=True)
    page.locator("#timeline").focus()
    page.locator("#timeline").press("ArrowRight")
    assert text("playhead") == "4460000000"
    page.locator("#timeline").press("ArrowLeft")
    assert text("playhead") == "4440000000"
    page.locator("#next").click()
    assert text("playhead") == "4460000000"
    page.locator("#previous").click()
    assert text("playhead") == "4440000000"
    go(4_440_000_001)
    assert text("observed") == "4440000000" and text("age") == "1"
    assert "gap" in text("state")
    checks.append("genuine: exact/forward/backward/keyboard/buttons/between-samples")

    page.goto(synthetic.as_uri())
    assert "user-supplied; not authenticated" in text("provenance")
    go(epoch + 1)
    assert text("observed") == str(epoch + 1)
    assert '"duplicate": "last"' in text("items")
    assert text("height") == text("posture") == "Not reported"
    assert text("frame") == attack
    assert not page.evaluate("Boolean(window.robotInjected)")
    assert page.locator("img").count() == 0
    assert "earlier" in text("duplicates") and "last" in text("duplicates")
    checks.append("synthetic: adjacent epoch nanoseconds/last duplicate/partial fields/injection")
    go(epoch + 50)
    assert text("observed") == str(epoch + 1) and text("age") == "49"
    go(epoch - 1)
    assert text("observed") == "None" and text("height") == "Not reported"
    page.locator("#next").click()
    assert text("playhead") == str(epoch)
    go(epoch + 201)
    assert text("observed") == str(epoch + 200) and text("age") == "1"
    assert "After last" in text("state")
    page.locator("#previous").click()
    assert text("playhead") == str(epoch + 200)
    assert text("height") == "Not reported"
    go(epoch + 100)
    assert "Time-only" in text("state") and text("height") == text("frame") == "Not reported"
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(output / "missing-mobile.png"), full_page=True)
    page.locator("#exact").fill("1e9")
    page.locator("#go").click()
    assert "canonical decimal" in text("error") and text("playhead") == str(epoch + 100)
    checks.append("synthetic: gaps/before-first/after-last/null/time-only/narrow/invalid input")
    page.goto(empty.as_uri())
    assert "Empty replay" in text("state")
    assert page.locator("#timeline").is_disabled()
    assert page.locator("#previous").is_disabled() and page.locator("#next").is_disabled()
    go(epoch + 1)
    assert text("observed") == "None"
    assert not network and not errors, (network, errors)
    checks.append("empty valid; offline context; zero network attempts; zero JavaScript errors")
    result = {
        "browser": browser.version,
        "offline": True,
        "checks": checks,
        "network_requests": network,
        "page_errors": errors,
        "synthetic_label": "Synthetic contract fixture, not a robot trial",
        "genuine_input": "tests/fixtures/original-recording/media/mcap/trial-01.mcap",
        "files": {
            str(f.relative_to(output)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in output.rglob("*")
            if f.is_file()
        },
    }
    (output / "browser-results.json").write_text(json.dumps(result, indent=2) + "\n")
    browser.close()
print(json.dumps({"checks": checks, "output": str(output)}, indent=2))
