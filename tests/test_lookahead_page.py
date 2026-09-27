"""Tests for scripts/lookahead_page.py (beach-math.com/teacher).

Run: python3 -m unittest discover -s tests
Read-only: nothing here writes to courses/*.json.
"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import build_site  # noqa: E402
import engine  # noqa: E402
import lookahead as la  # noqa: E402
import lookahead_page as lp  # noqa: E402

COURSES = [(p.stem, json.loads(p.read_text())) for p in sorted((ROOT / "courses").glob("*.json"))]
SLUG, COURSE = COURSES[0]
CALENDAR = engine.render(COURSE)[0]
FIRST = date.fromisoformat(CALENDAR[0]["date"])


class LookaheadPageTests(unittest.TestCase):
    def test_every_course_and_tab_present(self):
        page = lp.build_page(COURSES, today=FIRST)
        for slug, course in COURSES:
            self.assertIn(f'data-course="{slug}"', page)
            self.assertIn(f'data-show="{slug}"', page)

    def test_carries_every_day_from_build_date(self):
        page = lp.build_page([(SLUG, COURSE)], today=FIRST)
        for day in CALENDAR:
            self.assertIn(f'data-date="{day["date"]}"', page)

    def test_gap_flag_matches_missing_content(self):
        page = lp.build_page([(SLUG, COURSE)], today=FIRST)
        for day in CALENDAR:
            html = lp.render_day(day)
            self.assertEqual('data-gap="1"' in html, bool(la.missing_content(day)))
            self.assertIn(html, page)

    def test_not_indexed(self):
        self.assertIn('name="robots" content="noindex', lp.build_page(COURSES))

    def test_build_site_writes_teacher_page(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(build_site.main(["build_site.py", out]), 0)
            self.assertTrue((Path(out) / build_site.TEACHER_PATH / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
