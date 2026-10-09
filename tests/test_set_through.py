"""Set and planned days (a course's "set_through"; PLANNING.md, "Set and
planned days"): change notices only for what students relied on.

Run: python3 -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402
import render  # noqa: E402
from test_engine import make_course  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))
import apply_week  # noqa: E402

TODAY = date(2026, 10, 5)  # a Monday; set through Fri 10/9


def course(**extra):
    # No quizzes, so lesson i sits on the i-th class day from Thu 10/1:
    # 10/5 is index 2, 10/9 index 6, 10/12 index 7, 10/19 index 12.
    c = make_course("2026-10-01", "2026-10-30", lessons=30, quiz_rhythm_start="2027-01-01",
                    set_through="2026-10-09", **extra)
    engine.edit_lesson(c, 4, target="I can add.", link="https://example.com/l5",
                       homework=[{"text": "Practice 5", "due": "2026-10-09"}])
    engine.edit_lesson(c, 13, target="I can divide.", link="https://example.com/l14",
                       homework=[{"text": "Practice 14", "due": "2026-10-23"}])
    engine.edit_lesson(c, 16, kind="Test")  # Fri 10/23: a test, weeks out
    return c


def record(c, before, **kw):
    return engine.record_change(c, before, "summary", today=TODAY, **kw)


class RenderTests(unittest.TestCase):
    def test_days_are_set_through_the_date(self):
        days = {d["date"]: d["set"] for d in engine.render(course())[0]}
        self.assertTrue(days["2026-10-09"])
        self.assertFalse(days["2026-10-12"])

    def test_no_set_through_means_every_day_is_set(self):
        c = course()
        del c["set_through"]
        self.assertTrue(all(d["set"] for d in engine.render(c)[0]))


class NoticeTests(unittest.TestCase):
    def test_lost_set_day_is_a_change_but_planned_shifts_are_silent(self):
        c = course()
        before, _ = engine.render(c)
        engine.set_day(c, "2026-10-07", type="Other", note="Assembly")
        entry = record(c, before)
        self.assertTrue(entry["changed"])
        tagged = {d["date"] for d in entry["days"]}
        self.assertTrue({"2026-10-07", "2026-10-08", "2026-10-09"} <= tagged)
        planned = {t for t in tagged if t > "2026-10-09"}
        # The test moves (10/23 -> 10/26): always noticed. Nothing else planned is.
        self.assertEqual(planned, {"2026-10-23", "2026-10-26"})
        moved = next(d for d in entry["days"] if d["date"] == "2026-10-26")
        self.assertEqual(moved.get("moved_from"), "2026-10-23")

    def test_planned_shift_without_an_assessment_is_silent(self):
        c = course()
        engine.edit_lesson(c, 16, kind="Lesson")  # no test in the shift
        before, _ = engine.render(c)
        engine.set_day(c, "2026-10-14", type="Other", note="Assembly")
        self.assertIsNone(record(c, before))
        self.assertNotIn("changes", c)

    def test_planned_shift_that_moves_a_test_is_noticed(self):
        c = course()
        before, _ = engine.render(c)
        engine.set_day(c, "2026-10-14", type="Other", note="Assembly")
        entry = record(c, before)
        self.assertTrue(entry["changed"])
        self.assertIn("2026-10-26", {d["date"] for d in entry["days"]})
        self.assertNotIn("2026-10-15", {d["date"] for d in entry["days"]})

    def test_a_test_beyond_the_current_unit_is_not_noticed(self):
        c = course()
        engine.edit_lesson(c, 14, kind="Test")  # Wed 10/21: this unit's test
        before, _ = engine.render(c)
        engine.set_day(c, "2026-10-22", type="Other", note="Assembly")
        # The 10/23 test is in the next unit now: it moves, but quietly.
        self.assertIsNone(record(c, before))

    def test_target_and_link_changes_on_a_set_day(self):
        c = course()
        before, _ = engine.render(c)
        engine.edit_lesson(c, 4, target="I can add decimals.", link="https://example.com/new")
        entry = record(c, before)
        self.assertTrue(entry["changed"])
        [day] = entry["days"]
        self.assertEqual((day["date"], day["what"]), ("2026-10-07", "target"))

    def test_target_and_link_changes_on_a_planned_day_are_silent(self):
        c = course()
        before, _ = engine.render(c)
        engine.edit_lesson(c, 13, target="I can divide fractions.", link="https://example.com/new")
        self.assertIsNone(record(c, before))

    def test_small_fix_skips_a_set_day_target_rewording(self):
        c = course()
        before, _ = engine.render(c)
        engine.edit_lesson(c, 4, target="I can add!")
        entry = record(c, before, small_fix=True)
        self.assertIsNone(entry)

    def test_moved_due_date_on_set_homework_is_noticed(self):
        c = course()
        before, _ = engine.render(c)
        engine.edit_lesson(c, 4, homework=[{"text": "Practice 5", "due": "2026-10-12"}])
        entry = record(c, before)
        self.assertEqual([d["kind"] for d in entry["days"]], ["due moved"])

    def test_moved_due_date_on_planned_homework_is_silent(self):
        c = course()
        before, _ = engine.render(c)
        engine.edit_lesson(c, 13, homework=[{"text": "Practice 14", "due": "2026-10-26"}])
        self.assertIsNone(record(c, before))

    def test_filling_a_planned_day_is_not_even_updated(self):
        c = course()
        before, _ = engine.render(c)
        engine.edit_lesson(c, 8, target="I can plan.")   # Tue 10/13, planned
        engine.edit_lesson(c, 5, target="I can set.")    # Thu 10/8, set
        entry = record(c, before)
        self.assertEqual(entry["updated"], ["2026-10-08"])
        self.assertFalse(entry["changed"])


class PageTests(unittest.TestCase):
    def page(self, c):
        return render.build_page(c, engine.render(c)[0])

    def test_set_line_and_planned_marks(self):
        page = self.page(course())
        self.assertIn("Set through Fri 10/9.", page)
        self.assertIn("Later days are planned and may change.", page)
        self.assertIn('class="day day-lesson day-planned" data-date="2026-10-12"', page)
        self.assertNotIn('day-planned" data-date="2026-10-09"', page)
        self.assertIn('cell-planned" data-date="2026-10-12"', page)

    def test_planned_day_hides_its_lesson_link_and_marks_homework(self):
        page = self.page(course())
        set_panel = page.split('id="p-2026-10-07"')[1].split("</div></div>")[0]
        planned_panel = page.split('id="p-2026-10-20"')[1].split("</div></div>")[0]
        self.assertIn('href="https://example.com/l5" target="_blank" rel="noopener">', set_panel)
        self.assertIn("data-plan hidden", planned_panel)
        self.assertIn("Practice 14", planned_panel)
        self.assertIn("(planned)", planned_panel)
        self.assertNotIn("(planned)", set_panel)

    def test_no_set_through_no_marks(self):
        c = course()
        del c["set_through"]
        page = self.page(c)
        self.assertNotIn('class="setline"', page)
        self.assertNotIn("day-planned", page.split("<body>")[1].split("<script>")[0])


class StaleDateTests(unittest.TestCase):
    """A set-through date nobody advanced: the week students are in still
    counts as set (engine.set_floor), and a check says the date is behind."""

    def test_floor_is_this_friday_on_a_weekday_and_next_friday_on_a_weekend(self):
        self.assertEqual(engine.set_floor(date(2026, 10, 12)), "2026-10-16")  # Mon
        self.assertEqual(engine.set_floor(date(2026, 10, 16)), "2026-10-16")  # Fri
        self.assertEqual(engine.set_floor(date(2026, 10, 17)), "2026-10-23")  # Sat
        self.assertEqual(engine.set_floor(date(2026, 10, 18)), "2026-10-23")  # Sun

    def test_this_weeks_changes_are_noticed_with_a_stale_date(self):
        c = course()  # set through Fri 10/9
        before, _ = engine.render(c)
        engine.edit_lesson(c, 9, target="I can subtract.")  # Wed 10/14, blank before
        engine.set_day(c, "2026-10-15", type="Other", note="Assembly")
        entry = engine.record_change(c, before, "summary", today=date(2026, 10, 13))
        tagged = {d["date"] for d in entry["days"]}
        self.assertTrue({"2026-10-15", "2026-10-16"} <= tagged, "the week students are in")
        self.assertFalse({t for t in tagged if "2026-10-19" <= t < "2026-10-23"}, "next week is still planned")
        self.assertIn("2026-10-14", entry["updated"])

    def test_check_says_the_date_is_behind(self):
        c = course()
        self.assertEqual(engine.check_set_through_current(c, today=date(2026, 10, 9)), [])
        [warning] = engine.check_set_through_current(c, today=date(2026, 10, 10))
        self.assertIn("Set through is 10/9", warning)
        del c["set_through"]
        self.assertEqual(engine.check_set_through_current(c, today=date(2026, 10, 20)), [])

    def test_page_can_lift_planned_marks(self):
        page = render.build_page(course(), engine.render(course())[0])
        self.assertIn('data-through="2026-10-09"', page)
        planned_panel = page.split('id="p-2026-10-20"')[1].split("</div></div>")[0]
        self.assertIn('href="https://example.com/l14" target="_blank" rel="noopener" data-plan hidden', planned_panel)


class WeekFileTests(unittest.TestCase):
    def test_next_unset_week_becomes_set(self):
        c = course()
        line = apply_week.advance_set_through(c, "2026-10-12")
        self.assertEqual(c["set_through"], "2026-10-16")
        self.assertIn("Set through moves to 10/16", line)

    def test_a_week_further_out_stays_planned(self):
        c = course()
        line = apply_week.advance_set_through(c, "2026-10-19")
        self.assertEqual(c["set_through"], "2026-10-09")
        self.assertIn("planned", line)

    def test_a_set_week_leaves_the_date(self):
        c = course()
        line = apply_week.advance_set_through(c, "2026-10-05")
        self.assertEqual(c["set_through"], "2026-10-09")
        self.assertIn("already set", line)

    def test_a_week_off_in_between_still_counts_as_next(self):
        closed = [f"2026-10-{d}" for d in ("12", "13", "14", "15", "16")]
        c = make_course("2026-10-01", "2026-10-30", lessons=20, closed=closed, set_through="2026-10-09")
        apply_week.advance_set_through(c, "2026-10-19")
        self.assertEqual(c["set_through"], "2026-10-23")

    def test_course_without_set_through_is_untouched(self):
        c = course()
        del c["set_through"]
        self.assertEqual(apply_week.advance_set_through(c, "2026-10-12"), "")
        self.assertNotIn("set_through", c)


if __name__ == "__main__":
    unittest.main()
