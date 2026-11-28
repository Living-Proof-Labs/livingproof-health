# SPDX-License-Identifier: Apache-2.0
"""Deterministic trusted viewer shell; contains no recording or report data."""

from pathlib import Path


def render_static_viewer():
    directory = Path(__file__).parent
    template = (directory / "viewer.html").read_text()
    script = template.split('<script id="data" type="application/json">__DATA__</script><script>')[
        1
    ].split("</script>")[0]
    script = script.replace("__PRESENTATION__", (directory / "presentation.js").read_text())
    script = script.replace(
        "const data = JSON.parse(document.getElementById('data').textContent);",
        "const data = await loadDetails(location.hash, location.href);",
    )
    shell = template.split('<script id="data"')[0].replace("<main>", "<main hidden>")
    shell = shell.replace("connect-src 'none'", "connect-src 'self'")
    shell += '<p id="load-status" role="alert">Loading verified recorded data…</p><noscript>JavaScript is required for this local preview.</noscript><script>\n'
    shell += (directory / "loader.js").read_text()
    shell += (
        "\naddEventListener('hashchange', () => { document.querySelector('main').hidden=true; location.reload(); });\n(async () => { try {\n"
        + script
    )
    shell += "\ndocument.querySelector('main').hidden=false; document.getElementById('load-status').hidden=true;\n} catch(error) { document.getElementById('load-status').textContent='Cannot open replay: ' + error.message; } })();\n</script></body></html>"
    return shell
