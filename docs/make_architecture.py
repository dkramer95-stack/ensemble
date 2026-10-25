#!/usr/bin/env python3
"""Draw the system architecture used in the case study."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1800, 1000
NAVY = "#1b2b3f"
INK = "#26313f"
MUTED = "#637083"
LINE = "#c8d1dc"
CARD = "#ffffff"
SOFT = "#f3f6fa"
TEAL = "#2d6f8e"
AMBER = "#9a6a16"
PNG = Path(__file__).with_name("case-architecture.png")

FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, width: int):
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textbbox((0, 0), trial, font=fnt)[2] <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def box(draw, xy, title, lines, *, fill=CARD, outline=LINE, accent=None, dashed=False, radius=14):
    x0, y0, x1, y1 = xy
    if dashed:
        # A dashed border drawn as short segments around the rounded rectangle.
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill, outline=None)
        for start in range(x0 + radius, x1 - radius, 18):
            draw.line((start, y0, min(start + 10, x1 - radius), y0), fill=outline, width=2)
            draw.line((start, y1, min(start + 10, x1 - radius), y1), fill=outline, width=2)
        for start in range(y0 + radius, y1 - radius, 18):
            draw.line((x0, start, x0, min(start + 10, y1 - radius)), fill=outline, width=2)
            draw.line((x1, start, x1, min(start + 10, y1 - radius)), fill=outline, width=2)
    else:
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill, outline=outline, width=2)
    if accent:
        draw.rounded_rectangle((x0, y0, x1, y0 + 7), radius=3, fill=accent)
        draw.rectangle((x0, y0 + 4, x1, y0 + 7), fill=accent)
    y = y0 + (34 if accent else 22)
    draw.text((x0 + 22, y), title, font=font(24, True), fill=NAVY)
    y += 36
    for line in lines:
        for wrapped in wrap(draw, line, font(18), (x1 - x0) - 44):
            draw.text((x0 + 22, y), wrapped, font=font(18), fill=MUTED)
            y += 26
        y += 2
    return xy


def arrow(draw, points, *, color=NAVY, dashed=False, width=3, head=11):
    if dashed:
        for i in range(len(points) - 1):
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            steps = max(2, int(dist / 18))
            for s in range(steps):
                if s % 2:
                    continue
                a = s / steps
                b = min(1.0, (s + 1) / steps)
                draw.line((x0 + (x1 - x0) * a, y0 + (y1 - y0) * a,
                           x0 + (x1 - x0) * b, y0 + (y1 - y0) * b), fill=color, width=width)
    else:
        draw.line(points, fill=color, width=width, joint="curve")
    x0, y0 = points[-2]
    x1, y1 = points[-1]
    angle = __import__("math").atan2(y1 - y0, x1 - x0)
    left = (x1 - head * __import__("math").cos(angle - 0.45),
            y1 - head * __import__("math").sin(angle - 0.45))
    right = (x1 - head * __import__("math").cos(angle + 0.45),
             y1 - head * __import__("math").sin(angle + 0.45))
    draw.polygon([(x1, y1), left, right], fill=color)


def main():
    img = Image.new("RGB", (W, H), "#fbfcfe")
    draw = ImageDraw.Draw(img)

    draw.text((60, 34), "Heterogeneous multi-model debate system: execution and argument layers",
              font=font(27, True), fill=NAVY)
    draw.text((60, 72), "Solid path = core run. Dashed components = optional. Artifacts are the canonical interface between layers.",
              font=font(18), fill=MUTED)

    box(draw, (60, 140, 380, 250), "Prompt + context",
        ["one prompt, chosen isolation", "mode, timeout, model overrides"])
    box(draw, (60, 320, 380, 450), "Run orchestrator",
        ["parallel launch, process-group", "timeouts, per-provider state"])

    box(draw, (440, 120, 1220, 470), "Round 1 · independent execution",
        ["No model sees another model's answer before this round completes."],
        fill=SOFT, outline=NAVY)
    providers = [
        ((470, 205, 810, 320), "Kimi", ["kimi · kimi-code", "Moonshot auth"]),
        ((850, 205, 1190, 320), "Gemini", ["gemini · default", "API key / Vertex"]),
        ((470, 340, 810, 455), "DeepSeek", ["dsh --profile headless", "desktop account patch"]),
        ((850, 340, 1190, 455), "Codex", ["codex exec", "ChatGPT auth"]),
    ]
    for xy, title, lines in providers:
        box(draw, xy, title, lines, accent=TEAL)

    box(draw, (1280, 150, 1730, 390), "Canonical run store",
        ["results.json + per-model markdown", "raw stdout / stderr", "debate and challenge files", "meta.json: timings, tokens, errors"],
        fill=CARD, outline=NAVY)
    draw.text((1302, 398), "retains every raw response", font=font(16), fill=MUTED)
    box(draw, (1280, 440, 1730, 560), "Model judge · optional",
        ["compares initial answers,", "rebuttals, cross-examinations"], accent=AMBER, dashed=True)
    box(draw, (1280, 610, 1730, 780), "Report + local UI",
        ["HTML / Markdown report", "live panes, history, cross-examine", "same artifacts, different view"])

    box(draw, (440, 560, 1220, 900), "Argument layer · run after round 1",
        ["Every argument call receives the original prompt plus selected prior answers."],
        fill=SOFT, outline=NAVY)
    box(draw, (470, 650, 810, 850), "Directed challenge · primary",
        ["1 challenger → 1 target", "attack two claims, concede,", "state a verdict"], accent=TEAL)
    box(draw, (850, 650, 1190, 850), "Open debate · opt-in",
        ["each model sees every answer", "rebut, defend or revise,", "state position now"], accent=AMBER, dashed=True)

    # Core flow
    arrow(draw, [(380, 205), (440, 205)])
    arrow(draw, [(380, 385), (415, 385), (415, 300), (440, 300)])
    arrow(draw, [(1220, 250), (1280, 250)])
    arrow(draw, [(1250, 320), (1250, 700), (1220, 700)])
    arrow(draw, [(1510, 430), (1510, 440)], dashed=True)
    arrow(draw, [(1510, 560), (1510, 610)], dashed=True)
    arrow(draw, [(1220, 760), (1280, 690)])

    # small annotations

    draw.rounded_rectangle((60, 910, 380, 958), radius=8, fill="#eef2f7")
    draw.line((84, 934, 132, 934), fill=NAVY, width=3)
    draw.text((144, 924), "core", font=font(17), fill=NAVY)
    draw.line((230, 934, 278, 934), fill=AMBER, width=3)
    draw.text((290, 924), "optional / dashed", font=font(17), fill=AMBER)

    img.save(PNG, optimize=True)
    print(PNG)


if __name__ == "__main__":
    main()
