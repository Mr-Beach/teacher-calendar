"""Tests for v2's edit operations (PLAN-v2-phase1.md, M6): ops.py, on a
calendar copied from Math 6 the way a new teacher's is.

Run: python3 -m unittest discover -s v2/tests
"""
import copy
import re
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_store import MATH6, SCHOOL  # noqa: E402
import engine  # noqa: E402
import ops  # noqa: E402


def course():
    return engine.course_for_render(SCHOOL, engine.template_from(MATH6, SCHOOL))


def days(c):
    return {d["date"]: d for d in engine.render(c)[0]}


def lesson_days(c, after="2026-10-01"):
    return [d for d in engine.render(c)[0]
            if d["date"] >= after and d["type"] == "Instruction" and d["kind"] in ("Lesson", "Opener", "3-Act")]


class EditTests(unittest.TestCase):
    def setUp(self):
        self.c = course()
        self.day = lesson_days(self.c)[0]

    def edit(self, **fields):
        return ops.apply(self.c, {"op": "edit", "date": self.day["date"], "fields": fields}, SCHOOL)

    def test_fields(self):
        before = engine.render(self.c)[0]
        self.edit(target="I can   add.", link=" https://example.com/x ",
                  homework=[{"text": "pg 4", "due": "2026-10-30", "link": ""}, {"text": "  "}])
        after = days(self.c)[self.day["date"]]
        self.assertEqual((after["target"], after["link"]), ("I can add.", "https://example.com/x"))
        self.assertEqual([(h["text"], h["due"]) for h in after["homework"]], [("pg 4", "2026-10-30")])
        # Content only: no day's lesson moved.
        self.assertEqual([d["lesson_text"] for d in before], [d["lesson_text"] for d in engine.render(self.c)[0]])

    def test_title_keeps_its_code_only_when_she_does(self):
        self.day = next(d for d in lesson_days(self.c) if re.match(r"T\d+L\d+ ", d["lesson_text"]))
        code = self.day["lesson_text"].split(" ")[0]
        self.edit(title=f"{code} New name")
        self.assertEqual(days(self.c)[self.day["date"]]["lesson_text"], f"{code} New name")
        self.edit(title="Field trip prep")
        self.assertEqual(days(self.c)[self.day["date"]]["lesson_text"], "Field trip prep")

    def test_kind(self):
        self.edit(kind="Test")
        self.assertEqual(days(self.c)[self.day["date"]]["kind"], "Test")
        for kind in ("Quiz", "Self-Grading", "Opener", "Nonsense"):
            with self.subTest(kind=kind), self.assertRaises(ops.OpError):
                self.edit(kind=kind)

    def test_refused(self):
        bad = ({"link": "javascript:alert(1)"}, {"link": "/etc/passwd"},
               {"homework": [{"text": "x", "link": "javascript:alert(1)"}]},
               {"homework": [{"text": "x", "due": "tomorrow"}]},
               {"title": "   "}, {"teacher": "x"}, {}, {"target": "x" * 3000})
        for fields in bad:
            with self.subTest(fields=fields), self.assertRaises(ops.OpError):
                self.edit(**fields)

    def test_only_lessons(self):
        rendered = engine.render(self.c)[0]
        quiz = next(d for d in rendered if d["kind"] == "Quiz")
        closed = next(d for d in rendered if d["type"] == "No School")
        for date_ in (quiz["date"], closed["date"], "2026-10-10", "2031-01-01"):
            with self.subTest(date=date_), self.assertRaises(ops.OpError):
                ops.apply(self.c, {"op": "edit", "date": date_, "fields": {"title": "x"}}, SCHOOL)


