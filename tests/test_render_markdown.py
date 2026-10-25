"""render_markdown(): structure rendering plus allowlist sanitisation.

The sanitisation tests encode the TARGET behaviour of the HTML sanitiser the
Lead landed in ensemble.py (commit "security: allowlist-sanitise model HTML
output"): model output is untrusted, so render_markdown() must never emit
``<script>``/``<iframe>``/``<style>``, event-handler attributes or
``javascript:`` URLs, while ordinary Markdown must keep rendering.
"""

import importlib.util
import unittest

import _support  # noqa: F401  (must be imported before ensemble: isolates HOME)
import ensemble as E

HAS_MARKDOWN = importlib.util.find_spec("markdown") is not None
needs_markdown = unittest.skipUnless(
    HAS_MARKDOWN,
    "python-markdown is not installed; render_markdown() falls back to escaped <pre>",
)


class SanitisationAssertions:
    """Shared assertions for output that must not contain active content."""

    def assert_no_active_content(self, rendered):
        lowered = rendered.lower()
        self.assertNotIn("<script", lowered)
        self.assertNotIn("<iframe", lowered)
        self.assertNotIn("<style", lowered)
        self.assertNotIn("onerror=", lowered)
        self.assertNotIn("onload=", lowered)
        self.assertNotIn("javascript:", lowered)


# --------------------------------------------------------------------------- #
# Ordinary Markdown must still render
# --------------------------------------------------------------------------- #


@needs_markdown
class RenderMarkdownStructureTest(unittest.TestCase):
    def test_renders_headings(self):
        rendered = E.render_markdown("# Title\n\n## Subtitle")
        self.assertIn("<h1>Title</h1>", rendered)
        self.assertIn("<h2>Subtitle</h2>", rendered)

    def test_renders_unordered_list(self):
        rendered = E.render_markdown("- alpha\n- beta")
        self.assertIn("<ul>", rendered)
        self.assertIn("<li>alpha</li>", rendered)
        self.assertIn("<li>beta</li>", rendered)

    def test_renders_ordered_list(self):
        rendered = E.render_markdown("1. first\n2. second")
        self.assertIn("<ol>", rendered)
        self.assertIn("<li>first</li>", rendered)
        self.assertIn("<li>second</li>", rendered)

    def test_renders_fenced_code_with_language_class(self):
        rendered = E.render_markdown("```python\nprint('hi')\n```")
        self.assertIn("<pre>", rendered)
        self.assertIn('<code class="language-python">', rendered)
        self.assertIn("print('hi')", rendered)

    def test_renders_table_and_wraps_it_for_scrolling(self):
        rendered = E.render_markdown("| A | B |\n|---|---|\n| 1 | 2 |")
        self.assertIn("<table>", rendered)
        self.assertIn("<th>A</th>", rendered)
        self.assertIn("<td>1</td>", rendered)
        self.assertIn('class="table-wrap"', rendered)
        self.assertIn("</table></div>", rendered)

    def test_renders_inline_formatting(self):
        rendered = E.render_markdown("**bold** and `code` and *italic*")
        self.assertIn("<strong>bold</strong>", rendered)
        self.assertIn("<code>code</code>", rendered)
        self.assertIn("<em>italic</em>", rendered)

    def test_renders_blockquote(self):
        rendered = E.render_markdown("> quoted text")
        self.assertIn("<blockquote>", rendered)
        self.assertIn("quoted text", rendered)

    def test_empty_text_renders_empty(self):
        self.assertEqual(E.render_markdown(""), "")

    def test_plain_paragraph_is_untouched(self):
        self.assertEqual(E.render_markdown("just words"), "<p>just words</p>")


# --------------------------------------------------------------------------- #
# Sanitisation
# --------------------------------------------------------------------------- #


