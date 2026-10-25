#!/usr/bin/env python3
"""Build TOCHI-style public and anonymized PDFs from CASE_STUDY.md.

This is a CSS typeset approximation of the ACM TOCHI journal layout. It is not
generated with acmart because TeX is not installed on this machine.
"""
from __future__ import annotations

import argparse
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
MD = ROOT / "CASE_STUDY.md"
TITLE = "Directed Cross-Examination in Heterogeneous Multi-Model Agent Systems"
SUBTITLE = "A Design-Science Case Study"
DATE = "October 2026"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9227

CSS = r"""
@page {
  size: Letter;
  margin: 0.9in 1in 0.85in;
}
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0;
  color: #111;
  background: #fff;
  font-family: "Times New Roman", Times, serif;
  font-size: 10pt;
  line-height: 1.42;
}
.acm-meta {
  font: 8pt/1.4 Arial, Helvetica, sans-serif;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: #444;
  border-bottom: 1px solid #999;
  padding-bottom: 5pt;
  margin-bottom: 14pt;
}
h1.title {
  font: 700 19pt/1.2 Arial, Helvetica, sans-serif;
  letter-spacing: -.015em;
  margin: 0 0 6pt;
  color: #111;
}
.authors {
  font: 11pt/1.4 Arial, Helvetica, sans-serif;
  margin: 0 0 2pt;
  color: #111;
}
.affiliation { font: 9pt/1.4 Arial, Helvetica, sans-serif; color: #444; margin: 0 0 14pt; }
.acm-block {
  border-top: 1px solid #bbb;
  border-bottom: 1px solid #bbb;
  padding: 7pt 0;
  margin: 0 0 14pt;
  font: 8.2pt/1.4 Arial, Helvetica, sans-serif;
  color: #333;
}
.abstract {
  margin: 0 0 12pt;
  padding: 8pt 10pt;
  background: #f4f5f7;
}
.abstract h2, .ccs h2 {
  font: 700 9pt/1.2 Arial, Helvetica, sans-serif;
  letter-spacing: .12em;
  text-transform: uppercase;
  margin: 0 0 4pt;
  color: #111;
}
.abstract p { margin: 0 0 6pt; font-size: 9.4pt; }
.ccs { margin: 0 0 8pt; font-size: 9pt; }
.ccs p { margin: 0 0 4pt; }
.keywords { font-size: 9pt; margin: 0 0 16pt; }
h2 {
  font: 700 12.5pt/1.25 Arial, Helvetica, sans-serif;
  margin: 18pt 0 5pt;
  color: #111;
  break-after: avoid;
}
h3 {
  font: 700 10.5pt/1.3 Arial, Helvetica, sans-serif;
  margin: 12pt 0 3pt;
  color: #111;
  break-after: avoid;
}
h4 {
  font: 700 10pt/1.3 Arial, Helvetica, sans-serif;
  margin: 10pt 0 2pt;
  color: #111;
  break-after: avoid;
}
p { margin: 0 0 6pt; orphans: 2; widows: 2; }
blockquote {
  margin: 8pt 0 9pt;
  padding: 7pt 10pt;
  background: #f4f5f7;
  border-left: 2px solid #777;
  font-size: 9.4pt;
}
blockquote p:last-child { margin-bottom: 0; }
ul, ol { margin: 4pt 0 8pt 18pt; padding: 0; }
li { margin: 0 0 3pt; }
code {
  font-family: "Courier New", monospace;
  font-size: 8.4pt;
  background: #f1f2f4;
  padding: 0 2px;
}
pre {
  font-family: "Courier New", monospace;
  font-size: 7.8pt;
  line-height: 1.35;
  background: #f4f5f7;
  border: 1px solid #ddd;
  padding: 7pt 8pt;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 6pt 0 9pt;
  break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: 7.8pt; }
table {
  width: 100%;
  border-collapse: collapse;
  margin: 6pt 0 10pt;
  font: 7.8pt/1.35 Arial, Helvetica, sans-serif;
}
th {
  background: #222;
  color: #fff;
  text-align: left;
  border: 1px solid #222;
  padding: 3.5pt 5pt;
}
td { border: 1px solid #bbb; padding: 3.5pt 5pt; vertical-align: top; }
tr:nth-child(even) td { background: #f7f7f8; }
p:has(> img) { text-align: center; margin: 9pt 0 2pt; break-inside: avoid; break-after: avoid; }
img { max-width: 86%; height: auto; border: 1px solid #bbb; }
p:has(> img) + p { break-before: avoid; break-inside: avoid; }
p > em:only-child { display: block; font-size: 8.2pt; color: #444; margin: 3pt 0 10pt; }
.figure-block, .table-block { break-inside: avoid; page-break-inside: avoid; }
.figure-block img { margin-bottom: 2pt; }
p:has(+ pre) { break-after: avoid; }
p:has(+ table) { break-after: avoid; }
h2.appendix-start { break-before: page; page-break-before: always; }
.acm-refs { margin: 5pt 0 0 0; padding: 0; list-style: none; counter-reset: ref; font-size: 8.2pt; line-height: 1.35; }
.acm-refs li {
  counter-increment: ref;
  margin: 0 0 5pt;
  padding-left: 18pt;
  text-indent: -18pt;
}
.acm-refs li::before { content: "[" counter(ref) "] "; }
.acm-refs a { color: #111; }
"""

