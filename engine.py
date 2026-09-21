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
    "kind": "Quiz", "target": None, "classwork": None, "homework": None,
    "link": None,
}

# The closed sets from SPEC.md's data model. Edit functions below validate
# against these instead of accepting free text.
VALID_DAY_TYPES = {"Instruction", "Flex", "Testing", "No School", "Other"}
VALID_LESSON_KINDS = {"Lesson", "Opener", "Quiz", "Test", "3-Act"}

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
                # The tile/detail title is always lesson_code + district_title --
                # never overridden by target/classwork, which are detail-only
                # (PLANNING.md: title text should be readable, not a dumping
                # ground for the day's full learning target).
                base = (
                    f"{lesson['lesson_code']} {lesson['district_title']}".strip()
                    if lesson["lesson_code"] else lesson["district_title"]
                )
                kind = lesson["kind"]
            # A note on an instructional day is a reminder alongside the lesson
            # (a testing window, a snow-make-up flag), not a replacement for it.
            display = f"{base}\n{note}" if note else base
            calendar.append({
                "date": day["date"], "weekday": day["weekday"], "type": day["type"],
                "display": display, "lesson_text": base, "kind": kind,
                "homework": lesson["homework"] if lesson else None, "note": note,
                "target": lesson.get("target") if lesson else None,
                "classwork": lesson.get("classwork") if lesson else None,
                "link": lesson.get("link") if lesson else None,
            })
        else:
            # A non-instructional day has no lesson to show alongside, so the
            # note (e.g. "No School (Holiday)") replaces the bare type label.
            calendar.append({
                "date": day["date"], "weekday": day["weekday"], "type": day["type"],
                "display": note or day["type"], "lesson_text": None, "kind": None,
                "homework": None, "note": note, "target": None, "classwork": None,
                "link": None,
            })
    return calendar, leftover


_UNSET = object()


def set_day(course, date_str, type=_UNSET, note=_UNSET):
    """Change an existing school day's type and/or note in place. This is
    how a day is spent (Instruction -> No School/Other, an assembly or snow
    day) or earned back (Flex -> Instruction). Quizzes are never touched
    here -- they're computed by render(), never stored (see module
    docstring) -- so this only ever affects the five school-day types.

    Omit `type`/`note` to leave it unchanged; pass `note=None` explicitly
    to clear an existing note (e.g. undoing an assembly note)."""
    if type is not _UNSET and type not in VALID_DAY_TYPES:
        raise ValueError(f"not a valid day type: {type!r} (want one of {sorted(VALID_DAY_TYPES)})")
    for day in course["school_days"]:
        if day["date"] == date_str:
            if type is not _UNSET:
                day["type"] = type
            if note is not _UNSET:
                day["note"] = note
            return day
    raise ValueError(f"no school day dated {date_str}")


def insert_lesson(course, index, lesson):
    """Insert one entry into the sequence at `index` (a "spend" per
    PLANNING.md's day budget -- an extra lesson day, a make-up activity).
    `lesson` needs at least `district_title`; everything else defaults.

    The tile/detail title is always `lesson_code` + `district_title` --
    never overridden by `target`/`classwork`. So `district_title` should
    already be something a student can read; if the district's own title is
    opaque, write a clearer one here rather than relying on `target` to
    stand in for it (PLANNING.md: lesson text should be written for a sixth
    grader, not copied from an opaque district title).

    `target` (the day's I-can statement) and `classwork` (the activity,
    with its point value if any) are detail-only -- shown when a student
    clicks the day, never in the tile. Both are optional.

    `link` is an optional URL to a student-facing resource for that day --
    not the lesson-builder deck itself (Aaron isn't sharing those), but
    something like a Savvas key-concept excerpt for that lesson. OneDrive
    share links work well since his students are already on Outlook
    accounts; a relative path to a file committed under docs/ also works
    for anything simple enough to keep in this repo. Rendered as a button
    on the day's detail popup; omit it for a day with nothing to attach."""
    kind = lesson.get("kind", "Lesson")
    if kind not in VALID_LESSON_KINDS:
        raise ValueError(f"not a valid lesson kind: {kind!r} (want one of {sorted(VALID_LESSON_KINDS)})")
    if kind == "Quiz":
        raise ValueError('quizzes are computed by render(), never stored in the sequence -- see module docstring')
    entry = {
        "topic": lesson.get("topic"),
        "lesson_code": lesson.get("lesson_code"),
        "district_title": lesson["district_title"],
        "kind": kind,
        "target": lesson.get("target"),
        "classwork": lesson.get("classwork"),
        "homework": lesson.get("homework"),
        "link": lesson.get("link"),
    }
    seq = course["sequence"]
    if not 0 <= index <= len(seq):
        raise IndexError(f"sequence index {index} out of range (0-{len(seq)})")
    seq.insert(index, entry)
    return entry


