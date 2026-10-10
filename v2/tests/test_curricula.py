"""Tests for the curricula a v2 calendar starts from (curricula/*.json, read
from the district's sample calendars by scripts/import_district_calendar.py).

The PDFs aren't in the repo, so these check what was committed: each file is
a course the engine renders, it holds nothing a teacher chooses, and its day
counts per topic are the sample calendar's (checked against the district's
"at a Glance" documents on 10/10; where those disagree with their own
calendars, see DAYS). Plus the importer's cell reading, on cells as the
PDFs have them, which needs no PDF library.

Run: python3 -m unittest discover -s v2/tests
"""
import collections
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "scripts"))
from test_store import SCHOOL  # noqa: E402
import app  # noqa: E402
import engine  # noqa: E402
import import_district_calendar as imp  # noqa: E402

KEYS = [key for key, _ in app.TEMPLATES]

# Lesson days per topic (unit, for Algebra 1), from each sample calendar.
# They match the district's at-a-glance counts except: Math 6 Topic 7 (the
# glance says 21 and 20 in two places) and Topic 8 (22, though its own
# rule gives 21); Math 8 Topic 6 (the calendar repeats 6.10b after spring
# MAP); Algebra 1 Unit 2 (the calendar adds five IM Grade 8 lessons) and
# Unit 8 (the glance's window runs through the last day and snow days).
DAYS = {
    "math6": {"0": 3, "2": 15, "1": 21, "3": 21, "4": 23, "5": 25, "6": 15, "7": 21, "8": 21},
    "math8": {"0": 3, "2": 25, "3": 17, "4": 17, "5": 14, "1": 24, "6": 25, "7": 12, "8": 14},
    # Topics 10 and 13, and 12 and 11, share a review and test (counted
    # under the first); together they're the glance's 23 and 13.
    "math78": {"0": 3, "1": 16, "5": 17, "6": 18, "7": 20, "3": 13, "4": 9, "10": 16, "13": 7,
               "8": 7, "9": 10, "M8 5": 5, "2": 13, "12": 6, "11": 7},
    "algebra1": {"0": 3, "1": 16, "2": 25, "3": 13, "4": 12, "5": 25, "6": 26, "7": 18, "8": 27},
}


def load(key):
    return json.loads((ROOT / "curricula" / f"{key}.json").read_text())


class CurriculumTests(unittest.TestCase):
    def test_every_template_has_a_file(self):
        self.assertEqual(sorted(p.stem for p in (ROOT / "curricula").glob("*.json")), sorted(KEYS))

    def test_each_is_a_course_with_nothing_chosen(self):
        for key in KEYS:
            with self.subTest(key=key):
                c = load(key)
                calendar, leftover = engine.render(c)
                self.assertEqual(leftover, 0)
                self.assertFalse(any(d["kind"] in ("Quiz", "Self-Grading") for d in calendar))
                self.assertEqual((c["quiz_rule"], c["review_before_test"], c["show_classwork"]),
                                 ({"enabled": False}, False, False))
                for e in c["sequence"]:
                    self.assertIn(e["kind"], engine.VALID_LESSON_KINDS - {"Quiz"})
                    self.assertTrue(e["district_title"].strip())
                    self.assertEqual([e[f] for f in ("target", "homework", "link", "classwork")],
                                     [None] * 4)

    def test_day_counts_per_topic(self):
        for key in KEYS:
            with self.subTest(key=key):
                counts = collections.Counter(e["topic"] for e in load(key)["sequence"])
                self.assertEqual(dict(counts), DAYS[key])

    def test_it_starts_a_calendar_on_her_school_days(self):
        for key in KEYS:
            with self.subTest(key=key):
                doc = engine.template_from(load(key), SCHOOL)
                course = engine.course_for_render(SCHOOL, doc)
                self.assertEqual(engine.render(course)[1], 0)
                self.assertTrue(all(d["type"] in ("Flex", "Testing", "Other") for d in doc["day_changes"].values()))
                self.assertEqual(doc["quiz_rule"], {"enabled": False})

    def test_district_flex_and_testing_days_come_along(self):
        days = {d["date"]: d for d in load("math8")["school_days"]}
        self.assertEqual((days["2026-09-09"]["type"], days["2026-09-09"]["note"]), ("Flex", "Flex Day"))
        self.assertEqual(days["2026-10-20"]["note"], "MAP Testing")
        self.assertEqual(days["2027-05-19"]["note"], "SBA Testing")


