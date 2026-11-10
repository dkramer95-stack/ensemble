#!/usr/bin/env python3
"""Build the workshop paper, study design, feasibility memo, and writing sample."""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import markdown
import websocket

ROOT = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9228

DOCS = {
    "workshop": {
        "md": ROOT / "WORKSHOP_PAPER.md",
        "html": ROOT / "WORKSHOP_PAPER.html",
        "pdf": ROOT / "WORKSHOP_PAPER.pdf",
        "label": "Directed Cross-Examination · Workshop paper",
        "font": "10.5pt",
        "line": "1.38",
        "margin": "0.85in 0.95in 0.8in",
    },
    "study": {
        "md": ROOT / "STUDY_DESIGN.md",
        "html": ROOT / "STUDY_DESIGN.html",
        "pdf": ROOT / "STUDY_DESIGN.pdf",
        "label": "Evaluating Directed Cross-Examination · Study design",
        "font": "9.2pt",
        "line": "1.1",
        "margin": "0.8in 0.9in 0.75in",
    },
    "feasibility": {
        "md": ROOT / "EVALUATION_FEASIBILITY.md",
        "html": ROOT / "EVALUATION_FEASIBILITY.html",
        "pdf": ROOT / "EVALUATION_FEASIBILITY.pdf",
        "label": "Evaluation Feasibility · Decision memo",
        "font": "10.5pt",
        "line": "1.3",
        "margin": "0.85in 0.95in 0.8in",
    },
    "phd": {
        "md": ROOT / "PHD_WRITING_SAMPLE.md",
        "html": ROOT / "PHD_WRITING_SAMPLE.html",
        "pdf": ROOT / "PHD_WRITING_SAMPLE.pdf",
        "label": "Directed Cross-Examination · Writing sample",
        "font": "11pt",
        "line": "1.62",
        "margin": "1in 1in 0.85in",
    },
}


def css(font: str, line: str, margin: str) -> str:
    return f"""
@page {{ size: Letter; margin: {margin}; }}
* {{ box-sizing: border-box; }}
html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{
  margin: 0; color: #14171c; background: #fff;
  font-family: "Times New Roman", Times, serif;
  font-size: {font}; line-height: {line};
}}
h1 {{
  font: 700 20pt/1.18 Arial, Helvetica, sans-serif;
  letter-spacing: -.02em; margin: 0 0 6pt; color: #111;
}}
h1 + p {{ font: 10.5pt/1.4 Arial, Helvetica, sans-serif; color: #333; margin: 0 0 14pt; }}
h2 {{
  font: 700 12.5pt/1.25 Arial, Helvetica, sans-serif;
  margin: 16pt 0 4pt; color: #111; break-after: avoid;
}}
h3 {{
  font: 700 10.5pt/1.3 Arial, Helvetica, sans-serif;
  margin: 10pt 0 2pt; color: #111; break-after: avoid;
}}
p {{ margin: 0 0 5.5pt; orphans: 2; widows: 2; }}
blockquote {{
  margin: 7pt 0 8pt; padding: 6pt 9pt; background: #f4f5f7;
  border-left: 2px solid #777; font-size: .95em;
}}
blockquote p:last-child {{ margin-bottom: 0; }}
ul, ol {{ margin: 3pt 0 7pt 17pt; padding: 0; }}
li {{ margin: 0 0 2.5pt; }}
code {{ font-family: "Courier New", monospace; font-size: .84em; background: #f1f2f4; padding: 0 2px; }}
pre {{
  font-family: "Courier New", monospace; font-size: .78em; line-height: 1.35;
  background: #f4f5f7; border: 1px solid #ddd; padding: 6pt 7pt;
  white-space: pre-wrap; word-break: break-word; margin: 5pt 0 8pt; break-inside: avoid;
}}
pre code {{ background: none; padding: 0; }}
table {{ width: 100%; border-collapse: collapse; margin: 5pt 0 9pt; font: 8pt/1.3 Arial, Helvetica, sans-serif; }}
th {{ background: #222; color: #fff; text-align: left; border: 1px solid #222; padding: 3pt 4.5pt; }}
td {{ border: 1px solid #bbb; padding: 3pt 4.5pt; vertical-align: top; }}
tr:nth-child(even) td {{ background: #f7f7f8; }}
p:has(> img) {{ text-align: center; margin: 8pt 0 2pt; break-inside: avoid; break-after: avoid; }}
img {{ max-width: 88%; height: auto; border: 1px solid #bbb; }}
p:has(> img) + p {{ break-before: avoid; break-inside: avoid; }}
p > em:only-child {{ display: block; font-size: .9em; color: #444; margin: 2pt 0 9pt; }}
.figure-block, .table-block {{ break-inside: avoid; page-break-inside: avoid; }}
.figure-block img {{ margin-bottom: 2pt; }}
p:has(+ pre) {{ break-after: avoid; }}
p:has(+ table) {{ break-after: avoid; }}
"""