def cut_lesson(course, index):
    """Remove one entry from the sequence (an "earn" per PLANNING.md's day
    budget -- cutting an Opener, a 3-Act, or a duplicate lesson day)."""
    seq = course["sequence"]
    if not 0 <= index < len(seq):
        raise IndexError(f"sequence index {index} out of range (0-{len(seq) - 1})")
    return seq.pop(index)


def edit_lesson(course, index, **fields):
    """Update fields (district_title, homework, target, classwork, link,
    ...) on an existing sequence entry in place. Content only -- no
    day-budget effect."""
    seq = course["sequence"]
    if not 0 <= index < len(seq):
        raise IndexError(f"sequence index {index} out of range (0-{len(seq) - 1})")
    entry = seq[index]
    for key, value in fields.items():
        if key not in entry:
            raise ValueError(f"not a sequence field: {key!r} (want one of {sorted(entry)})")
        if key == "kind" and value not in VALID_LESSON_KINDS:
            raise ValueError(f"not a valid lesson kind: {value!r} (want one of {sorted(VALID_LESSON_KINDS)})")
        entry[key] = value
    return entry


def diff_impact(course, before_calendar, before_leftover):
    """Compare a pre-edit render() snapshot against the course's current
    state. Call render() before editing, make the edit, then pass its
    result here -- gives back the leftover-count change and the first date
    where the rendered calendar actually starts differing, which is what
    "everything after here shifted" means in practice. Report this in
    Aaron's terms (dates, what moved), not by dumping the raw diff."""
    after_calendar, after_leftover = render(course)
    first_shifted_date = None
    for before_day, after_day in zip(before_calendar, after_calendar):
        if before_day["display"] != after_day["display"]:
            first_shifted_date = after_day["date"]
            break
    return {
        "leftover_before": before_leftover,
        "leftover_after": after_leftover,
        "first_shifted_date": first_shifted_date,
    }


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


def check_lesson_shortfall(course):
    """Flag Instructional days with nothing planned -- the mirror image of
    the surplus `leftover` already returned by render(). render()'s leftover
    can only ever report the sequence running long (lessons with no day
    left); it floors at zero, so it can't represent the opposite case
    (sequence running out before days do). Not auto-fixed -- adding content
    or cutting a day is an editorial call -- so this just surfaces it."""
    calendar, _ = render(course)
    empty_dates = [
        d["date"] for d in calendar
        if d["type"] == "Instruction" and d["kind"] is None
    ]
    if not empty_dates:
        return []
    return [
        f"{len(empty_dates)} instructional day(s) with nothing planned, "
        f"{empty_dates[0]} through {empty_dates[-1]}"
    ]


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


def run_all_checks(course):
    """Every check.yield/render together, as (label, [warnings]) pairs --
    the one place that knows the full checklist, so nothing added here has
    to be separately wired into the CLI, the import script, and anywhere
    else that wants "is this course file okay?" See PLANNING.md's Sanity
    checks section, which this is meant to mirror."""
    return [
        ("test placement", check_test_placement(course)),
        ("unexplained closures", check_unexplained_closures(course)),
        ("lesson shortfall", check_lesson_shortfall(course)),
    ]


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "courses/math6.json")
    course = json.loads(path.read_text())
    calendar, leftover = render(course)
    print(f"leftover lessons with no day left: {leftover}", file=sys.stderr)
    for label, warnings in run_all_checks(course):
        for w in warnings:
            print(f"warning ({label}): {w}", file=sys.stderr)
    for day in calendar:
        if day["date"].startswith(sys.argv[2] if len(sys.argv) > 2 else "2026-09"):
            print(day["date"], day["weekday"], "|", day["display"])
