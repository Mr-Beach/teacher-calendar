"""Tests for scripts/lookahead.py against the real course files.

Run: python3 -m unittest discover -s tests
Read-only: nothing here writes to courses/*.json.
"""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import engine  # noqa: E402
import lookahead as la  # noqa: E402

COURSE = json.loads((ROOT / "courses" / "math6.json").read_text())
CALENDAR = engine.render(COURSE)[0]
FIRST_DATE = CALENDAR[0]["date"]


class LookaheadTests(unittest.TestCase):
    def test_counts_only_instruction_days(self):
        window = la.lookahead(COURSE, FIRST_DATE, 10)
        self.assertEqual(sum(d["type"] == "Instruction" for d in window), 10)

    def test_window_starts_and_ends_on_instruction_days(self):
        # Pick a window that spans a non-instructional day, from the live data.
        dates = [d["date"] for d in CALENDAR]
        closed = next(i for i, d in enumerate(CALENDAR)
                      if i > 0 and d["type"] != "Instruction"
                      and CALENDAR[i - 1]["type"] == "Instruction")
        window = la.lookahead(COURSE, dates[closed], 5)
        self.assertEqual(window[0]["type"], "Instruction")
        self.assertEqual(window[-1]["type"], "Instruction")

    def test_matches_rendered_calendar(self):
        window = la.lookahead(COURSE, FIRST_DATE, 5)
        by_date = {d["date"]: d for d in CALENDAR}
        for day in window:
            self.assertEqual(day, by_date[day["date"]])

    def test_past_end_of_year_is_empty(self):
        self.assertEqual(la.lookahead(COURSE, "2099-01-01", 10), [])

    def test_quiz_and_test_days_never_need_content(self):
        for day in CALENDAR:
            if day["kind"] in ("Quiz", "Test"):
                self.assertEqual(la.missing_content(day), [])

    def test_lesson_days_need_a_link(self):
        day = next(d for d in CALENDAR if d["kind"] == "Lesson")
        self.assertIn("link", la.missing_content({**day, "link": None}))
        self.assertNotIn("link", la.missing_content({**day, "link": "https://example.com"}))

    def test_needs_lists_only_gap_days(self):
        window = la.lookahead(COURSE, FIRST_DATE, 20)
        lines = la.format_needs(COURSE, window)
        gaps = [d for d in window if la.missing_content(d)]
        self.assertEqual(len(lines), 1 + len(gaps))
        for day, line in zip(gaps, lines[1:]):
            self.assertIn(day["lesson_text"], line)

    def test_needs_with_no_gaps(self):
        window = [d for d in la.lookahead(COURSE, FIRST_DATE, 5) if not la.missing_content(d)]
        self.assertIn("every lesson day has its content", la.format_needs(COURSE, window)[0])

    def test_cli_prints_every_course(self):
        out = io.StringIO()
        with redirect_stdout(out):
            la.main(["--from", FIRST_DATE, "--days", "3"])
        for path in (ROOT / "courses").glob("*.json"):
            self.assertIn(json.loads(path.read_text())["course"], out.getvalue())


if __name__ == "__main__":
    unittest.main()
