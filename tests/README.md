# ensemble test suite

Stdlib-only `unittest` suite for the local `ensemble` CLI + web app. No network
access is needed, and no provider CLI (`kimi`, `gemini`, `dsh`, `codex`) is ever
executed — `parse_output` is fed inline fixtures and the HTTP tests sit in front
of a real local server whose run-construction is patched out.

## Run it

```sh
cd ensemble
python3 -m unittest discover -s tests -v
```

Python 3.9 compatible (the interpreter shipped on this machine). Expected
result against the current app:

```
Ran 116 tests in ~0.6s
OK
```

`test_defect_regressions.py` keeps regression coverage for three defects this
suite found and that are now fixed (see "Defects found and fixed" below). They
fail against the pre-fix revision, so they are genuine regression tests.

## Isolation

`tests/_support.py` is imported by every test module **before** `ensemble`.
It points `ENSEMBLE_HOME` at a fresh `tempfile.mkdtemp()` directory, so the
suite never reads or writes the developer's real `~/.ensemble` (which matters
because `ensemble.py` resolves `HOME` at import time and `serve.py` derives
`RUNS_DIR` from it). The temp home is removed via `atexit`.

The HTTP test additionally:

* binds a real `ThreadingHTTPServer` on `127.0.0.1:0` in a daemon thread,
* mirrors `serve.main()` by loading `CONFIG`/`SETTINGS` and creating a temp
  `RUNS_DIR` (module import alone does not do this),
* patches `ensemble.which` to `None` so `health()` never probes installed CLIs
  (`codex login status`),
* patches `serve.Run` so no POST in the test can ever spawn a real run,
* shuts the server down and joins the thread in `tearDownClass`.

## Coverage map

| File | Covers |
|---|---|
| `test_parse_output.py` | `parse_output()` for `kimi-jsonl`, `codex-jsonl`, `dsh-jsonl`, `text`: assistant message assembly, last-message-wins, token/cache metadata, malformed JSONL lines, diagnostic stderr lines, stderr-only failures, empty output. |
| `test_config.py` | `deep_merge()` (recursive merge, no input mutation, `None` handling), `provider_settings()` (defaults, per-provider overrides, `defaults.models` precedence, extra providers, `None` entries, builtin table not mutated), `load_config()` (ordered deep merge, malformed-file tolerance, temp `CONFIG_PATHS`), `find_dsh()` env/settings overrides, `ENSEMBLE_HOME` isolation. |
| `test_render_markdown.py` | TARGET sanitisation behaviour: no `<script>`, `<iframe>`, `<style>`, `onerror=`/`onload=` handlers, `javascript:` hrefs (incl. entity-encoded and case variants), `data:` hrefs; comments/SVG dropped. Still renders headings, lists, fenced code, tables, blockquotes, links, images. |
| `test_artifacts.py` | `write_artifacts()` (all sidecar files, prompt/meta/results JSON), `write_report()` (`report.html`/`report.md`, cards, escaped error and prompt text, no active content), `load_run()` round-trip (prompt, meta, result fields, nested debate, prompt redaction, missing-run error). |
| `test_http_api.py` | `GET /api/health`, `/api/providers`, `/api/runs` (and seeded history + `/api/runs/<id>`) return 200 JSON; `POST /api/runs` returns 400 for empty/missing prompt, non-list/unknown `providers`, invalid context, invalid JSON; security headers; temp-home isolation. |
| `test_defect_regressions.py` | Regression tests for the three fixed defects below: newline-obfuscated `javascript:` href, non-object JSONL lines, `"defaults": null` config. |

The sanitisation tests target the allowlist sanitiser that landed in
`ensemble.py` (`security: allowlist-sanitise model HTML output; add CSP and
hardening headers`). Against the pre-sanitiser baseline they fail:
`render_markdown("<script>…")` used to pass raw `<script>` straight through.

## Defects found and fixed

All three were found by this suite and are fixed in the working tree; the
outputs below show the pre-fix behaviour and are kept as documentation.

### 1. `safe_url()` lets `java\nscript:` through (security, medium)

`render_markdown` emits an href with an embedded newline/tab inside the scheme.
Browsers strip ASCII tab/newline while parsing URLs, so the href becomes a live
`javascript:` URL on click.

```python
import ensemble
ensemble.render_markdown('<a href="java&#10;script:alert(document.domain)">x</a>')
# => '<p><a href="java\nscript:alert(1)">x</a></p>'   (unsafe after normalisation)
```

Fix: before scheme detection, strip ASCII tab/CR/LF from the value (or reject
URLs containing control characters), e.g. `re.sub(r"[\t\n\r]", "", value)`.

### 2. `parse_output()` crashes on valid non-object JSONL lines (low)

Valid JSON that is not an object makes the parser call `.get()` on `None`/`list`.

```python
import ensemble
ensemble.parse_output("kimi-jsonl", "null\n", "")
# AttributeError: 'NoneType' object has no attribute 'get'
ensemble.parse_output("codex-jsonl", "[1, 2]\n", "")
# AttributeError: 'list' object has no attribute 'get'
```

Fix: `if not isinstance(event, dict): continue` after `json.loads` in the
`kimi-jsonl` and `codex-jsonl` branches (`dsh-jsonl` already skips lines that do
not start with `{`).

### 3. `provider_settings()` crashes on `"defaults": null` (low)

A config file containing `"defaults": null` raises `AttributeError` even though
other readers (`build_specs`, `cmd_run`) tolerate it via
`(config.get("defaults") or {})`.

```python
import ensemble
ensemble.provider_settings({"defaults": None, "providers": {}})
# AttributeError: 'NoneType' object has no attribute 'get'
```

Fix: `defaults = config.get("defaults") or {}` at the top of `provider_settings`.
