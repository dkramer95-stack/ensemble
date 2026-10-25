"""write_artifacts() + write_report() + load_run() round-trip in a temp dir."""

import json
import tempfile
import unittest
from pathlib import Path

import _support  # noqa: F401  (must be imported before ensemble: isolates HOME)
import ensemble as E

PROMPT = "Compare <b>CRDTs</b> & databases; ignore <script>alert('prompt')</script>."

OK_TEXT = (
    "# Findings\n"
    "\n"
    "- CRDTs merge without coordination.\n"
    "- They trade latency for consistency.\n"
    "\n"
    "```python\n"
    "print(\"<script>alert('code')</script>\")\n"
    "```\n"
    "\n"
    "| Property | CRDT |\n"
    "|---|---|\n"
    "| Latency | low |\n"
)


def make_ok_result(prompt):
    result = E.Result(
        key="kimi",
        label="Kimi",
        accent="#5B5BD6",
        status="ok",
        text=OK_TEXT,
        elapsed=1.25,
        reported_ms=1200.0,
        tokens_in=100,
        tokens_out=20,
        tokens_total=120,
        cost=0.0012,
        model="kimi-code",
        exit_code=0,
        stdout='{"role":"assistant","content":"..."}\n',
        stderr="",
        argv=["kimi", "-p", prompt, "--output-format", "stream-json"],
    )
    result.debate = E.Result(
        key="kimi",
        label="Kimi",
        accent="#5B5BD6",
        status="ok",
        text="A short rebuttal.",
        elapsed=0.4,
        tokens_total=30,
        cost=0.0002,
        exit_code=0,
        stdout='{"role":"assistant","content":"A short rebuttal."}\n',
        stderr="",
    )
    return result


def make_error_result(prompt):
    return E.Result(
        key="codex",
        label="Codex",
        accent="#0B8F6A",
        status="error",
        error="exited with code 1: <script>alert('error')</script> & boom",
        hint="Install the Codex CLI, then run `ensemble doctor`.",
        elapsed=0.5,
        model="",
        exit_code=1,
        stdout="",
        stderr="Traceback: <b>unexpected</b> & bad\n",
        argv=["codex", "exec", prompt],
    )


def make_meta(prompt, tmpdir):
    return {
        "version": E.VERSION,
        "prompt": prompt,
        "created_at": "2026-10-25 20:00:00",
        "finished_at": "2026-10-25 20:00:08",
        "context": "temp",
        "cwd": str(tmpdir),
        "keys": ["kimi", "codex"],
        "models": {"kimi": "kimi-code"},
        "debate": True,
        "wall_seconds": 7.5,
        "command": "ensemble run --only kimi,codex <prompt>",
        "judge": {"label": "DeepSeek", "model": "deepseek-flash"},
    }


class ArtifactsRoundTripTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ensemble-artifacts-")
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name) / "2026-10-25_200000_crdts"
        self.meta = make_meta(PROMPT, self._tmp.name)
        self.results = [make_ok_result(PROMPT), make_error_result(PROMPT)]
        E.write_artifacts(self.run_dir, PROMPT, self.results, dict(self.meta))
        self.html_path = E.write_report(self.run_dir, dict(self.meta), self.results)
        self.html = (self.run_dir / "report.html").read_text()

    # -- write_artifacts -------------------------------------------------- #

    def test_write_artifacts_creates_expected_files(self):
        expected = [
            "prompt.md",
            "meta.json",
            "results.json",
            # ok result (plus its nested debate)
            "kimi.stdout.txt",
            "kimi.stderr.txt",
            "kimi.md",
            "kimi.debate.stdout.txt",
            "kimi.debate.stderr.txt",
            "kimi.debate.md",
            # failed result: no .md, but an .error.txt
            "codex.stdout.txt",
            "codex.stderr.txt",
            "codex.error.txt",
        ]
        for name in expected:
            with self.subTest(name=name):
                self.assertTrue((self.run_dir / name).is_file(), f"missing artifact {name}")

    def test_write_artifacts_does_not_write_answer_file_for_failures(self):
        self.assertFalse((self.run_dir / "codex.md").exists())

    def test_prompt_artifact_keeps_exact_prompt(self):
        self.assertEqual((self.run_dir / "prompt.md").read_text(), PROMPT.rstrip() + "\n")

    def test_meta_and_results_json_are_valid_and_consistent(self):
        meta = json.loads((self.run_dir / "meta.json").read_text())
        results = json.loads((self.run_dir / "results.json").read_text())
        self.assertEqual(meta["prompt"], PROMPT)
        self.assertEqual(meta["context"], "temp")
        self.assertEqual(meta["wall_seconds"], 7.5)
        self.assertEqual(len(results), 2)
        self.assertEqual(meta["results"], results)
        self.assertEqual([row["status"] for row in results], ["ok", "error"])
        self.assertEqual(meta["version"], E.VERSION)

    def test_stdout_and_stderr_artifacts_are_verbatim(self):
        self.assertEqual(
            (self.run_dir / "kimi.stdout.txt").read_text(),
            '{"role":"assistant","content":"..."}\n',
        )
        self.assertEqual(
            (self.run_dir / "codex.stderr.txt").read_text(),
            "Traceback: <b>unexpected</b> & bad\n",
        )
        self.assertIn("alert('error')", (self.run_dir / "codex.error.txt").read_text())

    # -- write_report ----------------------------------------------------- #

    def test_write_report_returns_report_path_and_writes_files(self):
        self.assertEqual(self.html_path, self.run_dir / "report.html")
        self.assertTrue(self.html_path.is_file())
        self.assertTrue((self.run_dir / "report.md").is_file())
        self.assertGreater(len(self.html), 1000)

    def test_report_html_is_well_formed_and_contains_cards(self):
        self.assertTrue(self.html.startswith("<!doctype html>"))
        self.assertIn("<title>", self.html)
        self.assertIn('class="card"', self.html)
        self.assertIn("Kimi", self.html)
        self.assertIn("Codex", self.html)
        self.assertIn('<span class="pill ok">ok</span>', self.html)
        self.assertIn('<span class="pill error">error</span>', self.html)

    def test_report_html_renders_markdown_answer(self):
        self.assertIn("<h1>Findings</h1>", self.html)
        self.assertIn("<li>CRDTs merge without coordination.</li>", self.html)
        self.assertIn("<pre><code", self.html)
        self.assertIn("<th>Property</th>", self.html)
        self.assertIn("<td>Latency</td>", self.html)
        self.assertIn('class="table-wrap"', self.html)

    def test_report_html_escapes_error_text(self):
        # The raw error must only ever appear escaped, never as live markup.
        self.assertIn("&lt;script&gt;", self.html)
        self.assertNotIn("<script>alert('error')</script>", self.html)
        self.assertIn("&amp; boom", self.html)
        self.assertIn("&lt;b&gt;unexpected&lt;/b&gt;", self.html)

    def test_report_html_has_no_active_content_from_model_output(self):
        lowered = self.html.lower()
        self.assertNotIn("<script", lowered)
        self.assertNotIn("onerror=", lowered)
        self.assertNotIn("onload=", lowered)
        self.assertNotIn("javascript:", lowered)

    def test_report_html_escapes_prompt(self):
        self.assertIn("&lt;script&gt;", self.html)
        self.assertNotIn("<script>alert('prompt')</script>", self.html)
        self.assertIn("&amp; databases", self.html)

    def test_report_markdown_contains_sections(self):
        markdown = (self.run_dir / "report.md").read_text()
        self.assertIn("# Ensemble", markdown)
        self.assertIn("## Prompt", markdown)
        self.assertIn("## Results", markdown)
        self.assertIn("| Model | Status | Time | Tokens | Cost | Output |", markdown)
        self.assertIn("Kimi", markdown)
        self.assertIn("Codex", markdown)

    # -- load_run round-trip ---------------------------------------------- #

    def test_load_run_returns_prompt_meta_and_results(self):
        prompt, meta, results = E.load_run(self.run_dir)
        self.assertEqual(prompt, PROMPT)
        self.assertIsInstance(meta, dict)
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(result, E.Result) for result in results))
        self.assertEqual([result.key for result in results], ["kimi", "codex"])
        self.assertEqual([result.status for result in results], ["ok", "error"])

    def test_load_run_preserves_meta(self):
        _, meta, _ = E.load_run(self.run_dir)
        self.assertEqual(meta["version"], E.VERSION)
        self.assertEqual(meta["context"], "temp")
        self.assertEqual(meta["wall_seconds"], 7.5)
        self.assertEqual(meta["models"], {"kimi": "kimi-code"})
        self.assertEqual(meta["keys"], ["kimi", "codex"])
        self.assertEqual(len(meta["results"]), 2)

    def test_load_run_preserves_successful_result_fields(self):
        _, _, results = E.load_run(self.run_dir)
        kimi = results[0]
        self.assertEqual(kimi.label, "Kimi")
        self.assertEqual(kimi.accent, "#5B5BD6")
        self.assertTrue(kimi.text.startswith("# Findings"))
        self.assertEqual(kimi.elapsed, 1.25)
        self.assertEqual(kimi.reported_ms, 1200.0)
        self.assertEqual(kimi.tokens_in, 100)
        self.assertEqual(kimi.tokens_out, 20)
        self.assertEqual(kimi.tokens_total, 120)
        self.assertEqual(kimi.cost, 0.0012)
        self.assertEqual(kimi.model, "kimi-code")
        self.assertEqual(kimi.exit_code, 0)

    def test_load_run_redacts_prompt_from_argv(self):
        _, _, results = E.load_run(self.run_dir)
        self.assertEqual(
            results[0].argv, ["kimi", "-p", "<prompt>", "--output-format", "stream-json"]
        )
        self.assertEqual(results[1].argv, ["codex", "exec", "<prompt>"])

    def test_load_run_preserves_nested_debate(self):
        _, _, results = E.load_run(self.run_dir)
        debate = results[0].debate
        self.assertIsNotNone(debate)
        self.assertEqual(debate.status, "ok")
        self.assertEqual(debate.text, "A short rebuttal.")
        self.assertEqual(debate.tokens_total, 30)

    def test_load_run_preserves_error_result_fields(self):
        _, _, results = E.load_run(self.run_dir)
        codex = results[1]
        self.assertEqual(codex.status, "error")
        self.assertIn("<script>", codex.error)
        self.assertIn("ensemble doctor", codex.hint)
        self.assertEqual(codex.exit_code, 1)
        # Raw stdout/stderr are intentionally not round-tripped through
        # results.json (they would bloat it); they live in sidecar artifacts.
        self.assertEqual(codex.stdout, "")
        self.assertEqual(codex.stderr, "")
        self.assertIn(
            "<b>unexpected</b>", (self.run_dir / "codex.stderr.txt").read_text()
        )

    def test_load_run_missing_run_raises(self):
        empty = Path(self._tmp.name) / "not-a-run"
        empty.mkdir()
        with self.assertRaises(FileNotFoundError):
            E.load_run(empty)


if __name__ == "__main__":
    unittest.main()
