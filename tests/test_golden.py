"""Golden files: v2's engine changes must not change Aaron's pages.

tests/golden/ holds frozen copies of both course files (as of 2026-10-08)
and exactly what they rendered to then: the student page and the
render() calendar. Refactors for v2 (PLAN-v2-phase1.md, M1) must
reproduce them byte for byte. The inputs are frozen copies, not
courses/*.json, so a weekly calendar edit never breaks this test.

If a change is meant to alter the page, regenerate on purpose and say so
in the commit:
    python3 tests/test_golden.py --regenerate
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402
import render  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"
SLUGS = ["math6", "math78"]


def outputs(course):
    calendar, leftover = engine.render(course)
    return {
        "page.html": render.build_page(course, calendar) + "\n",
        "calendar.json": json.dumps({"calendar": calendar, "leftover": leftover}, indent=1) + "\n",
    }


class GoldenTests(unittest.TestCase):
    def test_pages_and_calendars_unchanged(self):
        for slug in SLUGS:
            course = json.loads((GOLDEN / f"{slug}.json").read_text())
            for name, text in outputs(course).items():
                with self.subTest(slug=slug, file=name):
                    expected = (GOLDEN / f"{slug}.{name}").read_text()
                    self.assertTrue(text == expected,
                                    f"{slug}.{name} changed; regenerate only if that's intended")


def regenerate():
    for slug in SLUGS:
        course = json.loads((GOLDEN / f"{slug}.json").read_text())
        for name, text in outputs(course).items():
            (GOLDEN / f"{slug}.{name}").write_text(text)
            print(f"wrote tests/golden/{slug}.{name}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--regenerate"]:
        regenerate()
    else:
        unittest.main()