class AddTests(unittest.TestCase):
    def test_add_on_a_lesson_day_moves_the_rest_later(self):
        c = course()
        first, second = lesson_days(c)[:2]
        summary = ops.apply(c, {"op": "add", "date": first["date"],
                                "fields": {"title": "Catch-up day", "kind": "Lesson"}}, SCHOOL)
        after = days(c)
        self.assertEqual(after[first["date"]]["lesson_text"], "Catch-up day")
        self.assertEqual(after[second["date"]]["lesson_text"], first["lesson_text"])
        self.assertIn("later lessons each move one class day later", summary)

    def test_add_on_empty_days_fills_them_in_order(self):
        c = course()
        c["sequence"] = []
        first, second = [d for d in engine.render(c)[0]
                         if d["type"] == "Instruction" and d["kind"] is None][:2]
        ops.apply(c, {"op": "add", "date": first["date"], "fields": {"title": "Day one"}}, SCHOOL)
        summary = ops.apply(c, {"op": "add", "date": second["date"], "fields": {"title": "Day two"}}, SCHOOL)
        after = days(c)
        self.assertEqual((after[first["date"]]["lesson_text"], after[second["date"]]["lesson_text"]),
                         ("Day one", "Day two"))
        self.assertNotIn("later lessons", summary)

    def test_a_new_lesson_needs_a_title(self):
        c = course()
        with self.assertRaises(ops.OpError):
            ops.apply(c, {"op": "add", "date": lesson_days(c)[0]["date"], "fields": {"target": "x"}}, SCHOOL)


class DayTests(unittest.TestCase):
    def test_close_and_open(self):
        c = course()
        first, second = lesson_days(c)[:2]
        original = engine.render(c)[0]
        ops.apply(c, {"op": "close", "date": first["date"], "note": "Assembly"}, SCHOOL)
        after = days(c)
        self.assertEqual((after[first["date"]]["type"], after[first["date"]]["display"]),
                         ("No School", "Assembly"))
        self.assertIn(first["lesson_text"], [d["lesson_text"] for d in engine.render(c)[0]
                                             if d["date"] > first["date"]][:3])
        with self.assertRaises(ops.OpError):
            ops.apply(c, {"op": "close", "date": first["date"]}, SCHOOL)
        ops.apply(c, {"op": "open", "date": first["date"]}, SCHOOL)
        self.assertEqual(engine.render(c)[0], original)
        with self.assertRaises(ops.OpError):
            ops.apply(c, {"op": "open", "date": first["date"]}, SCHOOL)

    def test_a_school_closure_stays_closed(self):
        c = course()
        holiday = next(d for d in SCHOOL if d["type"] == "No School" and d["date"] > "2026-10-01")
        with self.assertRaises(ops.OpError) as cm:
            ops.apply(c, {"op": "open", "date": holiday["date"]}, SCHOOL)
        self.assertIn("school's calendar", str(cm.exception))

    def test_her_flex_day_can_open(self):
        c = course()
        flex = next((d for d in c["school_days"] if d["type"] == "Flex"), None)
        if flex is None:
            self.skipTest("no Flex day in this copy")
        ops.apply(c, {"op": "open", "date": flex["date"]}, SCHOOL)
        self.assertEqual(days(c)[flex["date"]]["type"], "Instruction")


class CopyWeekTests(unittest.TestCase):
    def test_repeats_the_weeks_lessons_after_it(self):
        c = course()
        c["sequence"] = []
        start = next(d for d in engine.render(c)[0] if d["type"] == "Instruction")
        ops.apply(c, {"op": "add", "date": start["date"], "fields": {"title": "Warm-up routine"}}, SCHOOL)
        first = next(d for d in engine.render(c)[0] if d["lesson_text"] == "Warm-up routine")
        friday = (engine.week_monday(first["date"]) + timedelta(days=4)).isoformat()
        ops.apply(c, {"op": "edit", "date": first["date"],
                      "fields": {"homework": [{"text": "Read", "due": friday}]}}, SCHOOL)
        summary = ops.apply(c, {"op": "copy_week", "date": first["date"]}, SCHOOL)
        self.assertIn("1 lesson added", summary)
        copies = [d for d in engine.render(c)[0] if d["lesson_text"] == "Warm-up routine"]
        self.assertEqual(len(copies), 2)
        old, new = copies
        shift = date.fromisoformat(new["date"]) - date.fromisoformat(old["date"])
        self.assertEqual(date.fromisoformat(new["homework"][0]["due"]),
                         date.fromisoformat(old["homework"][0]["due"]) + shift)

    def test_an_empty_week(self):
        c = course()
        c["sequence"] = []
        with self.assertRaises(ops.OpError):
            ops.apply(c, {"op": "copy_week", "date": "2026-10-12"}, SCHOOL)