class CellTests(unittest.TestCase):
    """Cells as pdfplumber gives them, district typos and all."""

    def read(self, key, *texts):
        seen, out = {}, []
        for text in texts:
            out += imp.ITEMS[key](imp.clean(text), seen)
        return [(e["lesson_code"], e["district_title"], e["kind"]) for e in out]

    def test_math6(self):
        self.assertEqual(self.read("math6", "1.2\nFluently Add,\nSubtract, and\nMultiply Decimals", "1.2",
                                   '1.4\n3-Act\n"Stocking Up"', "4. 10\nRelate Tables,\nGraphs", "4. 10"), [
            ("1.2", "Fluently Add, Subtract, and Multiply Decimals", "Lesson"),
            ("1.2", "Fluently Add, Subtract, and Multiply Decimals", "Lesson"),
            ("1.4", '3-Act Math: "Stocking Up"', "3-Act"),
            ("4.10", "Relate Tables, Graphs", "Lesson"), ("4.10", "Relate Tables, Graphs", "Lesson")])
        self.assertEqual(self.read("math6", "Topic 1 Opener\nPositive Rational\nNumbers", "Topic 1 Opener",
                                   "Topic 1\nAssessment\nCEA #1\nWindow:\n10/27 - 11/17"), [
            (None, "Topic 1 Opener: Positive Rational Numbers", "Opener"),
            (None, "Topic 1 Opener: Positive Rational Numbers", "Opener"),
            (None, "Topic 1 Test (CEA #1)", "Test")])

    def test_math78(self):
        self.assertEqual(self.read("math78", "5-4 Expand\nExpressions & 5-7\nSubtract\nExpressions",
                                   "Math 8 Topic 5-1 Estimate\nSolutions", "7-5 Part 1\nAssessment",
                                   "12-2 Understand\nPythagoren\nTheorem", "12-2 Understand the\nPythagorean"), [
            ("5.4 & 5.7", "Expand Expressions & Subtract Expressions", "Lesson"),
            ("M8 5.1", "Estimate Solutions", "Lesson"),
            (None, "Topic 7 Part 1 Test", "Test"),
            ("12.2", "Understand Pythagorean Theorem", "Lesson"),
            ("12.2", "Understand Pythagorean Theorem", "Lesson")])

    def test_math8(self):
        self.assertEqual(self.read("math8", "Leson 2.2a\nLet's Investigate:\nSolve Equations", "Lesson2.2b",
                                   "Lesson 1.11\nLet's Model in 3\nActs: Hard-\nWorking Organs",
                                   "Topic 2\nEnd of Topic\nAssessment", "CEA #1: Topic 3\nEnd of Topic Assessment"), [
            ("2.2", "Solve Equations", "Lesson"), ("2.2", "Solve Equations", "Lesson"),
            ("1.11", "3-Act Math: Hard-Working Organs", "3-Act"),
            (None, "Topic 2 Test", "Test"), (None, "Topic 3 Test (CEA #1)", "Test")])

    def test_algebra1(self):
        self.assertEqual(self.read("algebra1", "Alg1.1 Lesson 3: A\nGallery of Data\nAND Section A\nCheckpoint",
                                   "Math 8.4.3\nBalanced Moves\nand Math 8.4.4\nMore Balanced\nMoves",
                                   "CEA\nAlg1.2 End of Unit\nAssessment", "Alg1.8 Lesson 5: How Many",
                                   "Alg1.7 Lesson 6:\nRewriting"), [
            (None, "Unit 1 Lesson 3: A Gallery of Data + Section A Checkpoint", "Lesson"),
            (None, "Grade 8 Unit 4 Lesson 3: Balanced Moves + Grade 8 Unit 4 Lesson 4: More Balanced Moves", "Lesson"),
            (None, "Unit 2 End of Unit Assessment (CEA)", "Test"),
            (None, "Unit 8 Lesson 5: How Many", "Lesson"),
            (None, "Unit 8 Lesson 6: Rewriting", "Lesson")])  # the district's "Alg1.7" typo

    def test_days_that_arent_lessons(self):
        for text, want in (("Holiday\nNo School", "No School"), ("Flex Days", "Flex"),
                           ("Early Dismissal\nFlex Day", "Flex"), ("MAP Testing (exact\ndates vary by\nschool)", "Testing"),
                           ("Fall MAP Assessment", "Testing"), ("SBA", "Testing"),
                           ("Snow make up if\nneeded", "Other"), ("Last Day\nEarly Dismissal", "Other")):
            with self.subTest(text=text):
                self.assertEqual(imp.day_kind(imp.clean(text))[0], want)
        self.assertIsNone(imp.day_kind("1.2 Fluently Add"))

    def test_rows_are_dated_by_their_weekday(self):
        # Feb 1 and Mar 1 2027 are both Mondays; a month's first row is its own.
        self.assertEqual(imp._monday({0: "01"}, 2, 2027).isoformat(), "2027-02-01")
        self.assertEqual(imp._monday({0: "28"}, 10, 2026).isoformat(), "2026-09-28")
        with self.assertRaises(ValueError):
            imp._monday({0: "31"}, 10, 2026)  # Oct 31 2026 is a Saturday; Sep and Nov have no 31st


if __name__ == "__main__":
    unittest.main()
