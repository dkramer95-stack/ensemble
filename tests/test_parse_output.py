"""parse_output() across kimi-jsonl, codex-jsonl, dsh-jsonl and text modes.

Fixtures mirror the shapes each CLI actually emits, including interleaved
malformed JSONL lines and stderr-only failures.  No provider CLI is executed.
"""

import unittest

import _support  # noqa: F401  (must be imported before ensemble: isolates HOME)
import ensemble as E

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

KIMI_OK = "\n".join(
    [
        '{"role":"assistant","content":"A CRDT is a data structure that "}',
        '{"role":"tool","content":"tool output that must be ignored"}',
        '{"role":"user","content":"ignored user echo"}',
        '{"role":"assistant","content":[{"type":"output_text","text":"merges without coordination."}]}',
        '{"role":"assistant","content":[{"type":"thinking","text":"ignored reasoning"},'
        '{"type":"text","text":" Done."}]}',
    ]
)

KIMI_MALFORMED = "\n".join(
    [
        '{"role":"assistant","content":"first chunk"}',
        "this is not json at all",
        '{"role":"assistant","content":',
        "",
        "   ",
        '{"role":"assistant","content":[{"type":"text","text":" second chunk"}]}',
    ]
)

CODEX_OK = "\n".join(
    [
        '{"type":"thread.started","thread_id":"0199a7e0-aaaa-bbbb"}',
        '{"type":"item.completed","item":{"id":"item_1","type":"reasoning","text":"thinking..."}}',
        '{"type":"item.completed","item":{"id":"item_2","type":"agent_message",'
        '"text":"SQLite is the better fit for a small analytics product."}}',
        '{"type":"turn.completed","usage":{"input_tokens":1234,"output_tokens":321,'
        '"cached_input_tokens":900}}',
    ]
)

CODEX_MULTI_MESSAGE = "\n".join(
    [
        '{"type":"item.completed","item":{"type":"agent_message","text":"first draft"}}',
        '{"type":"item.completed","item":{"type":"agent_message","text":"final answer"}}',
    ]
)

CODEX_MALFORMED = "\n".join(
    [
        '{"type":"item.completed","item":{"type":"agent_message","text":"answer survives"}}',
        '{"type":"turn.completed","usage":',
        "{garbage}",
        "",
        '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
    ]
)

DSH_OK = "\n".join(
    [
        "[llm-deepseek-account] using desktop account",
        '{"type":"status","phase":"step_start"}',
        '{"type":"text","text":"Hel"}',
        '{"type":"text","text":"lo"}',
        '{"type":"status","phase":"step_end","usage":{"inputTokens":42,"outputTokens":7,'
        '"totalTokens":49}}',
        '{"type":"final","text":"Hello from DeepSeek"}',
    ]
)

DSH_CHUNKS_ONLY = "\n".join(
    [
        "[llm-deepseek-account] diagnostics line",
        '{"type":"text","text":"Hello "}',
        '{"type":"text","text":"world"}',
    ]
)

DSH_MALFORMED = "\n".join(
    [
        '{"type":"text","text":"still here"}',
        '{"type":"text"',
        "not json",
        "   ",
    ]
)


# --------------------------------------------------------------------------- #
# kimi-jsonl
# --------------------------------------------------------------------------- #


class ParseKimiJsonlTest(unittest.TestCase):
    def test_concatenates_assistant_text_blocks(self):
        text, error, meta = E.parse_output("kimi-jsonl", KIMI_OK, "")
        self.assertEqual(text, "A CRDT is a data structure that merges without coordination. Done.")
        self.assertEqual(error, "")
        self.assertEqual(meta, {})

    def test_ignores_non_assistant_roles_and_thinking_blocks(self):
        text, _, _ = E.parse_output("kimi-jsonl", KIMI_OK, "")
        self.assertNotIn("tool output", text)
        self.assertNotIn("ignored user echo", text)
        self.assertNotIn("ignored reasoning", text)

    def test_concatenates_plain_string_content_blocks(self):
        stdout = "\n".join(
            [
                '{"role":"assistant","content":["plain block one ", "plain block two"]}',
            ]
        )
        text, error, _ = E.parse_output("kimi-jsonl", stdout, "")
        self.assertEqual(text, "plain block one plain block two")
        self.assertEqual(error, "")

    def test_ignores_malformed_jsonl_lines(self):
        text, error, _ = E.parse_output("kimi-jsonl", KIMI_MALFORMED, "")
        self.assertEqual(text, "first chunk second chunk")
        self.assertEqual(error, "")

    def test_stderr_only_failure_returns_error(self):
        text, error, _ = E.parse_output("kimi-jsonl", "", "kimi: authentication failed\n")
        self.assertEqual(text, "")
        self.assertEqual(error, "kimi: authentication failed")

    def test_no_assistant_message_without_stderr_reports_reason(self):
        text, error, _ = E.parse_output("kimi-jsonl", '{"role":"user","content":"hi"}\n', "")
        self.assertEqual(text, "")
        self.assertIn("no assistant message", error)

    def test_empty_output_returns_empty_result(self):
        self.assertEqual(E.parse_output("kimi-jsonl", "", ""), ("", "", {}))

    def test_stderr_is_ignored_when_text_arrives(self):
        text, error, _ = E.parse_output("kimi-jsonl", KIMI_OK, "warning: retrying request\n")
        self.assertIn("A CRDT is a data structure", text)
        self.assertEqual(error, "")


# --------------------------------------------------------------------------- #
# codex-jsonl
# --------------------------------------------------------------------------- #