class PasteTests(unittest.TestCase):
    def test_skips_quizzes_and_closed_days(self):
        c = course()
        rendered = engine.render(c)[0]
        quiz = next(d for d in rendered if d["kind"] == "Quiz" and d["date"] > "2026-10-01")
        start = next(d for d in reversed(rendered) if d["date"] < quiz["date"] and d["type"] == "Instruction"
                     and d["kind"] not in ("Quiz", "Self-Grading"))
        rows = [{"target": f"Target {i}"} for i in range(3)]
        summary = ops.apply(c, {"op": "paste", "date": start["date"], "rows": rows}, SCHOOL)
        got = [d for d in engine.render(c)[0] if (d["target"] or "").startswith("Target ")]
        self.assertEqual([d["target"] for d in got], ["Target 0", "Target 1", "Target 2"])
        self.assertTrue(all(d["kind"] not in ("Quiz", "Self-Grading") and d["type"] == "Instruction" for d in got))
        self.assertNotIn(quiz["date"], [d["date"] for d in got])
        self.assertIn("3 days", summary)

    def test_fills_empty_days(self):
        c = course()
        c["sequence"] = []
        start = next(d for d in engine.render(c)[0] if d["type"] == "Instruction")
        ops.apply(c, {"op": "paste", "date": start["date"],
                      "rows": [{"title": "A", "target": "a"}, {"title": "B"}]}, SCHOOL)
        self.assertEqual([e["district_title"] for e in c["sequence"]], ["A", "B"])

    def test_refused(self):
        c = course()
        date_ = lesson_days(c)[0]["date"]
        for rows in ([], [{}], [{"title": "x"}] * (ops.MAX_PASTE_ROWS + 1), [{"link": "javascript:x"}],
                     [["x"]], "rows"):
            with self.subTest(n=len(rows)), self.assertRaises(ops.OpError):
                ops.apply(copy.deepcopy(c), {"op": "paste", "date": date_, "rows": rows}, SCHOOL)


class QuizDayTests(unittest.TestCase):
    def setUp(self):
        self.c = course()
        rendered = engine.render(self.c)[0]
        self.quiz = next(d for d in rendered if d["kind"] == "Quiz" and d["date"] > "2026-10-01")
        self.lesson = next(d for d in rendered if d["date"] > self.quiz["date"] and d["kind"] == "Lesson")

    def test_skip_and_back(self):
        original = engine.render(self.c)[0]
        self.assertIn("No quiz", ops.apply(self.c, {"op": "skip_quiz", "date": self.quiz["date"]}, SCHOOL))
        self.assertNotEqual(days(self.c)[self.quiz["date"]]["kind"], "Quiz")
        with self.assertRaises(ops.OpError):
            ops.apply(self.c, {"op": "skip_quiz", "date": self.quiz["date"]}, SCHOOL)
        ops.apply(self.c, {"op": "quiz_rule", "date": self.quiz["date"]}, SCHOOL)
        self.assertEqual(engine.render(self.c)[0], original)
        with self.assertRaises(ops.OpError):
            ops.apply(self.c, {"op": "quiz_rule", "date": self.quiz["date"]}, SCHOOL)

    def test_move_full_or_alongside(self):
        c = copy.deepcopy(self.c)
        ops.apply(c, {"op": "move_quiz", "date": self.quiz["date"], "to": self.lesson["date"]}, SCHOOL)
        self.assertEqual(days(c)[self.lesson["date"]]["kind"], "Quiz")
        self.assertNotEqual(days(c)[self.quiz["date"]]["kind"], "Quiz")
        c = copy.deepcopy(self.c)
        summary = ops.apply(c, {"op": "move_quiz", "date": self.quiz["date"], "to": self.lesson["date"],
                                "how": "paired"}, SCHOOL)
        self.assertIn("alongside", summary)
        after = days(c)
        # The quiz shares that day's period; its old day is a lesson again,
        # so the lessons between move a day earlier.
        self.assertTrue(after[self.lesson["date"]]["quiz_paired"])
        self.assertEqual(after[self.lesson["date"]]["kind"], "Lesson")
        self.assertEqual(after[self.quiz["date"]]["kind"], "Lesson")

    def test_move_refused(self):
        closed = next(d for d in engine.render(self.c)[0] if d["type"] == "No School")
        for op in ({"to": self.quiz["date"]}, {"to": closed["date"]}, {"to": None},
                   {"to": self.lesson["date"], "how": "sideways"}):
            with self.subTest(op=op), self.assertRaises(ops.OpError):
                ops.apply(copy.deepcopy(self.c), {"op": "move_quiz", "date": self.quiz["date"], **op}, SCHOOL)
        with self.assertRaises(ops.OpError):  # no quiz there to move
            ops.apply(self.c, {"op": "move_quiz", "date": self.lesson["date"], "to": self.quiz["date"]}, SCHOOL)


