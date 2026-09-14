"""Re-flow engine: (school-day calendar, course sequence) -> rendered calendar.

Instructional days take the next lesson off the sequence, in date order. Every
other day type renders as itself. Quizzes are NOT stored in the sequence --
they're computed fresh every render, straight from the rule in PLANNING.md
("quizzes go on Wednesdays, except test weeks / break-return weeks"). This
keeps quizzes correct no matter how the lesson sequence gets edited: editing
lessons only ever shifts lesson placement, never the quiz rhythm.

Because inserting a quiz can shift where a Test lands, which can change
which weeks count as "test weeks", quiz placement is solved by iterating to
a fixed point rather than computed in one pass.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

QUIZ_ITEM = {
    "topic": None, "lesson_code": None, "district_title": "Quiz",
    "kind": "Quiz", "student_text": None, "homework": None,
}

# A note mentioning "quiz" marks a day where a quiz was deliberately paired
# with a lesson instead of taking a full day (PLANNING.md's "Pairing"). The
# automatic Wednesday rule must not double up on a day already handled this
# way.
PAIRED_MARKER = "quiz"


def _week_monday(d):
    return d - timedelta(days=d.weekday())


def _break_return_wednesdays(school_days):
    """Wednesdays of any week that starts with the first school day back
    after a break of 5+ consecutive 'No School' school-calendar days."""
    return_weeks = set()
    for i, d in enumerate(school_days):
        if d["type"] == "No School":
            continue
        run = 0
        j = i - 1
        while j >= 0 and school_days[j]["type"] == "No School":
            run += 1
            j -= 1
        if run >= 5:
            return_weeks.add(_week_monday(date.fromisoformat(d["date"])))
    return {
        d["date"] for d in school_days
        if d["weekday"] == "Wed" and _week_monday(date.fromisoformat(d["date"])) in return_weeks
    }


def _place(school_days, sequence, quiz_dates):
    """Lay sequence items onto Instruction days, inserting QUIZ_ITEM (without
    consuming the sequence pointer) on each date in quiz_dates."""
    placements = []
    pointer = 0
    for day in school_days:
        if day["type"] != "Instruction":
            placements.append((day, None))
            continue
        if day["date"] in quiz_dates:
            placements.append((day, QUIZ_ITEM))
            continue
        item = sequence[pointer] if pointer < len(sequence) else None
        if item is not None:
            pointer += 1
        placements.append((day, item))
    leftover = max(0, len(sequence) - pointer)
    return placements, leftover


def _compute_quiz_dates(school_days, sequence, quiz_rhythm_start=None):
    wednesdays = [
        d["date"] for d in school_days
        if d["weekday"] == "Wed" and d["type"] == "Instruction"
        and (quiz_rhythm_start is None or d["date"] >= quiz_rhythm_start)
    ]
    break_return = _break_return_wednesdays(school_days)
    already_paired = {
        d["date"] for d in school_days
        if d["note"] and PAIRED_MARKER in d["note"].lower()
    }

    quiz_dates = set()
    for _ in range(10):
        placements, _ = _place(school_days, sequence, quiz_dates)
        test_weeks = {
            _week_monday(date.fromisoformat(day["date"]))
            for day, item in placements if item and item["kind"] == "Test"
        }
        new_quiz_dates = {
            wd for wd in wednesdays
            if wd not in already_paired
            and wd not in break_return
            and _week_monday(date.fromisoformat(wd)) not in test_weeks
        }
        if new_quiz_dates == quiz_dates:
            return quiz_dates
        quiz_dates = new_quiz_dates
    return quiz_dates  # converges in practice well within 10 iterations


def render(course):
    school_days = course["school_days"]
    sequence = course["sequence"]

    quiz_dates = _compute_quiz_dates(school_days, sequence, course.get("quiz_rhythm_start"))
    placements, leftover = _place(school_days, sequence, quiz_dates)

    calendar = []
    for day, lesson in placements:
        note = day["note"]
        if day["type"] == "Instruction":
            if lesson is None:
                base = "(no lesson planned)"
                kind = None
            else:
                text = lesson["student_text"] or lesson["district_title"]
                base = f"{lesson['lesson_code']} {text}".strip() if lesson["lesson_code"] else text
                kind = lesson["kind"]
            # A note on an instructional day is a reminder alongside the lesson
            # (a testing window, a snow-make-up flag), not a replacement for it.
            display = f"{base}\n{note}" if note else base
            calendar.append({
                "date": day["date"], "weekday": day["weekday"], "type": day["type"],
                "display": display, "lesson_text": base, "kind": kind,
                "homework": lesson["homework"] if lesson else None, "note": note,
            })
        else:
            # A non-instructional day has no lesson to show alongside, so the
            # note (e.g. "No School (Holiday)") replaces the bare type label.
            calendar.append({
                "date": day["date"], "weekday": day["weekday"], "type": day["type"],
                "display": note or day["type"], "lesson_text": None, "kind": None,
                "homework": None, "note": note,
            })
    return calendar, leftover


def check_test_placement(course):
    """Flag Tests landing somewhere PLANNING.md says to avoid. These aren't
    auto-fixed -- resolving one is an editorial call (what moves, and to
    where), so this just surfaces them for a human to decide."""
    school_days = course["school_days"]
    sequence = course["sequence"]
    quiz_dates = _compute_quiz_dates(school_days, sequence, course.get("quiz_rhythm_start"))
    placements, _ = _place(school_days, sequence, quiz_dates)
    return_weeks = {
        _week_monday(date.fromisoformat(d))
        for d in _break_return_wednesdays(school_days)
    }

    warnings = []
    for day, item in placements:
        if not item or item["kind"] != "Test":
            continue
        d = date.fromisoformat(day["date"])
        if d.weekday() == 0:
            warnings.append(f"{day['date']}: Test lands on a Monday")
        elif _week_monday(d) in return_weeks and d.weekday() in (0, 1, 2):
            warnings.append(f"{day['date']}: Test lands in the first Mon-Wed back from a break")
    return warnings


def check_unexplained_closures(course):
    """Flag a non-Instruction day with no note, sandwiched by Instruction
    days on both sides. Every *real* closure in this data (holiday, PD day,
    early dismissal) has a note explaining it -- an isolated one without a
    note has twice now turned out to be a data-entry mistake in the source
    workbook (a day that should have been Instruction). Heuristic, not a
    hard rule: a district could have a genuine unexplained one-off closure,
    but that's rare enough that a warning is worth the occasional false
    positive."""
    days = course["school_days"]
    warnings = []
    for i, d in enumerate(days):
        if d["type"] == "Instruction" or d["note"]:
            continue
        prev_instruction = i > 0 and days[i - 1]["type"] == "Instruction"
        next_instruction = i < len(days) - 1 and days[i + 1]["type"] == "Instruction"
        if prev_instruction and next_instruction:
            warnings.append(
                f"{d['date']} ({d['weekday']}): isolated '{d['type']}' with no note, "
                f"sandwiched by Instruction days -- double-check this against the source calendar"
            )
    return warnings


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "courses/math6.json")
    course = json.loads(path.read_text())
    calendar, leftover = render(course)
    print(f"leftover lessons with no day left: {leftover}", file=sys.stderr)
    for w in check_test_placement(course):
        print(f"warning: {w}", file=sys.stderr)
    for w in check_unexplained_closures(course):
        print(f"warning: {w}", file=sys.stderr)
    for day in calendar:
        if day["date"].startswith(sys.argv[2] if len(sys.argv) > 2 else "2026-09"):
            print(day["date"], day["weekday"], "|", day["display"])
