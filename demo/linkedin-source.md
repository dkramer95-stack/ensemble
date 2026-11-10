# LinkedIn source — ensemble demo

Three quotable lines from the run behind the demo page. All quotes are verbatim
substrings of what the models returned; only markdown emphasis markers were
stripped. Curly apostrophes, curly quotes and em dashes are preserved.

Run: 10 November 2026 · four providers queried · Kimi and Codex answered ·
DeepSeek (profile boot error) and Gemini (API HTTP 402) returned nothing ·
a Kimi judge synthesised the survivors in 34.7 s · 47.9 s end to end.

---

## 1. Kimi — why auditability settles it

> Publishing the code and review memos makes the group’s conclusions auditable and reproducible: outsiders can inspect assumptions, verify calculations, spot errors, and see how evidence shaped recommendations.

— **Kimi** (`kimi-code`), answer to the prompt, 13.2 s.

## 2. Codex — scrutiny instead of reputation

> Publishing both exposes errors and unsupported assumptions that a ten-person team may miss—and makes its conclusions credible because they withstand scrutiny, rather than because readers trust its reputation.

— **Codex** (model id not reported by the CLI), answer to the prompt, 10.4 s.

## 3. Kimi as judge — the verdict

> Codex is strongest by a narrow margin.

— **Kimi** (`kimi-code`), judge synthesis, first line of “Bottom line”, 34.7 s.

---

### Context for the post

The prompt, verbatim:

> Should a ten-person independent policy research group publish its internal analysis code and review memos as open source? Answer yes or no, then give the single strongest reason. Under 120 words.

Both answers finished under the 120-word limit (Kimi 55 words, Codex 51 words).
The judge called the two answers “near-identical substantively” and noted that
neither addresses costs, security risks, or chilling effects on candid internal
reviews.

The run is useful for the failure angle too: the judge wrote that “Gemini and
DeepSeek produced no assessable answers” and that no substantive weight should
be given to those failures — the report was still produced.
