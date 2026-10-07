"""Tests for render.py's student page, against the real course files.

Run: python3 -m unittest discover -s tests
Read-only: nothing here writes to courses/*.json.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402
import render  # noqa: E402

COURSES = [(p.stem, json.loads(p.read_text())) for p in sorted((ROOT / "courses").glob("*.json"))]


def page_and_calendar(course):
    calendar = engine.render(course)[0]
    return render.build_page(course, calendar), calendar


class PageTests(unittest.TestCase):
    def test_every_school_day_in_list_and_grid(self):
        for slug, course in COURSES:
            page, calendar = page_and_calendar(course)
            rows = set(re.findall(r'class="day [^"]*" data-date="([\d-]+)"', page))
            cells = set(re.findall(r'class="cell [^"]*" data-date="([\d-]+)"', page))
            in_months = {d["date"] for d in calendar
                         if any(x["type"] == "Instruction" and x["date"][:7] == d["date"][:7] for x in calendar)}
            self.assertEqual(rows, {d["date"] for d in calendar}, slug)
            self.assertEqual(cells, in_months, slug)

    def test_due_tag_on_exactly_the_days_something_is_due(self):
        for slug, course in COURSES:
            page, calendar = page_and_calendar(course)
            tagged = set(re.findall(r'data-date="([\d-]+)"[^>]*><span class="cell-top"><span class="cell-num">\d+</span>'
                                    + re.escape(render.DUE_TAG), page))
            self.assertEqual(tagged, {d["date"] for d in calendar if d["due"]}, slug)

    def test_due_and_given_each_get_a_line(self):
        day = {"kind": "Lesson", "due": [{"text": "Practice Log: a long sentence"}, {"text": "pg 2"}],
               "homework": [{"text": "pg 5"}]}
        self.assertEqual(render.row_summary(day), ["Due: Practice Log: a long sentence (+1 more)", "HW: pg 5"])
        self.assertEqual(render.row_summary({**day, "kind": "3-Act", "due": []}), ["3-Act task · HW: pg 5"])

    def test_topic_names_come_from_tests(self):
        self.assertEqual(render.topic_name("Topic 5 Test (CEA)"), "Topic 5")
        self.assertEqual(render.topic_name("Topic 7 Part 1 Test"), "Topic 7 Part 1")

    def test_topics_split_at_each_test_and_cover_every_day(self):
        for slug, course in COURSES:
            calendar = engine.render(course)[0]
            spans = render.topic_spans(calendar)
            tests = [d["date"] for d in calendar if d["kind"] == "Test"]
            self.assertEqual([end for _, _, end in spans][:len(tests)], tests, slug)
            self.assertEqual(spans[0][1], calendar[0]["date"], slug)

    def test_every_assignment_is_in_the_homework_view_once(self):
        for slug, course in COURSES:
            page, calendar = page_and_calendar(course)
            view = page.split('id="view-homework"')[1].split('id="view-year"')[0]
            expected = sum(1 for d in calendar for hw in d["homework"] or []
                           if hw["due"] and not engine.is_practice_log(hw))
            self.assertEqual(view.count("<li data-assigned="), expected, slug)

    def test_every_expandable_row_has_its_panel(self):
        for slug, course in COURSES:
            page, _ = page_and_calendar(course)
            controls = re.findall(r'aria-controls="(p-[\d-]+)"', page)
            panels = re.findall(r'class="panel" id="(p-[\d-]+)"', page)
            self.assertEqual(controls, panels, slug)
            self.assertEqual(len(panels), len(set(panels)), slug)

    def test_script_data_is_valid_json(self):
        for slug, course in COURSES:
            page, calendar = page_and_calendar(course)
            days = json.loads(re.search(r"const DAYS = (.*?);\n", page).group(1))
            self.assertEqual([d["date"] for d in days], [d["date"] for d in calendar], slug)
            json.loads(re.search(r"const HOMEWORK = (.*?);\n", page).group(1))
            self.assertEqual(json.loads(re.search(r"const FOCUS_UNIT = (.*?);\n", page).group(1)),
                             bool(course.get("focus_current_unit")), slug)
            self.assertEqual(json.loads(re.search(r"const CHANGES = (.*?);\n", page).group(1)),
                             course.get("changes") or [], slug)
            self.assertNotIn("%%", page, slug)  # every placeholder filled

    def test_long_titles_clamp_on_wide_cells(self):
        css = render.PAGE
        self.assertIn("-webkit-line-clamp: 2", css)

    def test_cell_labels(self):
        lesson = {"type": "Instruction", "kind": "Lesson", "lesson_text": "T1L2 Fluently Add Decimals",
                  "display": "", "note": None}
        self.assertEqual(render.cell_labels(lesson), ("T1L2", "T1L2", "Fluently Add Decimals"))
        combined = dict(lesson, lesson_text="T5L3 & T5L6 Simplify & Add")
        self.assertEqual(render.cell_labels(combined)[0], "T5L3 & T5L6")
        closed = {"type": "No School", "kind": None, "lesson_text": None, "display": "No School (Holiday)",
                  "note": "No School (Holiday)"}
        self.assertEqual(render.cell_labels(closed)[0], "Off")


if __name__ == "__main__":
    unittest.main()
