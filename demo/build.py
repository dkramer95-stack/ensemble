#!/usr/bin/env python3
"""Render one ensemble run as a single self-contained HTML page.

Standard library only. No network, no external CSS/JS/fonts/images, no analytics.

Usage:
    python3 build.py --run runs/<run-dir> --out index.html

The page is generated from the run's own files:
    prompt.md        the prompt (falls back to meta.json)
    meta.json        run metadata (created_at, wall_seconds, judge block)
    results.json     one row per provider (status, latency, model, answer text)
    judge.md         the judge synthesis (falls back to judge.json)

Sanitisation is enforced, not assumed: local absolute paths are scrubbed and the
build refuses to write a page containing the local home directory, the local
username, or anything shaped like an API key.
"""

import argparse
import datetime
import getpass
import html
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

BG = "#FAF9F6"
INK = "#16161B"
MUTED = "#5E5E69"
FAINT = "#8B8B95"
LINE = "#E5E1D8"
LINE_STRONG = "#D5D0C4"
CARD = "#FFFFFF"
OK = "#0B8F6A"
FAIL = "#B4483A"

# provider accents used when a run does not carry its own
FALLBACK_ACCENTS = {
    "kimi": "#5B5BD6",
    "codex": "#0B8F6A",
    "gemini": "#8B5CF6",
    "deepseek": "#2F6BFF",
}

# a path is anything absolute and local enough to leak where the run happened
PATH_RE = re.compile(
    r"(?:file://)?/(?:Users|home|Applications|opt|private|var|tmp|Volumes)/[^\s\"'<>)]*"
)
WIN_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+")
KEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,})\b"
)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def scrub(text):
    """Remove local absolute paths from any text taken out of the run."""
    if not text:
        return ""
    out = PATH_RE.sub("[local path]", str(text))
    out = WIN_PATH_RE.sub("[local path]", out)
    return out


def inline_md(text):
    """Escape, then render the small subset of inline markdown the run uses."""
    out = html.escape(scrub(text), quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`([^`]+?)`", r"<code>\1</code>", out)
    return out


def blocks_md(text):
    """Render blank-line separated paragraphs."""
    body = scrub(text).strip()
    if not body:
        return ""
    parts = [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", body) if p.strip()]
    return "".join("<p>" + inline_md(p) + "</p>" for p in parts)


def word_count(text):
    return len((text or "").split())


def fmt_secs(value):
    try:
        return "{:.1f} s".format(float(value))
    except (TypeError, ValueError):
        return "--"


def fmt_date(stamp):
    """'2026-11-10 10:47:14' -> '10 November 2026'."""
    if not stamp:
        return ""
    try:
        return datetime.datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S").strftime(
            "%d %B %Y"
        )
    except ValueError:
        return stamp.strip()[:10]


def accent_for(result):
    return result.get("accent") or FALLBACK_ACCENTS.get(result.get("key", ""), MUTED)


def join_names(names):
    """['Kimi', 'Codex'] -> 'Kimi and Codex'; three -> 'A, B and C'."""
    names = [n for n in names if n]
    if not names:
        return "none"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return "{} and {}".format(names[0], names[1])
    return "{}, and {}".format(", ".join(names[:-1]), names[-1])


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("could not read {}: {}".format(path, exc))


def load_run(run_dir):
    run_dir = Path(run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        raise SystemExit("run directory not found: {}".format(run_dir))
    results_path = run_dir / "results.json"
    if not results_path.exists():
        raise SystemExit("results.json not found in {}".format(run_dir))

    results = read_json(results_path)
    if not isinstance(results, list):
        raise SystemExit("results.json must be a list of provider rows")

    meta = {}
    if (run_dir / "meta.json").exists():
        meta = read_json(run_dir / "meta.json")

    prompt = ""
    prompt_path = run_dir / "prompt.md"
    if prompt_path.exists():
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        prompt = (meta.get("prompt") or "").strip()

    judge = None
    judge_md = run_dir / "judge.md"
    if judge_md.exists():
        text = judge_md.read_text(encoding="utf-8").strip()
        if text:
            judge = {"text": text, "meta": meta.get("judge") or {}}
    if judge is None and (run_dir / "judge.json").exists():
        payload = read_json(run_dir / "judge.json")
        if (payload.get("text") or "").strip():
            judge = {"text": payload["text"].strip(), "meta": payload}

    return {
        "prompt": prompt,
        "meta": meta,
        "results": results,
        "judge": judge,
    }


# ---------------------------------------------------------------------------
# judge markdown (only `## ` headings, paragraphs, and **bold**)
# ---------------------------------------------------------------------------


