# Ensemble demo — a report that survived two provider failures

A single static page showing what the `ensemble` tool returns for one prompt: the
answers from the models that responded, the judge's synthesis, and the providers
that failed — with their error types, not hidden.

The point of the page is the failure handling. Four providers were queried; two
returned nothing; the run still produced a complete report.

## The run

Run date: **10 November 2026**. Prompt (verbatim):

> Should a ten-person independent policy research group publish its internal analysis code and review memos as open source? Answer yes or no, then give the single strongest reason. Under 120 words.

| Provider | Outcome | Latency |
|---|---|---|
| DeepSeek | Failed — profile boot error (process exited during harness profile initialisation; no model call) | 0.2 s |
| Gemini | Failed — API error, HTTP 402 | 2.3 s |
| Codex | Answered — 51 words | 10.4 s |
| Kimi | Answered — 55 words | 13.2 s |
| Kimi (judge) | Synthesis | 34.7 s |

End to end: **47.9 s**. The providers ran concurrently; the slowest answer plus the
judge call accounts for the wall clock.

Judge headline: **“Codex is strongest by a narrow margin.”**

## Files

| File | What it is |
|---|---|
| `index.html` | The page. One self-contained file: no JavaScript, no external CSS, fonts, images or analytics. |
| `build.py` | Stdlib-only generator. Reads a run directory and writes the HTML. |
| `screenshots/desktop.png` | Headless Chrome capture at 1440×1100. |
| `linkedin-source.md` | Three verbatim quotes from the run, with attribution. |
| `runs/…` | The source run, untouched. |

## Rebuild

```sh
python3 build.py \
  --run "runs/2026-11-10_104714_should-a-ten-person-independent-policy-research-/" \
  --out index.html
```

`build.py` works on any run directory that contains `results.json`;
`meta.json`, `prompt.md` and `judge.md` (or `judge.json`) are used when present.
Output is deterministic — no build timestamps, so rebuilds are byte-identical.

Re-capture the screenshot:

```sh
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars \
  --force-device-scale-factor=1 --window-size=1440,1100 \
  --user-data-dir=/tmp/ensemble-demo-chrome \
  --no-first-run --no-default-browser-check \
  --virtual-time-budget=3000 \
  --screenshot="$PWD/screenshots/desktop.png" \
  "file://$PWD/index.html"
```

## Honest notes

- **2 of 4 providers were unavailable on this run.** No retry was attempted: the
  build session was prohibited from calling the network. The page reports the
  failures and their error types rather than quietly dropping them.
- The run's raw error text is a stack trace containing local paths. The page does
  not reproduce it; it classifies the failure (profile boot error, API error
  HTTP 402) and gives a factual one-line summary.
- Everything on the page is generated from the run's own files. There is no
  invented commentary about the models; latency, word counts and wall clock are
  computed from the run data.
- The judge's verdict and the models' answers are as returned. Markdown emphasis
  markers are rendered as emphasis; wording is untouched.

## Sanitisation

`build.py` scrubs absolute local paths and then refuses to write the page if it
would contain the local home directory, the local username, an `/Applications/`
or `file://` path, or anything shaped like an API key. The current `index.html`
is clean:

```sh
grep -nE "/Users/|/Applications/|file://|$USER|sk-[A-Za-z0-9]{8,}" index.html
# no output
```

The run directory is a local source only; `index.html` references no run id and
no local path.