class RenderMarkdownSanitisationTest(unittest.TestCase, SanitisationAssertions):
    def test_script_tag_and_its_content_are_dropped(self):
        rendered = E.render_markdown("Before <script>alert('xss')</script> after")
        self.assert_no_active_content(rendered)
        self.assertIn("Before", rendered)
        self.assertIn("after", rendered)
        self.assertNotIn("alert('xss')", rendered)

    def test_script_tag_with_attributes_is_dropped(self):
        rendered = E.render_markdown(
            '<script type="text/javascript" src="https://evil.example/x.js"></script>ok'
        )
        self.assert_no_active_content(rendered)
        self.assertIn("ok", rendered)
        self.assertNotIn("evil.example", rendered)

    def test_iframe_and_embed_subtrees_are_dropped(self):
        rendered = E.render_markdown(
            'see <iframe src="https://evil.example/embed">fallback</iframe> done'
        )
        self.assert_no_active_content(rendered)
        self.assertIn("see", rendered)
        self.assertIn("done", rendered)
        self.assertNotIn("evil.example", rendered)
        self.assertNotIn("fallback", rendered)

    def test_style_block_is_dropped(self):
        rendered = E.render_markdown("<style>body{display:none}</style>visible text")
        self.assert_no_active_content(rendered)
        self.assertIn("visible text", rendered)
        self.assertNotIn("display:none", rendered)

    def test_event_handler_attributes_are_dropped_from_images(self):
        rendered = E.render_markdown(
            '<img src="https://example.com/x.png" onerror="alert(1)" onload="alert(2)">'
        )
        self.assert_no_active_content(rendered)
        self.assertIn('src="https://example.com/x.png"', rendered)

    def test_event_handler_attributes_are_dropped_from_block_elements(self):
        rendered = E.render_markdown(
            '<div onclick="steal()" onmouseover="track()">hover text</div>'
        )
        lowered = rendered.lower()
        self.assertNotIn("onclick", lowered)
        self.assertNotIn("onmouseover", lowered)
        self.assertIn("hover text", rendered)

    def test_javascript_href_is_removed_from_markdown_link(self):
        rendered = E.render_markdown("[click me](javascript:alert(1))")
        self.assert_no_active_content(rendered)
        self.assertIn("click me", rendered)
        self.assertNotIn("href=", rendered)

    def test_javascript_href_is_removed_from_raw_anchor(self):
        rendered = E.render_markdown('<a href="javascript:alert(1)">tap</a>')
        self.assert_no_active_content(rendered)
        self.assertIn("tap", rendered)
        self.assertNotIn("href=", rendered)

    def test_javascript_scheme_is_case_insensitive(self):
        rendered = E.render_markdown('<a href="JaVaScRiPt:alert(1)">x</a>')
        self.assert_no_active_content(rendered)
        self.assertNotIn("href=", rendered)

    def test_entity_encoded_javascript_href_is_removed(self):
        rendered = E.render_markdown('<a href="&#106;avascript:alert(1)">x</a>')
        self.assert_no_active_content(rendered)
        self.assertNotIn("href=", rendered)

    def test_data_uri_href_is_removed(self):
        rendered = E.render_markdown(
            '[x](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)'
        )
        self.assert_no_active_content(rendered)
        self.assertNotIn("href=", rendered)

    def test_html_comments_are_dropped(self):
        rendered = E.render_markdown("<!-- <script>alert(1)</script> -->visible")
        self.assert_no_active_content(rendered)
        self.assertIn("visible", rendered)
        self.assertNotIn("<!--", rendered)

    def test_svg_subtree_is_dropped(self):
        rendered = E.render_markdown("a<svg><script>alert(1)</script></svg>b")
        self.assert_no_active_content(rendered)
        self.assertIn("ab", rendered)

    def test_raw_script_inside_fenced_code_stays_escaped_text(self):
        rendered = E.render_markdown("```\n<script>alert('code')</script>\n```")
        self.assert_no_active_content(rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_inline_code_keeps_angle_brackets_escaped(self):
        rendered = E.render_markdown("use `<script>` carefully")
        self.assert_no_active_content(rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_entity_encoded_script_source_does_not_become_a_tag(self):
        rendered = E.render_markdown("&lt;script&gt;alert('xss')&lt;/script&gt;")
        self.assertNotIn("<script", rendered.lower())
        self.assertIn("alert('xss')", rendered)

    @needs_markdown
    def test_safe_https_and_relative_links_survive(self):
        rendered = E.render_markdown(
            "[docs](https://example.com/docs) and [local](/runs/2026-01-01_000000_x)"
        )
        self.assertIn('href="https://example.com/docs"', rendered)
        self.assertIn('href="/runs/2026-01-01_000000_x"', rendered)

    @needs_markdown
    def test_safe_image_and_title_attributes_survive(self):
        rendered = E.render_markdown(
            '![alt text](https://example.com/pic.png "a title")'
        )
        self.assertIn('src="https://example.com/pic.png"', rendered)
        self.assertIn('alt="alt text"', rendered)
        self.assertIn('title="a title"', rendered)
        self.assert_no_active_content(rendered)


if __name__ == "__main__":
    unittest.main()