REFERENCES = [
    """Yilun Du, Shuang Li, Antonio Torralba, Joshua B. Tenenbaum, and Igor Mordatch. 2023. Improving Factuality and Reasoning in Language Models through Multiagent Debate. arXiv:2305.14325. https://doi.org/10.48550/arXiv.2305.14325""",
    """Tian Liang, Zhiwei He, Wenxiang Jiao, Xing Wang, Yan Wang, Rui Wang, Yujiu Yang, Shuming Shi, and Zhaopeng Tu. 2024. Encouraging Divergent Thinking in Large Language Models through Multi-Agent Debate. In Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing. arXiv:2305.19118. https://doi.org/10.48550/arXiv.2305.19118""",
    """Geoffrey Irving, Paul Christiano, and Dario Amodei. 2018. AI Safety via Debate. arXiv:1805.00899. https://doi.org/10.48550/arXiv.1805.00899""",
    """Akbir Khan, John Hughes, Dan Valentine, Laura Ruis, Kshitij Sachan, Ansh Radhakrishnan, Edward Grefenstette, Samuel R. Bowman, Tim Rocktäschel, and Ethan Perez. 2024. Debating with More Persuasive LLMs Leads to More Truthful Answers. arXiv:2402.06782. https://doi.org/10.48550/arXiv.2402.06782""",
    """Xuezhi Wang, Jason Wei, Dale Schuurmans, Quoc Le, Ed Chi, Sharan Narang, Aakanksha Chowdhery, and Denny Zhou. 2023. Self-Consistency Improves Chain of Thought Reasoning in Language Models. In International Conference on Learning Representations. arXiv:2203.11171. https://doi.org/10.48550/arXiv.2203.11171""",
    """Lianmin Zheng, Wei-Lin Chiang, Ying Sheng, Siyuan Zhuang, Zhanghao Wu, Yonghao Zhuang, Zi Lin, Zhuohan Li, Dacheng Li, Eric P. Xing, Hao Zhang, Joseph E. Gonzalez, and Ion Stoica. 2023. Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. In Advances in Neural Information Processing Systems 36. arXiv:2306.05685. https://doi.org/10.48550/arXiv.2306.05685""",
    """Chi-Min Chan, Weize Chen, Yusheng Su, Jianxuan Yu, Wei Xue, Shanghang Zhang, Jie Fu, and Zhiyuan Liu. 2023. ChatEval: Towards Better LLM-based Evaluators through Multi-Agent Debate. arXiv:2308.07201. https://doi.org/10.48550/arXiv.2308.07201""",
    """Qingyun Wu, Gagan Bansal, Jieyu Zhang, Yiran Wu, Beibin Li, Erkang Zhu, Li Jiang, Xiaoyun Zhang, Shaokun Zhang, Jiale Liu, Ahmed Hassan Awadallah, Ryen W. White, Doug Burger, and Chi Wang. 2023. AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation. arXiv:2308.08155. https://doi.org/10.48550/arXiv.2308.08155""",
    """Alan R. Hevner, Salvatore T. March, Jinsoo Park, and Sudha Ram. 2004. Design Science in Information Systems Research. MIS Quarterly 28, 1 (2004), 75-105. https://doi.org/10.2307/25148625""",
    """Per Runeson and Martin Höst. 2009. Guidelines for Conducting and Reporting Case Study Research in Software Engineering. Empirical Software Engineering 14, 2 (2009), 131-164. https://doi.org/10.1007/s10664-008-9102-8""",
]

