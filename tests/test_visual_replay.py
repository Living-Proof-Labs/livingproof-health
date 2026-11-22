# SPDX-License-Identifier: Apache-2.0
"""Presentation contract in real JavaScript; browser exercise is separately retained."""

import importlib.util
import json
from pathlib import Path
import subprocess

from livingproof_health.snapshots import Replay

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("demo", ROOT / "examples/recorded-replay/demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_as_of_lookup_epoch_duplicates_gaps_and_boundaries():
    path = ROOT / "examples/recorded-replay/presentation.js"
    program = """
const {presentationIndex: at} = require(process.argv[1]);
const epoch = 1700000000000000000n;
const rows = [0n,1n,1n,100n].map(n=>({time_ns:String(epoch+n)}));
const got = [-1n,0n,1n,2n,100n,101n,0n].map(n=>at(rows,epoch+n));
if(JSON.stringify(got)!==JSON.stringify([-1,0,2,2,3,3,0])) throw Error(got);
if(at([],epoch)!==-1) throw Error('empty');
"""
    subprocess.run(["node", "-e", program, str(path)], check=True, timeout=30)


def test_html_embedding_cannot_close_script(tmp_path):
    attack = "</script><script>window.robotInjected=true</script><img src=x onerror=alert(1)>"
    replay = Replay([{"time_ns": 1700000000000000001, "items": {"robot": attack}}])
    target = tmp_path / "viewer.html"
    demo.write_viewer(target, replay, {"input": {"provenance": attack}, "limitations": attack})
    html = target.read_text()
    assert attack not in html
    embedded = html.split('<script id="data" type="application/json">')[1].split("</script>")[0]
    assert json.loads(embedded)["replay"]["snapshots"][0]["items"]["robot"] == attack
    assert json.loads(embedded)["replay"]["snapshots"][0]["time_ns"] == "1700000000000000001"
    assert "innerHTML" not in html
    assert "connect-src 'none'" in html


def test_example_generates_self_contained_viewer(tmp_path):
    target = tmp_path / "demo"
    demo.demonstrate(demo.MCAP, target)
    viewer = (target / "viewer.html").read_text()
    assert "__DATA__" not in viewer and "__PRESENTATION__" not in viewer
    assert "genuine pinned G1 simulation recording" in viewer
    assert "<script src=" not in viewer
    assert "<link " not in viewer


def test_generated_controls_in_dom_model_not_visual_browser(tmp_path):
    """Execute the actual generated script, without claiming a real DOM/layout test."""
    epoch = 1700000000000000000
    replay = Replay(
        [
            {
                "time_ns": epoch,
                "items": {"base_pose": {"position": {"z": 0.8}, "frame_id": "world"}},
            },
            {"time_ns": epoch + 1, "items": {"posture": "earlier duplicate"}},
            {"time_ns": epoch + 1, "items": {"robot": "<img src=x onerror=alert(1)>"}},
            {"time_ns": epoch + 100},
        ]
    )
    target = tmp_path / "viewer.html"
    demo.write_viewer(
        target,
        replay,
        {"input": {"provenance": "synthetic unit fixture"}, "limitations": "sampled only"},
    )
    program = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const html = fs.readFileSync(process.argv[1], 'utf8');
const embedded = html.split('<script id="data" type="application/json">')[1].split('</script>')[0];
const script = html.split('</script><script>')[1].split('</script>')[0];
const nodes = {};
function get(id) { return nodes[id] ??= {textContent:'', value:'', disabled:false, events:{},
 setAttribute(){}, addEventListener(name, fn){this.events[name]=fn;}}; }
get('data').textContent = embedded;
vm.runInNewContext(script, {document:{getElementById:get}});
function exact(t) {get('exact').value=t;get('go').events.click();}
exact('1700000000000000001');
assert.equal(get('observed').textContent,'1700000000000000001');
assert.equal(get('height').textContent,'Not reported');
assert.equal(get('posture').textContent,'Not reported');
assert(get('items').textContent.includes('<img src=x'));
exact('1700000000000000050');
assert.equal(get('age').textContent,'49');
assert(get('state').textContent.includes('gap'));
get('previous').events.click();
assert.equal(get('playhead').textContent,'1700000000000000001');
get('next').events.click();
assert.equal(get('observed').textContent,'1700000000000000100');
assert(get('state').textContent.includes('Time-only'));
exact('0'); assert.equal(get('observed').textContent,'None');
exact('1700000000000000101'); assert.equal(get('age').textContent,'1');
assert(get('state').textContent.includes('After last'));
exact('1e9'); assert(get('error').textContent.includes('canonical'));
"""
    subprocess.run(["node", "-e", program, str(target)], check=True, timeout=30)
