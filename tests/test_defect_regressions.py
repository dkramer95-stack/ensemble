"""Regression tests for defects found during the improvement pass.

Each test below reproduced a real bug at the time it was written. They are
kept so the same mistakes cannot come back.
"""

import re
import unittest

import _support  # noqa: F401  (must be imported before ensemble: isolates HOME)
import ensemble as E


class DefectRegressionsTest(unittest.TestCase):
    def test_url_scheme_with_embedded_newline_is_rejected(self):
        # Browsers strip tab/CR/LF while parsing a URL, so an href of
        # "java\nscript:..." becomes a live javascript: URL once normalised.
        rendered = E.render_markdown(
            '<a href="java&#10;script:alert(document.domain)">click</a>'
        )
        match = re.search(r'href="([^"]*)"', rendered)
        if match is not None:
            href = re.sub(r"[\t\n\r]", "", match.group(1)).strip().lower()
            self.assertFalse(
                href.startswith("javascript:"),
                f"href normalises to executable URL: {match.group(1)!r} -> {href!r}",
            )

    def test_non_object_jsonl_lines_do_not_crash_parse_output(self):
        # "null" parses as JSON but is not a dict.
        text, error, meta = E.parse_output("kimi-jsonl", "null\n", "")
        self.assertEqual(text, "")
        self.assertIn("no assistant message", error)
        self.assertEqual(meta, {})

    def test_config_with_null_defaults_does_not_crash_provider_settings(self):
        # A config file with "defaults": null used to raise AttributeError.
        settings = E.provider_settings({"defaults": None, "providers": {}})
        self.assertEqual(settings["kimi"]["label"], "Kimi")


if __name__ == "__main__":
    unittest.main()
