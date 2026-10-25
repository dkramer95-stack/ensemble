/* ensemble web — client */
(() => {
  "use strict";

  const ACTIVE = new Set(["starting", "running", "debating", "judging", "finalizing", "cancelling"]);

  function isBusy(data) {
    if (!data) return false;
    if (ACTIVE.has(data.status)) return true;
    return (data.challenges || []).some((challenge) => challenge.status === "running");
  }
  const TERMINAL = new Set(["done", "partial", "error", "cancelled"]);

  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const S = {
    providers: [],
    selected: new Set(),
    runs: [],
    current: null,
    running: false,
    pollTimer: null,
    pollToken: 0,
    toastTimer: null,
    historyFilter: "",
  };

  const dom = {};

  function cacheDom() {
    dom.prompt = $("#prompt");
    dom.samples = $("#samples");
    dom.modelPicker = $("#model-picker");
    dom.context = $("#context");
    dom.timeout = $("#timeout");
    dom.debate = $("#debate");
    dom.judge = $("#judge");
    dom.judgeProvider = $("#judge-provider");
    dom.run = $("#run");
    dom.runLabel = $("#run-label");
    dom.newRun = $("#new-run");
    dom.empty = $("#empty");
    dom.runView = $("#run-view");
    dom.runTitle = $("#run-title");
    dom.runState = $("#run-state");
    dom.runMeta = $("#run-meta");
    dom.reportLink = $("#report-link");
    dom.panes = $("#panes");
    dom.challengeBar = $("#challenge-bar");
    dom.challengeFrom = $("#challenge-from");
    dom.challengeTo = $("#challenge-to");
    dom.challengeRun = $("#challenge-run");
    dom.challenges = $("#challenges");
    dom.cancel = $("#cancel");
    dom.reuse = $("#reuse");
    dom.judgePane = $("#judge-pane");
    dom.judgeModel = $("#judge-model");
    dom.judgeStatus = $("#judge-status");
    dom.judgeBody = $("#judge-body");
    dom.historyFilter = $("#history-filter");
    dom.historyList = $("#history-list");
    dom.historyEmpty = $("#history-empty");
    dom.readiness = $("#readiness-list");
    dom.crumb = $("#crumb");
    dom.toast = $("#toast");
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let data = {};
    try {
      data = await response.json();
    } catch (_) {
      data = {};
    }
    if (!response.ok) {
      throw new Error(data.error || `${response.status} ${response.statusText}`);
    }
    return data;
  }

  /* ------------------------------------------------------------ formatting */

  function fmtDuration(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    if (total < 60) return `${total}s`;
    const minutes = Math.floor(total / 60);
    const rest = total % 60;
    return `${minutes}m ${String(rest).padStart(2, "0")}s`;
  }

  function fmtTokens(value) {
    if (!value) return "";
    if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k tok`;
    return `${value} tok`;
  }

  function shortDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(value || "");
    if (!match) return "";
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${months[Number(match[2]) - 1]} ${Number(match[3])} · ${match[4]}:${match[5]}`;
  }

  const STATUS_TEXT = {
    queued: "queued",
    running: "running",
    ok: "done",
    error: "error",
    timeout: "timeout",
    empty: "empty",
    cancelled: "stopped",
  };

  const CONTEXT_TEXT = {
    temp: "isolated dirs",
    copy: "project copy",
    cwd: "in place",
  };

  const RUN_STATE = {
    starting: "Starting",
    running: "Running",
    debating: "Debating",
    judging: "Synthesizing",
    finalizing: "Finishing",
    cancelling: "Stopping",
    done: "Complete",
    partial: "Finished · partial",
    error: "Finished · errors",
    cancelled: "Stopped",
  };

  /* -------------------------------------------------------------------- init */

  async function init() {
    cacheDom();
    bindEvents();
    setModifierLabel();

    try {
      const [catalog, history] = await Promise.all([
        api("/api/providers"),
        api("/api/runs"),
      ]);
      S.providers = catalog.providers || [];
      S.selected = new Set(S.providers.filter((p) => p.ready !== false).map((p) => p.key));
      if (!S.selected.size) S.selected = new Set(S.providers.map((p) => p.key));
      renderModelPicker();
      renderJudgeOptions(catalog.defaults?.judge_provider);
      renderReadiness();
      if (catalog.defaults?.context && CONTEXT_TEXT[catalog.defaults.context]) {
        dom.context.value = catalog.defaults.context;
      }
      dom.debate.checked = Boolean(catalog.defaults?.debate ?? true);
      dom.judge.checked = Boolean(catalog.defaults?.judge ?? true);
      dom.judgeProvider.disabled = !dom.judge.checked;
      updateRunLabel();

      const runs = history.runs || [];
      renderHistory(runs);
      if (!runs.length) dom.historyEmpty.hidden = false;

      const wanted = new URLSearchParams(location.search).get("run");
      if (wanted) {
        await loadRun(wanted, { updateUrl: false });
      } else {
        showEmpty();
      }
    } catch (error) {
      toast(error.message || "could not reach the ensemble server", 5000);
      showEmpty();
    }
  }

  function bindEvents() {
    dom.run.addEventListener("click", startRun);
    dom.newRun.addEventListener("click", newComparison);
    dom.cancel.addEventListener("click", cancelRun);
    dom.challengeRun.addEventListener("click", startChallenge);
    dom.reuse.addEventListener("click", reusePrompt);
    dom.judge.addEventListener("change", () => {
      dom.judgeProvider.disabled = !dom.judge.checked;
    });

    dom.prompt.addEventListener("input", () => {
      const hasText = dom.prompt.value.trim().length > 0;
      dom.samples.hidden = hasText;
      growPrompt();
    });

    dom.samples.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-prompt]");
      if (!button) return;
      dom.prompt.value = button.dataset.prompt;
      dom.prompt.dispatchEvent(new Event("input"));
      dom.prompt.focus();
    });

    dom.historyFilter.addEventListener("input", () => {
      S.historyFilter = dom.historyFilter.value;
      renderHistoryItems();
    });

    dom.historyList.addEventListener("click", (event) => {
      const item = event.target.closest(".history-item");
      if (!item) return;
      if (S.running) {
        toast("Stop the current run before opening another.");
        return;
      }
      loadRun(item.dataset.id);
    });

    dom.panes.addEventListener("scroll", (event) => {
      if (event.target.classList && event.target.classList.contains("pane-body")) {
        updateOverflow(event.target.closest(".pane"));
      }
    }, true);

    dom.panes.addEventListener("click", (event) => {
      const copy = event.target.closest(".pane-copy");
      if (copy) {
        const pane = copy.closest(".pane");
        copyAnswer(pane);
        return;
      }
      const focus = event.target.closest(".pane-focus");
      if (focus) {
        toggleFocus(focus.closest(".pane"));
      }
    });

    document.addEventListener("keydown", (event) => {
      const mod = event.metaKey || event.ctrlKey;
      if (mod && event.key === "Enter") {
        event.preventDefault();
        if (!S.running) startRun();
        return;
      }
      if (mod && event.key.toLowerCase() === "k") {
        event.preventDefault();
        dom.prompt.focus();
        return;
      }
      if (event.key === "/" && !mod && !event.altKey && !isTypingTarget(event.target)) {
        event.preventDefault();
        dom.historyFilter.focus();
        dom.historyFilter.select();
        return;
      }
      if (event.key === "Escape" && document.activeElement === dom.historyFilter) {
        event.preventDefault();
        dom.historyFilter.value = "";
        dom.historyFilter.dispatchEvent(new Event("input"));
        dom.historyFilter.blur();
        return;
      }
      if (event.key === "Escape") {
        const focused = $(".pane.is-focused");
        if (focused) {
          event.preventDefault();
          toggleFocus(focused, false);
        }
      }
    });

    window.addEventListener("resize", () => {
      document.querySelectorAll("#panes .pane").forEach(updateOverflow);
    });

    window.addEventListener("popstate", () => {
      const wanted = new URLSearchParams(location.search).get("run");
      if (wanted && (!S.current || S.current.id !== wanted)) {
        loadRun(wanted, { updateUrl: false });
      }
    });
  }

  function setModifierLabel() {
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform || "");
    document.querySelectorAll("kbd").forEach((node) => {
      node.textContent = isMac ? "⌘↵" : "Ctrl↵";
    });
  }

  /* ------------------------------------------------------------------ setup */

  function renderModelPicker() {
    dom.modelPicker.replaceChildren();
    for (const provider of S.providers) {
      const button = el("button", "chip");
      button.type = "button";
      button.dataset.key = provider.key;
      button.style.setProperty("--accent", provider.accent || "#6B7280");
      button.setAttribute("aria-pressed", String(S.selected.has(provider.key)));
      if (provider.ready === false) button.title = `${provider.label}: ${provider.note || "not ready"}`;
      button.append(el("span", "dot"), document.createTextNode(provider.label));
      button.addEventListener("click", () => {
        if (S.running) {
          toast("Stop the current run before changing models.");
          return;
        }
        if (S.selected.has(provider.key)) {
          S.selected.delete(provider.key);
        } else {
          S.selected.add(provider.key);
          if (provider.ready === false) {
            toast(`${provider.label} is not ready: ${provider.note || "check authentication"}.`);
          }
        }
        button.setAttribute("aria-pressed", String(S.selected.has(provider.key)));
        renderJudgeOptions();
        updateRunLabel();
      });
      dom.modelPicker.append(button);
    }
  }

  function renderJudgeOptions(preferred) {
    const previous = preferred || dom.judgeProvider.value;
    const selected = S.providers.filter((p) => S.selected.has(p.key));
    dom.judgeProvider.replaceChildren();
    for (const provider of selected) {
      const option = el("option", null, provider.label);
      option.value = provider.key;
      dom.judgeProvider.append(option);
    }
    if (selected.some((p) => p.key === previous)) {
      dom.judgeProvider.value = previous;
    } else if (selected.some((p) => p.key === "deepseek")) {
      dom.judgeProvider.value = "deepseek";
    } else if (selected.length) {
      dom.judgeProvider.value = selected[0].key;
    }
  }

  function renderReadiness() {
    dom.readiness.replaceChildren();
    for (const provider of S.providers) {
      const row = el("div", "ready-row");
      const dot = el("span", "ready-dot");
      dot.dataset.ready = String(provider.ready === true);
      if (provider.ready === null || provider.ready === undefined) {
        dot.dataset.ready = "unknown";
        dot.style.opacity = "0.45";
      }
      const name = el("span", "ready-name", provider.label);
      const note = el("span", "ready-note", provider.note || "");
      row.title = `${provider.label}: ${provider.note || "ready"}`;
      row.append(dot, name, note);
      dom.readiness.append(row);
    }
  }

  function updateRunLabel() {
    const count = S.selected.size;
    dom.run.disabled = S.running || count === 0;
    if (S.running) {
      dom.runLabel.textContent = "Running…";
      return;
    }
    dom.runLabel.textContent = count === 0
      ? "Select a model"
      : `Run ${count} model${count === 1 ? "" : "s"}`;
  }

  function setPrompt(text) {
    dom.prompt.value = text || "";
    dom.prompt.dispatchEvent(new Event("input"));
  }

  function growPrompt() {
    dom.prompt.style.height = "auto";
    dom.prompt.style.height = `${Math.min(dom.prompt.scrollHeight, 320)}px`;
  }

  /* ------------------------------------------------------------------- runs */

  async function startRun() {
    if (S.running) return;
    const prompt = dom.prompt.value.trim();
    if (!prompt) {
      toast("Write a prompt first.");
      dom.prompt.focus();
      return;
    }
    const providers = [...S.selected];
    if (!providers.length) {
      toast("Select at least one model.");
      return;
    }

    dom.run.disabled = true;
    dom.runLabel.textContent = "Starting…";
    try {
      const data = await api("/api/runs", {
        method: "POST",
        body: JSON.stringify({
          prompt,
          providers,
          context: dom.context.value,
          debate: dom.debate.checked,
          judge: dom.judge.checked,
          judge_provider: dom.judge.checked ? dom.judgeProvider.value : null,
          timeout: Number(dom.timeout.value),
        }),
      });
      S.current = data;
      S.running = true;
      renderRun(data);
      setActiveHistory(data.id);
      updateUrl(data.id);
      startPolling();
      requestAnimationFrame(() => {
        dom.runView.scrollIntoView({
          behavior: prefersReducedMotion() ? "auto" : "smooth",
          block: "start",
        });
      });
    } catch (error) {
      toast(error.message || "could not start the run", 5000);
      S.running = false;
      updateRunLabel();
    }
  }

  async function loadRun(id, options = {}) {
    stopPolling();
    try {
      const data = await api(`/api/runs/${encodeURIComponent(id)}`);
      S.current = data;
      S.running = isBusy(data);
      setPrompt(data.prompt);
      renderRun(data);
      setActiveHistory(id);
      if (options.updateUrl !== false) updateUrl(id);
      if (S.running) startPolling();
    } catch (error) {
      toast(error.message || "could not load that run", 5000);
    }
  }

  function renderRun(data) {
    S.current = data;
    S.running = isBusy(data);

    dom.empty.hidden = true;
    dom.runView.hidden = false;
    dom.crumb.textContent = "Comparison";
    dom.runTitle.textContent = data.prompt;
    dom.runTitle.title = data.prompt;
    dom.runState.textContent = RUN_STATE[data.status] || data.status;
    dom.runState.dataset.status = data.status;

    const meta = [];
    meta.push(`${data.providers.length} model${data.providers.length === 1 ? "" : "s"}`);
    meta.push(fmtDuration(data.wall_seconds));
    meta.push(`${data.answered}/${data.total} answered`);
    meta.push(CONTEXT_TEXT[data.context] || data.context);
    if (data.debate_requested) meta.push("debate round");
    if (data.created_at) meta.push(shortDate(data.created_at));
    dom.runMeta.replaceChildren(...meta.map((text) => el("span", null, text)));

    dom.reportLink.hidden = !data.report_url;
    if (data.report_url) dom.reportLink.href = data.report_url;

    dom.cancel.hidden = !data.can_cancel;
    if (data.can_cancel) {
      dom.cancel.disabled = false;
      dom.cancel.textContent = "Stop";
    }

    renderPanes(data.providers, data.id);
    renderChallengeBar(data);
    renderChallenges(data);
    renderJudge(data);

    dom.run.disabled = S.running || S.selected.size === 0;
    dom.newRun.disabled = S.running;
    updateRunLabel();
    if (S.running) {
      const runningChallenge = (data.challenges || []).some((c) => c.status === "running");
      dom.runLabel.textContent = runningChallenge
        ? "Challenging…"
        : data.status === "judging"
          ? "Synthesizing…"
          : data.status === "debating" ? "Debating…" : "Running…";
    }

  }

  function renderPanes(providers, runId) {
    const signature = `${runId || ""}|${providers.map((p) => p.key).join("|")}`;
    if (dom.panes.dataset.signature !== signature) {
      dom.panes.replaceChildren();
      dom.panes.dataset.signature = signature;
      dom.panes.classList.remove("focused");
      for (const provider of providers) createPane(provider);
    }
    for (const provider of providers) updatePane(provider);
  }

  function createPane(provider) {
    const template = $("#pane-template");
    const pane = template.content.firstElementChild.cloneNode(true);
    pane.dataset.key = provider.key;
    const body = $(".pane-body", pane);
    body.tabIndex = 0;
    body.setAttribute("aria-label", `${provider.label} answer`);
    pane.style.setProperty("--accent", provider.accent || "#6B7280");
    $(".pane-title", pane).textContent = provider.label;
    $(".pane-model", pane).textContent = provider.model || "default";
    $(".pane-copy", pane).dataset.key = provider.key;
    dom.panes.append(pane);
  }

  function updatePane(provider) {
    const pane = dom.panes.querySelector(`.pane[data-key="${cssEscape(provider.key)}"]`);
    if (!pane) return;

    const focused = pane.classList.contains("is-focused");
    const status = provider.status || "queued";
    pane.className = `pane is-${status}${focused ? " is-focused" : ""}`;
    pane.setAttribute("aria-busy", String(status === "running" || status === "queued"));

    $(".pane-model", pane).textContent = provider.model || "default";

    const badge = $(".pane-status", pane);
    badge.className = `pane-status status ${status}`;
    badge.textContent = STATUS_TEXT[status] || status;

    const time = $(".pane-time", pane);
    time.textContent = status === "queued" ? "" : fmtDuration(provider.elapsed);
    time.title = provider.tokens_total ? `${provider.tokens_total.toLocaleString()} tokens` : "";

    const copy = $(".pane-copy", pane);
    copy.hidden = status !== "ok" || !provider.text;

    const body = $(".pane-body", pane);
    if (status === "ok") {
      const debate = provider.debate;
      const debateSig = debate
        ? `${debate.status}:${(debate.html || "").length}:${debate.error || ""}`
        : "none";
      const sig = `ok:${provider.html.length}:${debateSig}`;
      if (body.dataset.sig !== sig) {
        body.replaceChildren();
        const md = el("div", "md");
        md.innerHTML = provider.html;
        body.append(md);
        if (debate) body.append(debateBlock(debate));
        body.dataset.sig = sig;
      }
      updateOverflow(pane);
      return;
    }

    if (status === "queued" || status === "running") {
      if (!body.querySelector(".skeleton")) {
        body.replaceChildren(skeleton(status));
        body.dataset.sig = status;
      } else if (body.dataset.sig !== status) {
        body.replaceChildren(skeleton(status));
        body.dataset.sig = status;
        updateOverflow(pane);
      }
      return;
    }

    const sig = `${status}:${provider.error}:${provider.hint}`;
    if (body.dataset.sig === sig) return;
    body.replaceChildren(errorBody(provider));
    body.dataset.sig = sig;
    updateOverflow(pane);
  }

  function updateOverflow(pane) {
    if (!pane) return;
    const body = $(".pane-body", pane);
    if (!body) return;
    const focused = pane.classList.contains("is-focused");
    const overflowing = body.scrollHeight > body.clientHeight + 4;
    const horizontal = body.scrollWidth > body.clientWidth + 4;
    const atBottom = body.scrollTop + body.clientHeight >= body.scrollHeight - 6;
    pane.classList.toggle("has-overflow", overflowing && !atBottom && !focused);
    const button = $(".pane-focus", pane);
    if (button) button.hidden = !(overflowing || horizontal || focused);
  }

  function debateBlock(debate) {
    const wrap = el("section", "debate-block");
    const head = el("div", "debate-head");
    head.append(el("span", "debate-label", "Rebuttal"));
    const status = debate.status || "running";
    const badge = el("span", `status ${status}`);
    badge.textContent = status === "ok" ? "done" : status === "running" ? "arguing" : status;
    head.append(badge);
    let meta = status === "pending" || status === "running" ? "" : fmtDuration(debate.elapsed);
    if (debate.tokens_total && status === "ok") {
      meta += `${meta ? " · " : ""}${fmtTokens(debate.tokens_total)}`;
    }
    if (meta) head.append(el("span", "debate-meta", meta));
    wrap.append(head);

    if (status === "ok") {
      const md = el("div", "md");
      md.innerHTML = debate.html || "";
      wrap.append(md);
    } else if (status === "pending" || status === "running") {
      wrap.append(skeleton("running"));
    } else {
      const box = el("div", "pane-error");
      box.append(el("p", "err-msg", debate.error || "No rebuttal."));
      if (debate.hint) box.append(el("p", "err-hint", `→ ${debate.hint.replaceAll("`", "")}`));
      wrap.append(box);
    }
    return wrap;
  }

  function skeleton(status) {
    const wrap = el("div", "skeleton");
    for (const width of ["w92", "w84", "w71"]) {
      wrap.append(el("span", `skel ${width}`));
    }
    const thinking = el("div", "thinking", status === "queued" ? "waiting for a slot" : "thinking");
    wrap.append(thinking);
    return wrap;
  }

  function errorBody(provider) {
    const wrap = el("div", "pane-error");
    let message = provider.error || "No answer.";
    if (provider.status === "cancelled") message = "Stopped before this model answered.";
    if (provider.status === "timeout") message = provider.error || "The model timed out.";
    wrap.append(el("p", "err-msg", message));
    if (provider.hint) {
      const hint = el("p", "err-hint", `→ ${provider.hint.replaceAll("`", "")}`);
      wrap.append(hint);
    }
    return wrap;
  }

  function renderChallengeBar(data) {
    const eligible = data.providers.filter((p) => p.status === "ok" && p.html);
    const running = (data.challenges || []).some((c) => c.status === "running");
    const show = eligible.length >= 2 && !ACTIVE.has(data.status);
    dom.challengeBar.hidden = !show;
    if (!show) return;

    const signature = eligible.map((p) => `${p.key}:${p.label}`).join("|");
    if (dom.challengeBar.dataset.sig !== signature) {
      dom.challengeBar.dataset.sig = signature;
      const previousFrom = dom.challengeFrom.value;
      const previousTo = dom.challengeTo.value;
      dom.challengeFrom.replaceChildren();
      dom.challengeTo.replaceChildren();
      for (const provider of eligible) {
        const option = el("option", null, provider.label);
        option.value = provider.key;
        dom.challengeFrom.append(option);
        dom.challengeTo.append(option.cloneNode(true));
      }
      const keys = eligible.map((p) => p.key);
      dom.challengeFrom.value = keys.includes(previousFrom)
        ? previousFrom
        : keys.includes("kimi") ? "kimi" : keys[0];
      dom.challengeTo.value = keys.includes(previousTo) && previousTo !== dom.challengeFrom.value
        ? previousTo
        : keys.includes("deepseek") && dom.challengeFrom.value !== "deepseek"
          ? "deepseek"
          : keys.find((key) => key !== dom.challengeFrom.value);
    }
    dom.challengeRun.disabled = running;
    dom.challengeRun.textContent = running ? "Challenging…" : "Run challenge";
  }

  async function startChallenge() {
    if (!S.current) return;
    const from = dom.challengeFrom.value;
    const to = dom.challengeTo.value;
    if (!from || !to) {
      toast("Pick a challenger and a target.");
      return;
    }
    if (from === to) {
      toast("Pick two different models.");
      return;
    }
    dom.challengeRun.disabled = true;
    dom.challengeRun.textContent = "Starting…";
    try {
      await api(`/api/runs/${encodeURIComponent(S.current.id)}/challenge`, {
        method: "POST",
        body: JSON.stringify({ from, to }),
      });
      await loadRun(S.current.id, { updateUrl: false });
      startPolling();
      requestAnimationFrame(() => {
        dom.challenges.scrollIntoView({
          behavior: prefersReducedMotion() ? "auto" : "smooth",
          block: "nearest",
        });
      });
    } catch (error) {
      toast(error.message || "could not start the challenge", 5000);
      dom.challengeRun.disabled = false;
      dom.challengeRun.textContent = "Run challenge";
    }
  }

  function renderChallenges(data) {
    const challenges = data.challenges || [];
    dom.challenges.hidden = challenges.length === 0;
    dom.challenges.replaceChildren();
    if (!challenges.length) return;
    for (const challenge of challenges) {
      const item = el("article", "challenge-item");
      const head = el("div", "challenge-head");
      const route = el("div", "challenge-route");
      route.append(
        document.createTextNode(challenge.from_label || challenge.from_key || ""),
        el("span", "arrow", " → "),
        document.createTextNode(challenge.to_label || challenge.to_key || ""),
      );
      head.append(route);
      const status = challenge.status || "running";
      const badge = el("span", `status ${status}`);
      badge.textContent = status === "ok" ? "done" : status === "running" ? "arguing" : status;
      head.append(badge);
      const meta = el("span", "challenge-meta");
      meta.textContent = status === "running" ? "working…" : fmtDuration(challenge.elapsed);
      head.append(meta);
      item.append(head);

      if (status === "ok" && challenge.html) {
        const md = el("div", "md");
        md.innerHTML = challenge.html;
        item.append(md);
      } else if (status === "running") {
        item.append(skeleton("running"));
      } else {
        const box = el("div", "pane-error");
        box.append(el("p", "err-msg", challenge.error || "Challenge failed."));
        if (challenge.hint) {
          box.append(el("p", "err-hint", `→ ${challenge.hint.replaceAll("`", "")}`));
        }
        item.append(box);
      }
      dom.challenges.append(item);
    }
  }

  function renderJudge(data) {
    const judge = data.judge;
    const show = Boolean(judge) || data.status === "judging";
    dom.judgePane.hidden = !show;
    if (!show) return;

    const status = judge?.status || "running";
    dom.judgeStatus.className = `status ${status === "done" ? "ok" : status === "error" ? "error" : "running"}`;
    dom.judgeStatus.textContent = status === "done" ? "done" : status === "error" ? "error" : "synthesizing";
    dom.judgeModel.textContent = judge?.model ? `${judge.label || "Judge"} · ${judge.model}` : (judge?.label || "");

    if (status === "done") {
      if (dom.judgeBody.dataset.sig !== `done:${(judge.html || "").length}`) {
        dom.judgeBody.replaceChildren();
        const md = el("div", "md");
        md.innerHTML = judge.html || "";
        dom.judgeBody.append(md);
        dom.judgeBody.dataset.sig = `done:${(judge.html || "").length}`;
      }
      return;
    }

    if (status === "error") {
      const wrap = el("div", "pane-error");
      wrap.append(el("p", "err-msg", judge.error || "the judge did not return an answer"));
      dom.judgeBody.replaceChildren(wrap);
      dom.judgeBody.dataset.sig = "error";
      return;
    }

    if (!dom.judgeBody.querySelector(".skeleton")) {
      dom.judgeBody.replaceChildren(skeleton("running"));
      dom.judgeBody.dataset.sig = "running";
    }
  }

  function startPolling() {
    stopPolling();
    const token = S.pollToken;
    const tick = async () => {
      if (token !== S.pollToken || !S.current) return;
      try {
        const data = await api(`/api/runs/${encodeURIComponent(S.current.id)}`);
        if (token !== S.pollToken) return;
        renderRun(data);
        if (isBusy(data)) {
          S.pollTimer = setTimeout(tick, 700);
        } else {
          S.pollTimer = null;
          S.running = false;
          updateRunLabel();
          dom.newRun.disabled = false;
          await refreshHistory();
        }
      } catch (error) {
        if (token === S.pollToken) {
          toast(error.message || "lost contact with the run", 4000);
          S.pollTimer = setTimeout(tick, 2000);
        }
      }
    };
    S.pollTimer = setTimeout(tick, 350);
  }

  function stopPolling() {
    S.pollToken += 1;
    if (S.pollTimer) clearTimeout(S.pollTimer);
    S.pollTimer = null;
  }

  async function cancelRun() {
    if (!S.current) return;
    dom.cancel.disabled = true;
    dom.cancel.textContent = "Stopping…";
    try {
      const result = await api(`/api/runs/${encodeURIComponent(S.current.id)}/cancel`, { method: "POST" });
      if (!result.cancelled) {
        toast("This run cannot be stopped at this stage.");
        dom.cancel.disabled = false;
        dom.cancel.textContent = "Stop";
      }
    } catch (error) {
      toast(error.message || "could not stop the run", 4000);
      dom.cancel.disabled = false;
      dom.cancel.textContent = "Stop";
    }
  }

  function reusePrompt() {
    if (!S.current) return;
    dom.prompt.value = S.current.prompt;
    dom.prompt.dispatchEvent(new Event("input"));
    dom.prompt.focus();
    window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }

  function newComparison() {
    if (S.running) {
      toast("Stop the current run first.");
      return;
    }
    stopPolling();
    S.current = null;
    S.running = false;
    dom.prompt.value = "";
    dom.prompt.dispatchEvent(new Event("input"));
    dom.prompt.focus();
    dom.runView.hidden = true;
    dom.empty.hidden = false;
    dom.crumb.textContent = "New comparison";
    dom.reportLink.hidden = true;
    dom.panes.replaceChildren();
    dom.panes.dataset.signature = "";
    dom.judgePane.hidden = true;
    dom.runMeta.replaceChildren();
    dom.runTitle.textContent = "";
    setActiveHistory(null);
    updateUrl(null);
    updateRunLabel();
    window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }

  function showEmpty() {
    dom.empty.hidden = false;
    dom.runView.hidden = true;
    dom.crumb.textContent = "New comparison";
  }

  function setActiveHistory(id) {
    for (const item of dom.historyList.querySelectorAll(".history-item")) {
      if (item.dataset.id === id) item.setAttribute("aria-current", "true");
      else item.removeAttribute("aria-current");
    }
  }

  function updateUrl(id) {
    const url = id ? `/?run=${encodeURIComponent(id)}` : "/";
    history.replaceState({}, "", url);
  }

  /* ----------------------------------------------------------------- history */

  async function refreshHistory() {
    try {
      const data = await api("/api/runs");
      renderHistory(data.runs || []);
    } catch (_) {
      /* a failed refresh should not break the run view */
    }
  }

  function renderHistory(runs) {
    S.runs = runs;
    renderHistoryItems();
  }

  function renderHistoryItems() {
    const query = S.historyFilter.trim().toLowerCase();
    const runs = query
      ? S.runs.filter((run) => (run.prompt || "").toLowerCase().includes(query))
      : S.runs;
    dom.historyList.replaceChildren();
    dom.historyEmpty.hidden = S.runs.length > 0;
    for (const run of runs) {
      const item = el("button", "history-item");
      item.type = "button";
      item.dataset.id = run.id;
      if (S.current?.id === run.id) item.setAttribute("aria-current", "true");

      item.append(el("span", "hi-prompt", run.prompt));

      const meta = el("span", "hi-meta");
      meta.append(el("span", null, shortDate(run.created_at)));
      const dots = el("span", "hi-dots");
      for (const status of run.statuses || []) {
        const dot = el("i", "hi-dot");
        dot.dataset.s = status.status;
        dot.title = `${status.label}: ${STATUS_TEXT[status.status] || status.status}`;
        dots.append(dot);
      }
      meta.append(dots);
      item.append(meta);
      dom.historyList.append(item);
    }
    if (!runs.length && S.runs.length) {
      dom.historyList.append(el("p", "history-none", "No runs match."));
    }
    if (S.current?.id) setActiveHistory(S.current.id);
  }

  /* ------------------------------------------------------------------- focus */

  function toggleFocus(pane, force) {
    if (!pane) return;
    const shouldFocus = typeof force === "boolean" ? force : !pane.classList.contains("is-focused");
    for (const other of dom.panes.querySelectorAll(".pane")) {
      other.classList.remove("is-focused");
      const button = $(".pane-focus", other);
      if (button) {
        button.setAttribute("aria-label", "Expand full answer");
        button.title = "Expand full answer";
        const label = $(".pane-focus-label", button);
        if (label) label.textContent = "Expand";
        button.classList.remove("is-active");
      }
    }
    if (shouldFocus) {
      pane.classList.add("is-focused");
      dom.panes.classList.add("focused");
      const button = $(".pane-focus", pane);
      if (button) {
        button.setAttribute("aria-label", "Collapse this answer");
        button.title = "Collapse this answer";
        const label = $(".pane-focus-label", button);
        if (label) label.textContent = "Collapse";
        button.classList.add("is-active");
        pane.classList.remove("has-overflow");
      }
    } else {
      dom.panes.classList.remove("focused");
    }
    requestAnimationFrame(() => updateOverflow(pane));
  }

  function paneAnswer(pane) {
    const key = pane?.dataset.key;
    const provider = key
      ? (S.current?.providers || []).find((item) => item.key === key)
      : null;
    if (provider?.text) return provider.text;
    const body = pane?.querySelector(".md");
    return body ? body.innerText.trim() : "";
  }

  async function copyAnswer(pane) {
    const text = paneAnswer(pane);
    if (!text) {
      toast("Copy failed");
      return;
    }
    const copied = await writeClipboard(text);
    toast(copied ? "Copied" : "Copy failed");
  }

  async function writeClipboard(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_) {
        /* the Clipboard API can reject: fall back to the selection trick */
      }
    }
    return legacyCopy(text);
  }

  function legacyCopy(text) {
    const area = el("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "0";
    area.style.left = "-9999px";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (_) {
      copied = false;
    }
    area.remove();
    return copied;
  }

  /* ------------------------------------------------------------------- misc */

  function toast(message, duration = 2800) {
    dom.toast.textContent = message;
    dom.toast.classList.add("show");
    if (S.toastTimer) clearTimeout(S.toastTimer);
    S.toastTimer = setTimeout(() => dom.toast.classList.remove("show"), duration);
  }

  function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function isTypingTarget(node) {
    if (!node || node.nodeType !== 1) return false;
    const tag = node.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || node.isContentEditable;
  }

  function cssEscape(value) {
    if (window.CSS && typeof CSS.escape === "function") return CSS.escape(value);
    return String(value).replace(/["\\]/g, "\\$&");
  }

  init();
})();
