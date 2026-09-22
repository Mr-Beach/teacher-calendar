"""Tests for scripts/apply_week.py against the real course file.

Run: python3 -m unittest discover -s tests
Each test works on an in-memory copy (or a temp copy of the repo for the
CLI test), so courses/math6.json is never modified.
"""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import engine  # noqa: E402
import apply_week as aw  # noqa: E402

COURSE = json.loads((ROOT / "courses" / "math6.json").read_text())


def lesson_on(course, date):
    return aw._placements_by_date(course)[date][2]


class ApplyWeekTests(unittest.TestCase):
    def setUp(self):
        self.course = copy.deepcopy(COURSE)
        cal = engine.render(self.course)[0]
        # Pick dates from the live data rather than hard-coding them, so the
        # tests keep working as the calendar moves on.
        coded = [d for d in cal if d["kind"] == "Lesson" and d["lesson_text"][:1].isdigit()]
        pairs = [(a, b) for a, b in zip(coded, coded[1:]) if a["lesson_text"] == b["lesson_text"]]
        self.day1, self.day2 = pairs[0]
        self.code = self.day1["lesson_text"].split()[0]
        self.quiz = next(d for d in cal if d["kind"] == "Quiz")
        self.closed = next(d for d in cal if d["type"] == "No School")

    def plan_apply(self, days):
        edits = aw.plan_changes(self.course, {"days": days})
        aw.apply_changes(self.course, edits)
        return edits

    def test_content_edit_lands_on_the_right_one_of_two_same_code_days(self):
        before = engine.render(self.course)
        self.plan_apply([{
            "date": self.day2["date"], "expect": self.code,
            "target": "I can do the thing.", "classwork": "Workbook p. 1",
            "homework": ["p. 2, due Fri", "(continued) p. 1"], "link": "https://example.org/x",
        }])
        self.assertEqual(lesson_on(self.course, self.day2["date"])["target"], "I can do the thing.")
        self.assertEqual(lesson_on(self.course, self.day2["date"])["homework"],
                         ["p. 2, due Fri", "(continued) p. 1"])
        self.assertEqual(lesson_on(self.course, self.day1["date"]),
                         lesson_on(COURSE, self.day1["date"]),
                         "Day 1 of the same lesson must be untouched")
        impact = engine.diff_impact(self.course, *before)
        self.assertIsNone(impact["first_shifted_date"])
        self.assertEqual(impact["leftover_before"], impact["leftover_after"])

    def test_note_on_a_lesson_day_is_not_a_reflow(self):
        before = engine.render(self.course)
        self.plan_apply([{"date": self.day1["date"], "note": "Bring a calculator."}])
        impact = aw.placement_impact(self.course, *before)
        self.assertIsNone(impact["first_shifted_date"])

    def test_only_the_edited_entry_changes(self):
        self.plan_apply([{"date": self.day1["date"], "expect": self.code, "target": "X"}])
        changed = [i for i, (a, b) in enumerate(zip(COURSE["sequence"], self.course["sequence"])) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertEqual(COURSE["school_days"], self.course["school_days"])

    def test_title_substring_works_as_expect(self):
        title = self.day1["lesson_text"].split(" ", 1)[1]
        self.plan_apply([{"date": self.day1["date"], "expect": title.lower()[:12], "target": "Y"}])
        self.assertEqual(lesson_on(self.course, self.day1["date"])["target"], "Y")

    def test_code_expect_is_exact(self):
        item = {"lesson_code": "1.10", "district_title": "Something"}
        self.assertFalse(aw._matches("1.1", item))
        self.assertTrue(aw._matches("1.10", item))
        self.assertTrue(aw._matches("something", item))

    def test_mismatched_expect_rejects_and_changes_nothing(self):
        snapshot = copy.deepcopy(self.course)
        with self.assertRaises(aw.WeekError) as cm:
            aw.plan_changes(self.course, {"days": [
                {"date": self.day1["date"], "expect": "9.9", "target": "Z"}]})
        self.assertIn("shifted", str(cm.exception))
        self.assertEqual(snapshot, self.course)

    def test_missing_expect_rejected_for_lesson_edits(self):
        with self.assertRaises(aw.WeekError):
            aw.plan_changes(self.course, {"days": [{"date": self.day1["date"], "target": "Z"}]})

    def test_quiz_day_takes_a_note_but_not_lesson_content(self):
        with self.assertRaises(aw.WeekError) as cm:
            aw.plan_changes(self.course, {"days": [
                {"date": self.quiz["date"], "expect": "Quiz", "homework": ["x"]}]})
        self.assertIn("quiz", str(cm.exception))
        self.plan_apply([{"date": self.quiz["date"], "note": "Quiz covers 1.1-1.2."}])
        day = next(d for d in self.course["school_days"] if d["date"] == self.quiz["date"])
        self.assertEqual(day["note"], "Quiz covers 1.1-1.2.")

    def test_closed_day_rejects_lesson_content(self):
        with self.assertRaises(aw.WeekError):
            aw.plan_changes(self.course, {"days": [
                {"date": self.closed["date"], "expect": "x", "target": "nope"}]})

    def test_structural_fields_rejected(self):
        with self.assertRaises(aw.WeekError) as cm:
            aw.plan_changes(self.course, {"days": [
                {"date": self.day1["date"], "type": "Other", "note": "Assembly"}]})
        self.assertIn("Claude Code", str(cm.exception))

    def test_empty_homework_becomes_null_and_null_clears(self):
        self.plan_apply([{"date": self.day1["date"], "expect": self.code, "homework": ["a"]}])
        self.plan_apply([{"date": self.day1["date"], "expect": self.code, "homework": []}])
        self.assertIsNone(lesson_on(self.course, self.day1["date"])["homework"])

    def test_reapplying_is_a_no_op(self):
        week = [{"date": self.day1["date"], "expect": self.code, "target": "T", "note": "N"}]
        self.assertEqual(len(self.plan_apply(week)), 2)
        self.assertEqual(self.plan_apply(week), [])

    def test_every_problem_reported_at_once(self):
        with self.assertRaises(aw.WeekError) as cm:
            aw.plan_changes(self.course, {"days": [
                {"date": "1999-01-01", "note": "x"},
                {"date": self.day1["date"], "expect": "9.9", "target": "x"},
                {"date": self.day2["date"], "expect": self.code, "homework": "not a list"},
            ]})
        self.assertEqual(str(cm.exception).count("\n- ") + 1, 3)

    def test_cli_writes_file_in_existing_style_and_dry_run_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            week = repo / "inbox" / "test.json"
            week.parent.mkdir(exist_ok=True)
            week.write_text(json.dumps({"course": "math6", "week_of": "test", "days": [
                {"date": self.day1["date"], "expect": self.code, "classwork": "Workbook p. 5 – 6"}]}))
            course_file = repo / "courses" / "math6.json"
            original = course_file.read_text()
            run = lambda *a: subprocess.run([sys.executable, "scripts/apply_week.py", *a],
                                            cwd=repo, capture_output=True, text=True)
            r = run(str(week), "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(course_file.read_text(), original)
            r = run(str(week), "--summary", str(repo / "s.md"))
            self.assertEqual(r.returncode, 0, r.stderr)
            new = course_file.read_text()
            self.assertIn("\\u2013", new, "non-ASCII must stay escaped like the rest of the file")
            diff = [l for l in zip(original.splitlines(), new.splitlines()) if l[0] != l[1]]
            self.assertEqual(len(diff), 1, "exactly one line should change")
            self.assertIn("No dates moved", (repo / "s.md").read_text())
            bad = repo / "inbox" / "bad.json"
            bad.write_text(json.dumps({"days": [{"date": self.day1["date"], "expect": "9.9", "target": "x"}]}))
            r = run(str(bad))
            self.assertEqual(r.returncode, 1)
            self.assertEqual(course_file.read_text(), new)


if __name__ == "__main__":
    unittest.main()
