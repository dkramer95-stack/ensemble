#!/usr/bin/env python3
"""
ensemble web — a local control desk for running one prompt through several models.

Serves a small single-page app on 127.0.0.1 and reuses the ensemble engine for
execution, reports, and artifacts. No third-party dependencies.

    python3 serve.py --port 8765 --open
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import ensemble as E  # noqa: E402

WEB_DIR = ROOT / "web"
RUNS_DIR = E.HOME / "runs"
RUNS_LOCK = threading.RLock()
RUNS: Dict[str, "Run"] = {}
MAX_ACTIVE = 4
CONFIG: dict = {}
SETTINGS: Dict[str, dict] = {}
STARTED = time.time()
HEALTH_CACHE: dict = {"at": 0.0, "data": None}

TERMINAL = {"done", "partial", "error", "cancelled"}
ACTIVE_STATES = {"starting", "running", "debating", "judging", "finalizing", "cancelling"}

STATUS_COLORS = {
    "ok": "var(--ok)",
    "error": "var(--err)",
    "timeout": "var(--warn)",
    "empty": "var(--warn)",
    "cancelled": "var(--faint)",
    "running": "var(--primary)",
    "queued": "var(--line-strong)",
}


def now_label() -> str:
    return E.now_local().strftime("%Y-%m-%d %H:%M:%S")


def provider_preview(key: str) -> dict:
    cfg = SETTINGS.get(key, {})
    return {
        "key": key,
        "label": cfg.get("label", key),
        "accent": cfg.get("accent", "#6B7280"),
        "model": cfg.get("model") or "default",
    }


def health() -> List[dict]:
    now = time.time()
    if HEALTH_CACHE["data"] is not None and now - HEALTH_CACHE["at"] < 15:
        return HEALTH_CACHE["data"]

    rows = []
    for key in E.all_keys(SETTINGS):
        cfg = SETTINGS[key]
        ready: Optional[bool]
        note = ""
        binary = E.find_dsh(SETTINGS) if key == "deepseek" else E.which(cfg.get("bin", key))
        ready = bool(binary)
        if not binary:
            note = "not installed"
        elif key == "codex":
            try:
                proc = subprocess.run(
                    [binary, "login", "status"], capture_output=True, text=True,
                    timeout=12, stdin=subprocess.DEVNULL,
                )
                text = (proc.stdout or proc.stderr).strip()
                ready = "logged in" in text.lower()
                note = "ChatGPT" if ready else "sign in required"
            except Exception:  # noqa: BLE001
                note = "status unknown"
        elif key == "kimi":
            note = f"plan {cfg.get('model') or 'default'}"
        elif key == "gemini":
            env_auth = E.gemini_api_key() or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") or os.environ.get("GOOGLE_GENAI_USE_GCA")
            creds = Path.home() / ".gemini" / "oauth_creds.json"
            settings_file = Path.home() / ".gemini" / "settings.json"
            if env_auth:
                ready = True
                note = "API key"
            elif creds.is_file():
                ready = False
                note = "API key required"
            elif settings_file.is_file():
                ready = False
                note = "API key required"
            else:
                ready = False
                note = "sign in required"
        elif key == "deepseek":
            mode = E.deepseek_auth_mode(CONFIG)
            if mode == "account":
                ready = E.deepseek_account_available()
                note = "desktop account" if ready else "sign in to DSH"
            else:
                ready = bool(os.environ.get("DEEPSEEK_API_KEY"))
                note = "API key" if ready else "no API key"
        else:
            note = cfg.get("model") or ""

        rows.append({
            "key": key,
            "label": cfg["label"],
            "accent": cfg.get("accent"),
            "ready": ready,
            "note": note,
        })
    HEALTH_CACHE.update({"at": now, "data": rows})
    return rows


def provider_catalog() -> dict:
    providers = []
    for row in health():
        preview = provider_preview(row["key"])
        preview["ready"] = row["ready"]
        preview["note"] = row["note"]
        providers.append(preview)
    return {
        "providers": providers,
        "defaults": {
            "context": "temp",
            "judge": True,
            "debate": False,
            "judge_provider": "deepseek" if "deepseek" in SETTINGS else E.all_keys(SETTINGS)[0],
            "timeout": 300,
        },
    }


class Run:
    def __init__(self, prompt: str, keys: List[str], context: str, judge: bool,
                 judge_provider: Optional[str], timeout: int, models: dict,
                 debate: bool = False):
        self.prompt = prompt
        self.keys = keys
        self.context = context
        self.judge_requested = judge
        self.judge_provider = judge_provider
        self.debate_requested = debate
        self.debate_started = False
        self.debate_error = ""
        self.models = models or {}
        self.lock = threading.RLock()
        self.status = "starting"
        self.error = ""
        self.cancel_requested = False
        self.finishing = False
        self.finished = threading.Event()
        self.procs: Dict[str, object] = {}
        self.judge: Optional[dict] = None
        self.started_at = time.time()
        self.final_wall: Optional[float] = None
        self.mono = time.monotonic()
        self.created_at = now_label()
        self.settings = copy.deepcopy(SETTINGS)
        if timeout:
            for key in self.settings:
                self.settings[key]["timeout"] = timeout

        self.run_dir = E.make_run_dir(None, prompt)
        self.id = self.run_dir.name
        self.workdirs: Dict[str, Path] = {}
        self.cleanups: List[Path] = []
        self.specs: List[E.Spec] = []
        self.parts: Dict[str, dict] = {}
        for key in keys:
            cfg = self.settings[key]
            self.parts[key] = {
                "key": key,
                "label": cfg["label"],
                "accent": cfg.get("accent", "#444"),
                "model": self.models.get(key) or cfg.get("model") or "",
                "status": "queued",
                "started": None,
                "elapsed": 0.0,
                "result": None,
                "html": "",
                "debate": None,
                "debate_status": "waiting",
                "debate_html": "",
                "debate_started": None,
            }
        self.meta = {
            "version": E.VERSION,
            "prompt": prompt,
            "created_at": self.created_at,
            "context": context,
            "cwd": str(Path.cwd()),
            "keys": keys,
            "models": models,
            "debate": debate,
            "command": "ensemble web",
        }
        self._build()

    def _build(self) -> None:
        self.workdirs, self.cleanups = E.allocate_workdirs(
            self.keys, self.context, Path.cwd(), False
        )
        for key in self.keys:
            try:
                spec = E.build_specs(
                    [key], self.prompt, self.settings, self.models,
                    self.workdirs, self.context, self.run_dir, CONFIG,
                )[0]
                self.specs.append(spec)
            except Exception as exc:  # noqa: BLE001 - record per-provider failure
                result = E.Result(
                    key=key,
                    label=self.parts[key]["label"],
                    accent=self.parts[key]["accent"],
                    status="error",
                    error=str(exc),
                    hint=E.hint_for(key, str(exc)),
                    model=self.parts[key]["model"],
                )
                self.parts[key]["result"] = result
                self.parts[key]["status"] = "error"

    def start(self) -> None:
        with self.lock:
            self.status = "running" if self.specs else "finalizing"
        if not self.specs:
            self._maybe_finish()
            return
        for spec in self.specs:
            threading.Thread(target=self._worker, args=(spec,), daemon=True).start()

    def _worker(self, spec: E.Spec) -> None:
        part = self.parts[spec.key]
        with self.lock:
            part["status"] = "running"
            part["started"] = time.monotonic()
        try:
            result = E.execute(spec, set_active=self._register)
        except Exception as exc:  # noqa: BLE001 - never wedge a run
            result = E.Result(
                key=spec.key, label=self.parts[spec.key]["label"],
                accent=self.parts[spec.key]["accent"], status="error",
                error=f"runner crashed: {exc}", model=spec.model,
            )
        html = E.render_markdown(result.text) if result.status == "ok" and result.text else ""
        with self.lock:
            part["result"] = result
            part["status"] = result.status
            part["elapsed"] = result.elapsed
            part["html"] = html
        self._maybe_finish()

    def _register(self, key: str, proc) -> None:
        with self.lock:
            if proc is None:
                self.procs.pop(key, None)
            else:
                self.procs[key] = proc
                cancel = self.cancel_requested
            if proc is not None and cancel:
                E.kill_tree(proc)

    def _maybe_finish(self) -> None:
        start_debate = False
        with self.lock:
            if self.finishing:
                return
            if any(p["status"] in ("queued", "running") for p in self.parts.values()):
                return

            if self.debate_requested and not self.debate_started:
                self.debate_started = True
                ok_count = sum(1 for p in self.parts.values() if p["status"] == "ok")
                if ok_count >= 2 and not self.cancel_requested:
                    self.status = "debating"
                    for part in self.parts.values():
                        if part["status"] == "ok":
                            part["debate_status"] = "pending"
                            part["debate_started"] = time.monotonic()
                        else:
                            part["debate_status"] = "skipped"
                    start_debate = True
                else:
                    for part in self.parts.values():
                        part["debate_status"] = "skipped"

            if start_debate:
                pass
            elif any(p["debate_status"] in ("pending", "running") for p in self.parts.values()):
                return
            else:
                self.finishing = True
                has_ok = any(p["status"] == "ok" for p in self.parts.values())
                if self.judge_requested and has_ok and not self.cancel_requested:
                    self.status = "judging"
                else:
                    self.status = "finalizing"

        if start_debate:
            threading.Thread(target=self._run_debate, daemon=True).start()
        else:
            threading.Thread(target=self._finalize, daemon=True).start()

    def _debate_result(self, result: E.Result) -> None:
        with self.lock:
            part = self.parts.get(result.key)
            if not part:
                return
            part["debate"] = result
            part["debate_status"] = result.status
            part["debate_html"] = E.render_markdown(result.text) if result.status == "ok" and result.text else ""
            initial = part.get("result")
            if initial is not None:
                initial.debate = result

    def _run_debate(self) -> None:
        try:
            with self.lock:
                results = [self.parts[key]["result"] for key in self.keys
                           if self.parts[key]["result"] is not None]
            debates = E.debate_round(
                self.run_dir, self.prompt, results, self.settings, self.models,
                self.workdirs, self.context, CONFIG,
                quiet=True, on_active=self._register, on_result=self._debate_result,
            )
            for result in debates.values():
                self._debate_result(result)
        except Exception as exc:  # noqa: BLE001 - keep the initial answers
            with self.lock:
                self.debate_error = str(exc)
        finally:
            with self.lock:
                for part in self.parts.values():
                    if part["debate_status"] in ("pending", "running"):
                        part["debate_status"] = "error"
            self._maybe_finish()

    def _finalize(self) -> None:
        info = None
        try:
            with self.lock:
                results = [self.parts[key]["result"] for key in self.keys
                           if self.parts[key]["result"] is not None]
                has_ok = any(r.status == "ok" for r in results)
                cancelled = self.cancel_requested
                meta = dict(self.meta)
            meta["wall_seconds"] = round(time.time() - self.started_at, 2)
            meta["finished_at"] = now_label()
            meta["status"] = "cancelled" if cancelled else "running"
            E.write_artifacts(self.run_dir, self.prompt, results, meta)

            if self.judge_requested and has_ok and not cancelled:
                with self.lock:
                    self.judge = {
                        "status": "running",
                        "label": self.settings.get(self.judge_provider or "", {}).get("label", ""),
                        "model": "",
                    }
                provider = self.judge_provider
                if provider and not any(r.key == provider and r.status == "ok" for r in results):
                    provider = None
                try:
                    info = E.run_judge(
                        self.run_dir, self.prompt, results, meta, CONFIG, self.settings,
                        provider, None, 300, True, quiet=True,
                    )
                except Exception as exc:  # noqa: BLE001 - keep the answers
                    info = None
                    with self.lock:
                        self.judge = {"status": "error", "error": str(exc)}
                if info:
                    with self.lock:
                        self.judge = {
                            "status": "done",
                            "label": info["label"],
                            "model": info["model"],
                            "text": info["text"],
                            "html": E.render_markdown(info["text"]),
                            "elapsed": info["elapsed"],
                        }
                else:
                    with self.lock:
                        self.judge = {"status": "error", "error": "the judge did not return an answer"}

            debated = [r for r in results if r.debate]
            debates_ok = all(r.debate.status == "ok" for r in debated) if debated else True
            if cancelled:
                status = "cancelled"
            elif not has_ok:
                status = "error"
            elif all(r.status == "ok" for r in results) and debates_ok:
                status = "done"
            else:
                status = "partial"

            self.final_wall = round(time.time() - self.started_at, 2)
            meta["wall_seconds"] = self.final_wall
            meta["finished_at"] = now_label()
            meta["status"] = status
            meta["results"] = [E.result_to_dict(r, self.prompt) for r in results]
            (self.run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
            E.write_report(self.run_dir, meta, results, judge=info)
            with self.lock:
                self.status = status
                self.meta = meta
        except Exception as exc:  # noqa: BLE001 - surface, don't kill the server
            self.final_wall = round(time.time() - self.started_at, 2)
            with self.lock:
                self.status = "error"
                self.error = str(exc)
        finally:
            for path in self.cleanups:
                shutil.rmtree(path, ignore_errors=True)
            self.finished.set()

    def cancel(self) -> bool:
        with self.lock:
            if self.status not in ("starting", "running", "debating"):
                return False
            self.cancel_requested = True
            self.status = "cancelling"
            procs = list(self.procs.values())
        for proc in procs:
            E.kill_tree(proc)
        return True

    def snapshot(self) -> dict:
        with self.lock:
            now = time.monotonic()
            providers = []
            for key in self.keys:
                part = self.parts[key]
                result = part["result"]
                status = part["status"]
                if self.cancel_requested and status != "ok":
                    status = "cancelled"
                elapsed = result.elapsed if result else (
                    now - part["started"] if part["started"] else 0.0
                )
                debate = part.get("debate")
                debate_obj = None
                if debate:
                    debate_obj = {
                        "status": debate.status,
                        "elapsed": round(debate.elapsed, 1),
                        "tokens_total": debate.tokens_total,
                        "html": part.get("debate_html", "") if debate.status == "ok" else "",
                        "text": debate.text if debate.status == "ok" else "",
                        "error": debate.error,
                        "hint": debate.hint,
                    }
                elif part.get("debate_status") in ("pending", "running"):
                    dstarted = part.get("debate_started") or now
                    debate_obj = {
                        "status": part["debate_status"],
                        "elapsed": round(now - dstarted, 1),
                        "tokens_total": None,
                        "html": "",
                        "text": "",
                        "error": "",
                        "hint": "",
                    }
                providers.append({
                    "key": key,
                    "label": part["label"],
                    "accent": part["accent"],
                    "model": part["model"],
                    "status": status,
                    "elapsed": round(elapsed, 1),
                    "tokens_total": result.tokens_total if result else None,
                    "cost": result.cost if result else None,
                    "html": part["html"] if status == "ok" else "",
                    "text": result.text if result and status == "ok" else "",
                    "error": result.error if result else "",
                    "hint": result.hint if result else "",
                    "debate": debate_obj,
                })
            answered = sum(1 for p in providers if p["status"] == "ok")
            wall = self.final_wall if self.final_wall is not None else time.time() - self.started_at
            report = self.run_dir / "report.html"
            return {
                "id": self.id,
                "status": self.status,
                "prompt": self.prompt,
                "created_at": self.created_at,
                "context": self.context,
                "judge_requested": self.judge_requested,
                "debate_requested": self.debate_requested,
                "debate_error": self.debate_error,
                "wall_seconds": round(wall, 1),
                "answered": answered,
                "total": len(providers),
                "providers": providers,
                "judge": self.judge,
                "report_url": f"/runs/{self.id}/report.html" if report.exists() else None,
                "can_cancel": self.status in ("starting", "running", "debating"),
                "error": self.error,
            }


CHALLENGE_LOCK = threading.RLock()
ACTIVE_CHALLENGES: Dict[str, List["ChallengeState"]] = {}


class ChallengeState:
    def __init__(self, run_id: str, run_dir: Path, prompt: str, meta: dict,
                 results: List[E.Result], challenger: E.Result, target: E.Result,
                 settings: Dict[str, dict], config: dict, timeout: float):
        self.run_id = run_id
        self.run_dir = run_dir
        self.prompt = prompt
        self.meta = meta
        self.results = results
        self.challenger = challenger
        self.target = target
        self.settings = settings
        self.config = config
        self.timeout = timeout
        self.models = dict(meta.get("models") or {})
        self.id = (
            f"{time.strftime('%Y%m%d-%H%M%S')}-{challenger.key}-vs-{target.key}-"
            f"{os.urandom(2).hex()}"
        )
        self.status = "running"
        self.error = ""
        self.result: Optional[dict] = None
        self.started = time.monotonic()
        self.started_at = now_label()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            result = E.run_challenge(
                self.run_dir, self.prompt, self.challenger, self.target,
                self.settings, self.models, self.config, timeout=self.timeout,
            )
            challenge = E.result_to_challenge(
                self.id, result, self.challenger, self.target
            )
            E.save_challenge(self.run_dir, challenge)
            name = E.safe_filename(f"{self.challenger.key}-vs-{self.target.key}-{self.id}")
            (self.run_dir / f"challenge-{name}.md").write_text(
                (result.text or result.error or "") + "\n"
            )
            (self.run_dir / f"challenge-{name}.stdout.txt").write_text(result.stdout or "")
            (self.run_dir / f"challenge-{name}.stderr.txt").write_text(result.stderr or "")
            self.result = challenge
            self.status = challenge["status"]
            self.error = challenge.get("error", "")
            self._render()
        except Exception as exc:  # noqa: BLE001 - surface in the UI
            self.status = "error"
            self.error = str(exc)
            self.result = {
                "id": self.id,
                "from_key": self.challenger.key,
                "from_label": self.challenger.label,
                "to_key": self.target.key,
                "to_label": self.target.label,
                "status": "error",
                "text": "",
                "error": str(exc),
                "hint": "",
                "elapsed": round(time.monotonic() - self.started, 2),
                "tokens_total": None,
                "model": self.challenger.model,
                "created_at": self.started_at,
            }
            try:
                E.save_challenge(self.run_dir, self.result)
            except Exception:
                pass
        finally:
            with CHALLENGE_LOCK:
                active = ACTIVE_CHALLENGES.get(self.run_id, [])
                ACTIVE_CHALLENGES[self.run_id] = [c for c in active if c.id != self.id]

    def _render(self) -> None:
        try:
            prompt, meta, results = E.load_run(self.run_dir)
            judge = None
            judge_path = self.run_dir / "judge.json"
            if judge_path.is_file():
                judge = json.loads(judge_path.read_text())
            E.write_report(
                self.run_dir, meta, results, judge=judge,
                challenges=E.load_challenges(self.run_dir),
            )
        except Exception as exc:  # noqa: BLE001 - keep the challenge result
            self.error = f"report render failed: {exc}"

    def snapshot(self) -> dict:
        if self.result:
            return self.result
        return {
            "id": self.id,
            "from_key": self.challenger.key,
            "from_label": self.challenger.label,
            "to_key": self.target.key,
            "to_label": self.target.label,
            "status": "running",
            "text": "",
            "error": self.error,
            "hint": "",
            "elapsed": round(time.monotonic() - self.started, 2),
            "tokens_total": None,
            "model": self.challenger.model,
            "created_at": self.started_at,
        }


def start_challenge(run_id: str, from_key: str, to_key: str,
                    timeout: float = 300) -> ChallengeState:
    run_dir = RUNS_DIR / run_id
    if not (run_dir / "meta.json").is_file():
        raise ValueError("run not found")
    prompt, meta, results = E.load_run(run_dir)
    by_key = {r.key: r for r in results}
    challenger = by_key.get(from_key)
    target = by_key.get(to_key)
    if not challenger or not target:
        raise ValueError("unknown challenger or target")
    if challenger.key == target.key:
        raise ValueError("challenger and target must be different")
    if challenger.status != "ok" or not challenger.text:
        raise ValueError(f"{challenger.label} has no successful initial answer")
    if target.status != "ok" or not target.text:
        raise ValueError(f"{target.label} has no successful answer to challenge")

    settings = copy.deepcopy(SETTINGS)
    state = ChallengeState(
        run_id, run_dir, prompt, meta, results, challenger, target,
        settings, CONFIG, timeout,
    )
    with CHALLENGE_LOCK:
        ACTIVE_CHALLENGES.setdefault(run_id, []).append(state)
    state.start()
    return state


def challenges_for(run_id: str) -> List[dict]:
    run_dir = RUNS_DIR / run_id
    saved = E.load_challenges(run_dir)
    with CHALLENGE_LOCK:
        active = [state.snapshot() for state in ACTIVE_CHALLENGES.get(run_id, [])]
    merged = {item.get("id"): item for item in saved}
    for item in active:
        merged[item.get("id")] = item
    items = list(merged.values())
    for item in items:
        if item.get("status") == "ok" and item.get("text") and not item.get("html"):
            item["html"] = E.render_markdown(item["text"])
    items.sort(key=lambda item: item.get("created_at", ""))
    return items


def active_runs() -> int:
    with RUNS_LOCK:
        return sum(1 for run in RUNS.values() if run.status in ACTIVE_STATES)


def derive_status(meta: dict, results: List[E.Result]) -> str:
    explicit = meta.get("status")
    if explicit in TERMINAL:
        return explicit
    if not results:
        return "error"
    if all(r.status == "ok" for r in results):
        return "done"
    if any(r.status == "ok" for r in results):
        return "partial"
    return "error"


def disk_snapshot(run_id: str) -> Optional[dict]:
    run_dir = RUNS_DIR / run_id
    meta_path = run_dir / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text())
        results = [E.dict_to_result(row) for row in json.loads((run_dir / "results.json").read_text())]
    except Exception:  # noqa: BLE001
        return None

    by_key = {r.key: r for r in results}
    keys = meta.get("keys") or [r.key for r in results]
    status = derive_status(meta, results)
    providers = []
    for key in keys:
        result = by_key.get(key)
        cfg = SETTINGS.get(key, {})
        part_status = result.status if result else "error"
        if status == "cancelled" and part_status != "ok":
            part_status = "cancelled"
        debate_obj = None
        if result and result.debate:
            d = result.debate
            debate_obj = {
                "status": d.status,
                "elapsed": round(d.elapsed, 1),
                "tokens_total": d.tokens_total,
                "html": E.render_markdown(d.text) if d.status == "ok" and d.text else "",
                "text": d.text if d.status == "ok" else "",
                "error": d.error,
                "hint": d.hint,
            }
        providers.append({
            "key": key,
            "label": (result.label if result else cfg.get("label", key)),
            "accent": cfg.get("accent", "#6B7280"),
            "model": (result.model if result else "") or cfg.get("model") or "",
            "status": part_status,
            "elapsed": round(result.elapsed, 1) if result else 0,
            "tokens_total": result.tokens_total if result else None,
            "cost": result.cost if result else None,
            "html": E.render_markdown(result.text) if result and result.text and part_status == "ok" else "",
            "text": result.text if result and part_status == "ok" else "",
            "error": result.error if result else "",
            "hint": result.hint if result else "",
            "debate": debate_obj,
        })

    judge = None
    judge_md = run_dir / "judge.md"
    if judge_md.is_file():
        meta_judge = meta.get("judge") or {}
        text = judge_md.read_text()
        judge = {
            "status": "done",
            "label": meta_judge.get("label") or "Synthesis",
            "model": meta_judge.get("model") or "",
            "text": text,
            "html": E.render_markdown(text),
            "elapsed": meta_judge.get("elapsed"),
        }

    report = run_dir / "report.html"
    return {
        "id": run_id,
        "status": status,
        "prompt": meta.get("prompt", ""),
        "created_at": meta.get("created_at", ""),
        "context": meta.get("context", "temp"),
        "judge_requested": bool(judge) or bool(meta.get("judge")),
        "debate_requested": bool(meta.get("debate")),
        "wall_seconds": meta.get("wall_seconds", 0),
        "answered": sum(1 for p in providers if p["status"] == "ok"),
        "total": len(providers),
        "providers": providers,
        "judge": judge,
        "report_url": f"/runs/{run_id}/report.html" if report.is_file() else None,
        "can_cancel": False,
        "error": "",
    }


def history() -> List[dict]:
    items = []
    if not RUNS_DIR.is_dir():
        return items
    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        meta_path = run_dir / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:  # noqa: BLE001
            continue
        rows = meta.get("results") or []
        statuses = [
            {
                "key": row.get("key"),
                "label": row.get("label") or row.get("key"),
                "status": row.get("status", "error"),
            }
            for row in rows
        ]
        status = meta.get("status")
        if status not in TERMINAL:
            ok = sum(1 for row in rows if row.get("status") == "ok")
            status = "done" if rows and ok == len(rows) else ("partial" if ok else "error")
        items.append({
            "id": run_dir.name,
            "prompt": meta.get("prompt", ""),
            "created_at": meta.get("created_at", ""),
            "wall_seconds": meta.get("wall_seconds", 0),
            "answered": sum(1 for row in rows if row.get("status") == "ok"),
            "total": len(rows),
            "status": status,
            "statuses": statuses,
            "judge": bool(meta.get("judge")) or (run_dir / "judge.md").is_file(),
            "debate": bool(meta.get("debate")),
        })
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items[:40]


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".md": "text/markdown; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = f"ensemble-web/{E.VERSION}"

    def log_message(self, fmt, *args):  # noqa: D401 - quiet server
        return

    def _security_headers(self):
        """Baseline hardening: model output is untrusted, so constrain the page."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https: http:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )

    def _json(self, payload, code=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message, code=400):
        self._json({"error": message}, code)

    def _file(self, path: Path, download=False):
        if not path.is_file():
            self._error("not found", 404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._file(WEB_DIR / "index.html")
            return
        if path in ("/app.css", "/app.js"):
            self._file(WEB_DIR / path.lstrip("/"))
            return
        if path == "/api/health":
            self._json({"ok": True, "version": E.VERSION})
            return
        if path == "/api/providers":
            self._json(provider_catalog())
            return
        if path == "/api/runs":
            self._json({"runs": history()})
            return
        match = re.fullmatch(r"/api/runs/([A-Za-z0-9._-]+)", path)
        if match:
            run_id = match.group(1)
            with RUNS_LOCK:
                run = RUNS.get(run_id)
            if run:
                payload = run.snapshot()
                payload["challenges"] = challenges_for(run_id)
                self._json(payload)
                return
            snapshot = disk_snapshot(run_id)
            if snapshot:
                snapshot["challenges"] = challenges_for(run_id)
                self._json(snapshot)
            else:
                self._error("run not found", 404)
            return
        match = re.fullmatch(r"/runs/([A-Za-z0-9._-]+)/report\.html", path)
        if match:
            self._file(RUNS_DIR / match.group(1) / "report.html")
            return
        match = re.fullmatch(r"/runs/([A-Za-z0-9._-]+)/judge\.md", path)
        if match:
            self._file(RUNS_DIR / match.group(1) / "judge.md")
            return
        self._error("not found", 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/runs":
            self._create_run()
            return
        match = re.fullmatch(r"/api/runs/([A-Za-z0-9._-]+)/challenge", path)
        if match:
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:  # noqa: BLE001
                self._error("invalid JSON", 400)
                return
            from_key = str(body.get("from") or "")
            to_key = str(body.get("to") or "")
            try:
                timeout = float(body.get("timeout") or 300)
            except Exception:  # noqa: BLE001
                timeout = 300
            timeout = max(30.0, min(timeout, 900.0))
            try:
                state = start_challenge(match.group(1), from_key, to_key, timeout)
            except ValueError as exc:
                self._error(str(exc), 400)
                return
            except Exception as exc:  # noqa: BLE001
                self._error(f"could not start challenge: {exc}", 500)
                return
            self._json(state.snapshot(), 202)
            return
        match = re.fullmatch(r"/api/runs/([A-Za-z0-9._-]+)/cancel", path)
        if match:
            with RUNS_LOCK:
                run = RUNS.get(match.group(1))
            if not run:
                self._error("run not found", 404)
                return
            self._json({"cancelled": run.cancel(), "id": run.id})
            return
        self._error("not found", 404)

    def _create_run(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 2_000_000:
                self._error("prompt is too large", 413)
                return
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:  # noqa: BLE001
            self._error("invalid JSON", 400)
            return

        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            self._error("write a prompt first", 400)
            return
        if len(prompt) > 100_000:
            self._error("prompt is too long (100k characters max)", 400)
            return

        available = E.all_keys(SETTINGS)
        requested = body.get("providers") or available
        if not isinstance(requested, list):
            self._error("providers must be a list", 400)
            return
        keys = [key for key in available if key in requested and SETTINGS[key].get("enabled", True)]
        if not keys:
            self._error("select at least one model", 400)
            return

        context = body.get("context") or "temp"
        if context not in ("temp", "copy", "cwd"):
            self._error("invalid context", 400)
            return
        judge = bool(body.get("judge"))
        debate = body.get("debate")
        if debate is None:
            debate = False
        else:
            debate = bool(debate)
        judge_provider = body.get("judge_provider")
        if judge_provider not in available:
            judge_provider = None
        timeout = body.get("timeout")
        try:
            timeout = int(timeout or 300)
        except Exception:  # noqa: BLE001
            timeout = 300
        timeout = max(30, min(timeout, 1800))
        models = body.get("models") or {}
        if not isinstance(models, dict):
            models = {}

        if active_runs() >= MAX_ACTIVE:
            self._error("too many runs are already active; stop one first", 429)
            return

        try:
            run = Run(prompt, keys, context, judge, judge_provider, timeout, models, debate=debate)
        except Exception as exc:  # noqa: BLE001
            self._error(f"could not prepare the run: {exc}", 500)
            return

        with RUNS_LOCK:
            RUNS[run.id] = run
        run.start()
        self._json(run.snapshot(), 201)


def main(argv=None) -> int:
    global CONFIG, SETTINGS
    parser = argparse.ArgumentParser(
        prog="ensemble web",
        description="Run one prompt through several models in a local web UI.",
    )
    parser.add_argument("--port", type=int, default=8765, help="port on 127.0.0.1 (default 8765)")
    parser.add_argument("--open", dest="open_browser", action="store_true", default=True,
                        help="open the browser when the server is ready (default)")
    parser.add_argument("--no-open", dest="open_browser", action="store_false",
                        help="do not open a browser")
    args = parser.parse_args(argv)

    CONFIG = E.load_config()
    SETTINGS = E.provider_settings(CONFIG)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"ensemble web: cannot bind 127.0.0.1:{args.port}: {exc}", file=sys.stderr)
        return 1
    server.daemon_threads = True

    url = f"http://127.0.0.1:{args.port}"
    print(f"ensemble web  ·  {url}")
    print(f"  runs        {RUNS_DIR}")
    print(f"  models      {', '.join(SETTINGS[key]['label'] for key in E.all_keys(SETTINGS))}")
    print("  stop        Ctrl-C")
    if args.open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nensemble web: stopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
