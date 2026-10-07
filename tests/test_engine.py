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
        # The next week's quiz slot is still there; self-grading takes it.
        self.assertEqual(days["2026-10-14"]["kind"], "Self-Grading")

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


class SelfGradingTests(unittest.TestCase):
    """The Wednesday after a test week is test self-grading, in the quiz's slot."""
    LESSONS = [("A", "Lesson"), ("B", "Lesson"), ("C", "Lesson"),
               ("Topic 1 Review", "Lesson"), ("Topic 1 Test", "Test")] + [("D", "Lesson")] * 20

    def test_takes_the_quiz_slot_without_moving_lessons(self):
        course = make_course("2026-10-05", "2026-10-23", lessons=self.LESSONS)
        days = by_date(course)
        self.assertEqual(days["2026-10-14"]["lesson_text"], "Test Self-Grading")
        self.assertEqual(days["2026-10-21"]["kind"], "Quiz")
        without = make_course("2026-10-05", "2026-10-23", lessons=self.LESSONS)
        placed = lambda c: [(d, i) for d, i in engine.place(c)[0]
                            if i not in (engine.QUIZ_ITEM, engine.SELF_GRADING_ITEM)]
        self.assertEqual(placed(course), placed(without))
        self.assertEqual(engine.check_self_grading(course), [])

    def test_follows_the_test_when_it_moves(self):
        course = make_course("2026-10-05", "2026-10-23", lessons=self.LESSONS)
        engine.insert_lesson(course, 0, {"district_title": "Extra"})
        engine.insert_lesson(course, 0, {"district_title": "Extra"})
        engine.insert_lesson(course, 0, {"district_title": "Extra"})
        days = by_date(course)  # the test now lands the week of 10/12
        self.assertEqual(days["2026-10-15"]["kind"], "Test")
        self.assertEqual(days["2026-10-21"]["kind"], "Self-Grading")
        self.assertNotIn("Self-Grading", [days[d]["kind"] for d in ("2026-10-07", "2026-10-14")])

    def test_no_slot_is_flagged_not_forced(self):
        course = make_course("2026-10-05", "2026-10-23", lessons=self.LESSONS,
                             closed=("2026-10-14",))
        days = by_date(course)
        self.assertNotIn("Self-Grading", [d["kind"] for d in days.values()])
        [warning] = engine.check_self_grading(course)
        self.assertIn("2026-10-14", warning)

    def test_paired_with_a_lesson_when_wednesday_is_closed(self):
        course = make_course("2026-10-05", "2026-10-23", lessons=self.LESSONS,
                             closed=("2026-10-14",))
        before = [d["lesson_text"] for d in engine.render(course)[0]]
        engine.set_day(course, "2026-10-13", self_grading="paired")
        cal = engine.render(course)[0]
        self.assertEqual([d["lesson_text"] for d in cal], before)  # nothing moves
        self.assertTrue(by_date(course)["2026-10-13"]["self_grading_paired"])
        self.assertEqual(engine.check_self_grading(course), [])
        with self.assertRaises(ValueError):
            engine.set_day(course, "2026-10-14", self_grading="paired")  # a closed day

    def test_full_override_keeps_the_quiz(self):
        course = make_course("2026-10-05", "2026-10-23", lessons=self.LESSONS)
        engine.set_day(course, "2026-10-14", quiz="full")
        self.assertEqual(by_date(course)["2026-10-14"]["kind"], "Quiz")

    def test_never_stored(self):
        course = make_course("2026-10-05", "2026-10-09")
        with self.assertRaises(ValueError):
            engine.insert_lesson(course, 0, {"district_title": "Test Self-Grading",
                                             "kind": "Self-Grading"})


