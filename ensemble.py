#!/usr/bin/env python3
"""
ensemble — run one prompt through several agent CLIs at the same time.

Providers out of the box: Kimi, Gemini, DeepSeek (via DSH headless), Codex.
Each provider runs in its own throwaway working copy, failures are isolated,
and every run produces a side-by-side HTML report plus raw artifacts.

Usage:
    ensemble "Explain CRDTs in one paragraph"
    ensemble run --only kimi,codex "Review this idea: ..."
    ensemble doctor --probe
    ensemble judge ~/.ensemble/runs/2026-10-19_2305_some-prompt
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as _dt
import html
import json
from html.parser import HTMLParser
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Dict, List, Optional, Tuple

VERSION = "1.1.0"
HOME = Path(os.environ.get("ENSEMBLE_HOME", Path.home() / ".ensemble")).expanduser()
GEMINI_KEY_FILE = HOME / "gemini.key"
CONFIG_PATHS = [
    Path.home() / ".config" / "ensemble" / "config.json",
    Path.cwd() / "ensemble.config.json",
]
DSH_BUNDLED = Path(
    "/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh"
)
DSH_CREDENTIALS = Path.home() / ".dsh" / ".credentials.yaml"

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

# --------------------------------------------------------------------------- #
# Provider definitions
# --------------------------------------------------------------------------- #

PROVIDERS: Dict[str, dict] = {
    "kimi": {
        "label": "Kimi",
        "accent": "#5B5BD6",
        "model": "kimi-code",
        "timeout": 300,
        "parse": "kimi-jsonl",
        "enabled": True,
        "bin": "kimi",
    },
    "gemini": {
        "label": "Gemini",
        "accent": "#8B5CF6",
        "model": None,
        "timeout": 300,
        "parse": "text",
        "enabled": True,
        "bin": "gemini",
    },
    "deepseek": {
        "label": "DeepSeek",
        "accent": "#2F6BFF",
        "model": "deepseek-flash",
        "timeout": 300,
        "parse": "dsh-jsonl",
        "enabled": True,
        "bin": "dsh",
    },
    "codex": {
        "label": "Codex",
        "accent": "#0B8F6A",
        "model": None,
        "timeout": 300,
        "parse": "codex-jsonl",
        "enabled": True,
        "bin": "codex",
    },
}
ORDER = ["kimi", "gemini", "deepseek", "codex"]

STATUS_STYLE = {
    "ok": ("\033[32m", "ok"),
    "error": ("\033[31m", "error"),
    "timeout": ("\033[33m", "timeout"),
    "empty": ("\033[33m", "empty"),
    "running": ("\033[36m", "running"),
}


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #


def now_local() -> _dt.datetime:
    return _dt.datetime.now().astimezone()


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def use_color(no_color: bool) -> bool:
    return (not no_color) and sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def colorize(text: str, code: str, enabled: bool) -> str:
    return f"{code}{text}\033[0m" if enabled else text


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def human_int(n: Optional[int]) -> str:
    if n is None:
        return "—"
    return f"{n:,}"


def human_secs(sec: float) -> str:
    if sec < 10:
        return f"{sec:.1f}s"
    if sec < 100:
        return f"{sec:.0f}s"
    return f"{sec / 60:.1f}m"


def truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0].rstrip()
    if cut.endswith((".", "!", "?")):
        cut = cut[:-1].rstrip()
    return (cut or text[: max(0, limit - 1)]) + "…"


def first_line(text: str, limit: int = 110) -> str:
    for line in text.splitlines():
        if line.strip():
            return truncate(line.strip(), limit)
    return "Untitled prompt"


def deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict:
    merged = {"defaults": {}, "providers": {}}
    for path in CONFIG_PATHS:
        if path.is_file():
            try:
                merged = deep_merge(merged, json.loads(path.read_text()))
            except Exception as exc:  # noqa: BLE001 - config is best effort
                eprint(f"ensemble: ignoring {path}: {exc}")
    return merged


def provider_settings(config: dict) -> Dict[str, dict]:
    settings = {}
    for key, base in PROVIDERS.items():
        override = (config.get("providers") or {}).get(key, {}) or {}
        merged = deep_merge(base, override)
        if key in (config.get("defaults", {}).get("models") or {}):
            merged["model"] = config["defaults"]["models"][key]
        settings[key] = merged
    for key, override in (config.get("providers") or {}).items():
        if key in settings:
            continue
        base = {
            "label": key.replace("-", " ").title(),
            "accent": "#6B7280",
            "model": None,
            "timeout": 300,
            "parse": "text",
            "enabled": True,
            "bin": key,
        }
        settings[key] = deep_merge(base, override or {})
    return settings


def all_keys(settings: Dict[str, dict]) -> List[str]:
    extras = sorted(key for key in settings if key not in ORDER)
    return [key for key in ORDER if key in settings] + extras


def find_dsh(settings: dict) -> Optional[str]:
    env = os.environ.get("ENSEMBLE_DSH_PATH")
    if env and Path(env).is_file():
        return env
    override = settings.get("deepseek", {}).get("path")
    if override and Path(override).is_file():
        return override
    found = shutil.which("dsh")
    if found:
        return found
    if DSH_BUNDLED.is_file():
        return str(DSH_BUNDLED)
    return None


def deepseek_account_available() -> bool:
    try:
        raw = DSH_CREDENTIALS.read_text(errors="ignore")
    except OSError:
        return False
    return "deepseek-account-platform/" in raw and "token:" in raw


def gemini_api_key() -> str:
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if key:
        return key
    try:
        return GEMINI_KEY_FILE.read_text().strip()
    except OSError:
        return ""


def gemini_authenticated() -> bool:
    """Headless Gemini needs an API key or Vertex, not just an OAuth login."""
    return bool(
        gemini_api_key()
        or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")
        or os.environ.get("GOOGLE_GENAI_USE_GCA")
    )


def which(cmd: str) -> Optional[str]:
    if os.path.sep in cmd:
        return cmd if Path(cmd).is_file() else None
    return shutil.which(cmd)


# --------------------------------------------------------------------------- #
# Prompt sources and working directories
# --------------------------------------------------------------------------- #


def read_prompt(args) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).expanduser().read_text()
    parts = list(args.prompt or [])
    if parts == ["-"]:
        return sys.stdin.read()
    if parts:
        return " ".join(parts)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


COPY_IGNORE = shutil.ignore_patterns(
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    ".nuxt",
    "dist",
    "build",
    "target",
    ".cache",
    ".DS_Store",
    "*.pyc",
    "ensemble-runs",
)


def snapshot_project(src: Path, dest: Path, max_mb: int = 400) -> None:
    """Copy a project into dest. In git repos, copy tracked+untracked (not ignored)."""
    git = shutil.which("git")
    files: List[Path] = []
    if git and (src / ".git").exists():
        try:
            proc = subprocess.run(
                [git, "-C", str(src), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                capture_output=True,
                timeout=60,
            )
            if proc.returncode == 0:
                files = [src / p.decode("utf-8", "replace") for p in proc.stdout.split(b"\0") if p]
        except Exception:  # noqa: BLE001 - fall back to a plain copy
            files = []

    if files:
        total = 0
        for item in files:
            if not item.is_file():
                continue
            total += item.stat().st_size
            if total > max_mb * 1024 * 1024:
                raise RuntimeError(
                    f"project is larger than {max_mb} MB; use --context cwd instead"
                )
            target = dest / item.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
        return

    shutil.copytree(src, dest, ignore=COPY_IGNORE, symlinks=True, dirs_exist_ok=True)


def allocate_workdirs(
    keys: List[str], context: str, base_cwd: Path, keep: bool
) -> Tuple[Dict[str, Path], List[Path]]:
    """Return (provider -> workdir, temp dirs to clean up)."""
    if context == "cwd":
        return {key: base_cwd for key in keys}, []

    dirs: Dict[str, Path] = {}
    cleanups: List[Path] = []
    for key in keys:
        path = Path(tempfile.mkdtemp(prefix=f"ensemble-{key}-"))
        cleanups.append(path)
        if context == "copy":
            snapshot = path / "project"
            snapshot.mkdir()
            snapshot_project(base_cwd, snapshot)
            path = snapshot
        dirs[key] = path
    if keep:
        cleanups = []
    return dirs, cleanups


# --------------------------------------------------------------------------- #
# Command construction
# --------------------------------------------------------------------------- #


def _quote_yaml(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9._:/-]+", value or ""):
        return value
    return json.dumps(value)


def deepseek_patch(run_dir: Path, model: str, auth_mode: str) -> Optional[Path]:
    lines: List[str] = []
    if auth_mode == "account":
        lines += [
            "- id: authorization",
            "  disabled: false",
            "- id: credentials",
            "  disabled: false",
            "- id: deepseek-account",
            "  disabled: false",
        ]
    lines += [
        "- id: agent-default-model",
        "  config:",
        "    provider: deepseek-account" if auth_mode == "account" else "    provider: deepseek-official",
        f"    model: {_quote_yaml(model)}",
    ]
    path = run_dir / "deepseek.patch.yml"
    path.write_text("\n".join(lines) + "\n")
    return path


def deepseek_auth_mode(config: dict) -> str:
    explicit = (
        os.environ.get("ENSEMBLE_DEEPSEEK_AUTH")
        or (config.get("defaults") or {}).get("deepseek_auth")
        or "auto"
    )
    if explicit in ("account", "api-key"):
        return explicit
    return "account" if deepseek_account_available() else "api-key"


@dataclass
class Spec:
    key: str
    label: str
    accent: str
    argv: List[str]
    cwd: Path
    timeout: float
    parse: str
    model: str = ""
    env: Dict[str, str] = field(default_factory=dict)


def build_specs(
    keys: List[str],
    prompt: str,
    settings: Dict[str, dict],
    models: Dict[str, str],
    workdirs: Dict[str, Path],
    context: str,
    run_dir: Path,
    config: dict,
    prompt_map: Optional[Dict[str, str]] = None,
) -> List[Spec]:
    specs: List[Spec] = []
    default_timeout = float((config.get("defaults") or {}).get("timeout", 300))
    for key in keys:
        cfg = settings[key]
        current_prompt = (prompt_map or {}).get(key, prompt)
        model = models.get(key) or cfg.get("model") or ""
        timeout = float(cfg.get("timeout", default_timeout))
        cwd = workdirs[key]
        env = {}

        if cfg.get("command"):
            template = [str(part) for part in cfg["command"]]
            argv = [
                part.replace("{prompt}", current_prompt).replace("{model}", model).replace("{workdir}", str(cwd))
                for part in template
            ]
            parse = cfg.get("parse", "text")
        elif key == "gemini":
            key_value = gemini_api_key()
            if key_value:
                env["GEMINI_API_KEY"] = key_value
            argv = ["gemini", "-p", current_prompt, "--output-format", "text", "--skip-trust"]
            if model:
                argv += ["-m", model]
            if context == "cwd":
                argv += ["--approval-mode", "plan"]
            parse = "text"
        elif key == "codex":
            argv = [
                "codex",
                "exec",
                "--skip-git-repo-check",
                "--json",
                "--color",
                "never",
                "-s",
                "read-only" if context == "cwd" else "workspace-write",
            ]
            if model:
                argv += ["-m", model]
            argv.append(current_prompt)
            parse = "codex-jsonl"
        elif key == "kimi":
            argv = ["kimi", "-p", current_prompt, "--output-format", "stream-json"]
            if model:
                argv += ["-m", model]
            if context == "cwd":
                argv += ["--plan"]
            parse = "kimi-jsonl"
        elif key == "deepseek":
            dsh = find_dsh(settings)
            if not dsh:
                raise RuntimeError(
                    "DeepSeek runner not found: install the DSH app or set ENSEMBLE_DSH_PATH"
                )
            auth = deepseek_auth_mode(config)
            patch = deepseek_patch(run_dir, model or "deepseek-flash", auth)
            argv = [dsh, "--profile", "headless"]
            if patch:
                argv += ["--patch", str(patch)]
            argv += ["--json", current_prompt]
            parse = "dsh-jsonl"
        else:
            raise RuntimeError(f"unknown provider: {key}")

        specs.append(
            Spec(
                key=key,
                label=cfg["label"],
                accent=cfg.get("accent", "#444"),
                argv=argv,
                cwd=cwd,
                timeout=timeout,
                parse=parse,
                model=model,
                env=env,
            )
        )
    return specs


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #

ACTIVE: set = set()


def kill_tree(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:  # noqa: BLE001
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass
    try:
        proc.wait(timeout=3)
    except Exception:  # noqa: BLE001
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass


@dataclass
class Result:
    key: str
    label: str
    accent: str
    status: str
    text: str = ""
    error: str = ""
    hint: str = ""
    elapsed: float = 0.0
    reported_ms: Optional[float] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    tokens_total: Optional[int] = None
    cost: Optional[float] = None
    model: str = ""
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    argv: List[str] = field(default_factory=list)
    debate: Optional["Result"] = None


def execute(spec: Spec, set_active=None) -> Result:
    started = time.monotonic()
    env = dict(os.environ)
    env.update(spec.env)
    env.setdefault("NO_COLOR", "1")
    result = Result(
        key=spec.key,
        label=spec.label,
        accent=spec.accent,
        status="running",
        model=spec.model,
        argv=spec.argv,
    )
    try:
        proc = subprocess.Popen(
            spec.argv,
            cwd=str(spec.cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            env=env,
            start_new_session=True,
        )
    except FileNotFoundError:
        result.elapsed = time.monotonic() - started
        result.status = "error"
        result.error = f"command not found: {spec.argv[0]}"
        result.hint = f"Install the {spec.label} CLI, then run `ensemble doctor`."
        return result
    except Exception as exc:  # noqa: BLE001
        result.elapsed = time.monotonic() - started
        result.status = "error"
        result.error = str(exc)
        return result

    ACTIVE.add(proc)
    if set_active:
        set_active(spec.key, proc)
    timed_out = False
    try:
        out, err = proc.communicate(timeout=spec.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=5)
        except Exception:  # noqa: BLE001
            out, err = "", ""
    finally:
        ACTIVE.discard(proc)
        if set_active:
            set_active(spec.key, None)

    result.elapsed = time.monotonic() - started
    result.exit_code = proc.returncode
    result.stdout = strip_ansi(out or "")
    result.stderr = strip_ansi(err or "")

    if timed_out:
        result.status = "timeout"
        result.error = f"timed out after {human_secs(spec.timeout)}"
        result.hint = "Raise it with --timeout, or try a smaller prompt."
        result.text = parse_output(spec.parse, result.stdout, result.stderr)[0]
        return result

    text, error, meta = parse_output(spec.parse, result.stdout, result.stderr)
    result.text = text
    result.error = error
    for key, value in meta.items():
        setattr(result, key, value)
    result.model = result.model or spec.model

    if result.status != "error":
        if result.error:
            result.status = "error"
        elif result.exit_code not in (0, None) and not text.strip():
            result.status = "error"
            result.error = result.stderr.strip() or f"exited with code {result.exit_code}"
        elif not text.strip():
            result.status = "empty"
            result.error = "model returned an empty response"
        else:
            result.status = "ok"

    if result.status != "ok":
        result.hint = hint_for(result.key, result.error + "\n" + result.stderr)
    return result


def parse_output(parse: str, stdout: str, stderr: str) -> Tuple[str, str, dict]:
    """Return (text, error, metadata) for one provider's raw output."""
    meta: dict = {}
    text = ""
    error = ""

    if parse == "codex-jsonl":
        messages: List[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            kind = event.get("type")
            if kind == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message" and item.get("text"):
                    messages.append(item["text"])
            elif kind == "turn.completed":
                usage = event.get("usage") or {}
                meta["tokens_in"] = usage.get("input_tokens")
                meta["tokens_out"] = usage.get("output_tokens")
                cached = usage.get("cached_input_tokens") or 0
                if meta["tokens_in"] is not None:
                    meta["tokens_total"] = meta["tokens_in"] + (meta["tokens_out"] or 0)
                if cached:
                    meta["tokens_cached"] = cached
            elif kind in ("error", "turn.failed"):
                error = str(event.get("message") or event.get("error") or event)
        text = messages[-1] if messages else ""
        if not text:
            text = stdout.strip() if not stdout.lstrip().startswith("{") else ""
        if not text and not error:
            error = tail(stderr) or "Codex returned no final message"

    elif parse == "kimi-jsonl":
        chunks: List[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if event.get("role") != "assistant":
                continue
            content = event.get("content")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") in ("text", "output_text"):
                        chunks.append(block.get("text") or "")
                    elif isinstance(block, str):
                        chunks.append(block)
        text = "".join(chunks).strip()
        if not text:
            error = tail(stderr) or ("Kimi returned no assistant message" if stdout.strip() else "")

    elif parse == "dsh-jsonl":
        chunks: List[str] = []
        final = ""
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue  # diagnostics such as [llm-deepseek-account] ...
            try:
                event = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            kind = event.get("type")
            if kind == "text" and event.get("text"):
                chunks.append(event["text"])
            elif kind == "final" and event.get("text"):
                final = event["text"]
            elif kind == "status" and event.get("phase") == "step_end":
                usage = event.get("usage") or {}
                meta["tokens_in"] = usage.get("inputTokens")
                meta["tokens_out"] = usage.get("outputTokens")
                meta["tokens_total"] = usage.get("totalTokens")
            elif kind == "error":
                error = str(event.get("message") or event)
        text = final or "".join(chunks).strip()
        if not text and not error:
            error = tail(stderr)

    else:  # plain text
        text = stdout.strip()
        if not text and stderr.strip():
            error = tail(stderr)

    return text.strip(), error.strip(), meta


def tail(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return "…" + text[-limit:]


HINTS = {
    "kimi": [
        (("insufficient balance", "suspended", "429"),
         "Moonshot balance is exhausted. Top up at platform.moonshot.ai, or use the Kimi Code plan: `--model kimi=kimi-code`."),
    ],
    "deepseek": [
        (("account_sign_in_required", "missing_credential", "no api key"),
         "Sign in to DeepSeek in the DSH app, or export DEEPSEEK_API_KEY and set ENSEMBLE_DEEPSEEK_AUTH=api-key."),
    ],
    "gemini": [
        (("set an auth method", "gemini_api_key", "google_genai", "not logged in"),
         "Run `gemini` to sign in, or export GEMINI_API_KEY=... and retry."),
    ],
    "codex": [
        (("not logged in", "401 unauthorized", "login"),
         "Run `codex login` and retry."),
    ],
}


def hint_for(key: str, text: str) -> str:
    lowered = (text or "").lower()
    for needles, hint in HINTS.get(key, []):
        if any(needle in lowered for needle in needles):
            return hint
    return ""


# --------------------------------------------------------------------------- #
# Progress + terminal summary
# --------------------------------------------------------------------------- #


class Progress:
    def __init__(self, specs: List[Spec], enabled: bool, label: Optional[str] = None):
        self.specs = specs
        self.label = label or ""
        self.quiet = not enabled
        self.enabled = enabled and sys.stderr.isatty()
        self.started: Dict[str, float] = {}
        self.finished: Dict[str, Result] = {}
        self.last = ""
        self.spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spin_i = 0

    def start(self):
        if self.quiet:
            return
        label = f"{len(self.specs)} model" + ("" if len(self.specs) == 1 else "s")
        prefix = f"{self.label} · " if self.label else ""
        if self.enabled:
            eprint(colorize(f"◆ ensemble · {prefix}{label} · running in parallel", "\033[1m", True))
        else:
            eprint(f"ensemble: {prefix}running {label} in parallel (timeout {human_secs(self.specs[0].timeout)})")

    def tick(self, active_keys: List[str]):
        if not self.enabled or not active_keys:
            return
        elapsed = time.time() - min(self.started.values()) if self.started else 0
        names = " · ".join(self.specs_by_key()[k].label for k in active_keys)
        frame = self.spinner[self.spin_i % len(self.spinner)]
        self.spin_i += 1
        line = f"  {frame} {human_secs(elapsed):>5}  waiting on {names}"
        if line != self.last:
            sys.stderr.write("\r\033[K" + line[:200])
            sys.stderr.flush()
            self.last = line

    def specs_by_key(self):
        return {spec.key: spec for spec in self.specs}

    def begin(self, key: str):
        self.started[key] = time.time()

    def finish(self, result: Result):
        self.finished[result.key] = result
        if self.quiet:
            return
        if self.enabled:
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()
        icon = {"ok": "✓", "error": "✗", "timeout": "◷", "empty": "○"}.get(result.status, "•")
        detail = human_secs(result.elapsed)
        if result.status == "ok":
            detail += f" · {human_int(len(result.text))} chars"
            if result.tokens_total:
                detail += f" · {human_int(result.tokens_total)} tok"
        elif result.error:
            detail += f" · {truncate(result.error, 90)}"
        eprint(f"  {icon} {result.label:<9} {detail}")

    def clear(self):
        if self.enabled and self.last:
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()


def print_summary(results: List[Result], no_color: bool, show_hints: bool = True) -> None:
    col = use_color(no_color)
    print()
    header = f"{'MODEL':<10} {'STATUS':<8} {'TIME':>7} {'TOKENS':>8} {'OUTPUT':>9}  MODEL"
    print(colorize(header, "\033[2m", col))
    for result in results:
        status = result.status
        code = {"ok": "\033[32m", "error": "\033[31m", "timeout": "\033[33m", "empty": "\033[33m"}.get(
            status, "\033[0m"
        )
        tokens = human_int(result.tokens_total) if result.tokens_total else "—"
        out = f"{len(result.text):,}" if result.text else "—"
        colored_status = colorize(f"{status:<8}", code, col)
        print(
            f"{result.label:<10} {colored_status} "
            f"{human_secs(result.elapsed):>7} {tokens:>8} {out:>9}  {result.model or 'default'}"
        )
    if show_hints:
        hinted = [r for r in results if r.hint and r.status != "ok"]
        if hinted:
            print()
            for result in hinted:
                bold_label = colorize(result.label, "\033[1m", col)
                print(f"  {bold_label}: {result.hint}")


def print_paths(run_dir: Path, result_count: int, no_color: bool) -> None:
    col = use_color(no_color)
    print()
    dim = lambda text: colorize(text, "\033[2m", col)
    print(f"  {dim('Report')}  {run_dir / 'report.html'}")
    print(f"  {dim('Folder')}  {run_dir}")
    print(f"  {dim('Models')}  {result_count} ran · raw output kept per provider")
    print()


# --------------------------------------------------------------------------- #
# Parallel runner
# --------------------------------------------------------------------------- #


def run_specs(specs: List[Spec], no_color: bool = False, quiet: bool = False,
              sequential: bool = False, phase_label: Optional[str] = None,
              on_active=None, on_result=None) -> List[Result]:
    if not specs:
        return []
    progress = Progress(specs, enabled=not quiet, label=phase_label)
    started = time.time()
    progress.started = {spec.key: started for spec in specs}
    progress.start()

    results: List[Result] = []
    if sequential:
        for spec in specs:
            result = execute(spec, set_active=on_active)
            progress.finish(result)
            if on_result:
                on_result(result)
            results.append(result)
        progress.clear()
        return results

    executor = cf.ThreadPoolExecutor(max_workers=min(8, len(specs)))
    futures = {executor.submit(execute, spec, on_active): spec for spec in specs}
    pending = set(futures)
    try:
        while pending:
            done, pending = cf.wait(pending, timeout=0.2)
            for future in done:
                spec = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 - keep the run alive
                    result = Result(
                        key=spec.key,
                        label=spec.label,
                        accent=spec.accent,
                        status="error",
                        error=f"runner crashed: {exc}",
                        model=spec.model,
                        argv=spec.argv,
                    )
                results.append(result)
                progress.finish(result)
                if on_result:
                    on_result(result)
            if pending:
                progress.tick([futures[f].key for f in pending])
    except KeyboardInterrupt:
        for proc in list(ACTIVE):
            kill_tree(proc)
        executor.shutdown(wait=False, cancel_futures=True)
        progress.clear()
        eprint("\ninterrupted — stopped all running models")
        raise
    executor.shutdown(wait=True)
    progress.clear()
    order = {spec.key: index for index, spec in enumerate(specs)}
    return sorted(results, key=lambda item: order.get(item.key, 99))


# --------------------------------------------------------------------------- #
# Debate round
# --------------------------------------------------------------------------- #


def build_debate_prompts(prompt: str, results: List[Result], max_chars: int = 8000) -> Dict[str, str]:
    ok = [r for r in results if r.status == "ok" and r.text]
    if len(ok) < 2:
        return {}

    def body(result: Result) -> str:
        text = result.text.strip()
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "\n…[truncated]"
        return text

    prompts: Dict[str, str] = {}
    for target in ok:
        blocks = []
        for result in ok:
            marker = " — YOUR INITIAL ANSWER" if result.key == target.key else ""
            blocks.append(
                f"--- {result.label} ({result.model or 'default'}){marker} ---\n{body(result)}"
            )
        prompts[target.key] = "\n".join([
            "You are in a structured debate with other AI models. All of you answered "
            "this prompt independently:",
            "",
            "```text",
            prompt.rstrip(),
            "```",
            "",
            "Here are the initial answers:",
            "",
            "\n\n".join(blocks),
            "",
            f"You are {target.label}. Write a rebuttal, not a new essay. Do exactly three things:",
            "1. Attack the strongest claim in another answer that you believe is wrong. "
            "Quote it in one sentence and explain the error.",
            "2. Defend, correct, or revise your own initial answer. If another model changed "
            "your mind, name the exact claim that did it.",
            "3. End with \"My position now:\" followed by at most 80 words stating your final answer.",
            "",
            "Be direct and specific. No compliments, no restating the prompt, no full rewrite.",
        ])
    return prompts


def debate_round(run_dir: Path, prompt: str, results: List[Result],
                 settings: Dict[str, dict], models: Dict[str, str],
                 workdirs: Dict[str, Path], context: str, config: dict,
                 no_color: bool = False, quiet: bool = False,
                 sequential: bool = False, on_active=None, on_result=None,
                 phase_label: str = "Round 2 · debate") -> Dict[str, Result]:
    """Run one rebuttal round. Returns debate results keyed by provider."""
    ok = [r for r in results if r.status == "ok" and r.text]
    if len(ok) < 2:
        return {}
    prompts = build_debate_prompts(prompt, ok)
    specs: List[Spec] = []
    out: Dict[str, Result] = {}
    for initial in ok:
        try:
            spec = build_specs(
                [initial.key], prompt, settings, models, workdirs, context,
                run_dir, config, prompt_map=prompts,
            )[0]
            specs.append(spec)
        except Exception as exc:  # noqa: BLE001 - keep the other rebuttals
            out[initial.key] = Result(
                key=initial.key, label=initial.label, accent=initial.accent,
                status="error", error=f"debate setup failed: {exc}",
                model=initial.model, hint=hint_for(initial.key, str(exc)),
            )
    if specs:
        ran = run_specs(
            specs, no_color=no_color, quiet=quiet, sequential=sequential,
            phase_label=phase_label, on_active=on_active, on_result=on_result,
        )
        out.update({result.key: result for result in ran})
    return out


def attach_debates(results: List[Result], debates: Dict[str, Result]) -> None:
    for result in results:
        if result.key in debates:
            result.debate = debates[result.key]


# --------------------------------------------------------------------------- #
# Directed cross-examination
# --------------------------------------------------------------------------- #


def load_challenges(run_dir: Path) -> List[dict]:
    path = run_dir / "challenges.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def save_challenge(run_dir: Path, challenge: dict) -> None:
    challenges = load_challenges(run_dir)
    challenges = [c for c in challenges if c.get("id") != challenge.get("id")]
    challenges.append(challenge)
    (run_dir / "challenges.json").write_text(json.dumps(challenges, indent=2) + "\n")


def build_challenge_prompt(prompt: str, challenger: Result, target: Result) -> str:
    def body(result: Result) -> str:
        text = (result.text or "").strip()
        if len(text) > 8000:
            text = text[:8000].rstrip() + "\n…[truncated]"
        return text

    own = body(challenger)
    return "\n".join([
        f"You are {challenger.label}. The original prompt was:",
        "",
        "```text",
        prompt.rstrip(),
        "```",
        "",
        f"--- {target.label}'S ANSWER (the target) ---",
        body(target),
        "",
        f"--- YOUR OWN INITIAL ANSWER ({challenger.label}) ---",
        own if own else "(none)",
        "",
        f"Argue directly against {target.label}'s answer. Do not restate your own answer "
        "as the main body and do not write a generic essay. Do exactly three things:",
        f"1. Quote the two weakest claims in {target.label}'s answer and explain precisely why they fail.",
        "2. Give the strongest counterargument or missing evidence for each.",
        "3. State what a better answer would conclude, and where you concede the target may be right.",
        "",
        "Be direct and specific. Max 300 words. End with a line starting \"Verdict:\".",
    ])


def run_challenge(run_dir: Path, prompt: str, challenger: Result, target: Result,
                  settings: Dict[str, dict], models: Dict[str, str], config: dict,
                  timeout: float = 300, set_active=None) -> Result:
    workdir = Path(tempfile.mkdtemp(prefix=f"ensemble-challenge-{challenger.key}-"))
    try:
        spec = build_specs(
            [challenger.key], build_challenge_prompt(prompt, challenger, target),
            settings, models, {challenger.key: workdir}, "temp", run_dir, config,
        )[0]
        spec.timeout = timeout
        return execute(spec, set_active=set_active)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def result_to_challenge(challenge_id: str, result: Result, challenger: Result,
                        target: Result) -> dict:
    return {
        "id": challenge_id,
        "from_key": challenger.key,
        "from_label": challenger.label,
        "to_key": target.key,
        "to_label": target.label,
        "status": result.status,
        "text": result.text,
        "error": result.error,
        "hint": result.hint,
        "elapsed": round(result.elapsed, 2),
        "tokens_total": result.tokens_total,
        "model": result.model or challenger.model,
        "created_at": now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


# --------------------------------------------------------------------------- #
# Artifacts and reports
# --------------------------------------------------------------------------- #


def safe_filename(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", key)


def result_to_dict(result: Result, prompt: str) -> dict:
    argv = []
    for part in result.argv:
        argv.append("<prompt>" if part == prompt else part)
    return {
        "key": result.key,
        "label": result.label,
        "accent": result.accent,
        "status": result.status,
        "text": result.text,
        "error": result.error,
        "hint": result.hint,
        "elapsed": round(result.elapsed, 3),
        "reported_ms": result.reported_ms,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "tokens_total": result.tokens_total,
        "cost": result.cost,
        "model": result.model,
        "exit_code": result.exit_code,
        "argv": argv,
        "debate": result_to_dict(result.debate, prompt) if result.debate else None,
    }


def dict_to_result(data: dict) -> Result:
    return Result(
        key=data.get("key", "?"),
        label=data.get("label", data.get("key", "?")),
        accent=data.get("accent", "#444"),
        status=data.get("status", "error"),
        text=data.get("text", ""),
        error=data.get("error", ""),
        hint=data.get("hint", ""),
        elapsed=float(data.get("elapsed", 0)),
        reported_ms=data.get("reported_ms"),
        tokens_in=data.get("tokens_in"),
        tokens_out=data.get("tokens_out"),
        tokens_total=data.get("tokens_total"),
        cost=data.get("cost"),
        model=data.get("model", ""),
        exit_code=data.get("exit_code"),
        argv=data.get("argv", []),
        debate=dict_to_result(data["debate"]) if data.get("debate") else None,
    )


def write_artifacts(run_dir: Path, prompt: str, results: List[Result], meta: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "prompt.md").write_text(prompt.rstrip() + "\n")
    def write_result_files(result: Result, suffix: str = "") -> None:
        name = safe_filename(result.key) + suffix
        (run_dir / f"{name}.stdout.txt").write_text(result.stdout or "")
        (run_dir / f"{name}.stderr.txt").write_text(result.stderr or "")
        if result.text:
            (run_dir / f"{name}.md").write_text(result.text.rstrip() + "\n")
        elif result.error:
            (run_dir / f"{name}.error.txt").write_text(result.error.rstrip() + "\n")

    for result in results:
        write_result_files(result)
        if result.debate:
            write_result_files(result.debate, ".debate")
    meta = dict(meta)
    meta["results"] = [result_to_dict(r, prompt) for r in results]
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    (run_dir / "results.json").write_text(
        json.dumps([result_to_dict(r, prompt) for r in results], indent=2) + "\n"
    )


def load_run(run_dir: Path) -> Tuple[str, dict, List[Result]]:
    meta = json.loads((run_dir / "meta.json").read_text())
    prompt = meta.get("prompt", "")
    results = [dict_to_result(row) for row in json.loads((run_dir / "results.json").read_text())]
    return prompt, meta, results


SANITIZE_TAGS = {
    "a", "b", "blockquote", "br", "code", "dd", "del", "div", "dl", "dt",
    "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins",
    "kbd", "li", "ol", "p", "pre", "s", "span", "strong", "sub", "summary",
    "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
SANITIZE_VOID = {"br", "hr", "img"}
# Whole subtrees are dropped, including their text.
SANITIZE_DROP = {
    "script", "style", "iframe", "frame", "frameset", "object", "embed",
    "applet", "template", "noscript", "svg", "math", "form", "input",
    "button", "select", "textarea", "link", "meta", "base",
}
SANITIZE_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "code": {"class"},
    "pre": {"class"},
    "span": {"class"},
    "div": {"class"},
    "th": {"align", "colspan", "rowspan"},
    "td": {"align", "colspan", "rowspan"},
}
_SCHEME_RE = re.compile(r"^\s*([a-zA-Z][a-zA-Z0-9+.-]*):")


def safe_url(value: str) -> bool:
    """Allow relative URLs and http/https/mailto only."""
    if not value:
        return False
    match = _SCHEME_RE.match(value)
    if not match:
        return True
    return match.group(1).lower() in ("http", "https", "mailto")


class _Sanitizer(HTMLParser):
    """Rebuild an HTML fragment from an allowlist of tags and attributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.stack: List[str] = []
        self.skip = 0

    def _attrs(self, tag: str, attrs) -> str:
        allowed = SANITIZE_ATTRS.get(tag, set())
        rendered: List[str] = []
        for name, value in attrs:
            name = (name or "").lower()
            if name not in allowed or value is None:
                continue
            if name in ("href", "src") and not safe_url(value):
                continue
            rendered.append(f' {name}="{html.escape(value, quote=True)}"')
        if tag == "img":
            rendered.append(' referrerpolicy="no-referrer"')
            rendered.append(' loading="lazy"')
        return "".join(rendered)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in SANITIZE_DROP:
            self.skip += 1
            return
        if self.skip or tag not in SANITIZE_TAGS:
            return
        self.parts.append(f"<{tag}{self._attrs(tag, attrs)}>")
        if tag not in SANITIZE_VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self.skip or tag not in SANITIZE_TAGS or tag in SANITIZE_DROP:
            return
        self.parts.append(f"<{tag}{self._attrs(tag, attrs)}>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in SANITIZE_DROP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in self.stack:
            return
        while self.stack:
            top = self.stack.pop()
            self.parts.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(html.escape(data, quote=False))

    def handle_comment(self, data):  # comments never reach the page
        return

    def close(self):
        super().close()
        while self.stack:
            self.parts.append(f"</{self.stack.pop()}>")


def sanitize_html(fragment: str) -> str:
    """Strip anything executable from an HTML fragment (model output)."""
    parser = _Sanitizer()
    try:
        parser.feed(fragment or "")
        parser.close()
    except Exception:  # noqa: BLE001 - fail closed on malformed markup
        return f"<pre>{html.escape(fragment or '')}</pre>"
    return "".join(parser.parts)


def render_markdown(text: str) -> str:
    try:
        import markdown  # type: ignore

        body = markdown.markdown(
            text,
            extensions=["fenced_code", "tables", "sane_lists"],
            output_format="html5",
        )
    except Exception:  # noqa: BLE001 - no dependency on the markdown package
        return f"<pre>{html.escape(text)}</pre>"

    # markdown passes raw HTML through untouched; model output is untrusted.
    body = sanitize_html(body)

    def wrap_table(match):
        table = match.group(0)
        head = re.search(r"<tr>(.*?)</tr>", table, re.S)
        wide = bool(head and head.group(1).count("<th") >= 4)
        cls = "table-wrap wide" if wide else "table-wrap"
        return f'<div class="{cls}">{table}</div>'

    return re.sub(r"<table>.*?</table>", wrap_table, body, flags=re.S)


CSS = """
:root{
  --paper:#f5f2ea; --card:#ffffff; --ink:#191b1f; --muted:#6d7178; --line:#e4dfd3;
  --soft:#faf8f2; --navy:#1f3a5f;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
}
@media (prefers-color-scheme:dark){
  :root{--paper:#131519;--card:#1a1d23;--ink:#e9e7e1;--muted:#9ba1aa;--line:#2b3038;--soft:#15181d;--navy:#9db4d6}
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font:15px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
main{max-width:1480px;margin:0 auto;padding:54px 28px 80px}
.hero{max-width:1050px}
.kicker{font-size:11px;letter-spacing:.19em;text-transform:uppercase;color:var(--muted);font-weight:600}
h1{font:600 38px/1.16 var(--serif);margin:14px 0 16px;letter-spacing:-.01em}
.meta{display:flex;flex-wrap:wrap;gap:8px}
.chip{font-size:12px;color:var(--muted);border:1px solid var(--line);background:var(--card);
  border-radius:999px;padding:4px 11px}
.chip b{color:var(--ink);font-weight:600}
details.prompt{margin:30px 0 26px;border:1px solid var(--line);background:var(--card);
  border-radius:12px;padding:0 18px}
details.prompt summary{cursor:pointer;padding:12px 0;font-size:12px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--muted);font-weight:600}
.prompt-body{white-space:pre-wrap;font:13.5px/1.65 var(--mono);padding:4px 0 18px;
  overflow-wrap:anywhere;max-height:340px;overflow:auto}
.summary{margin:0 0 28px;border:1px solid var(--line);border-radius:12px;background:var(--card);overflow:auto}
table{width:100%;border-collapse:collapse}
th{font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);
  text-align:left;padding:10px 14px;border-bottom:1px solid var(--line);font-weight:600}
td{padding:11px 14px;border-bottom:1px solid var(--line);font-size:13.5px;vertical-align:middle}
tr:last-child td{border-bottom:0}
td.num{font-variant-numeric:tabular-nums;color:var(--muted)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent);margin-right:8px}
.pill{display:inline-block;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
  font-weight:600;padding:3px 8px;border-radius:999px}
.pill.ok{background:#e8f4ee;color:#14603f}
.pill.error{background:#fbeceb;color:#8f2b22}
.pill.timeout,.pill.empty{background:#fbf1df;color:#7c5413}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px;align-items:start}
@media(min-width:1200px){
  .grid:has(.card:nth-child(3):last-child){grid-template-columns:repeat(3,minmax(0,1fr))}
}
.card{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--accent);
  border-radius:14px;overflow:hidden;box-shadow:0 1px 2px rgba(20,25,35,.05)}
.card-top{display:flex;align-items:center;justify-content:space-between;gap:10px;
  padding:16px 20px 12px;flex-wrap:wrap}
.card-title{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
h2{font:600 20px/1.2 var(--serif);margin:0}
.model{font:11px/1.4 var(--mono);color:var(--muted);background:var(--soft);
  border:1px solid var(--line);padding:2px 7px;border-radius:6px}
.metrics{padding:0 20px 12px;font-size:12px;color:var(--muted);
  font-variant-numeric:tabular-nums;display:flex;gap:14px;flex-wrap:wrap}
.md{padding:2px 20px 20px;font-size:14.5px;overflow-wrap:anywhere}
.md p{margin:0 0 .8em}
.md h1,.md h2,.md h3{font-family:var(--serif);line-height:1.25;margin:1em 0 .45em}
.md h1{font-size:1.35em}.md h2{font-size:1.22em}.md h3{font-size:1.1em}
.md ul,.md ol{padding-left:1.3em;margin:0 0 .9em}
.md li{margin:.22em 0}
.md code{font:0.9em var(--mono);background:var(--soft);border:1px solid var(--line);
  border-radius:5px;padding:1px 5px}
.md pre{background:#171b22;color:#e8edf6;padding:14px 16px;border-radius:10px;overflow:auto;
  font:12.5px/1.55 var(--mono);border:1px solid #0d1015}
.md pre code{background:none;border:0;padding:0;color:inherit;font-size:inherit}
.md blockquote{margin:0 0 .9em;padding:2px 0 2px 14px;border-left:3px solid var(--accent);color:var(--muted)}
.md table{font-size:13px;margin:0}
.md th,.md td{padding:6px 9px;border:1px solid var(--line);
  overflow-wrap:normal;word-break:normal}
.table-wrap{max-width:100%;overflow-x:auto;margin:.6em 0 .9em}
.md a{color:var(--navy);text-decoration:underline;text-underline-offset:2px}
.md img{max-width:100%;border-radius:8px}
.debate-block{margin:0 20px 20px;padding-top:14px;border-top:1px solid var(--line)}
.debate-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.debate-label{font:600 10px/1 var(--sans);letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.debate-meta{margin-left:auto;font:10.5px/1.4 var(--mono);color:var(--muted)}
.debate-block .md{padding:0}
.debate-block .error{margin:0}
.error{margin:0 20px 14px;background:#fdf1ef;border:1px solid #f1cfc8;color:#7b2a20;
  border-radius:10px;padding:13px 15px;font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}
.hint{margin:0 20px 18px;font-size:12.5px;color:var(--muted)}
.hint code{font-family:var(--mono);background:var(--soft);border:1px solid var(--line);
  border-radius:4px;padding:1px 4px}
details.raw{margin-top:10px}
details.raw summary{cursor:pointer;font-size:11px;color:var(--muted)}
details.raw pre{margin:8px 0 0;font:11.5px/1.5 var(--mono);white-space:pre-wrap;color:var(--muted)}
.judge{margin:28px 0;border:1px solid #d9c9a3;border-top:3px solid #b8860b;
  border-radius:14px;background:var(--card);padding:4px 22px 20px}
.challenges{margin:28px 0;display:flex;flex-direction:column;gap:14px}
.challenge{border:1px solid var(--line);border-radius:14px;background:var(--card);padding:16px 20px 20px}
.challenge-head{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap}
.challenge-label{font:600 10px/1 var(--sans);letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.challenge-route{font:600 15px/1.3 var(--sans);letter-spacing:-.01em}
.challenge-route .arrow{color:var(--muted);font-weight:400;margin:0 5px}
.challenge-meta{margin-left:auto;font:10.5px/1.4 var(--mono);color:var(--muted)}
.challenge .md{padding:10px 0 0}
.challenge .error{margin:10px 0 0}
.judge .kicker{margin-top:16px}
footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);font-size:11.5px;
  color:var(--muted);display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
@media (prefers-color-scheme:dark){
  .error{background:#2a1a18;border-color:#5a302b;color:#f0b5ac}
  .pill.ok{background:#143024;color:#7fd6a8}
  .pill.error{background:#321a18;color:#f3a79c}
  .pill.timeout,.pill.empty{background:#302614;color:#e5c07b}
}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
@media(max-width:640px){main{padding:34px 16px 60px}h1{font-size:28px}}
@media print{body{background:#fff}.card,.summary,.judge{box-shadow:none;break-inside:avoid}
  .grid{grid-template-columns:1fr 1fr}}
"""

HTML_TEMPLATE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>$css</style>
</head>
<body>
<main>
  <header class="hero">
    <div class="kicker">Ensemble · one prompt, $count models</div>
    <h1>$headline</h1>
    <div class="meta">$chips</div>
  </header>

  <details class="prompt" open>
    <summary>Prompt</summary>
    <div class="prompt-body">$prompt</div>
  </details>

  <section class="summary">
    <table>
      <thead><tr><th>Model</th><th>Status</th><th>Time</th><th>Tokens</th><th>Cost</th><th>Output</th></tr></thead>
      <tbody>$rows</tbody>
    </table>
  </section>

  <section class="grid">
$cards
  </section>

$challenges

$judge

  <footer>
    <span>ensemble v$version · generated $generated</span>
    <span>$folder</span>
  </footer>
</main>
</body>
</html>
""")


def fmt_cost(cost: Optional[float]) -> str:
    if cost is None:
        return "—"
    if cost == 0:
        return "$0"
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.3f}"


def status_pill(status: str) -> str:
    cls = status if status in ("ok", "error", "timeout", "empty") else "empty"
    return f'<span class="pill {cls}">{html.escape(status)}</span>'


def debate_section_html(debate: Result) -> str:
    if debate.status == "ok" and debate.text:
        meta = human_secs(debate.elapsed)
        if debate.tokens_total:
            meta += f" · {human_int(debate.tokens_total)} tok"
        return (
            '<section class="debate-block">'
            '<div class="debate-head"><span class="debate-label">Rebuttal</span>'
            f'{status_pill(debate.status)}<span class="debate-meta">{html.escape(meta)}</span></div>'
            f'<div class="md">{render_markdown(debate.text)}</div></section>'
        )
    raw = (debate.stderr or debate.stdout or "").strip()
    raw_html = f'<details class="raw"><summary>Raw output</summary><pre>{html.escape(tail(raw, 3000))}</pre></details>' if raw else ""
    hint = f'<p class="hint">→ {html.escape(debate.hint.replace("`", ""))}</p>' if debate.hint else ""
    return (
        '<section class="debate-block">'
        '<div class="debate-head"><span class="debate-label">Rebuttal</span>'
        f'{status_pill(debate.status)}<span class="debate-meta">{html.escape(human_secs(debate.elapsed))}</span></div>'
        f'<div class="error">{html.escape(debate.error or debate.status)}{raw_html}</div>{hint}</section>'
    )


def card_html(result: Result) -> str:
    style = f'style="--accent:{html.escape(result.accent)}"'
    model = result.model or "default"
    metrics = [human_secs(result.elapsed)]
    if result.text:
        metrics.append(f"{len(result.text):,} chars")
    if result.tokens_total:
        metrics.append(f"{human_int(result.tokens_total)} tok")
    if result.cost is not None and result.status == "ok":
        metrics.append(fmt_cost(result.cost))
    metric_html = "".join(f"<span>{html.escape(item)}</span>" for item in metrics)

    if result.status == "ok":
        body = f'<div class="md">{render_markdown(result.text)}</div>'
        if result.debate:
            body += debate_section_html(result.debate)
    else:
        raw = (result.stderr or result.stdout or "").strip()
        raw_html = ""
        if raw:
            raw_html = (
                f'<details class="raw"><summary>Raw output</summary>'
                f"<pre>{html.escape(tail(raw, 4000))}</pre></details>"
            )
        body = (
            f'<div class="error">{html.escape(result.error or result.status)}'
            f"{raw_html}</div>"
        )
        if result.hint:
            body += f'<p class="hint">→ {html.escape(result.hint.replace("`", ""))}</p>'
        elif result.status == "timeout":
            body += '<p class="hint">→ Raise --timeout, or try a shorter prompt.</p>'

    return f"""    <article class="card" {style}>
      <div class="card-top">
        <div class="card-title"><span class="dot"></span><h2>{html.escape(result.label)}</h2>
          <span class="model">{html.escape(model)}</span></div>
        {status_pill(result.status)}
      </div>
      <div class="metrics">{metric_html}</div>
      {body}
    </article>"""


def summary_rows(results: List[Result]) -> str:
    rows = []
    for result in results:
        rows.append(
            "<tr>"
            f'<td><span class="dot" style="--accent:{html.escape(result.accent)}"></span>'
            f"<strong>{html.escape(result.label)}</strong></td>"
            f"<td>{status_pill(result.status)}</td>"
            f'<td class="num">{human_secs(result.elapsed)}</td>'
            f'<td class="num">{human_int(result.tokens_total) if result.tokens_total else "—"}</td>'
            f'<td class="num">{fmt_cost(result.cost) if result.status == "ok" else "—"}</td>'
            f'<td class="num">{f"{len(result.text):,} chars" if result.text else "—"}</td>'
            "</tr>"
        )
    return "\n".join(rows)


def report_markdown(meta: dict, results: List[Result], judge: Optional[dict],
                    challenges: Optional[List[dict]] = None) -> str:
    prompt = meta.get("prompt", "")
    lines = [
        f"# Ensemble — {first_line(prompt, 80)}",
        "",
        f"*{meta.get('created_at', '')} · {len(results)} models · "
        f"{human_secs(float(meta.get('wall_seconds', 0)))} wall · "
        f"context: {meta.get('context', 'temp')}*",
        "",
        "## Prompt",
        "",
        "```text",
        prompt.rstrip(),
        "```",
        "",
        "## Results",
        "",
        "| Model | Status | Time | Tokens | Cost | Output |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for result in results:
        tokens = human_int(result.tokens_total) if result.tokens_total else "—"
        chars = f"{len(result.text):,}" if result.text else "—"
        lines.append(
            f"| {result.label} | {result.status} | {human_secs(result.elapsed)} | "
            f"{tokens} | {fmt_cost(result.cost) if result.status == 'ok' else '—'} | {chars} |"
        )
    lines.append("")
    debated = sum(1 for r in results if r.debate)
    if debated:
        lines += [f"*Rebuttal round: {debated}/{len(results)} models responded.*", ""]
    for result in results:
        lines += [f"## {result.label} — {result.status} ({human_secs(result.elapsed)})", ""]
        if result.text:
            lines += [result.text.strip(), ""]
        else:
            lines += [f"> **{result.error or result.status}**", ""]
            if result.hint:
                lines += [f"*{result.hint}*", ""]
        if result.debate:
            debate = result.debate
            lines += [f"### Rebuttal — {debate.status} ({human_secs(debate.elapsed)})", ""]
            if debate.text:
                lines += [debate.text.strip(), ""]
            else:
                lines += [f"> **{debate.error or debate.status}**", ""]
                if debate.hint:
                    lines += [f"*{debate.hint}*", ""]
    for challenge in challenges or []:
        route = f"{challenge.get('from_label', '')} → {challenge.get('to_label', '')}"
        lines += [f"## Cross-examination — {route}", ""]
        if challenge.get("text"):
            lines += [challenge["text"].strip(), ""]
        else:
            lines += [f"> **{challenge.get('error') or challenge.get('status', 'failed')}**", ""]
    if judge and judge.get("text"):
        lines += [f"## Synthesis — judged by {judge.get('label', '')}", "", judge["text"].strip(), ""]
    lines += ["---", "", f"Generated by ensemble v{VERSION}.", ""]
    return "\n".join(lines)


def challenge_section_html(challenges: List[dict]) -> str:
    if not challenges:
        return ""
    blocks = []
    for challenge in challenges:
        route = (
            f'<span class="challenge-label">Cross-examination</span>'
            f'<span class="challenge-route">{html.escape(challenge.get("from_label", ""))}'
            f'<span class="arrow">→</span>{html.escape(challenge.get("to_label", ""))}</span>'
        )
        status = challenge.get("status", "error")
        meta = f'{human_secs(float(challenge.get("elapsed") or 0))}'
        if challenge.get("tokens_total"):
            meta += f' · {human_int(int(challenge["tokens_total"]))} tok'
        if status == "ok" and challenge.get("text"):
            body = f'<div class="md">{render_markdown(challenge["text"])}</div>'
        else:
            body = f'<div class="error">{html.escape(challenge.get("error") or status)}</div>'
            if challenge.get("hint"):
                body += f'<p class="hint">→ {html.escape(str(challenge["hint"]).replace("`", ""))}</p>'
        blocks.append(
            f'<section class="challenge"><div class="challenge-head">{route}'
            f'{status_pill(status)}<span class="challenge-meta">{html.escape(meta)}</span></div>'
            f'{body}</section>'
        )
    return '<section class="challenges">' + "".join(blocks) + "</section>"


def write_report(run_dir: Path, meta: dict, results: List[Result],
                 judge: Optional[dict] = None,
                 challenges: Optional[List[dict]] = None) -> Path:
    prompt = meta.get("prompt", "")
    ok = sum(1 for result in results if result.status == "ok")
    chips = [
        f'<span class="chip"><b>{len(results)}</b> models</span>',
        f'<span class="chip"><b>{ok}</b> answered</span>',
        f'<span class="chip">{human_secs(float(meta.get("wall_seconds", 0)))} wall</span>',
        f'<span class="chip">context: {html.escape(str(meta.get("context", "temp")))}</span>',
        f'<span class="chip">{html.escape(str(meta.get("created_at", "")))}</span>',
    ]
    if meta.get("debate"):
        chips.append('<span class="chip">debate: 1 rebuttal round</span>')
    challenges_html = challenge_section_html(challenges or [])
    judge_html = ""
    if judge and judge.get("text"):
        judge_html = (
            '  <section class="judge">\n'
            f'    <div class="kicker">Synthesis · judged by {html.escape(judge.get("label", ""))}</div>\n'
            f'    <div class="md">{render_markdown(judge["text"])}</div>\n'
            "  </section>"
        )
    page = HTML_TEMPLATE.substitute(
        title=html.escape(f"Ensemble — {first_line(prompt, 70)}"),
        css=CSS,
        count=len(results),
        headline=html.escape(first_line(prompt, 150)),
        chips="".join(chips),
        prompt=html.escape(prompt.rstrip()),
        rows=summary_rows(results),
        cards="\n".join(card_html(result) for result in results),
        challenges=challenges_html,
        judge=judge_html,
        version=VERSION,
        generated=html.escape(str(meta.get("finished_at", ""))),
        folder=html.escape(str(run_dir)),
    )
    html_path = run_dir / "report.html"
    html_path.write_text(page)
    (run_dir / "report.md").write_text(report_markdown(meta, results, judge, challenges))
    return html_path


# --------------------------------------------------------------------------- #
# Judge / synthesis
# --------------------------------------------------------------------------- #


def build_judge_prompt(prompt: str, results: List[Result],
                       challenges: Optional[List[dict]] = None) -> str:
    chunks = [
        "You are the judge in a side-by-side comparison of AI models that each "
        "received the identical prompt below. Be concise, specific, and fair.",
        "",
        "ORIGINAL PROMPT:",
        "```text",
        prompt.rstrip(),
        "```",
        "",
    ]
    has_debates = any(r.debate and r.debate.text for r in results)
    for result in results:
        if result.status != "ok" or not result.text:
            chunks += [f"--- {result.label} ({result.model or 'default'}) — FAILED: {result.error or result.status} ---", ""]
            continue
        body = result.text.strip()
        if len(body) > 14000:
            body = body[:14000].rstrip() + "\n…[truncated]"
        chunks += [
            f"--- {result.label} ({result.model or 'default'}) — {human_secs(result.elapsed)}, "
            f"{len(result.text):,} chars ---",
            body,
            "",
        ]
        if result.debate and result.debate.text:
            rebuttal = result.debate.text.strip()
            if len(rebuttal) > 8000:
                rebuttal = rebuttal[:8000].rstrip() + "\n…[truncated]"
            chunks += [f"--- {result.label} — REBUTTAL after reading the others ---", rebuttal, ""]
    if challenges:
        chunks += ["CROSS-EXAMINATIONS (one model arguing directly against another's answer):", ""]
        for challenge in challenges:
            if not challenge.get("text"):
                continue
            body = challenge["text"].strip()
            if len(body) > 8000:
                body = body[:8000].rstrip() + "\n…[truncated]"
            chunks += [
                f"--- {challenge.get('from_label', '')} → {challenge.get('to_label', '')} ---",
                body,
                "",
            ]
    if has_debates:
        chunks += [
            "The models then saw each other's initial answers and wrote rebuttals. Use both rounds:",
            "note who changed position, which attack landed, and who defended successfully.",
            "Do not treat a rebuttal as a fresh independent answer.",
            "",
        ]
    chunks += [
        "Write a comparison with exactly these sections:",
        "1. Bottom line — one paragraph naming the strongest answer and why.",
        "2. Consensus — what all (or most) agree on.",
        "3. Divergence — the substantive disagreements, contradictions, or framing differences.",
        "4. Model by model — one short paragraph each: its distinctive contribution and its weakest claim."
        + (" Include what it conceded or changed in the rebuttal round." if any(r.debate and r.debate.text for r in results) else ""),
        "5. What to trust where — practical guidance on which answer to use for what.",
        "",
        "Name factual errors or unsupported claims explicitly. Do not invent agreement "
        "that is not there, and do not pad. If the answers are near-identical, say so plainly.",
    ]
    return "\n".join(chunks)


def run_judge(run_dir: Path, prompt: str, results: List[Result], meta: dict,
              config: dict, settings: Dict[str, dict], provider_key: Optional[str],
              model: Optional[str], timeout: float, no_color: bool,
              quiet: bool = False) -> Optional[dict]:
    ok = [result for result in results if result.status == "ok" and result.text]
    if not ok:
        eprint("ensemble: no successful answers to judge")
        return None
    key = provider_key
    if not key:
        key = "deepseek" if any(result.key == "deepseek" and result.status == "ok" for result in results) else ok[0].key
    if key not in settings:
        eprint(f"ensemble: unknown judge provider {key!r}")
        return None

    judge_prompt = build_judge_prompt(prompt, results, load_challenges(run_dir))
    workdir = Path(tempfile.mkdtemp(prefix=f"ensemble-judge-{key}-"))
    try:
        spec = build_specs(
            [key],
            judge_prompt,
            settings,
            {key: model} if model else {},
            {key: workdir},
            "temp",
            run_dir,
            config,
        )[0]
        spec.timeout = timeout
        if not quiet:
            eprint(f"◆ ensemble · judging with {settings[key]['label']}"
                   f" ({model or settings[key].get('model') or 'default'})")
        judged = run_specs([spec], no_color=no_color, quiet=quiet)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if not judged:
        return None
    result = judged[0]
    if result.status != "ok":
        eprint(f"ensemble: judge failed — {result.error}")
        if result.hint:
            eprint(f"  {result.hint}")
        return None

    info = {
        "provider": key,
        "label": settings[key]["label"],
        "model": result.model or model or "",
        "text": result.text,
        "elapsed": round(result.elapsed, 3),
        "created_at": now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }
    (run_dir / "judge.md").write_text(result.text.rstrip() + "\n")
    (run_dir / "judge.json").write_text(json.dumps(info, indent=2) + "\n")
    meta["judge"] = {k: v for k, v in info.items() if k != "text"}
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    write_report(run_dir, meta, results, judge=info, challenges=load_challenges(run_dir))
    return info


# --------------------------------------------------------------------------- #
# Doctor
# --------------------------------------------------------------------------- #


def short_version(text: str) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return truncate(line, 46)


def cmd_doctor(args) -> int:
    config = load_config()
    settings = provider_settings(config)
    keys = select_keys(argparse.Namespace(only=args.only, skip=None), settings)
    col = use_color(args.no_color)
    print(colorize("ensemble doctor", "\033[1m", col))
    print()

    checks = {}
    for key in keys:
        cfg = settings[key]
        if key == "deepseek":
            path = find_dsh(settings)
        else:
            path = which(cfg.get("bin", key))
        row = {"path": path, "version": "", "auth": "", "hint": "", "ok": bool(path)}
        if path:
            try:
                proc = subprocess.run([path, "--version"], capture_output=True, text=True,
                                      timeout=20, stdin=subprocess.DEVNULL)
                row["version"] = short_version(proc.stdout or proc.stderr)
            except Exception:  # noqa: BLE001
                row["version"] = "(version unavailable)"
        if key == "gemini" and path:
            env_auth = gemini_api_key() or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") or os.environ.get("GOOGLE_GENAI_USE_GCA")
            creds = Path.home() / ".gemini" / "oauth_creds.json"
            settings_file = Path.home() / ".gemini" / "settings.json"
            if env_auth:
                row["auth"] = "API key / Vertex configured"
            elif creds.is_file():
                row["auth"] = "Google login saved; headless needs API key"
                row["hint"] = "export GEMINI_API_KEY=... (Google login alone is blocked for free tier)"
            elif settings_file.is_file():
                row["auth"] = "configured (probe to verify)"
            else:
                row["auth"] = "not signed in"
                row["hint"] = "export GEMINI_API_KEY=..."
        elif key == "codex" and path:
            try:
                proc = subprocess.run([path, "login", "status"], capture_output=True, text=True,
                                      timeout=20, stdin=subprocess.DEVNULL)
                text = (proc.stdout or proc.stderr).strip()
                if "logged in" in text.lower():
                    row["auth"] = truncate(text, 40)
                else:
                    row["auth"] = "not logged in"
                    row["hint"] = "codex login"
            except Exception:  # noqa: BLE001
                row["auth"] = "auth state unknown"
        elif key == "kimi" and path:
            try:
                proc = subprocess.run([path, "provider", "list"], capture_output=True, text=True,
                                      timeout=20, stdin=subprocess.DEVNULL)
                text = proc.stdout or ""
                default = ""
                for line in text.splitlines():
                    if line.lower().startswith("default model:"):
                        default = line.split(":", 1)[1].strip()
                row["auth"] = f"configured (default {default or '?'})"
                if default.startswith("moonshot") and cfg.get("model") == "kimi-code":
                    row["auth"] += " · using kimi-code override"
            except Exception:  # noqa: BLE001
                row["auth"] = "auth state unknown"
        elif key == "deepseek" and path:
            auth = deepseek_auth_mode(config)
            if auth == "account":
                row["auth"] = "desktop account token found" if deepseek_account_available() else "account selected, no token"
                if not deepseek_account_available():
                    row["hint"] = "sign in to DSH"
            else:
                row["auth"] = "DEEPSEEK_API_KEY set" if os.environ.get("DEEPSEEK_API_KEY") else "no API key"
                if not os.environ.get("DEEPSEEK_API_KEY"):
                    row["hint"] = "export DEEPSEEK_API_KEY=..."
        checks[key] = row

        icon = colorize("✓", "\033[32m", col) if row["ok"] else colorize("✗", "\033[31m", col)
        print(f"  {icon} {cfg['label']:<9} {row['version'] or 'not found':<24} {row['auth']}")
        if row["hint"]:
            hint_text = colorize("→ " + row["hint"], "\033[33m", col)
            print(f"      {hint_text}")

    if args.probe:
        print()
        print(colorize("  probing each model with a one-word prompt…", "\033[2m", col))
        specs: List[Spec] = []
        bases: List[Path] = []
        for key in keys:
            if not checks[key]["ok"]:
                continue
            base = Path(tempfile.mkdtemp(prefix=f"ensemble-probe-{key}-"))
            bases.append(base)
            try:
                spec = build_specs([key], "Reply with exactly: OK", settings, {},
                                   {key: base}, "temp", base, config)[0]
                spec.timeout = 90
                specs.append(spec)
            except Exception as exc:  # noqa: BLE001
                checks[key]["ok"] = False
                checks[key]["hint"] = str(exc)
        try:
            probed = run_specs(specs, quiet=True) if specs else []
        finally:
            for base in bases:
                shutil.rmtree(base, ignore_errors=True)
        for result in probed:
            icon = colorize("✓", "\033[32m", col) if result.status == "ok" else colorize("✗", "\033[31m", col)
            detail = human_secs(result.elapsed)
            if result.status == "ok":
                detail += f" · {truncate(result.text, 30)!r}"
            else:
                detail += f" · {truncate(result.error, 100)}"
            print(f"  {icon} {result.label:<9} {detail}")
            if result.status != "ok" and result.hint:
                hint_text = colorize("→ " + result.hint, "\033[33m", col)
                print(f"      {hint_text}")
        ok_count = sum(1 for result in probed if result.status == "ok")
        print()
        print(f"  Live probe: {ok_count}/{len(probed)} models answered.")
        if ok_count < len(probed):
            print("  Fix the auth hints above, then run `ensemble doctor --probe` again.")
        return 0 if (ok_count == len(probed) or not args.strict) else 1

    print()
    if not all(row["ok"] for row in checks.values()):
        print("  Install the missing CLIs, then rerun `ensemble doctor`." if not args.probe
              else "  Install the missing CLIs and fix the auth hints above.")
        return 1 if args.strict else 0
    print("  All commands found. Run with --probe to test live authentication.")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def select_keys(args, settings: Dict[str, dict]) -> List[str]:
    enabled = [key for key in all_keys(settings) if settings.get(key, {}).get("enabled", True)]
    only = getattr(args, "only", None)
    skip = getattr(args, "skip", None)
    if only:
        requested = [part.strip() for part in only.split(",") if part.strip()]
        unknown = [part for part in requested if part not in settings]
        if unknown:
            raise SystemExit(f"ensemble: unknown provider(s): {', '.join(unknown)}")
        enabled = [key for key in all_keys(settings) if key in requested]
    if skip:
        skipped = {part.strip() for part in skip.split(",")}
        enabled = [key for key in enabled if key not in skipped]
    if not enabled:
        raise SystemExit("ensemble: no providers selected")
    return enabled


def parse_models(values: Optional[List[str]]) -> Dict[str, str]:
    models: Dict[str, str] = {}
    for value in values or []:
        for pair in value.split(","):
            if not pair.strip():
                continue
            if "=" not in pair:
                raise SystemExit(f"ensemble: --model expects provider=model, got {pair!r}")
            key, model = pair.split("=", 1)
            models[key.strip()] = model.strip()
    return models


def make_run_dir(out: Optional[str], prompt: str) -> Path:
    base = Path(out).expanduser() if out else HOME / "runs"
    base.mkdir(parents=True, exist_ok=True)
    stamp = now_local().strftime("%Y-%m-%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", first_line(prompt, 60).lower()).strip("-")[:48] or "run"
    path = base / f"{stamp}_{slug}"
    counter = 2
    while path.exists():
        path = base / f"{stamp}_{slug}-{counter}"
        counter += 1
    path.mkdir(parents=True)
    try:
        latest = HOME / "latest"
        if latest.is_symlink() or latest.is_file():
            latest.unlink()
        elif latest.exists():
            shutil.rmtree(latest)
        latest.symlink_to(path, target_is_directory=True)
    except Exception:  # noqa: BLE001 - convenience only
        pass
    return path


def cmd_providers(args) -> int:
    config = load_config()
    settings = provider_settings(config)
    col = use_color(args.no_color)
    print(colorize(f"{'KEY':<10} {'LABEL':<10} {'MODEL':<18} {'TIMEOUT':>8}  ENABLED  COMMAND", "\033[2m", col))
    for key in all_keys(settings):
        cfg = settings[key]
        enabled = "yes" if cfg.get("enabled", True) else "no"
        model = cfg.get("model") or "default"
        print(f"{key:<10} {cfg['label']:<10} {model:<18} {int(cfg.get('timeout', 300)):>7}s  "
              f"{enabled:<7}  {cfg.get('bin', '')}")
    print()
    print("  Override a model:   ensemble --model kimi=moonshot-ai/kimi-k2.7-code \"…\"")
    print("  Select providers:   ensemble --only kimi,codex \"…\"")
    return 0


def cmd_run(args) -> int:
    config = load_config()
    settings = provider_settings(config)
    if args.timeout:
        for key in settings:
            settings[key]["timeout"] = args.timeout
    keys = select_keys(args, settings)
    if "gemini" in keys and not args.only and not gemini_authenticated():
        keys = [key for key in keys if key != "gemini"]
        eprint("ensemble: skipping Gemini (not signed in; run `gemini` or export GEMINI_API_KEY)")
        if not keys:
            eprint("ensemble: no other providers are enabled")
            return 2
    prompt = read_prompt(args).strip()
    if not prompt:
        eprint("ensemble: no prompt. Pass it as arguments, use --prompt-file, or pipe stdin.")
        return 2

    base_cwd = Path(args.cwd or os.getcwd()).expanduser().resolve()
    if not base_cwd.is_dir():
        eprint(f"ensemble: --cwd is not a directory: {base_cwd}")
        return 2
    context = args.context or (config.get("defaults") or {}).get("context") or "temp"
    models = parse_models(args.model)
    unknown_models = [key for key in models if key not in keys]
    if unknown_models:
        eprint(f"ensemble: --model for unselected provider(s): {', '.join(unknown_models)}")
        return 2

    run_dir = make_run_dir(args.out, prompt)
    meta = {
        "version": VERSION,
        "prompt": prompt,
        "created_at": now_local().strftime("%Y-%m-%d %H:%M:%S"),
        "context": context,
        "cwd": str(base_cwd),
        "keys": keys,
        "models": models,
        "debate": args.debate,
        "command": subprocess.list2cmdline([sys.argv[0]] + sys.argv[1:]),
    }

    workdirs, cleanups = allocate_workdirs(keys, context, base_cwd, args.keep_workdirs)
    specs: List[Spec] = []
    early: List[Result] = []
    try:
        for key in keys:
            try:
                specs.append(
                    build_specs([key], prompt, settings, models, workdirs, context, run_dir, config)[0]
                )
            except Exception as exc:  # noqa: BLE001 - one broken provider shouldn't stop the rest
                early.append(
                    Result(
                        key=key,
                        label=settings[key]["label"],
                        accent=settings[key].get("accent", "#444"),
                        status="error",
                        error=str(exc),
                        hint=hint_for(key, str(exc)),
                        model=models.get(key) or settings[key].get("model") or "",
                    )
                )

        if args.dry_run:
            print(f"run dir: {run_dir}")
            print(f"context: {context}  cwd: {base_cwd}")
            for spec in specs:
                rendered = [("<prompt>" if part == prompt else part) for part in spec.argv]
                print(f"  {spec.label:<9} [{spec.cwd}]  {subprocess.list2cmdline(rendered)[:300]}")
            for result in early:
                print(f"  {result.label:<9} unavailable: {result.error}")
            return 0

        started = time.time()
        results = run_specs(specs, no_color=args.no_color, quiet=args.quiet or args.json)
        results = sorted(results + early, key=lambda item: keys.index(item.key))

        if args.debate:
            debates = debate_round(
                run_dir, prompt, results, settings, models, workdirs, context, config,
                no_color=args.no_color, quiet=args.quiet or args.json,
                sequential=args.sequential,
            )
            attach_debates(results, debates)
            if not debates and not args.quiet and not args.json:
                eprint("ensemble: rebuttal round skipped (need at least two successful answers)")

        wall = time.time() - started
        meta["wall_seconds"] = round(wall, 2)
        meta["finished_at"] = now_local().strftime("%Y-%m-%d %H:%M:%S")
        write_artifacts(run_dir, prompt, results, meta)
        html_path = write_report(run_dir, meta, results)

        judge_info = None
        if args.judge:
            judge_info = run_judge(
                run_dir, prompt, results, meta, config, settings,
                args.judge_provider, None, 300, args.no_color, args.quiet,
            )
            if judge_info:
                wall = time.time() - started
                meta["wall_seconds"] = round(wall, 2)
                meta["results"] = [result_to_dict(r, prompt) for r in results]
                (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
                write_report(run_dir, meta, results, judge=judge_info)

        payload = {
            "run_dir": str(run_dir),
            "report": str(html_path),
            "prompt": prompt,
            "wall_seconds": round(wall, 2),
            "results": [result_to_dict(result, prompt) for result in results],
            "judge": judge_info,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        elif args.quiet:
            print(html_path)
        else:
            print_summary(results, args.no_color)
            if args.debate:
                rebuttals = sum(1 for r in results if r.debate and r.debate.status == "ok")
                print(f"  Debate    {rebuttals}/{sum(1 for r in results if r.status == 'ok')} rebuttals")
            print_paths(run_dir, len(results), args.no_color)
            if judge_info:
                print(f"  {'Judge':<8}  {run_dir / 'judge.md'}")
                print()
        if args.open:
            opener = "open" if sys.platform == "darwin" else ("xdg-open" if sys.platform.startswith("linux") else None)
            if opener:
                subprocess.run([opener, str(html_path)], check=False)
        if args.strict and any(
            result.status != "ok" or (result.debate and result.debate.status != "ok")
            for result in results
        ):
            return 1
        return 0
    finally:
        for path in cleanups:
            shutil.rmtree(path, ignore_errors=True)


def cmd_judge(args) -> int:
    run_dir = Path(args.run).expanduser().resolve()
    if not (run_dir / "meta.json").is_file():
        eprint(f"ensemble: not a run directory: {run_dir}")
        return 2
    config = load_config()
    settings = provider_settings(config)
    prompt, meta, results = load_run(run_dir)
    info = run_judge(
        run_dir, prompt, results, meta, config, settings,
        args.provider, args.model, args.timeout, args.no_color, args.quiet,
    )
    if not info:
        return 1
    meta["judge"] = {k: v for k, v in info.items() if k != "text"}
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    write_report(run_dir, meta, results, judge=info, challenges=load_challenges(run_dir))
    if not args.quiet:
        print()
        print(f"  Judge    {run_dir / 'judge.md'}")
        print(f"  Report   {run_dir / 'report.html'}")
        print()
    if args.open:
        opener = "open" if sys.platform == "darwin" else ("xdg-open" if sys.platform.startswith("linux") else None)
        if opener:
            subprocess.run([opener, str(run_dir / "report.html")], check=False)
    return 0


def cmd_challenge(args) -> int:
    run_dir = Path(args.run).expanduser().resolve()
    if not (run_dir / "meta.json").is_file():
        eprint(f"ensemble: not a run directory: {run_dir}")
        return 2
    config = load_config()
    settings = provider_settings(config)
    prompt, meta, results = load_run(run_dir)
    by_key = {r.key: r for r in results}
    challenger = by_key.get(args.from_key)
    target = by_key.get(args.to_key)
    if not challenger:
        eprint(f"ensemble: unknown challenger {args.from_key!r}")
        return 2
    if not target:
        eprint(f"ensemble: unknown target {args.to_key!r}")
        return 2
    if target.status != "ok" or not target.text:
        eprint(f"ensemble: {target.label} has no successful answer to challenge")
        return 2
    if challenger.status != "ok" or not challenger.text:
        eprint(f"ensemble: {challenger.label} did not produce an initial answer")
        return 2
    if challenger.key == target.key:
        eprint("ensemble: challenger and target must be different models")
        return 2

    models = dict(meta.get("models") or {})
    if args.model:
        models[challenger.key] = args.model
    result = run_challenge(
        run_dir, prompt, challenger, target, settings, models, config,
        timeout=args.timeout,
    )
    cid = f"{time.strftime('%Y%m%d-%H%M%S')}-{challenger.key}-vs-{target.key}-{os.urandom(2).hex()}"
    challenge = result_to_challenge(cid, result, challenger, target)
    save_challenge(run_dir, challenge)
    name = safe_filename(f"{challenger.key}-vs-{target.key}-{cid}")
    (run_dir / f"challenge-{name}.md").write_text((result.text or result.error or "") + "\n")
    (run_dir / f"challenge-{name}.stdout.txt").write_text(result.stdout or "")
    (run_dir / f"challenge-{name}.stderr.txt").write_text(result.stderr or "")

    judge_info = None
    judge_path = run_dir / "judge.json"
    if judge_path.is_file():
        try:
            judge_info = json.loads(judge_path.read_text())
        except Exception:  # noqa: BLE001
            judge_info = None
    write_report(run_dir, meta, results, judge=judge_info, challenges=load_challenges(run_dir))

    if not args.quiet:
        print(f"{challenger.label} → {target.label}: {result.status} "
              f"({human_secs(result.elapsed)}, {len(result.text or '')} chars)")
        print(f"  Report  {run_dir / 'report.html'}")
        print(f"  Challenge  {run_dir / f'challenge-{name}.md'}")
        print()
    if args.json:
        print(json.dumps(challenge, indent=2))
    if args.open:
        opener = "open" if sys.platform == "darwin" else ("xdg-open" if sys.platform.startswith("linux") else None)
        if opener:
            subprocess.run([opener, str(run_dir / "report.html")], check=False)
    return 0 if result.status == "ok" else 1


def cmd_web(args) -> int:
    """Exec the local web server so it owns the process and Ctrl-C cleanly."""
    serve_path = Path(__file__).resolve().parent / "serve.py"
    if not serve_path.is_file():
        eprint(f"ensemble: web server is missing: {serve_path}")
        return 1
    argv = [sys.executable, str(serve_path), "--port", str(args.port)]
    if not args.open:
        argv.append("--no-open")
    os.execv(sys.executable, argv)
    return 0


def cmd_last(args) -> int:
    run_dir = None
    latest = HOME / "latest"
    if latest.exists():
        run_dir = latest.resolve()
    else:
        base = HOME / "runs"
        candidates = sorted([p for p in base.glob("*") if (p / "report.html").is_file()])
        if candidates:
            run_dir = candidates[-1]
    if not run_dir:
        eprint("ensemble: no runs yet")
        return 1
    print(run_dir)
    print(run_dir / "report.html")
    if args.open:
        opener = "open" if sys.platform == "darwin" else ("xdg-open" if sys.platform.startswith("linux") else None)
        if opener:
            subprocess.run([opener, str(run_dir / "report.html")], check=False)
    return 0


def add_common(parser):
    parser.add_argument("--no-color", action="store_true", help="disable ANSI color")
    parser.add_argument("--quiet", "-q", action="store_true", help="suppress progress and summary")


def build_run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ensemble run",
        description="Run one prompt through several agent CLIs at the same time.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            examples:
              ensemble "Explain CRDTs in one paragraph"
              ensemble --only kimi,codex --context cwd "Review the auth flow in this repo"
              ensemble --model kimi=moonshot-ai/kimi-k2.7-code --timeout 600 "…"
              echo "Summarize this log" | ensemble - --context copy
              ensemble --judge "Which database should I use for a side project?"
            """
        ),
    )
    parser.add_argument("prompt", nargs="*", help="prompt text, or - to read stdin")
    parser.add_argument("--prompt-file", help="read the prompt from a file")
    parser.add_argument("--only", help="comma-separated providers (default: all)")
    parser.add_argument("--skip", help="comma-separated providers to skip")
    parser.add_argument("--model", action="append", metavar="PROVIDER=MODEL",
                        help="override a model; repeatable or comma-separated")
    parser.add_argument("--timeout", type=float, default=None,
                        help="seconds per provider (default 300, or config)")
    parser.add_argument("--context", choices=["temp", "copy", "cwd"],
                        help="temp: empty dir per model (default); copy: project snapshot; cwd: run here")
    parser.add_argument("--cwd", help="project directory to copy or use (default: current)")
    parser.add_argument("--out", help="output directory (default ~/.ensemble/runs)")
    parser.add_argument("--debate", dest="debate", action="store_true", default=False,
                        help="open debate: every model rebuts every other answer")
    parser.add_argument("--no-debate", dest="debate", action="store_false",
                        help="skip the rebuttal round")
    parser.add_argument("--judge", action="store_true", help="add a synthesis of the answers")
    parser.add_argument("--judge-provider", help="provider used for --judge (default deepseek)")
    parser.add_argument("--open", action="store_true", help="open the HTML report when done")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--sequential", action="store_true", help="run providers one at a time")
    parser.add_argument("--keep-workdirs", action="store_true", help="keep temp project copies")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any provider fails")
    parser.add_argument("--dry-run", action="store_true", help="print commands, run nothing")
    add_common(parser)
    return parser


def build_doctor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ensemble doctor",
                                     description="Check CLIs, versions, and authentication.")
    parser.add_argument("--probe", action="store_true", help="send a one-word prompt to each model")
    parser.add_argument("--only", help="comma-separated providers")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any CLI is missing")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--quiet", "-q", action="store_true", help=argparse.SUPPRESS)
    return parser


def build_challenge_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ensemble challenge",
        description="Have one model argue directly against another model's answer.",
    )
    parser.add_argument("run", help="run directory (or ~/.ensemble/latest)")
    parser.add_argument("--from", dest="from_key", required=True, help="challenger provider key")
    parser.add_argument("--to", dest="to_key", required=True, help="target provider key")
    parser.add_argument("--model", help="model override for the challenger")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--json", action="store_true")
    add_common(parser)
    return parser


def build_web_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ensemble web",
        description="Run one prompt through several models in a local web UI.",
    )
    parser.add_argument("--port", type=int, default=8765, help="port on 127.0.0.1 (default 8765)")
    parser.add_argument("--open", dest="open", action="store_true", default=True,
                        help="open the browser when ready (default)")
    parser.add_argument("--no-open", dest="open", action="store_false",
                        help="do not open a browser")
    return parser


def build_judge_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ensemble judge",
                                     description="Synthesize an existing run with one model.")
    parser.add_argument("run", help="run directory (or ~/.ensemble/latest)")
    parser.add_argument("--provider", help="judge provider (default deepseek)")
    parser.add_argument("--model", help="judge model override")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--open", action="store_true")
    add_common(parser)
    return parser


def print_help() -> None:
    print(textwrap.dedent(f"""\
        ensemble v{VERSION} — one prompt, several models, side by side.

        usage:
          ensemble "prompt"                 run Kimi, Gemini, DeepSeek and Codex in parallel
          ensemble run [options] "prompt"   same, with flags
          ensemble doctor [--probe]         check installs, versions and authentication
          ensemble judge <run-dir>          synthesize a finished run with one model
          ensemble challenge <run-dir> --from kimi --to deepseek
          ensemble web                      open the local comparison UI
          ensemble providers                show provider configuration
          ensemble last [--open]            show the most recent run

        run options:
          --only kimi,codex                 select providers
          --model kimi=MODEL                override a model (repeatable)
          --context temp|copy|cwd           working directory strategy (default: temp)
          --timeout SECONDS                 per-model timeout (default: 300)
          --debate / --no-debate            open all-vs-all debate (default: off)
          --judge                           add a cross-model synthesis
          --out DIR                         where to write the run (default: ~/.ensemble/runs)
          --open                            open the HTML report when done
          --json                            machine-readable result on stdout

        examples:
          ensemble "Explain CRDTs in one paragraph"
          ensemble --context copy --cwd . "Review this codebase's error handling"
          ensemble --only deepseek,codex --judge "Pick one: Postgres, SQLite, DuckDB?"
          ensemble doctor --probe
          ensemble web --port 8765

        reports land in <run-dir>/report.html (side-by-side) and report.md.
        """))
    print()


def real_main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print_help()
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print(f"ensemble {VERSION}")
        return 0

    commands = {"run", "doctor", "judge", "challenge", "providers", "last", "web"}
    if argv[0] in commands:
        command, rest = argv[0], argv[1:]
    else:
        command, rest = "run", argv

    if command == "run":
        args = build_run_parser().parse_args(rest)
        return cmd_run(args)
    if command == "doctor":
        return cmd_doctor(build_doctor_parser().parse_args(rest))
    if command == "judge":
        return cmd_judge(build_judge_parser().parse_args(rest))
    if command == "challenge":
        return cmd_challenge(build_challenge_parser().parse_args(rest))
    if command == "web":
        return cmd_web(build_web_parser().parse_args(rest))
    if command == "providers":
        parser = argparse.ArgumentParser(prog="ensemble providers")
        parser.add_argument("--no-color", action="store_true")
        return cmd_providers(parser.parse_args(rest))
    if command == "last":
        parser = argparse.ArgumentParser(prog="ensemble last")
        parser.add_argument("--open", action="store_true")
        return cmd_last(parser.parse_args(rest))
    return 2


def main():
    raise SystemExit(real_main())


if __name__ == "__main__":
    main()
