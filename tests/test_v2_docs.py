"""Tests for v2's calendar documents: course_for_render / split_course
(a calendar stored apart from its school's days) and template_from (the
"start from my Math 6" copy). SPEC-v2.md, "Data model".

Run: python3 -m unittest discover -s tests
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"
MATH6 = json.loads((GOLDEN / "math6.json").read_text())
MATH78 = json.loads((GOLDEN / "math78.json").read_text())


class SplitTests(unittest.TestCase):
    def test_round_trip_against_another_courses_days(self):
        # Math 7/8 differs from Math 6 on a couple dozen days: a good stand-in
        # for a calendar with its own changes against a shared school record.
        school = MATH6["school_days"]
        doc = engine.split_course(MATH78, school)
        self.assertNotIn("school_days", doc)
        self.assertTrue(0 < len(doc["day_changes"]) < 40)
        self.assertEqual(engine.course_for_render(school, doc), MATH78)
        self.assertEqual(engine.render(engine.course_for_render(school, doc)), engine.render(MATH78))

    def test_no_changes_against_its_own_days(self):
        self.assertEqual(engine.split_course(MATH6, MATH6["school_days"])["day_changes"], {})

    def test_editing_the_built_course_never_touches_the_school(self):
        school = copy.deepcopy(MATH6["school_days"])
        course = engine.course_for_render(school, engine.split_course(MATH6, school))
        engine.set_day(course, "2026-10-20", type="Other", note="Assembly")
        self.assertEqual(school, MATH6["school_days"])
        doc = engine.split_course(course, school)
        self.assertEqual(doc["day_changes"]["2026-10-20"]["note"], "Assembly")

    def test_mismatched_dates_are_refused(self):
        with self.assertRaises(ValueError):
            engine.course_for_render(MATH6["school_days"], {"day_changes": {"2026-07-04": {}}})
        with self.assertRaises(ValueError):
            engine.split_course(MATH6, MATH6["school_days"][1:])


class SchoolRecordTests(unittest.TestCase):
    def test_closures_only(self):
        school = engine.school_record(MATH6, MATH78)
        self.assertEqual(len(school), len(MATH6["school_days"]))
        self.assertEqual({d["type"] for d in school}, {"Instruction", "No School"})
        closed = [d["date"] for d in MATH6["school_days"] if d["type"] == "No School"]
        self.assertEqual([d["date"] for d in school if d["type"] == "No School"], closed)
        self.assertEqual({d["note"] for d in school if d["type"] == "Instruction"}, {None})

    def test_each_course_is_school_plus_its_own_changes(self):
        school = engine.school_record(MATH6, MATH78)
        for course in (MATH6, MATH78):
            doc = engine.split_course(course, school)
            self.assertEqual(engine.course_for_render(school, doc), course)

    def test_disagreeing_closures_are_refused(self):
        other = copy.deepcopy(MATH78)
        day = next(d for d in other["school_days"] if d["type"] == "Instruction")
        day["type"] = "No School"
        with self.assertRaises(ValueError):
            engine.school_record(MATH6, other)


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.doc = engine.template_from(MATH6)

    def test_keeps_the_sequence_and_targets(self):
        self.assertEqual(len(self.doc["sequence"]), len(MATH6["sequence"]))
        for new, old in zip(self.doc["sequence"], MATH6["sequence"]):
            for k in ("topic", "lesson_code", "district_title", "kind", "target"):
                self.assertEqual(new[k], old[k])

    def test_nothing_points_at_the_original_teachers_accounts(self):
        text = json.dumps(self.doc)
        self.assertNotIn("http", text)
        self.assertNotIn("Beach", text)
        for entry in self.doc["sequence"]:
            for k in ("homework", "link", "classwork", "extra_materials"):
                self.assertIsNone(entry[k])

    def test_starts_clean_on_its_schools_days(self):
        self.assertEqual(self.doc["changes"], [])
        self.assertEqual(self.doc["day_changes"], {})
        course = engine.course_for_render(MATH6["school_days"], self.doc)
        calendar, leftover = engine.render(course)
        self.assertEqual(leftover, engine.render(MATH6)[1])

    def test_copy_from_another_calendar_brings_its_flex_and_testing_days(self):
        school = engine.school_record(MATH6, MATH78)
        doc = engine.template_from(MATH78, school)
        own = {d["date"]: d for d in MATH78["school_days"] if d["type"] in ("Flex", "Testing", "Other")}
        self.assertEqual(set(doc["day_changes"]), set(own))
        for day in doc["day_changes"].values():
            self.assertEqual(set(day), {"date", "weekday", "type", "note"}, "no quiz or self-grading overrides")
        course = engine.course_for_render(school, doc)
        self.assertEqual([d["type"] for d in course["school_days"]],
                         [d["type"] for d in MATH78["school_days"]])
        notes = {d["note"] for d in course["school_days"] if d["type"] == "Instruction"}
        self.assertEqual(notes, {None}, "the source teacher's class-day notes don't come along")

    def test_copy_doesnt_change_the_original(self):
        self.assertEqual(MATH6, json.loads((GOLDEN / "math6.json").read_text()))


if __name__ == "__main__":
    unittest.main()
