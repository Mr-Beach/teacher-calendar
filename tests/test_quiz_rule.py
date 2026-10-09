"""Tests for the quiz rule as settings (engine.quiz_rule; SPEC-v2's
"Recurring activities"), on a small made-up course so each setting's
effect is easy to see. Aaron's own pages are covered by test_golden.py.

Run: python3 -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402
import render  # noqa: E402

START = date(2026, 9, 7)  # a Monday


def lesson(n, kind="Lesson", title=None):
    return {"topic": "1", "lesson_code": f"1.{n}", "district_title": title or f"Lesson {n}",
            "kind": kind, "homework": None, "link": None, "target": None,
            "classwork": None, "extra_materials": None}


def make_course(weeks=6, closed=(), test_at=None, **settings):
    """Mon-Fri school days for `weeks` weeks (dates in `closed` are No
    School), and enough lessons to fill them; lesson `test_at` (1-based) is
    a Test, with a review day just before it."""
    days = []
    for i in range(weeks * 7):
        d = START + timedelta(days=i)
        if d.weekday() < 5:
            days.append({"date": d.isoformat(), "weekday": d.strftime("%a"),
                         "type": "No School" if d.isoformat() in closed else "Instruction",
                         "note": None})
    seq = [lesson(n) for n in range(1, weeks * 5 + 1)]
    if test_at:
        seq[test_at - 2] = lesson(test_at - 1, title="Topic 1 Review")
        seq[test_at - 1] = lesson(test_at, kind="Test", title="Topic 1 Test")
    return {"course": "Test", "school_days": days, "sequence": seq, **settings}


def quiz_days(course):
    return [d["date"] for d in engine.render(course)[0] if d["kind"] == "Quiz"]


def weekdays_of(dates):
    return {date.fromisoformat(d).strftime("%a") for d in dates}


class QuizRuleTests(unittest.TestCase):
    def test_default_is_every_wednesday_full_period(self):
        course = make_course()
        self.assertEqual(len(quiz_days(course)), 6)
        self.assertEqual(weekdays_of(quiz_days(course)), {"Wed"})
        self.assertEqual(engine.render(course)[1], 6, "six quiz days push six lessons off the end")

    def test_weekday(self):
        course = make_course(quiz_rule={"weekday": "Thu"})
        self.assertEqual(weekdays_of(quiz_days(course)), {"Thu"})

    def test_every_other_week_counts_from_start(self):
        course = make_course(quiz_rule={"every_weeks": 2, "start": "2026-09-14"})
        self.assertEqual(quiz_days(course), ["2026-09-16", "2026-09-30", "2026-10-14"])

    def test_disabled_rule_leaves_only_forced_quiz_days(self):
        course = make_course(quiz_rule={"enabled": False}, test_at=8)
        self.assertEqual(quiz_days(course), [])
        self.assertEqual(engine.check_self_grading(course), [])
        engine.set_day(course, "2026-09-24", quiz="full")
        self.assertEqual(quiz_days(course), ["2026-09-24"])

    def test_shared_quiz_moves_nothing(self):
        course = make_course(quiz_rule={"sits": "shared"})
        calendar, leftover = engine.render(course)
        self.assertEqual(quiz_days(course), [])
        self.assertEqual(leftover, 0)
        paired = [d["date"] for d in calendar if d["quiz_paired"]]
        self.assertEqual(len(paired), 6)
        self.assertEqual(weekdays_of(paired), {"Wed"})

    def test_shared_self_grading_takes_the_shared_quiz_slot(self):
        # Lesson 8 is the Test: Wed 9/16 under a shared rule (nothing moves).
        course = make_course(quiz_rule={"sits": "shared"}, test_at=8)
        by_date = {d["date"]: d for d in engine.render(course)[0]}
        self.assertEqual(by_date["2026-09-16"]["kind"], "Test")
        self.assertFalse(by_date["2026-09-16"]["quiz_paired"], "no quiz in a test week")
        self.assertTrue(by_date["2026-09-23"]["self_grading_paired"])
        self.assertFalse(by_date["2026-09-23"]["quiz_paired"])
        self.assertEqual(engine.check_self_grading(course), [])

    def test_full_self_grading_day_and_its_weekday(self):
        course = make_course(quiz_rule={"weekday": "Thu"}, test_at=8)
        kinds = {d["date"]: d["kind"] for d in engine.render(course)[0]}
        test_date = next(d for d, k in kinds.items() if k == "Test")
        monday = date.fromisoformat(test_date) - timedelta(days=date.fromisoformat(test_date).weekday())
        self.assertEqual(kinds[(monday + timedelta(days=10)).isoformat()], "Self-Grading")

    def test_self_grading_off(self):
        course = make_course(quiz_rule={"self_grading": False}, test_at=8)
        self.assertNotIn("Self-Grading", [d["kind"] for d in engine.render(course)[0]])
        self.assertEqual(engine.check_self_grading(course), [])

    def test_skip_test_week_is_optional(self):
        with_skip = make_course(test_at=8, quiz_rule={"self_grading": False})
        without = make_course(test_at=8, quiz_rule={"skip": [], "self_grading": False})
        self.assertEqual(len(quiz_days(without)), len(quiz_days(with_skip)) + 1)

    def test_break_return_skip_follows_the_weekday(self):
        closed = {(date(2026, 9, 21) + timedelta(days=i)).isoformat() for i in range(5)}
        course = make_course(closed=closed, quiz_rule={"weekday": "Thu"})
        self.assertNotIn("2026-10-01", quiz_days(course))
        course["quiz_rule"]["skip"] = ["test_week"]
        self.assertIn("2026-10-01", quiz_days(course))

    def test_link_falls_back_to_v1_quiz_link(self):
        course = make_course(quiz_link="https://example.com/v1")
        self.assertEqual(engine.quiz_rule(course)["link"], "https://example.com/v1")
        course["quiz_rule"] = {"link": "https://example.com/v2"}
        quiz = next(d for d in engine.render(course)[0] if d["kind"] == "Quiz")
        self.assertEqual(quiz["link"], "https://example.com/v2")

    def test_bad_settings_are_refused(self):
        for bad in ({"weekday": "Sat"}, {"every_weeks": 3}, {"sits": "half"},
                    {"skip": ["full_moon"]}, {"colour": "red"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                engine.quiz_rule(make_course(quiz_rule=bad))


class OtherSettingsTests(unittest.TestCase):
    def test_review_before_test_can_be_turned_off(self):
        course = make_course(test_at=8)
        course["sequence"][6] = lesson(7)  # no review day before the test
        self.assertTrue(engine.check_review_before_test(course))
        course["review_before_test"] = False
        self.assertEqual(engine.check_review_before_test(course), [])

    def test_teacher_name_on_the_page(self):
        course = make_course(school_year="2026-27")
        page = render.build_page(course, engine.render(course)[0])
        self.assertIn("Mr. Beach · 2026-27", page)
        course["teacher"] = "Ms. Rivera"
        page = render.build_page(course, engine.render(course)[0])
        self.assertIn("Ms. Rivera · 2026-27", page)
        self.assertNotIn("Mr. Beach", page)


if __name__ == "__main__":
    unittest.main()