class QuizOverrideTests(unittest.TestCase):
    """A school day's `quiz` field (engine.QUIZ_OVERRIDES)."""

    def setUp(self):
        self.course = make_course("2026-10-05", "2026-10-16")

    def test_note_mentioning_quiz_changes_nothing(self):
        engine.set_day(self.course, "2026-10-07", note="Quiz corrections due today")
        self.assertIn("2026-10-07", quiz_dates(self.course))

    def test_none(self):
        engine.set_day(self.course, "2026-10-07", quiz="none")
        self.assertEqual(quiz_dates(self.course), ["2026-10-14"])
        self.assertEqual(by_date(self.course)["2026-10-07"]["kind"], "Lesson")

    def test_paired(self):
        engine.set_day(self.course, "2026-10-07", quiz="paired")
        day = by_date(self.course)["2026-10-07"]
        self.assertEqual((day["kind"], day["quiz_paired"]), ("Lesson", True))
        self.assertEqual(quiz_dates(self.course), ["2026-10-14"])

    def test_move_a_quiz_to_thursday(self):
        engine.set_day(self.course, "2026-10-07", quiz="none")
        engine.set_day(self.course, "2026-10-08", quiz="full")
        self.assertEqual(quiz_dates(self.course), ["2026-10-08", "2026-10-14"])

    def test_full_quiz_overrides_test_week(self):
        # Mon A, Tue review, Wed test: a test week, so no quiz -- until a
        # full quiz is set on Tuesday (the test slides to Thursday, same week).
        lessons = [("A", "Lesson"), ("Topic 1 Review", "Lesson"), ("Topic 1 Test", "Test")]
        course = make_course("2026-10-05", "2026-10-09", lessons=lessons)
        self.assertEqual(quiz_dates(course), [])
        engine.set_day(course, "2026-10-06", quiz="full")
        self.assertEqual(quiz_dates(course), ["2026-10-06"])
        self.assertEqual(by_date(course)["2026-10-08"]["kind"], "Test")

    def test_clearing_the_override(self):
        engine.set_day(self.course, "2026-10-07", quiz="none")
        engine.set_day(self.course, "2026-10-07", quiz=None)
        self.assertNotIn("quiz", self.course["school_days"][2])
        self.assertIn("2026-10-07", quiz_dates(self.course))

    def test_rejected_without_changing_the_day(self):
        with self.assertRaises(ValueError):
            engine.set_day(self.course, "2026-10-08", type="No School", quiz="full")
        self.assertEqual(self.course["school_days"][3]["type"], "Instruction")
        self.assertNotIn("quiz", self.course["school_days"][3])
        with self.assertRaises(ValueError):
            engine.set_day(self.course, "2026-10-08", quiz="maybe")


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



class PracticeLogLinkTests(unittest.TestCase):
    def test_assignment_carries_its_logs_folder(self):
        course = make_course("2026-10-05", "2026-10-09", lessons=5, quiz_rhythm_start="2027-01-01")
        engine.edit_lesson(course, 0, homework=[{"text": "Practice Log: weekly", "due": "2026-10-09",
                                                 "link": "https://example.org/week1-keys"}])
        engine.edit_lesson(course, 1, homework=[{"text": "Lesson 2 practice", "due": "2026-10-07"}])
        days = by_date(course)
        [due] = days["2026-10-07"]["due"]
        self.assertEqual(due["log_link"], "https://example.org/week1-keys")

    def _two_week_log(self, assignments):
        course = make_course("2026-10-05", "2026-10-16", lessons=10, quiz_rhythm_start="2027-01-01")
        engine.edit_lesson(course, 0, homework=[{"text": "Practice Log: two weeks", "due": "2026-10-16",
                                                 "link": "https://example.org/keys"}])
        for i in range(assignments):
            engine.edit_lesson(course, i + 1, homework=[{"text": f"Lesson {i + 2} practice", "due": "2026-10-15",
                                                         "link": "https://example.org/hw"}])
        return course

    def test_five_assignments_is_fine(self):
        self.assertEqual(engine.check_practice_log_size(self._two_week_log(5)), [])

    def test_sixth_assignment_is_flagged(self):
        [warning] = engine.check_practice_log_size(self._two_week_log(6))
        self.assertIn("6 assignments", warning)

    def _log_around_test(self, log_due):
        lessons = ([(f"Lesson {i + 1}", "Lesson") for i in range(5)] + [("Review", "Lesson"), ("Topic 1 Test", "Test")]
                   + [(f"Lesson {i + 7}", "Lesson") for i in range(3)])
        course = make_course("2026-10-05", "2026-10-16", lessons=lessons, quiz_rhythm_start="2027-01-01")
        engine.edit_lesson(course, 0, homework=[{"text": "Practice Log: two weeks", "due": log_due,
                                                 "link": "https://example.org/keys"}])
        return course

    def test_log_due_on_review_day_is_fine(self):
        course = self._log_around_test("2026-10-12")  # the test is Tue 10/13
        self.assertEqual(engine.check_practice_log_before_test(course, today=date(2026, 10, 5)), [])

    def test_log_due_after_test_is_flagged(self):
        course = self._log_around_test("2026-10-16")
        [warning] = engine.check_practice_log_before_test(course, today=date(2026, 10, 5))
        self.assertIn("2026-10-13 test", warning)

    def test_past_log_is_not_flagged(self):
        course = self._log_around_test("2026-10-16")
        self.assertEqual(engine.check_practice_log_before_test(course, today=date(2026, 10, 19)), [])