class SettingsTests(unittest.TestCase):
    def settings(self, c, **settings):
        return ops.apply(c, {"op": "settings", "settings": settings}, SCHOOL)

    def settings_before_school(self, c, **settings):
        # Set up before the year starts, so there's no past to keep.
        return ops.apply(c, {"op": "settings", "settings": settings, "today": date(2026, 8, 1)}, SCHOOL)

    def test_quiz_rule(self):
        c = course()
        before = {d["date"] for d in engine.render(c)[0] if d["kind"] == "Quiz"}
        summary = self.settings_before_school(c, quiz={"weekday": "Thu", "every_weeks": 2})
        self.assertIn("Thursdays", summary)
        self.assertIn("every other week", summary)
        after = [d for d in engine.render(c)[0] if d["kind"] == "Quiz"]
        self.assertTrue(after and all(d["weekday"] == "Thu" for d in after))
        self.assertLess(len(after), len(before))
        self.assertIn("quizzes off", self.settings_before_school(c, quiz={"enabled": False}))
        self.assertFalse(any(d["kind"] == "Quiz" for d in engine.render(c)[0]))
        self.assertIn("quizzes on", self.settings_before_school(c, quiz={"enabled": True}))
        self.settings_before_school(c, quiz={"sits": "shared"})
        self.assertTrue(any(d["quiz_paired"] for d in engine.render(c)[0]))
        self.assertFalse(any(d["kind"] == "Quiz" for d in engine.render(c)[0]))

    def test_a_rule_change_leaves_the_past_alone(self):
        c = course()
        before = engine.render(c)[0]
        today = date(2026, 11, 2)
        ops.apply(c, {"op": "settings", "settings": {"quiz": {"weekday": "Fri", "sits": "shared"}},
                      "today": today}, SCHOOL)
        after = engine.render(c)[0]

        self.assertEqual([d for d in after if d["date"] < "2026-11-02"],
                         [d for d in before if d["date"] < "2026-11-02"])
        self.assertTrue(any(d["kind"] == "Self-Grading" for d in after if d["date"] < "2026-11-02"))
        later = [d for d in after if d["date"] >= "2026-11-02"]
        self.assertTrue(any(d["quiz_paired"] and d["weekday"] == "Fri" for d in later))
        self.assertFalse(any(d["kind"] == "Quiz" for d in later))

    def test_the_rest(self):
        c = course()
        summary = self.settings(c, course="Math 6, Period 2", teacher="Ms. Rivera", theme="plum",
                                show_classwork=True, review_before_test=False)
        self.assertEqual((c["course"], c["teacher"], c["theme"], c["show_classwork"], c["review_before_test"]),
                         ("Math 6, Period 2", "Ms. Rivera", "plum", True, False))
        self.assertIn("class title", summary)
        self.settings(c, teacher="")
        self.assertNotIn("teacher", c)  # back to her account's name
        self.assertEqual(self.settings(c, theme="plum"), "Settings saved")

    def test_refused(self):
        for settings in ({}, {"theme": "neon"}, {"course": " "}, {"course": "x" * 81}, {"show_classwork": "yes"},
                         {"quiz": {"weekday": "Sat"}}, {"quiz": {"every_weeks": 3}}, {"quiz": {"sits": "half"}},
                         {"quiz": {"link": "x"}}, {"quiz": {"enabled": "maybe"}}, {"owner": 2}):
            with self.subTest(settings=settings), self.assertRaises(ops.OpError):
                self.settings(course(), **settings)


class ApplyTests(unittest.TestCase):
    def test_malformed(self):
        for op in (None, [], {"op": "edit"}, {"op": "edit", "date": "10/20"}, {"op": "drop", "date": "2026-10-20"}):
            with self.subTest(op=op), self.assertRaises(ops.OpError):
                ops.apply(course(), op, SCHOOL)

    def test_engine_validation_still_applies(self):
        # Every edit goes through engine.py's own functions.
        c = course()
        ops.apply(c, {"op": "edit", "date": lesson_days(c)[0]["date"], "fields": {"title": "Fine"}}, SCHOOL)
        self.assertTrue(all(e["kind"] in engine.VALID_LESSON_KINDS - {"Quiz"} for e in c["sequence"]))


if __name__ == "__main__":
    unittest.main()