def parse_judge(text):
    sections = []
    current = None
    for line in scrub(text).splitlines():
        if line.startswith("## "):
            if current is not None:
                sections.append(current)
            current = {"title": line[3:].strip(), "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current is not None:
        sections.append(current)

    parsed = []
    for section in sections:
        body = "\n".join(section["lines"]).strip()
        match = re.match(r"^(\d+)\.\s+(.+)$", section["title"])
        parsed.append(
            {
                "num": match.group(1) if match else "",
                "title": match.group(2) if match else section["title"],
                "body": body,
            }
        )
    return parsed


def split_headline(body):
    """Pull the leading **bold** sentence out of a judge section body."""
    match = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", body, re.S)
    if not match:
        return "", body
    return match.group(1).strip(), match.group(2).strip()


# ---------------------------------------------------------------------------
# failure classification
# ---------------------------------------------------------------------------


def classify_failure(result):
    """Return (error type, one-line factual detail). Never copies raw traces."""
    error = (result.get("error") or "").lower()
    exit_code = result.get("exit_code")
    status_match = re.search(r"status:\s*(\d{3})", error)

    if "profile" in error or "app-boot" in error or "composeprofile" in error:
        return (
            "Profile boot error",
            "The provider process exited during harness profile initialisation, "
            "before any model call. No answer was recorded.",
        )
    if status_match:
        return (
            "API error (HTTP {})".format(status_match.group(1)),
            "The model API/streaming request failed with HTTP {}. "
            "No answer was recorded.".format(status_match.group(1)),
        )
    if "api" in error or "stream" in error or "request" in error:
        return (
            "API error",
            "The model API request failed. No answer was recorded.",
        )
    if exit_code not in (None, 0):
        return (
            "Process error (exit {})".format(exit_code),
            "The provider process exited without returning an answer.",
        )
    return ("Provider error", "No answer was recorded for this provider.")


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def render_answer(result):
    label = result.get("label") or result.get("key") or "Unknown"
    elapsed = fmt_secs(result.get("elapsed"))
    text = result.get("text") or ""
    words = word_count(text)
    model = (result.get("model") or "").strip()
    bits = [model if model else "model not reported", "{} words".format(words)]
    if result.get("tokens_out"):
        bits.append("{} output tokens".format(result["tokens_out"]))
    meta_line = " &middot; ".join(html.escape(bit) for bit in bits)

    return """
      <article class="answer" style="--accent:{accent}">
        <header class="ahead">
          <div class="awho">
            <span class="adot" aria-hidden="true"></span>
            <h3>{label}</h3>
            <span class="chip chip-ok">answered</span>
          </div>
          <span class="alat">{elapsed}</span>
        </header>
        <p class="ameta">{meta_line}</p>
        <div class="prose">{body}</div>
      </article>""".format(
        accent=accent_for(result),
        label=html.escape(label),
        elapsed=elapsed,
        meta_line=meta_line,
        body=blocks_md(text),
    )


def render_timeline(results, judge):
    rows = []
    ordered = sorted(
        results, key=lambda r: float(r.get("elapsed") or 0.0)
    )
    successful = [r for r in ordered if (r.get("status") == "ok" and (r.get("text") or "").strip())]
    failed = [r for r in ordered if r not in successful]
    judge_elapsed = 0.0
    if judge:
        try:
            judge_elapsed = float(judge.get("meta", {}).get("elapsed") or 0.0)
        except (TypeError, ValueError):
            judge_elapsed = 0.0

    peak = max(
        [float(r.get("elapsed") or 0.0) for r in results] + [judge_elapsed, 0.001]
    )

    for result in successful:
        elapsed = float(result.get("elapsed") or 0.0)
        width = max(0.6, 100.0 * elapsed / peak)
        rows.append(
            """
        <div class="trow">
          <span class="tname"><i class="tdot" style="--accent:{accent}"></i>{label}</span>
          <span class="track"><span class="bar" style="--accent:{accent};width:{width:.1f}%"></span></span>
          <span class="tsec">{elapsed}</span>
        </div>""".format(
                accent=accent_for(result),
                label=html.escape(result.get("label") or result.get("key") or "?"),
                width=width,
                elapsed=fmt_secs(elapsed),
            )
        )

    for result in failed:
        elapsed = float(result.get("elapsed") or 0.0)
        width = max(0.6, 100.0 * elapsed / peak)
        rows.append(
            """
        <div class="trow fail">
          <span class="tname"><i class="tdot"></i>{label}</span>
          <span class="track"><span class="bar" style="width:{width:.1f}%"></span></span>
          <span class="tsec">{elapsed}</span>
        </div>""".format(
                label=html.escape(result.get("label") or result.get("key") or "?"),
                width=width,
                elapsed=fmt_secs(elapsed),
            )
        )

    if judge:
        width = max(0.6, 100.0 * judge_elapsed / peak)
        judge_label = "Judge &middot; {}".format(
            html.escape(judge.get("meta", {}).get("label") or judge.get("meta", {}).get("provider") or "Kimi")
        )
        rows.append(
            """
        <div class="trow judge">
          <span class="tname"><i class="tdot"></i>{label}</span>
          <span class="track"><span class="bar" style="width:{width:.1f}%"></span></span>
          <span class="tsec">{elapsed}</span>
        </div>""".format(
                label=judge_label,
                width=width,
                elapsed=fmt_secs(judge_elapsed),
            )
        )

    return "".join(rows)


def render_judge(judge):
    if not judge:
        return ""
    meta = judge.get("meta") or {}
    label = meta.get("label") or meta.get("provider") or "Judge"
    model = meta.get("model") or ""
    elapsed = fmt_secs(meta.get("elapsed"))
    attribution = " &middot; ".join(
        html.escape(bit) for bit in [label, model, elapsed] if bit
    )

    sections = parse_judge(judge.get("text") or "")
    headline = ""
    lead = ""
    rest = []
    for section in sections:
        if section["title"].lower() == "bottom line":
            headline, lead = split_headline(section["body"])
        else:
            rest.append(section)

    if not headline:
        # no recognisable bottom line: show the first paragraph as the pull quote
        first = (judge.get("text") or "").split("\n\n")[0]
        headline, lead = first.strip(), ""

    blocks = []
    for section in rest:
        blocks.append(
            """
          <div class="vblock">
            <span class="vnum">{num}</span>
            <div class="vbody">
              <h3>{title}</h3>
              {body}
            </div>
          </div>""".format(
                num=html.escape(
                    "{:02d}".format(int(section["num"]))
                    if section["num"].isdigit()
                    else (section["num"] or "")
                ),
                title=html.escape(section["title"]),
                body=blocks_md(section["body"]) or "<p></p>",
            )
        )

    lead_html = '<p class="vlead">{}</p>'.format(inline_md(lead)) if lead else ""

    return """
    <div class="verdict">
      <div class="vlabel"><span>Judge synthesis</span><span class="vattr">{attribution}</span></div>
      <blockquote class="vquote">{headline}</blockquote>
      {lead}
      <div class="vblocks">{blocks}</div>
    </div>""".format(
        attribution=attribution,
        headline=inline_md(headline),
        lead=lead_html,
        blocks="".join(blocks),
    )


def render_failures(failed):
    rows = []
    for result in failed:
        etype, detail = classify_failure(result)
        model = (result.get("model") or "").strip()
        rows.append(
            """
        <div class="frow">
          <div class="fid">
            <strong>{label}</strong>
            <span class="fmodel">{model}</span>
          </div>
          <div class="fbody">
            <span class="ftype">{etype}</span>
            <p class="fdet">{detail}</p>
          </div>
          <span class="ftime">{elapsed}</span>
        </div>""".format(
            label=html.escape(result.get("label") or result.get("key") or "?"),
            model=html.escape(model if model else "model not reported"),
            etype=html.escape(etype),
            detail=html.escape(detail),
            elapsed=fmt_secs(result.get("elapsed")),
        )
        )
    return "".join(rows)


# ---------------------------------------------------------------------------
# page
# ---------------------------------------------------------------------------


def render(run):
    meta = run["meta"]
    results = run["results"]
    judge = run["judge"]
    answered = [
        r
        for r in results
        if r.get("status") == "ok" and (r.get("text") or "").strip()
    ]
    failed = sorted(
        [r for r in results if r not in answered],
        key=lambda r: float(r.get("elapsed") or 0.0),
    )
    total = len(results)

    run_date = fmt_date(meta.get("created_at")) or "undated run"
    wall = fmt_secs(meta.get("wall_seconds"))
    judge_elapsed = fmt_secs((judge or {}).get("meta", {}).get("elapsed"))
    judge_label = (judge or {}).get("meta", {}).get("label") or (judge or {}).get("meta", {}).get("provider") or "Judge"
    judge_model = (judge or {}).get("meta", {}).get("model") or ""
    judge_attr = " &middot; ".join(
        html.escape(bit) for bit in [judge_label, judge_model, judge_elapsed] if bit
    )

    n_answered = len(answered)
    n_failed = len(failed)
    answer_names = join_names(
        [html.escape(r.get("label") or r.get("key") or "?") for r in answered]
    )

    if n_failed:
        title = "Half the ensemble failed. The report shipped."
        title_html = "Half the ensemble failed.<br>The report shipped."
    else:
        title = "Four providers. One question. One report."
        title_html = "Four providers. One question.<br>One report."

    if n_failed:
        lede = (
            "One prompt, sent to {total} model providers in parallel on {date}. "
            "{a} answered and {f} produced no answer at all. A {judge} judge "
            "compared the answers that survived, and the run still closed in {wall} "
            "with a synthesised report &mdash; this page."
        ).format(
            total=total,
            date=run_date,
            a=n_answered,
            f=n_failed,
            judge=html.escape(judge_label),
            wall=wall,
        )
    else:
        lede = (
            "One prompt, sent to {total} model providers in parallel on {date}. "
            "All {total} answered. A {judge} judge compared them, and the run closed "
            "in {wall} with a synthesised report &mdash; this page."
        ).format(
            total=total,
            date=run_date,
            judge=html.escape(judge_label),
            wall=wall,
        )

    answers_html = "".join(render_answer(r) for r in answered) or (
        '<p class="empty">No provider returned an answer on this run.</p>'
    )

    succeeded_sentence = (
        "Every provider is its own process whose outcome is stored as one result "
        "row, so a failure is recorded and skipped rather than fatal — the "
        "{n} answer{plural} that arrived {was} kept, and the judge call still ran, "
        "which is how a {total}-provider run with {f} failure{s} still produced a "
        "complete report."
    ).format(
        n=n_answered,
        plural="" if n_answered == 1 else "s",
        was="was" if n_answered == 1 else "were",
        total=total,
        f=n_failed,
        s="" if n_failed == 1 else "s",
    )

    judge_html = render_judge(judge)
    judge_section = ""
    if judge_html:
        run_shape = ""
        try:
            slowest = max(float(r.get("elapsed") or 0.0) for r in answered)
            wall_value = float(meta.get("wall_seconds") or 0.0)
            judge_value = float((judge or {}).get("meta", {}).get("elapsed") or 0.0)
            parallel = abs((slowest + judge_value) - wall_value) < 1.5
        except (TypeError, ValueError):
            parallel = False
        if parallel:
            run_shape = (
                "Providers ran concurrently, then the judge ran: the slowest answer "
                "plus the judge roughly equals the {} wall clock.".format(wall)
            )
        judge_section = """
    <section class="section" id="judge">
      <div class="shead">
        <span class="snum">{num}</span>
        <h2>The judge synthesis</h2>
        <p class="snote">A separate call after the answers were in: {attr}.{shape}</p>
      </div>
      {judge}
    </section>""".format(
            num="02",
            attr=judge_attr,
            shape=(" " + run_shape) if run_shape else "",
            judge=judge_html,
        )

    failures_section = ""
    if failed:
        failures_section = """
    <section class="section" id="failures">
      <div class="shead">
        <span class="snum">{num}</span>
        <h2>Providers that failed</h2>
        <p class="snote">Reported honestly, not hidden: {n} of {total} providers produced no answer. Each failure was recorded against its own provider row and the run moved on.</p>
      </div>
      <div class="failpanel">
        <div class="fhead">
          <span class="fdot" aria-hidden="true"></span>
          <span class="fheadlabel">Failed providers</span>
          <span class="fchip">{n} of {total}</span>
        </div>
        {rows}
      </div>
      <div class="survived">
        <div class="slabel">Why the run still succeeded</div>
        <p>{sentence}</p>
      </div>
    </section>""".format(
            num="03" if judge_html else "02",
            n=n_failed,
            total=total,
            rows=render_failures(failed),
            sentence=inline_md(succeeded_sentence),
        )

    scroll_bits = [
        "{} answer{}".format(n_answered, "" if n_answered == 1 else "s")
    ]
    if judge_html:
        scroll_bits.append("judge synthesis")
    if n_failed:
        scroll_bits.append(
            "{} failure{}".format(n_failed, "" if n_failed == 1 else "s")
        )
    scrollnote = " &middot; ".join(scroll_bits) + " &darr;"

    if judge_html:
        judge_line = "Judge &middot; {} &middot; {}".format(
            html.escape(judge_label), judge_elapsed
        )
    else:
        judge_line = "No judge call on this run"

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<header class="hero">
  <div class="wrap">
    <div class="topbar">
      <span class="wordmark">ENSEMBLE</span>
      <span class="topmeta">Multi-model report &middot; {run_date}</span>
    </div>
    <h1>{title_html}</h1>
    <p class="lede">{lede}</p>

    <section class="prompt">
      <div class="label">The prompt</div>
      <p>{prompt}</p>
    </section>

    <div class="stats">
      <div class="stat"><b>{total}</b><span>providers queried</span></div>
      <div class="stat"><b>{n_answered}</b><span>answers returned</span></div>
      <div class="stat"><b>{n_failed}</b><span>providers failed</span></div>
      <div class="stat"><b>{wall}</b><span>end to end</span></div>
    </div>

    <section class="timeline">
      <div class="label">Who returned, and how long it took</div>
      {timeline}
      <div class="legend">
        <span><i class="lg-ok"></i>answered</span>
        <span><i class="lg-fail"></i>failed</span>
        <span><i class="lg-judge"></i>judge</span>
      </div>
    </section>

    <div class="scrollnote">{scrollnote}</div>
  </div>
</header>

<main>
  <div class="wrap">
    <section class="section" id="answers">
      <div class="shead">
        <span class="snum">01</span>
        <h2>The answers</h2>
        <p class="snote">{n_answered} of {total} providers returned an answer; {answer_names} produced usable text. Latency is wall time for that provider.</p>
      </div>
      {answers}
    </section>
    {judge_section}
    {failures_section}
  </div>
</main>

<footer>
  <div class="wrap">
    <div class="foot">
      <div>
        <p><strong>One static file.</strong> No JavaScript, no external fonts, no images, no analytics.</p>
        <p>Generated from this run&rsquo;s <code>meta.json</code>, <code>results.json</code> and <code>judge.md</code> by <code>build.py</code>, a stdlib-only Python script. Rebuild: <code>python3 build.py --run &lt;run-dir&gt;</code></p>
      </div>
      <div class="footfacts">
        <p>{run_date}<br>{total} providers &middot; {n_answered} answered &middot; {wall} wall<br>{judge_line}</p>
      </div>
    </div>
  </div>
</footer>
</body>
</html>
""".format(
        css=CSS,
        run_date=html.escape(run_date),
        title=html.escape(title),
        title_html=title_html,
        lede=lede,
        prompt=inline_md(run["prompt"]),
        total=total,
        n_answered=n_answered,
        n_failed=n_failed,
        wall=wall,
        timeline=render_timeline(results, judge),
        answer_names=answer_names,
        answers=answers_html,
        judge_section=judge_section,
        failures_section=failures_section,
        scrollnote=scrollnote,
        judge_line=judge_line,
        judge_label=html.escape(judge_label),
        judge_elapsed=judge_elapsed,
    )


# ---------------------------------------------------------------------------
# styles (self-contained: no imports, no external assets)
# ---------------------------------------------------------------------------

CSS = r"""
:root{
  --bg:#FAF9F6;
  --card:#FFFFFF;
  --ink:#16161B;
  --muted:#5E5E69;
  --faint:#8B8B95;
  --line:#E5E1D8;
  --line-strong:#D5D0C4;
  --ok:#0B8F6A;
  --fail:#B4483A;
  --serif: Georgia, "Iowan Old Style", "Times New Roman", serif;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;
  background:var(--bg);
  color:var(--ink);
  font-family:var(--sans);
  font-size:16px;
  line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:900px;margin:0 auto;padding:0 40px}
p{margin:0}
/* ---------- hero ---------- */
.hero{
  min-height:100vh;
  display:flex;
  flex-direction:column;
  padding:60px 0 44px;
  border-bottom:1px solid var(--line);
  background:
    radial-gradient(880px 460px at 10% -10%, rgba(91,91,214,.06), transparent 62%),
    radial-gradient(720px 420px at 98% 2%, rgba(11,143,106,.05), transparent 60%),
    var(--bg);
}
.hero .wrap{width:100%;display:flex;flex-direction:column;flex:1}
.topbar{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:54px}
.wordmark{font-size:12px;font-weight:800;letter-spacing:.24em}
.topmeta{font-size:11px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
h1{
  margin:0 0 24px;
  font-size:clamp(40px,4.5vw,60px);
  line-height:1.02;
  letter-spacing:-.032em;
  font-weight:800;
}
.lede{margin:0 0 42px;max-width:64ch;font-size:19px;line-height:1.55;color:var(--muted)}
.label{font-size:11px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
.prompt{margin:0 0 42px;padding:2px 0 2px 26px;border-left:3px solid var(--ink)}
.prompt .label{margin-bottom:12px}
.prompt p{
  font-family:var(--serif);
  font-size:23px;
  line-height:1.4;
  letter-spacing:-.005em;
  color:#1B1B22;
  max-width:60ch;
}
.stats{
  display:flex;
  margin:0 0 42px;
  padding:18px 0;
  border-top:1px solid var(--line-strong);
  border-bottom:1px solid var(--line-strong);
}
.stat{flex:1;padding:0 22px;border-left:1px solid var(--line)}
.stat:first-child{padding-left:0;border-left:0}
.stat b{display:block;margin-bottom:7px;font-size:28px;font-weight:800;letter-spacing:-.02em;line-height:1}
.stat span{display:block;font-size:10.5px;font-weight:600;letter-spacing:.13em;text-transform:uppercase;color:var(--muted)}
.timeline{margin:0 0 40px}
.timeline .label{margin-bottom:6px}
.trow{display:grid;grid-template-columns:124px 1fr 62px;align-items:center;gap:18px;padding:6px 0}
.tname{display:flex;align-items:center;gap:8px;font-size:13.5px;font-weight:600;white-space:nowrap}
.tdot{display:inline-block;width:8px;height:8px;border-radius:2px;background:var(--accent,#999);flex:0 0 auto}
.trow.fail .tname{color:var(--muted)}
.trow.fail .tdot{background:#D9BDB5}
.trow.judge .tdot{background:#26262E}
.track{display:block;height:14px;border-radius:7px;background:#EFECE4;overflow:hidden}
.bar{display:block;height:100%;border-radius:7px;background:var(--accent,#333);min-width:6px}
.trow.fail .bar{
  background:repeating-linear-gradient(135deg,#D8B7AE 0 3px,#F3E5E0 3px 7px);
  box-shadow:inset 0 0 0 1px #E3CFC8;
}
.trow.judge .bar{background:#26262E}
.tsec{font-family:var(--mono);font-size:12px;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
.legend{display:flex;gap:22px;margin-top:12px;font-size:11px;letter-spacing:.05em;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px}
.lg-ok{background:var(--ok)}
.lg-fail{background:repeating-linear-gradient(135deg,#D8B7AE 0 2px,#F3E5E0 2px 5px);box-shadow:inset 0 0 0 1px #E3CFC8}
.lg-judge{background:#26262E}
.scrollnote{margin-top:auto;padding-top:30px;font-size:11.5px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--faint)}
/* ---------- sections ---------- */
main{padding:0 0 24px}
.section{padding:0 0 78px}
.shead{
  display:grid;
  grid-template-columns:52px 1fr;
  gap:0 16px;
  align-items:baseline;
  margin-bottom:28px;
  padding-top:28px;
  border-top:1px solid var(--line-strong);
}
.shead:first-child{border-top:0;padding-top:8px}
.snum{font-family:var(--mono);font-size:12px;color:var(--faint)}
.shead h2{margin:0;font-size:clamp(26px,3vw,34px);font-weight:800;letter-spacing:-.022em;line-height:1.08}
.snote{grid-column:2;margin-top:7px;max-width:60ch;font-size:15px;line-height:1.55;color:var(--muted)}
/* ---------- answers ---------- */
.answer{
  margin-bottom:20px;
  padding:28px 30px 30px;
  background:var(--card);
  border:1px solid var(--line);
  border-left:4px solid var(--accent);
  border-radius:16px;
  box-shadow:0 1px 2px rgba(22,22,27,.04);
}
.answer:last-child{margin-bottom:0}
.ahead{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
.awho{display:flex;align-items:center;gap:10px}
.adot{display:inline-block;width:10px;height:10px;border-radius:3px;background:var(--accent)}
.ahead h3{margin:0;font-size:19px;font-weight:700;letter-spacing:-.01em}
.chip{font-size:10.5px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;padding:4px 9px;border-radius:999px}
.chip-ok{color:#0B8F6A;background:rgba(11,143,106,.08);box-shadow:inset 0 0 0 1px rgba(11,143,106,.22)}
.alat{font-family:var(--mono);font-size:14px;font-variant-numeric:tabular-nums;color:var(--ink);white-space:nowrap;padding-top:2px}
.ameta{margin:7px 0 18px;font-size:13px;color:var(--faint)}
.prose{font-family:var(--serif);font-size:20px;line-height:1.62;color:#202027}
.prose p{margin:0 0 14px}
.prose p:last-child{margin-bottom:0}
.prose strong{font-weight:700}
/* ---------- judge ---------- */
.verdict{
  padding:40px 40px 36px;
  background:#17171C;
  color:#EDEAE3;
  border-radius:20px;
}
.vlabel{display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-bottom:26px;font-size:11px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#9C99A6}
.vattr{font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;color:#817E8B;text-transform:none}
.vquote{
  margin:0 0 20px;
  font-family:var(--serif);
  font-size:clamp(26px,3.2vw,36px);
  font-weight:400;
  line-height:1.2;
  letter-spacing:-.015em;
  color:#F6F3EC;
}
.vlead{margin:0 0 34px;max-width:62ch;font-size:17px;line-height:1.6;color:#B9B5C0}
.vblocks{border-top:1px solid rgba(255,255,255,.12)}
.vblock{display:grid;grid-template-columns:44px 1fr;gap:16px;padding:24px 0;border-bottom:1px solid rgba(255,255,255,.09)}
.vblock:last-child{border-bottom:0;padding-bottom:0}
.vnum{font-family:var(--mono);font-size:12px;color:#7E7B88;padding-top:5px}
.vbody h3{margin:0 0 9px;font-size:15px;font-weight:700;letter-spacing:.02em;color:#F2EFE8}
.vbody p{margin:0 0 10px;font-family:var(--serif);font-size:17.5px;line-height:1.62;color:#C6C2CC}
.vbody p:last-child{margin-bottom:0}
.vbody strong{color:#F6F3EC;font-weight:700}
/* ---------- failures ---------- */
.failpanel{border:1px solid #E7D4CE;border-radius:18px;background:#FFFDFB;overflow:hidden}
.fhead{display:flex;align-items:center;gap:11px;padding:16px 28px;border-bottom:1px solid #F0E3DE;background:#FBF3F0}
.fdot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--fail)}
.fheadlabel{font-size:11px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:#8F4034}
.fchip{margin-left:auto;font-family:var(--mono);font-size:11px;color:#9C3B2C;background:#F8E7E1;border:1px solid #EFD6CD;border-radius:999px;padding:3px 9px}
.frow{display:grid;grid-template-columns:170px 1fr 66px;gap:22px;align-items:start;padding:24px 28px;border-bottom:1px solid #F4E9E4}
.frow:last-child{border-bottom:0}
.fid strong{display:block;font-size:16.5px;letter-spacing:-.01em}
.fmodel{display:block;margin-top:4px;font-family:var(--mono);font-size:11px;color:var(--faint)}
.ftype{display:inline-block;margin-bottom:9px;padding:3px 8px;font-family:var(--mono);font-size:11.5px;font-weight:600;color:#9C3B2C;background:#FBEDE8;border:1px solid #EFD6CD;border-radius:6px}
.fdet{margin:0;max-width:52ch;font-size:14px;line-height:1.55;color:var(--muted)}
.ftime{font-family:var(--mono);font-size:12px;color:var(--faint);text-align:right;font-variant-numeric:tabular-nums;padding-top:3px}
.survived{margin-top:26px;padding:22px 26px;background:rgba(11,143,106,.05);border-left:3px solid var(--ok);border-radius:0 12px 12px 0}
.slabel{margin-bottom:9px;font-size:11px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#0B8F6A}
.survived p{font-family:var(--serif);font-size:19px;line-height:1.55;color:#1E1E24;max-width:66ch}
.empty{margin:0;padding:26px;border:1px dashed var(--line-strong);border-radius:12px;color:var(--muted)}
/* ---------- footer ---------- */
footer{margin-top:10px;padding:34px 0 56px;border-top:1px solid var(--line)}
.foot{display:flex;justify-content:space-between;gap:40px;font-size:12.5px;line-height:1.65;color:var(--faint)}
.foot p{margin:0 0 8px}
.foot p:last-child{margin-bottom:0}
.foot strong{color:var(--muted);font-weight:700}
.foot code{font-family:var(--mono);font-size:11.5px;color:var(--muted);background:#F1EEE7;border:1px solid var(--line);border-radius:4px;padding:1px 5px}
.footfacts{flex:0 0 auto;text-align:right;font-family:var(--mono);font-size:11px;line-height:1.7;color:var(--faint)}
/* ---------- small screens ---------- */
@media (max-width:760px){
  .wrap{padding:0 22px}
  .hero{padding-top:40px}
  .stats{flex-wrap:wrap;gap:16px 0}
  .stat{flex:1 1 40%;border-left:0;padding:0}
  .trow{grid-template-columns:104px 1fr 54px;gap:12px}
  .frow{grid-template-columns:1fr;gap:10px;padding:22px}
  .ftime{text-align:left;padding-top:0}
  .verdict{padding:28px 24px}
  .vblock{grid-template-columns:34px 1fr;gap:10px}
  .vlabel{flex-direction:column;gap:6px}
  .foot{flex-direction:column;gap:18px}
  .footfacts{text-align:left}
  .answer{padding:24px 22px}
}
@media (max-width:560px){
  h1{font-size:34px}
  .topbar{flex-direction:column;align-items:flex-start;gap:7px;margin-bottom:40px}
  .lede{font-size:17.5px}
  .prompt p{font-size:20px}
  .stats{gap:16px 0}
  .stat{flex:1 1 42%}
  .legend{flex-wrap:wrap;gap:12px}
  .vquote{font-size:24px}
  .vbody p{font-size:16.5px}
}
@media print{
  .hero{min-height:0}
  .scrollnote{display:none}
}
"""


# ---------------------------------------------------------------------------
# sanitisation gate
# ---------------------------------------------------------------------------


def assert_clean(document):
    """Refuse to emit a page that leaks local paths, usernames, or secrets."""
    lower = document.lower()
    problems = []

    for needle in ("/users/", "file://", "/applications/", "/opt/homebrew/", ".local/bin"):
        if needle in lower:
            problems.append(needle)

    home = str(Path.home())
    if home and home != "/" and home.lower() in lower:
        problems.append("home directory")

    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = ""
    if len(user) >= 3 and user.lower() in lower:
        problems.append("local username")

    if KEY_RE.search(document):
        problems.append("API-key-shaped token")

    if problems:
        raise SystemExit(
            "refusing to write page: forbidden local data found: "
            + ", ".join(sorted(set(problems)))
        )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render one ensemble run as a self-contained HTML page."
    )
    parser.add_argument("--run", required=True, help="run directory to read")
    parser.add_argument("--out", default="index.html", help="output HTML file")
    args = parser.parse_args(argv)

    run = load_run(args.run)
    document = render(run)
    assert_clean(document)

    out_path = Path(args.out)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(document, encoding="utf-8")

    answered = sum(
        1 for r in run["results"] if r.get("status") == "ok" and (r.get("text") or "").strip()
    )
    failed = len(run["results"]) - answered
    judge = run["judge"]
    judge_name = ""
    if judge:
        judge_name = (judge.get("meta") or {}).get("label") or (
            judge.get("meta") or {}
        ).get("provider") or ""
    size = len(document.encode("utf-8"))
    print(
        "wrote {} ({:.1f} KB) — {} providers, {} answered, {} failed{}".format(
            out_path,
            size / 1024.0,
            len(run["results"]),
            answered,
            failed,
            (", judge " + judge_name) if judge_name else "",
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