REPLACEMENTS = [
    ("(Du et al., 2023; Liang et al., 2024)", "[1, 2]"),
    ("(Irving et al., 2018; Khan et al., 2024)", "[3, 4]"),
    ("Du et al. (2023)", "Du et al. [1]"),
    ("Liang et al. (2024)", "Liang et al. [2]"),
    ("Irving et al. (2018)", "Irving et al. [3]"),
    ("Khan et al. (2024)", "Khan et al. [4]"),
    ("Wang et al. (2023)", "Wang et al. [5]"),
    ("Zheng et al. (2023)", "Zheng et al. [6]"),
    ("Chan et al. (2023)", "Chan et al. [7]"),
    ("AutoGen (Wu et al., 2023)", "AutoGen [8]"),
    ("(Hevner et al., 2004)", "[9]"),
    ("Runeson and Höst (2009)", "Runeson and Höst [10]"),
]

CCS = """<p>• Human-centered computing → Human computer interaction (HCI); HCI design and evaluation methods; Empirical studies in HCI.</p>
<p>• Computing methodologies → Multi-agent systems; Natural language processing.</p>
<p>• Software and its engineering → Software design engineering.</p>"""


def md(text: str) -> str:
    return markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )


def source_parts():
    text = MD.read_text()
    intro = text.index("## 1. Introduction")
    refs = text.index("## References")
    app = text.index("## Appendix A")
    abstract_start = text.index("**Abstract**") + len("**Abstract**")
    keywords_start = text.index("**Keywords:**")
    abstract_md = text[abstract_start:keywords_start].strip()
    keywords = text[keywords_start + len("**Keywords:**"):intro].strip().strip("*")
    body_md = text[intro:refs]
    for old, new in REPLACEMENTS:
        body_md = body_md.replace(old, new)
    return abstract_md, keywords, body_md, text[app:]


def build_html(submission: bool) -> Path:
    abstract_md, keywords, body_md, app_md = source_parts()
    body_html = md(body_md)
    app_html = md(app_md).replace("<h2>Appendix A.", '<h2 class="appendix-start">Appendix A.', 1)
    abstract_html = md(abstract_md)
    author = "Anonymous Author(s)" if submission else "Derek Kramer"
    affiliation = "Anonymous submission" if submission else "Independent Researcher, Jakarta, Indonesia"
    meta = "ACM Transactions on Computer-Human Interaction · " + ("Anonymous submission" if submission else "Manuscript submitted for review")
    refs = "".join(f"<li>{r}</li>" for r in REFERENCES)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{TITLE}</title>
<style>{CSS}</style>
</head>
<body>
<div class="acm-meta">{meta}</div>
<h1 class="title">{TITLE}</h1>
<div class="authors">{author}</div>
<div class="affiliation">{affiliation} · {DATE}</div>
<div class="acm-block"><b>ACM Reference Format:</b><br>{author}. 2026. {TITLE}: {SUBTITLE}. ACM Trans. Comput.-Hum. Interact. Manuscript submitted for review.</div>
<div class="abstract"><h2>Abstract</h2>{abstract_html}</div>
<div class="ccs"><h2>CCS Concepts</h2>{CCS}</div>
<p class="keywords"><b>Keywords:</b> {keywords}</p>
{body_html}
<h2>References</h2>
<ol class="acm-refs">{refs}</ol>
{app_html}
</body>
</html>
"""
    name = "CASE_STUDY_TOCHI_ANON.html" if submission else "CASE_STUDY_TOCHI.html"
    path = ROOT / name
    path.write_text(page)
    print(f"wrote {path}")
    return path


def print_pdf(html_path: Path, pdf_path: Path, submission: bool) -> None:
    footer = "Anonymous submission · ACM TOCHI" if submission else "Derek Kramer · ACM TOCHI"
    profile = Path(tempfile.mkdtemp(prefix="tochi-pdf-"))
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
        time.sleep(.4)
        result = send("Page.printToPDF", {
            "printBackground": True,
            "paperWidth": 8.5,
            "paperHeight": 11,
            "marginTop": .85,
            "marginBottom": .8,
            "marginLeft": .95,
            "marginRight": .95,
            "displayHeaderFooter": True,
            "headerTemplate": "<span></span>",
            "footerTemplate": f"<div style='width:100%;font:7.5px Arial;color:#555;padding:0 .95in;display:flex;justify-content:space-between'><span>{footer}</span><span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>",
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
    parser.add_argument("--submission", action="store_true", help="build only the anonymized version")
    args = parser.parse_args()
    if args.submission:
        print_pdf(build_html(True), ROOT / "CASE_STUDY_TOCHI_ANON.pdf", True)
    else:
        print_pdf(build_html(False), ROOT / "CASE_STUDY_TOCHI.pdf", False)
        print_pdf(build_html(True), ROOT / "CASE_STUDY_TOCHI_ANON.pdf", True)
