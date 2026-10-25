#!/usr/bin/env python3
"""Render CASE_STUDY.md to a self-contained HTML page and a PDF."""
from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import markdown
import websocket

ROOT = Path(__file__).resolve().parent
MD = ROOT / "CASE_STUDY.md"
PUBLIC_HTML = ROOT / "CASE_STUDY.html"
PUBLIC_PDF = ROOT / "CASE_STUDY.pdf"
SUBMISSION_HTML = ROOT / "CASE_STUDY_SUBMISSION.html"
SUBMISSION_PDF = ROOT / "CASE_STUDY_SUBMISSION.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9226

CSS = r"""
:root {
  --navy: #1b2b3f;
  --navy-2: #263c56;
  --ink: #202631;
  --muted: #66707d;
  --line: #d9dee6;
  --paper: #ffffff;
  --soft: #f5f7fa;
}
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: Arial, Helvetica, sans-serif;
  font-size: 10.5pt;
  line-height: 1.58;
}
.cover {
  min-height: 9.15in;
  padding: .62in .62in .5in;
  border-radius: 8px;
  background: var(--navy);
  color: #f4f7fb;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  page-break-after: always;
}
.cover .kicker { color: #a9bfd6; }
.cover h1 {
  font-size: 30pt;
  line-height: 1.05;
  letter-spacing: -.025em;
  margin: .35in 0 .12in;
  color: #ffffff;
  max-width: 5.6in;
}
.cover .dek {
  font-size: 15pt;
  line-height: 1.35;
  color: #c9d6e5;
  max-width: 5.4in;
  margin: 0;
}
.cover .byline { margin: .45in 0 0; font-size: 11pt; color: #e7edf5; }
.cover .note { margin: .12in 0 0; font-size: 9pt; color: #9fb3c9; }
.kicker {
  font-size: 8.5pt;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: bold;
}
.article-head { margin: 0 0 .28in; padding-bottom: .18in; border-bottom: 2px solid var(--navy); }
.article-meta { font-size: 9pt; color: var(--muted); margin: 6pt 0 0; }
.article-head h1 { font-size: 21pt; line-height: 1.12; margin: .08in 0 .06in; color: var(--navy); letter-spacing: -.02em; }
.article-head .dek { font-size: 12pt; line-height: 1.4; color: var(--muted); margin: 0; }
h2 {
  font-size: 16pt;
  line-height: 1.2;
  color: var(--navy);
  margin: 22pt 0 6pt;
  padding-top: 4pt;
  break-after: avoid;
}
h3 {
  font-size: 11.5pt;
  line-height: 1.3;
  color: var(--ink);
  margin: 13pt 0 3pt;
  break-after: avoid;
}
h4 {
  font-size: 10.5pt;
  line-height: 1.3;
  color: var(--ink);
  margin: 10pt 0 2pt;
  break-after: avoid;
}
p { margin: 0 0 6.5pt; orphans: 2; widows: 2; }
blockquote {
  margin: 10pt 0 12pt;
  padding: 10pt 13pt;
  background: var(--soft);
  border-left: 3px solid var(--navy);
  color: #2b3441;
  font-size: 10pt;
}
blockquote p:last-child { margin-bottom: 0; }
ul, ol { margin: 4pt 0 8pt 16pt; padding: 0; }
li { margin: 0 0 3pt; }
code {
  font-family: "SF Mono", Menlo, Consolas, monospace;
  font-size: 8.7pt;
  background: #eef1f5;
  border: 1px solid #e1e5eb;
  border-radius: 3px;
  padding: 0 3px;
}
pre {
  background: #f3f5f8;
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 8pt 9pt;
  overflow: hidden;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 7pt 0 10pt;
  break-inside: avoid;
}
pre code { background: none; border: 0; padding: 0; font-size: 8.3pt; line-height: 1.45; }
table {
  width: 100%;
  border-collapse: collapse;
  margin: 6pt 0 10pt;
  font-size: 8.4pt;
  break-inside: avoid;
}
th {
  background: var(--navy);
  color: #ffffff;
  text-align: left;
  padding: 5pt 7pt;
  border: 1px solid var(--navy);
  font-size: 8.5pt;
  letter-spacing: .02em;
}
td { padding: 3.5pt 6pt; border: 1px solid var(--line); vertical-align: top; }
tr:nth-child(even) td { background: #fafbfc; }
p:has(> img) { margin: 12pt 0 2pt; break-inside: avoid; break-after: avoid; page-break-after: avoid; text-align: center; }
p:has(> img) + p { break-before: avoid; page-break-before: avoid; break-inside: avoid; }
p:has(+ pre) { break-after: avoid; }
p:has(+ table) { break-after: avoid; }
.figure-block, .table-block { break-inside: avoid; page-break-inside: avoid; }
.figure-block img { margin-bottom: 2pt; }
.table-block table { margin-top: 2pt; }
.references p {
  font-size: 8.6pt;
  line-height: 1.42;
  margin: 0 0 6pt;
  padding-left: 14pt;
  text-indent: -14pt;
  break-inside: avoid;
}
.references a { color: var(--navy); }
.nowrap { white-space: nowrap; }
h2.appendix-start { break-before: page; page-break-before: always; }
.abstract-head {
  font-size: 9pt;
  letter-spacing: .16em;
  text-transform: uppercase;
  color: var(--navy);
  margin: 10pt 0 3pt;
  break-after: avoid;
}
img { max-width: 86%; height: auto; border: 1px solid var(--line); border-radius: 5px; }
p > em:only-child {
  display: block;
  margin: 3pt 0 12pt;
  font-size: 8.5pt;
  line-height: 1.4;
  color: var(--muted);
  text-align: left;
}
a { color: var(--navy); text-decoration: none; }
strong { color: #11161f; }
hr { border: 0; border-top: 1px solid var(--line); margin: 16pt 0; }
.footer { font-size: 8pt; color: var(--muted); }
@media print { a { color: var(--navy); } }
"""


