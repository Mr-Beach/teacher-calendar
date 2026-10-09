"""Every color preset (render.THEMES) must stay readable: the text and
fill pairs the page actually uses meet WCAG contrast -- 4.5:1 for text,
3:1 for the focus outline and borders a student needs to see.

Run: python3 -m unittest discover -s tests
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402
import render  # noqa: E402

# The page's own :root (the "teal" preset) -- read from PAGE, so this test
# follows the page if a base color changes.
BASE = dict(re.findall(r"(--[a-z-]+): (#[0-9A-Fa-f]{6});", render.PAGE.split("}%%THEME%%")[0]))

# (foreground, background, minimum): pairs the page puts together.
PAIRS = [
    ("--ink", "--bg", 4.5), ("--ink", "--card", 4.5), ("--muted", "--card", 4.5),
    ("--muted", "--bg", 4.5), ("--on-ink", "--ink", 4.5), ("--on-ink", "--accent", 4.5),
    ("--ink", "--today", 4.5), ("--ink", "--soon", 4.5), ("--ink", "--soft", 4.5),
    ("--closed-ink", "--closed-bg", 4.5), ("--quiz-ink", "--quiz-bg", 4.5),
    ("--test-ink", "--test-bg", 4.5), ("--ink", "--quiz-bg", 4.5), ("--ink", "--test-bg", 4.5),
    ("--accent", "--bg", 3.0), ("--accent", "--card", 3.0), ("--dashed", "--card", 3.0),
]


def luminance(hex_color):
    def channel(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(hex_color[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class ThemeTests(unittest.TestCase):
    def test_every_preset_is_readable(self):
        for name, overrides in render.THEMES.items():
            colors = {**BASE, **overrides}
            for fg, bg, minimum in PAIRS:
                with self.subTest(theme=name, pair=(fg, bg)):
                    ratio = contrast(colors[fg], colors[bg])
                    self.assertGreaterEqual(ratio, minimum, f"{name}: {fg} on {bg} is {ratio:.2f}:1")

    def test_presets_only_change_known_colors(self):
        for name, overrides in render.THEMES.items():
            self.assertLessEqual(set(overrides), set(BASE), name)
            for meaning in ("--quiz-bg", "--quiz-ink", "--test-bg", "--test-ink",
                            "--today", "--soon", "--on-ink"):
                self.assertNotIn(meaning, overrides, f"{name} changes {meaning}")

    def test_theme_on_the_page(self):
        course = {"course": "Test", "school_days": [], "sequence": []}
        page = render.build_page(course, [])
        self.assertNotIn("%%THEME%%", page)
        course["theme"] = "forest"
        self.assertIn("--ink: #1E3324;", render.build_page(course, []))
        course["theme"] = "neon"
        with self.assertRaises(ValueError):
            render.build_page(course, [])


if __name__ == "__main__":
    unittest.main()