class ParseCodexJsonlTest(unittest.TestCase):
    def test_last_agent_message_wins(self):
        text, error, _ = E.parse_output("codex-jsonl", CODEX_OK, "")
        self.assertEqual(text, "SQLite is the better fit for a small analytics product.")
        self.assertEqual(error, "")

    def test_later_agent_message_overrides_earlier_draft(self):
        text, _, _ = E.parse_output("codex-jsonl", CODEX_MULTI_MESSAGE, "")
        self.assertEqual(text, "final answer")

    def test_usage_metadata_from_turn_completed(self):
        _, _, meta = E.parse_output("codex-jsonl", CODEX_OK, "")
        self.assertEqual(meta["tokens_in"], 1234)
        self.assertEqual(meta["tokens_out"], 321)
        self.assertEqual(meta["tokens_total"], 1555)
        self.assertEqual(meta["tokens_cached"], 900)

    def test_cached_tokens_omitted_when_zero(self):
        stdout = '{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}\n'
        _, _, meta = E.parse_output("codex-jsonl", stdout, "")
        self.assertNotIn("tokens_cached", meta)
        self.assertEqual(meta["tokens_total"], 10)

    def test_error_event_becomes_error(self):
        stdout = '{"type":"turn.failed","message":"rate limited: 429"}\n'
        text, error, _ = E.parse_output("codex-jsonl", stdout, "")
        self.assertEqual(text, "")
        self.assertEqual(error, "rate limited: 429")

    def test_plain_text_stdout_falls_back_to_text(self):
        text, error, _ = E.parse_output("codex-jsonl", "Plain codex final answer\n", "")
        self.assertEqual(text, "Plain codex final answer")
        self.assertEqual(error, "")

    def test_stderr_only_failure_returns_error(self):
        text, error, _ = E.parse_output("codex-jsonl", "", "codex: command not found\n")
        self.assertEqual(text, "")
        self.assertEqual(error, "codex: command not found")

    def test_silent_failure_has_default_message(self):
        text, error, _ = E.parse_output("codex-jsonl", "", "")
        self.assertEqual(text, "")
        self.assertEqual(error, "Codex returned no final message")

    def test_ignores_malformed_jsonl_lines(self):
        text, error, _ = E.parse_output("codex-jsonl", CODEX_MALFORMED, "")
        self.assertEqual(text, "answer survives")
        self.assertEqual(error, "")
        _, _, meta = E.parse_output("codex-jsonl", CODEX_MALFORMED, "")
        self.assertEqual(meta["tokens_in"], 10)
        self.assertEqual(meta["tokens_out"], 5)


# --------------------------------------------------------------------------- #
# dsh-jsonl
# --------------------------------------------------------------------------- #


class ParseDshJsonlTest(unittest.TestCase):
    def test_final_message_wins_over_streamed_chunks(self):
        text, error, _ = E.parse_output("dsh-jsonl", DSH_OK, "")
        self.assertEqual(text, "Hello from DeepSeek")
        self.assertEqual(error, "")

    def test_streamed_text_chunks_concatenate_without_final(self):
        text, error, _ = E.parse_output("dsh-jsonl", DSH_CHUNKS_ONLY, "")
        self.assertEqual(text, "Hello world")
        self.assertEqual(error, "")

    def test_usage_metadata_from_step_end(self):
        _, _, meta = E.parse_output("dsh-jsonl", DSH_OK, "")
        self.assertEqual(meta["tokens_in"], 42)
        self.assertEqual(meta["tokens_out"], 7)
        self.assertEqual(meta["tokens_total"], 49)

    def test_ignores_diagnostic_lines_and_malformed_json(self):
        text, error, _ = E.parse_output("dsh-jsonl", DSH_MALFORMED, "")
        self.assertEqual(text, "still here")
        self.assertEqual(error, "")

    def test_error_event_becomes_error(self):
        stdout = '{"type":"error","message":"403 forbidden: no credentials"}\n'
        text, error, _ = E.parse_output("dsh-jsonl", stdout, "")
        self.assertEqual(text, "")
        self.assertEqual(error, "403 forbidden: no credentials")

    def test_stderr_only_failure_returns_error(self):
        text, error, _ = E.parse_output("dsh-jsonl", "", "dsh: no credentials available\n")
        self.assertEqual(text, "")
        self.assertEqual(error, "dsh: no credentials available")

    def test_empty_output_returns_empty_result(self):
        self.assertEqual(E.parse_output("dsh-jsonl", "", ""), ("", "", {}))


# --------------------------------------------------------------------------- #
# text mode
# --------------------------------------------------------------------------- #


class ParseTextTest(unittest.TestCase):
    def test_returns_trimmed_stdout(self):
        self.assertEqual(E.parse_output("text", "  plain answer  \n\n", ""), ("plain answer", "", {}))

    def test_preserves_internal_newlines(self):
        text, _, _ = E.parse_output("text", "line one\nline two\n", "")
        self.assertEqual(text, "line one\nline two")

    def test_stderr_only_failure_returns_error(self):
        text, error, _ = E.parse_output("text", "   \n", "gemini: model not found\n")
        self.assertEqual(text, "")
        self.assertEqual(error, "gemini: model not found")

    def test_empty_output_returns_empty_result(self):
        self.assertEqual(E.parse_output("text", "", ""), ("", "", {}))

    def test_unknown_parse_mode_is_treated_as_text(self):
        # The text branch is the fallback for any non-JSONL value.
        self.assertEqual(E.parse_output("some-future-mode", "hello\n", ""), ("hello", "", {}))


if __name__ == "__main__":
    unittest.main()