def md_to_html() -> str:
    text = MD.read_text()
    marker = "**Abstract**"
    if marker in text:
        text = text[text.index(marker) + len(marker):].lstrip()
    text = text.replace("> **Abstract.**", "> **Abstract.**", 1)
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    # Keep captions attached to the figures and tables they describe.
    body = re.sub(
        r'(<p><img[^>]+></p>\s*)(<p><em>Figure \d+\..*?</em></p>)',
        r'<div class="figure-block">\1\2</div>',
        body,
        flags=re.S,
    )
    body = re.sub(
        r'(<p><strong>Table \d+\..*?</strong></p>\s*)(<table>.*?</table>)',
        r'<div class="table-block">\1\2</div>',
        body,
        flags=re.S,
    )
    body = re.sub(
        r'(<h2>References</h2>)(.*?)(?=<h2>Appendix A)',
        r'\1<div class="references">\2</div>',
        body,
        flags=re.S,
    )
    body = body.replace('<h2>Appendix A.', '<h2 class="appendix-start">Appendix A.', 1)
    return body


def build_html(submission: bool = False) -> None:
    body = md_to_html()
    if submission:
        cover = ""
        kicker = "Manuscript"
        article_meta = "Anonymous submission · October 2026"
        html_path = SUBMISSION_HTML
    else:
        cover = """<section class="cover">
  <div>
    <div class="kicker">Working paper · Case study</div>
    <h1>Directed Cross-Examination in Heterogeneous Multi-Model Agent Systems</h1>
    <p class="dek">A design-science case study of argument, state, and failure in a local LLM debate system.</p>
  </div>
  <div>
    <p class="byline">Derek Kramer<br>Independent researcher, Jakarta, Indonesia</p>
    <p class="note">October 2026 · Not peer reviewed</p>
  </div>
</section>"""
        kicker = "Working paper · Case study"
        article_meta = "Derek Kramer · Independent researcher, Jakarta, Indonesia · October 2026"
        html_path = PUBLIC_HTML

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Directed Cross-Examination in Heterogeneous Multi-Model Agent Systems</title>
<style>{CSS}</style>
</head>
<body>
{cover}
<article>
<header class="article-head">
  <div class="kicker">{kicker}</div>
  <h1>Directed Cross-Examination in Heterogeneous Multi-Model Agent Systems</h1>
  <p class="dek">A Design-Science Case Study</p>
  <p class="article-meta">{article_meta}</p>
</header>
<h2 class="abstract-head">Abstract</h2>
{body}
</article>
</body>
</html>
"""
    html_path.write_text(page)
    print(f"wrote {html_path}")


def build_pdf(submission: bool = False) -> None:
    html_path = SUBMISSION_HTML if submission else PUBLIC_HTML
    pdf_path = SUBMISSION_PDF if submission else PUBLIC_PDF
    run_label = "Anonymous submission" if submission else "Directed Cross-Examination in Heterogeneous Multi-Model Agent Systems"
    profile = Path(tempfile.mkdtemp(prefix="case-pdf-"))
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
        time.sleep(2.5)
        send("Runtime.evaluate", {"expression": "Promise.all(Array.from(document.images).map(i => i.complete ? true : new Promise(r => { i.onload = r; i.onerror = r; })))", "awaitPromise": True})
        time.sleep(.5)
        result = send("Page.printToPDF", {
            "printBackground": True,
            "paperWidth": 8.5,
            "paperHeight": 11,
            "marginTop": .62,
            "marginBottom": .62,
            "marginLeft": .75,
            "marginRight": .75,
            "displayHeaderFooter": True,
            "headerTemplate": "<span></span>",
            "footerTemplate": f"<div style='width:100%;font:8px Arial;color:#66707d;padding:0 .75in;display:flex;justify-content:space-between'><span>{run_label}</span><span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>",
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", action="store_true", help="build the public edition")
    parser.add_argument("--submission", action="store_true", help="build the anonymized submission edition")
    args = parser.parse_args()
    if not args.public and not args.submission:
        args.public = args.submission = True
    if args.public:
        build_html(submission=False)
        build_pdf(submission=False)
    if args.submission:
        build_html(submission=True)
        build_pdf(submission=True)