def md_to_html(text: str) -> str:
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    body = __import__("re").sub(
        r'(<p><img[^>]+></p>\s*)(<p><em>Figure \d+\..*?</em></p>)',
        r'<div class="figure-block">\1\2</div>',
        body,
        flags=__import__("re").S,
    )
    body = __import__("re").sub(
        r'(<p><strong>Table \d+\..*?</strong></p>\s*)(<table>.*?</table>)',
        r'<div class="table-block">\1\2</div>',
        body,
        flags=__import__("re").S,
    )
    return body


def print_pdf(html_path: Path, pdf_path: Path, label: str) -> None:
    profile = Path(tempfile.mkdtemp(prefix="short-pdf-"))
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--disable-gpu",
        f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
        "--remote-allow-origins=*", "--window-size=1200,1600", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=.5)
                break
            except Exception:
                time.sleep(.1)
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?url=about:blank", method="PUT")
        target = json.loads(urllib.request.urlopen(req, timeout=5).read())
        ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=60)
        counter = [0]

        def send(method, params=None):
            counter[0] += 1
            ident = counter[0]
            ws.send(json.dumps({"id": ident, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == ident:
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    return msg.get("result", {})

        send("Page.enable")
        send("Page.navigate", {"url": html_path.as_uri()})
        time.sleep(2.2)
        send("Runtime.evaluate", {"expression": "Promise.all(Array.from(document.images).map(i => i.complete ? true : new Promise(r => { i.onload = r; i.onerror = r; })))", "awaitPromise": True})
        time.sleep(.3)
        result = send("Page.printToPDF", {
            "printBackground": True,
            "paperWidth": 8.5,
            "paperHeight": 11,
            "marginTop": .8,
            "marginBottom": .75,
            "marginLeft": .9,
            "marginRight": .9,
            "displayHeaderFooter": True,
            "headerTemplate": "<span></span>",
            "footerTemplate": f"<div style='width:100%;font:7.5px Arial;color:#555;padding:0 .9in;display:flex;justify-content:space-between'><span>{label}</span><span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>",
        })
        pdf_path.write_bytes(base64.b64decode(result["data"]))
        print(f"wrote {pdf_path}")
        ws.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


def build(key: str) -> None:
    cfg = DOCS[key]
    text = cfg["md"].read_text()
    body = md_to_html(text)
    page = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{cfg['label']}</title>
<style>{css(cfg['font'], cfg['line'], cfg['margin'])}</style></head>
<body>{body}</body>
</html>
"""
    cfg["html"].write_text(page)
    print(f"wrote {cfg['html']}")
    print_pdf(cfg["html"], cfg["pdf"], cfg["label"])


if __name__ == "__main__":
    import sys
    keys = sys.argv[1:] or list(DOCS)
    for key in keys:
        build(key)