class RecordChangeTests(unittest.TestCase):
    """engine.record_change: what counts as a change families already saw."""
    TODAY = date(2026, 10, 5)

    def course(self):
        # No quizzes, so lessons sit on consecutive class days.
        course = make_course("2026-10-01", "2026-10-30", lessons=30, quiz_rhythm_start="2027-01-01")
        engine.edit_lesson(course, 5, classwork="Workbook pg 10",
                           homework=[{"text": "Practice 6", "due": "2026-10-14"}])
        return course

    def record(self, course, before, **kw):
        return engine.record_change(course, before, "summary", today=self.TODAY, **kw)

    def test_filling_a_blank_is_not_a_change(self):
        course = self.course()
        before, _ = engine.render(course)
        engine.edit_lesson(course, 6, classwork="New class work",
                           homework=[{"text": "Practice 7", "due": "2026-10-15"}])
        entry = self.record(course, before)
        # Not a change, but news: the day is tagged "Updated", not "Changed".
        self.assertFalse(entry["changed"])
        self.assertEqual((entry["days"], entry["updated"]), ([], ["2026-10-09"]))

    def test_no_edit_logs_nothing(self):
        course = self.course()
        before, _ = engine.render(course)
        self.assertIsNone(self.record(course, before))
        self.assertNotIn("changes", course)

    def test_lost_day_tags_the_near_days_and_logs_one_entry(self):
        course = self.course()
        before, _ = engine.render(course)
        engine.set_day(course, "2026-10-07", type="Other", note="Assembly")
        entry = self.record(course, before, reason="assembly")
        self.assertEqual(course["changes"], [entry])
        self.assertEqual(entry["reason"], "assembly")
        days = {d["date"] for d in entry["days"]}
        # The lost day and the next class days in the window are tagged...
        self.assertIn("2026-10-07", days)
        self.assertIn("2026-10-08", days)
        # ...days past the 5-class-day window are not (no tests there).
        self.assertNotIn("2026-10-20", days)
        lost = next(d for d in entry["days"] if d["date"] == "2026-10-07")
        self.assertEqual((lost["was"], lost["now"]), ("Lesson 5", "Assembly"))

    def test_past_days_are_left_alone(self):
        course = self.course()
        before, _ = engine.render(course)
        engine.set_day(course, "2026-10-02", type="Other", note="Assembly")
        entry = self.record(course, before)
        self.assertTrue(all(d["date"] >= "2026-10-05" for d in entry["days"]))

    def test_moved_test_is_tagged_beyond_the_window(self):
        lessons = [("A", "Lesson")] * 15 + [("Topic 1 Test", "Test")] + [("B", "Lesson")] * 10
        course = make_course("2026-10-01", "2026-10-30", lessons=lessons, quiz_rhythm_start="2027-01-01")
        before, _ = engine.render(course)
        engine.set_day(course, "2026-10-06", type="Other", note="Assembly")
        days = {d["date"] for d in self.record(course, before)["days"]}
        self.assertIn("2026-10-22", days)  # was the test
        self.assertIn("2026-10-23", days)  # is the test now
        self.assertNotIn("2026-10-21", days)  # an ordinary lesson out there
        arrived = next(d for d in self.record(course, before)["days"] if d["date"] == "2026-10-23")
        self.assertEqual(arrived.get("moved_from"), "2026-10-22")

    def test_moved_due_date(self):
        course = self.course()
        before, _ = engine.render(course)
        engine.edit_lesson(course, 5, homework=[{"text": "Practice 6", "due": "2026-10-16"}])
        [d] = self.record(course, before)["days"]
        self.assertEqual((d["date"], d["was"], d["now"]),
                         ("2026-10-14", "Practice 6 (due 10/14)", "Practice 6 (due 10/16)"))

    def test_dropped_and_reworded_assignments(self):
        course = self.course()
        before, _ = engine.render(course)
        engine.edit_lesson(course, 5, homework=None)
        [d] = self.record(course, before)["days"]
        self.assertIsNone(d["now"])
        course = self.course()
        before, _ = engine.render(course)
        engine.edit_lesson(course, 5, homework=[{"text": "Practice 6 (odds)", "due": "2026-10-14"}])
        # Reworded, due beyond the 5-class-day window: logged, not tagged.
        self.assertEqual(self.record(course, before)["days"], [])
        course = self.course()
        engine.edit_lesson(course, 5, homework=[{"text": "Practice 6", "due": "2026-10-08"}])
        before, _ = engine.render(course)
        engine.edit_lesson(course, 5, homework=[{"text": "Practice 6 (odds)", "due": "2026-10-08"}])
        [d] = self.record(course, before)["days"]
        self.assertEqual(d["now"], "Practice 6 (odds) (due 10/8)")

    def test_small_fix_skips_wording_but_not_dates(self):
        course = self.course()
        before, _ = engine.render(course)
        engine.edit_lesson(course, 5, classwork="Workbook page 10",
                           homework=[{"text": "Practice 6!", "due": "2026-10-14"}])
        self.assertIsNone(self.record(course, before, small_fix=True))
        engine.edit_lesson(course, 5, homework=[{"text": "Practice 6!", "due": "2026-10-15"}])
        self.assertIsNotNone(self.record(course, before, small_fix=True))

    def test_changed_class_work_on_the_same_lesson(self):
        course = self.course()
        before, _ = engine.render(course)
        engine.edit_lesson(course, 5, classwork="Something else")
        [d] = self.record(course, before)["days"]
        self.assertEqual((d["what"], d["was"]), ("class work", "Workbook pg 10"))

if __name__ == "__main__":
    unittest.main()
