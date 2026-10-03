"""Tests for engine.py's placement rules (PLANNING.md), on small made-up
courses rather than the real ones -- so each rule is pinned down on its own,
whatever this year's calendar happens to look like.

Run: python3 -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402


def make_course(start, end, lessons=40, closed=(), **extra):
    """Every weekday from `start` to `end` (ISO) is Instruction, except the
    dates in `closed` (No School). `lessons` is a count of plain lessons or
    a list of (title, kind) pairs."""
    days, d = [], date.fromisoformat(start)
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            iso = d.isoformat()
            days.append({"date": iso, "weekday": d.strftime("%a"),
                         "type": "No School" if iso in closed else "Instruction",
                         "note": None})
        d += timedelta(days=1)
    if isinstance(lessons, int):
        lessons = [(f"Lesson {i + 1}", "Lesson") for i in range(lessons)]
    course = {"course": "Test", "school_days": days, "sequence": []}
    for title, kind in lessons:
        engine.insert_lesson(course, len(course["sequence"]), {"district_title": title, "kind": kind})
    course.update(extra)
    return course


def by_date(course):
    return {d["date"]: d for d in engine.render(course)[0]}


def quiz_dates(course):
    return [d["date"] for d in engine.render(course)[0] if d["kind"] == "Quiz"]


class QuizRuleTests(unittest.TestCase):
    def test_quiz_every_wednesday(self):
        course = make_course("2026-10-05", "2026-10-30")
        self.assertEqual(quiz_dates(course),
                         ["2026-10-07", "2026-10-14", "2026-10-21", "2026-10-28"])

    def test_quiz_rhythm_start(self):
        course = make_course("2026-10-05", "2026-10-30", quiz_rhythm_start="2026-10-15")
        self.assertEqual(quiz_dates(course), ["2026-10-21", "2026-10-28"])

    def test_quiz_doesnt_use_up_a_lesson(self):
        course = make_course("2026-10-05", "2026-10-09", lessons=4)
        cal = engine.render(course)[0]
        self.assertEqual([d["lesson_text"] for d in cal],
                         ["Lesson 1", "Lesson 2", "Quiz", "Lesson 3", "Lesson 4"])

    def test_no_quiz_in_a_test_week(self):
        # Mon-Tue lessons, Wed would be a quiz, Thu review, Fri test.
        lessons = [("A", "Lesson"), ("B", "Lesson"), ("C", "Lesson"),
                   ("Topic 1 Review", "Lesson"), ("Topic 1 Test", "Test")] + [("D", "Lesson")] * 10
        course = make_course("2026-10-05", "2026-10-16", lessons=lessons)
        days = by_date(course)
        self.assertNotEqual(days["2026-10-07"]["kind"], "Quiz")
        self.assertEqual(days["2026-10-14"]["kind"], "Quiz")

    def test_test_week_found_after_quizzes_shift_it(self):
        # Without a quiz on 10/7 the Test would land in week one; with it,
        # the Test slides to Monday of week two -- the fixed point must agree.
        lessons = [("A", "Lesson")] * 4 + [("Topic 1 Test", "Test")] + [("B", "Lesson")] * 10
        course = make_course("2026-10-05", "2026-10-16", lessons=lessons)
        days = by_date(course)
        test_day = next(d for d, v in days.items() if v["kind"] == "Test")
        test_week = date.fromisoformat(test_day) - timedelta(days=date.fromisoformat(test_day).weekday())
        for q in quiz_dates(course):
            qd = date.fromisoformat(q)
            self.assertNotEqual(qd - timedelta(days=qd.weekday()), test_week)

    def test_no_quiz_first_week_back_from_a_long_break(self):
        brk = [f"2026-12-{d}" for d in (21, 22, 23, 24, 25, 28, 29, 30, 31)] + ["2027-01-01"]
        course = make_course("2026-12-14", "2027-01-15", closed=brk)
        quizzes = quiz_dates(course)
        self.assertIn("2026-12-16", quizzes)
        self.assertNotIn("2027-01-06", quizzes)
        self.assertIn("2027-01-13", quizzes)

    def test_short_closure_keeps_the_quiz(self):
        course = make_course("2026-10-05", "2026-10-16", closed={"2026-10-12"})
        self.assertIn("2026-10-14", quiz_dates(course))

    def test_no_quiz_day_before_thanksgiving(self):
        course = make_course("2026-11-16", "2026-11-25")
        self.assertEqual(quiz_dates(course), ["2026-11-18"])
        self.assertEqual(engine._day_before_thanksgiving(2026), "2026-11-25")
        self.assertEqual(engine._day_before_thanksgiving(2027), "2027-11-24")
        self.assertEqual(engine._day_before_thanksgiving(2029), "2029-11-21")

    def test_losing_a_day_shifts_lessons_but_not_quizzes(self):
        course = make_course("2026-10-05", "2026-10-16")
        before = by_date(course)
        engine.set_day(course, "2026-10-06", type="Other", note="Assembly")
        after = by_date(course)
        self.assertEqual(after["2026-10-08"]["lesson_text"], before["2026-10-06"]["lesson_text"])
        self.assertEqual(quiz_dates(course), ["2026-10-07", "2026-10-14"])

    def test_quiz_cannot_be_stored(self):
        course = make_course("2026-10-05", "2026-10-09")
        with self.assertRaises(ValueError):
            engine.insert_lesson(course, 0, {"district_title": "Quiz", "kind": "Quiz"})


class CheckTests(unittest.TestCase):
    def test_leftover_lessons(self):
        course = make_course("2026-10-05", "2026-10-09", lessons=6)
        self.assertEqual(engine.render(course)[1], 2)
        [warning] = engine.check_leftover_lessons(course)
        self.assertIn("Lesson 5, Lesson 6", warning)
        self.assertEqual(engine.check_leftover_lessons(make_course("2026-10-05", "2026-10-09", lessons=4)), [])

    def test_review_before_test(self):
        ok = [("A", "Lesson"), ("Topic 1 Review", "Lesson"), ("Topic 1 Test", "Test")]
        self.assertEqual(engine.check_review_before_test(make_course("2026-10-05", "2026-10-09", lessons=ok)), [])
        missing = [("A", "Lesson"), ("B", "Lesson"), ("Topic 1 Test", "Test")]
        [warning] = engine.check_review_before_test(make_course("2026-10-05", "2026-10-09", lessons=missing))
        self.assertIn("'B'", warning)

    def test_closed_day_between_review_and_test_is_fine(self):
        lessons = [("A", "Lesson"), ("B", "Lesson"), ("Topic 1 Review", "Lesson"), ("Topic 1 Test", "Test")]
        course = make_course("2026-10-05", "2026-10-09", lessons=lessons, closed={"2026-10-08"},
                             quiz_rhythm_start="2026-11-01")
        self.assertEqual(by_date(course)["2026-10-09"]["kind"], "Test")
        self.assertEqual(engine.check_review_before_test(course), [])

    def test_monday_test_flagged(self):
        lessons = [("A", "Lesson")] * 3 + [("Topic 1 Review", "Lesson"), ("Topic 1 Test", "Test")]
        course = make_course("2026-10-06", "2026-10-12", lessons=lessons, quiz_rhythm_start="2026-11-01")
        self.assertEqual(by_date(course)["2026-10-12"]["kind"], "Test")
        [warning] = engine.check_test_placement(course)
        self.assertIn("Monday", warning)

    def test_run_all_checks_clean_course(self):
        course = make_course("2026-10-05", "2026-10-09", lessons=4)
        self.assertEqual([w for _, ws in engine.run_all_checks(course) for w in ws], [])


if __name__ == "__main__":
    unittest.main()
