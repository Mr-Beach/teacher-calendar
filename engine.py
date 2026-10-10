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

The Wednesday of the week after a topic test is the test self-grading day
(SELF_GRADING_ITEM), also computed, never stored: it takes that week's quiz
slot, so it never moves a lesson.

A school day's optional `quiz` overrides the rule for that one day (see
QUIZ_OVERRIDES). It's the only override: a day's note is plain
student-facing text and never changes placement.
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

QUIZ_ITEM = {
    "topic": None, "lesson_code": None, "district_title": "Quiz",
    "kind": "Quiz", "target": None, "classwork": None, "homework": None,
    "link": None, "extra_materials": None,
}

# The Wednesday after a test week: students grade their own test (PLANNING.md,
# "Assessments"). Like QUIZ_ITEM, computed by render() and never stored.
SELF_GRADING_ITEM = {
    "topic": None, "lesson_code": None, "district_title": "Test Self-Grading",
    "kind": "Self-Grading", "target": None, "classwork": None, "homework": None,
    "link": None, "extra_materials": None,
}

# The closed sets from SPEC.md's data model. Edit functions below validate
# against these instead of accepting free text.
VALID_DAY_TYPES = {"Instruction", "Flex", "Testing", "No School", "Other"}
VALID_LESSON_KINDS = {"Lesson", "Opener", "Quiz", "Test", "3-Act", "Project"}
# The kinds students are assessed on, computed ones included. Their dates
# count as set as soon as they're on the calendar (PLANNING.md, "Set and
# planned days").
ASSESSMENT_KINDS = {"Quiz", "Test", "Project", "Self-Grading"}
# What an Instruction day shows when the sequence has run out.
NO_LESSON = "(no lesson planned)"

# A school day's optional "quiz" field -- the one way to override the
# Wednesday rule on a given day. Absent means the rule decides.
#   "none":   no quiz here (a week that needs none for a reason outside the
#             rule's exceptions, or the Wednesday half of moving a quiz).
#   "paired": the quiz shares the period with that day's lesson
#             (PLANNING.md's "Pairing") -- the lesson still takes the day,
#             and the page shows the quiz alongside it.
#   "full":   a full-period quiz day here even where the rule wouldn't put
#             one (the other half of moving a quiz, e.g. to Thursday).
QUIZ_OVERRIDES = {"none", "paired", "full"}

# The quiz rule, as settings (SPEC-v2's "Recurring activities", for the
# quiz). A course's optional "quiz_rule" overrides any of these; without
# one, the rule is exactly PLANNING.md's: Wednesdays, every week, a full
# period, with its three skips. v1's "quiz_rhythm_start" and "quiz_link"
# still supply the start and link, so Aaron's course files need no change.
#   enabled:      False means no quizzes from the rule (a "full" day
#                 override still makes one).
#   weekday:      "Mon".."Fri".
#   every_weeks:  1, or 2 for every other week, counted in calendar weeks
#                 from `start`'s week (a skipped week still counts).
#   start:        first date the rule applies from (None: the first day).
#   sits:         "full" takes the whole period and lessons flow past it;
#                 "shared" shares the period with that day's lesson, like
#                 a "paired" day override, and moves nothing.
#   skip:         which of QUIZ_SKIPS apply.
#   link:         where students find the quizzes.
#   self_grading: whether the test self-grading day takes the quiz slot
#                 the week after a test (and is checked for).
QUIZ_SKIPS = {"test_week", "break_return", "day_before_thanksgiving"}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
_WEEKDAY_NAMES = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
                  "Thu": "Thursday", "Fri": "Friday"}
QUIZ_RULE_DEFAULTS = {
    "enabled": True, "weekday": "Wed", "every_weeks": 1, "start": None,
    "sits": "full", "skip": sorted(QUIZ_SKIPS), "link": None, "self_grading": True,
}


def quiz_rule(course):
    """The course's effective quiz rule: QUIZ_RULE_DEFAULTS, then v1's
    quiz_rhythm_start/quiz_link, then its own "quiz_rule". Raises
    ValueError on a setting it doesn't recognize."""
    rule = dict(QUIZ_RULE_DEFAULTS, start=course.get("quiz_rhythm_start"),
                link=course.get("quiz_link"))
    rule.update(course.get("quiz_rule") or {})
    if set(rule) != set(QUIZ_RULE_DEFAULTS):
        raise ValueError(f"unknown quiz_rule setting(s): {sorted(set(rule) - set(QUIZ_RULE_DEFAULTS))}")
    if rule["weekday"] not in WEEKDAYS:
        raise ValueError(f"quiz_rule weekday must be one of {WEEKDAYS}, got {rule['weekday']!r}")
    if rule["every_weeks"] not in (1, 2):
        raise ValueError(f"quiz_rule every_weeks must be 1 or 2, got {rule['every_weeks']!r}")
    if rule["sits"] not in ("full", "shared"):
        raise ValueError(f"quiz_rule sits must be 'full' or 'shared', got {rule['sits']!r}")
    if set(rule["skip"]) - QUIZ_SKIPS:
        raise ValueError(f"quiz_rule skip must come from {sorted(QUIZ_SKIPS)}, got {rule['skip']!r}")
    return rule


# A school day's optional "self_grading" field: "paired" puts test
# self-grading in the same period as that day's lesson -- for a test whose
# following Wednesday has no quiz slot to take (check_self_grading).
# Nothing moves; the page shows "+ Test self-grading" on the lesson.
# "full" makes the day a whole-period self-grading day whatever the quiz
# rule says, like a "full" quiz override (lessons flow past it). v2 uses it
# to keep a past self-grading day where it was when the quiz weekday changes.
SELF_GRADING_OVERRIDES = {"paired", "full"}


def display_code(lesson_code):
    """Show a stored lesson_code the way Schoology and Aaron's files name it:
    "1.6" -> "T1L6", "5.3 & 5.6" -> "T5L3 & T5L6", "M8 5.1" -> "M8 T5L1".
    Storage stays "1.6" -- week files and apply_week.py match on that."""
    return re.sub(r"\b(\d+)\.(\d+)\b", r"T\1L\2", lesson_code)


def normalize_homework(value):
    """Canonical form of a lesson's `homework`: a list of
    {"text": ..., "due": "YYYY-MM-DD" or None}, or None for nothing assigned.
    An item may also carry an optional "link" -- where students find that
    assignment (e.g. a study guide in a review folder, not the day's lesson
    folder). It's kept only when set, so unlinked items stay two-key.
    A Practice Log item may carry "includes" -- the assignments it covers,
    each {"text", "due"}, copied from the homework they name -- for a log
    the automatic due-date window would get wrong (see
    _practice_log_contents). Kept only when set.

    Homework is stored once, on the lesson it's assigned with -- never
    repeated on later days. `due` is a fixed calendar date: it's how much
    time students were given, not tied to content, so a lost day that shifts
    the lesson (and so the day it's assigned) never moves the due date.
    A plain string is accepted as an assignment with no due date."""
    if value is None or value == []:
        return None
    if not isinstance(value, list):
        raise ValueError("homework must be a list of assignments, or null")
    items = []
    for item in value:
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict) or set(item) - {"text", "due", "link", "includes"}:
            raise ValueError(f'each homework item needs "text" and optionally "due"/"link"/"includes", got {item!r}')
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"homework text must be a non-empty string, got {text!r}")
        due = item.get("due")
        if due is not None:
            try:
                date.fromisoformat(due)
            except (TypeError, ValueError):
                raise ValueError(f"homework due date must be YYYY-MM-DD, got {due!r}") from None
        hw = {"text": text.strip(), "due": due}
        link = item.get("link")
        if link is not None:
            if not isinstance(link, str) or not link.strip():
                raise ValueError(f"homework link must be a non-empty string, got {link!r}")
            hw["link"] = link.strip()
        includes = item.get("includes")
        if includes is not None:
            covered = normalize_homework(includes)
            if not covered or any(set(c) - {"text", "due"} for c in covered):
                raise ValueError(f'"includes" must be a non-empty list of {{"text", "due"}}, got {includes!r}')
            hw["includes"] = covered
        items.append(hw)
    return items


# --- Dates, as every page and script shows them ------------------------------

def week_monday(iso):
    """The Monday of an ISO date's week, as a date."""
    d = date.fromisoformat(iso)
    return d - timedelta(days=d.weekday())


def month_day(iso):
    """'2026-09-29' -> '9/29'."""
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}"


def short_date(iso):
    """'2026-09-29' -> 'Tue 9/29', the way due dates read to students."""
    return f"{date.fromisoformat(iso).strftime('%a')} {month_day(iso)}"


def _day_before_thanksgiving(year):
    """The Wednesday before US Thanksgiving (the fourth Thursday of
    November), as an ISO date -- PLANNING.md's third no-quiz exception."""
    nov1 = date(year, 11, 1)
    first_thursday = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    return (first_thursday + timedelta(weeks=3, days=-1)).isoformat()


def lesson_title(item):
    """A sequence entry's tile/detail title: lesson_code (shown as T1L6) +
    district_title -- never target/classwork, which are detail-only
    (PLANNING.md: title text should be readable, not a dumping ground for
    the day's full learning target)."""
    if item["lesson_code"]:
        return f"{display_code(item['lesson_code'])} {item['district_title']}".strip()
    return item["district_title"]


def _break_return_weeks(school_days):
    """Mondays of any week that starts with the first school day back
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
            return_weeks.add(week_monday(d["date"]))
    return return_weeks


def _break_return_days(school_days, weekday="Wed"):
    """The `weekday` of each break-return week (_break_return_weeks)."""
    return_weeks = _break_return_weeks(school_days)
    return {
        d["date"] for d in school_days
        if d["weekday"] == weekday and week_monday(d["date"]) in return_weeks
    }


def _place(school_days, sequence, quiz_dates, self_grading_dates=frozenset()):
    """Lay sequence items onto Instruction days, inserting QUIZ_ITEM (without
    consuming the sequence pointer) on each date in quiz_dates --
    SELF_GRADING_ITEM instead on those also in self_grading_dates."""
    placements = []
    pointer = 0
    for day in school_days:
        if day["type"] != "Instruction":
            placements.append((day, None))
            continue
        if day["date"] in quiz_dates:
            placements.append((day, SELF_GRADING_ITEM if day["date"] in self_grading_dates
                               else QUIZ_ITEM))
            continue
        item = sequence[pointer] if pointer < len(sequence) else None
        if item is not None:
            pointer += 1
        placements.append((day, item))
    leftover = max(0, len(sequence) - pointer)
    return placements, leftover


def _is_stored_lesson(item):
    """Whether a placed item is a sequence entry -- not nothing, and not a
    computed quiz or self-grading day."""
    return item is not None and item is not QUIZ_ITEM and item is not SELF_GRADING_ITEM


def _forced_quiz_dates(school_days):
    """Days with a "full" quiz override, or a "full" self-grading one: a
    full-period quiz slot whatever the rule says."""
    return {d["date"] for d in school_days
            if (d.get("quiz") == "full" or d.get("self_grading") == "full") and d["type"] == "Instruction"}


def _forced_self_grading_dates(school_days):
    """Days with a "full" self-grading override (SELF_GRADING_OVERRIDES)."""
    return {d["date"] for d in school_days
            if d.get("self_grading") == "full" and d["type"] == "Instruction"}


def _full_dates(rule, quiz_dates, forced):
    """The quiz slots that take a whole period: all of them under a "full"
    rule, only the forced ones under a "shared" rule."""
    return quiz_dates if rule["sits"] == "full" else quiz_dates & forced


def _compute_quiz_dates(school_days, sequence, rule):
    """Every quiz slot: the rule's days (minus its skips and any day with a
    `quiz` override) plus the forced ones. Full-period quizzes can push a
    Test into a different week, which changes which weeks are test weeks,
    so this iterates to a fixed point."""
    forced = _forced_quiz_dates(school_days)
    if not rule["enabled"]:
        return set(forced)
    start = rule["start"]
    first_monday = week_monday(start or school_days[0]["date"])
    candidates = [
        d["date"] for d in school_days
        if d["weekday"] == rule["weekday"] and d["type"] == "Instruction"
        and (start is None or d["date"] >= start)
        and (week_monday(d["date"]) - first_monday).days // 7 % rule["every_weeks"] == 0
    ]
    skip = set(rule["skip"])
    break_return = _break_return_days(school_days, rule["weekday"]) if "break_return" in skip else set()
    overridden = {d["date"] for d in school_days if d.get("quiz")}

    quiz_dates = set()
    for _ in range(10):
        placements, _ = _place(school_days, sequence, _full_dates(rule, quiz_dates, forced))
        test_weeks = _test_weeks(placements) if "test_week" in skip else set()
        new_quiz_dates = forced | {
            qd for qd in candidates
            if qd not in overridden
            and qd not in break_return
            and not ("day_before_thanksgiving" in skip and qd == _day_before_thanksgiving(int(qd[:4])))
            and week_monday(qd) not in test_weeks
        }
        if new_quiz_dates == quiz_dates:
            return quiz_dates
        quiz_dates = new_quiz_dates
    return quiz_dates  # converges in practice well within 10 iterations


def _test_weeks(placements):
    return {week_monday(day["date"])
            for day, item in placements if item and item["kind"] == "Test"}


def _self_grading_day(test_week_monday, weekday="Wed"):
    """The quiz weekday of the week after a test week."""
    return (test_week_monday + timedelta(days=7 + WEEKDAYS.index(weekday))).isoformat()


def _compute_self_grading_dates(school_days, sequence, quiz_dates, rule):
    """The quiz slots that fall on the quiz weekday of the week after a
    test week. Only an existing quiz slot qualifies -- self-grading
    replaces that week's quiz, so it never moves a lesson. A day with no
    quiz slot (a holiday, a `quiz` override) gets none; check_self_grading
    flags it. A "full" override on that day keeps the quiz."""
    if not rule["self_grading"]:
        return set()
    forced = _forced_quiz_dates(school_days)
    placements, _ = _place(school_days, sequence, _full_dates(rule, quiz_dates, forced))
    return ({_self_grading_day(m, rule["weekday"]) for m in _test_weeks(placements)}
            & (quiz_dates - forced))


def _placement(course):
    """(placements, leftover, shared_quiz, shared_self_grading): place()'s
    result plus the dates a "shared" quiz rule pairs a quiz, or the test
    self-grading that replaces it, with that day's lesson."""
    school_days, sequence = course["school_days"], course["sequence"]
    rule = quiz_rule(course)
    quiz_dates = _compute_quiz_dates(school_days, sequence, rule)
    self_grading = (_compute_self_grading_dates(school_days, sequence, quiz_dates, rule)
                    | _forced_self_grading_dates(school_days))
    full = _full_dates(rule, quiz_dates, _forced_quiz_dates(school_days))
    placements, leftover = _place(school_days, sequence, full, self_grading & full)
    shared = quiz_dates - full
    return placements, leftover, shared - self_grading, shared & self_grading


def _homework_with_links(lesson):
    """A lesson's homework as rendered, each item with a "link" key: its own
    `link` (the assignment's page in Schoology), or None. It deliberately
    doesn't fall back to the lesson's `link` -- that's the lesson folder, and
    an assignment should open the assignment itself. An unlinked assignment
    is flagged by check_homework_links instead."""
    if not lesson:
        return []
    return [{**hw, "link": hw.get("link")}
            for hw in normalize_homework(lesson.get("homework")) or []]


def is_practice_log(hw):
    """A Practice Log is the two-week container students record their practice
    in -- recognized by its text, since it's entered like any other homework."""
    return hw["text"].lower().startswith("practice log")


def _practice_log_contents(placements):
    """What each Practice Log covers: every other assignment due from the day
    the log is assigned through the day it's due, soonest first. Derived, not
    stored, so the list follows the homework as it's planned and never needs
    re-entering -- unless the log lists its own "includes" (a log whose
    window doesn't match its contents), whose items pick up the link of the
    assignment they name. Each item also says the day it's given
    ("assigned"; None for one the calendar doesn't have), since a log can
    cover assignments not given yet. Keyed by (assigned date, log text)."""
    assigned = [(day["date"], hw) for day, lesson in placements
                for hw in _homework_with_links(lesson)]
    given = {(hw["text"], hw["due"]): (date_, hw["link"]) for date_, hw in assigned}
    contents = {}
    for start, log in assigned:
        if not is_practice_log(log):
            continue
        if log.get("includes"):
            covered = log["includes"]
        elif log["due"]:
            covered = sorted(({"text": hw["text"], "due": hw["due"]} for _, hw in assigned
                              if hw["due"] and not is_practice_log(hw) and start <= hw["due"] <= log["due"]),
                             key=lambda hw: hw["due"])
        else:
            continue
        contents[(start, log["text"])] = []
        for c in covered:
            day, link = given.get((c["text"], c["due"]), (None, None))
            contents[(start, log["text"])].append({**c, "link": link, "assigned": day})
    return contents


def shows_classwork(course):
    """Whether a course shows class work at all (its "show_classwork",
    default on). Off, render() blanks every day's class work, so nothing
    downstream -- the page, the look-ahead, change tracking -- sees it; what's
    stored stays, and turning it back on brings it back."""
    return course.get("show_classwork", True)


def place(course):
    """(placements, leftover): each school day paired with the sequence
    entry, QUIZ_ITEM, or None that lands on it -- the one placement every
    caller shares, so nothing can disagree with render()."""
    return _placement(course)[:2]


def set_through(course):
    """The course's "set through" date (ISO), or None if it doesn't use one.
    Every day up to and including it is set: its target, homework, due
    dates, and links are final. Every day after it is planned: the expected
    lesson order and homework, which may still shift (PLANNING.md, "Set
    and planned days"). Aaron sets one week at a time."""
    value = course.get("set_through")
    if value is not None:
        date.fromisoformat(value)  # raises ValueError on a malformed date
    return value


def set_floor(today=None):
    """The last date that counts as set whatever a course's set_through
    says: the Friday of the school week students are in -- this week on a
    weekday, the coming week on a weekend. A set-through date nobody
    advanced can never leave the days students are using unnoticed."""
    today = today or school_today()
    monday = week_monday(today.isoformat()) + timedelta(days=7 if today.weekday() >= 5 else 0)
    return (monday + timedelta(days=4)).isoformat()


def render(course):
    placements, leftover, shared_quiz, shared_sg = _placement(course)
    through = set_through(course)
    quiz_link = quiz_rule(course)["link"]

    # Homework shows twice: on the day it's assigned (with its lesson) and on
    # its due date, which is fixed and independent of where lessons land.
    # A Practice Log carries the assignments it covers ("includes"; the page
    # shows them as a checklist on the log's due date), and each assignment
    # it covers carries that log's due date ("log_due"; the page tags the
    # assignment with it) and its link ("log_link": the log's answer-key
    # folder, where the page sends it for its key). An assignment in two
    # logs gets the earlier one.
    log_contents = _practice_log_contents(placements)
    log_due_of, log_link_of = {}, {}
    for day, lesson in placements:
        for log in _homework_with_links(lesson):
            covered = log_contents.get((day["date"], log["text"]))
            if not covered or not log["due"]:
                continue
            for c in covered:
                key = (c["text"], c["due"])
                if key not in log_due_of or log["due"] < log_due_of[key]:
                    log_due_of[key] = log["due"]
                    log_link_of[key] = log["link"]

    def homework_for(day, lesson):
        items = _homework_with_links(lesson)
        for hw in items:
            if (day["date"], hw["text"]) in log_contents:
                hw["includes"] = log_contents[(day["date"], hw["text"])]
            elif (hw["text"], hw["due"]) in log_due_of:
                hw["log_due"] = log_due_of[(hw["text"], hw["due"])]
                hw["log_link"] = log_link_of[(hw["text"], hw["due"])]
        return items

    due_by_date = {}
    for day, lesson in placements:
        for hw in homework_for(day, lesson):
            if hw["due"]:
                entry = {"text": hw["text"], "assigned": day["date"], "link": hw["link"]}
                if "includes" in hw:
                    entry["includes"] = hw["includes"]
                if "log_due" in hw:
                    entry["log_due"] = hw["log_due"]
                    entry["log_link"] = hw["log_link"]
                due_by_date.setdefault(hw["due"], []).append(entry)

    calendar = []
    for day, lesson in placements:
        note = day["note"]
        # A non-instructional day has no lesson to show alongside, so the
        # note (e.g. "No School (Holiday)") replaces the bare type label.
        entry = {
            "date": day["date"], "weekday": day["weekday"], "type": day["type"],
            "set": through is None or day["date"] <= through,
            "display": note or day["type"], "lesson_text": None, "kind": None,
            "quiz_paired": False, "self_grading_paired": False,
            "homework": None, "due": due_by_date.get(day["date"]), "note": note,
            # True, or which periods ("4th period"): set_day's teacher_out.
            "teacher_out": day.get("teacher_out"),
            "target": None, "classwork": None, "link": None, "extra_materials": None,
        }
        if day["type"] == "Instruction":
            base = lesson_title(lesson) if lesson else NO_LESSON
            stored = _is_stored_lesson(lesson)
            entry.update({
                # A note on an instructional day is a reminder alongside the lesson
                # (a testing window, a snow-make-up flag), not a replacement for it.
                "display": f"{base}\n{note}" if note else base,
                "lesson_text": base, "kind": lesson["kind"] if lesson else None,
                # A quiz or self-grading sharing the period with this lesson
                # (QUIZ_OVERRIDES, SELF_GRADING_OVERRIDES, a "shared" rule).
                "quiz_paired": stored and (day.get("quiz") == "paired" or day["date"] in shared_quiz),
                "self_grading_paired": stored and (day.get("self_grading") == "paired"
                                                   or day["date"] in shared_sg),
                "homework": homework_for(day, lesson) or None,
            })
        if lesson:
            entry.update({
                "target": lesson.get("target"),
                "classwork": lesson.get("classwork") if shows_classwork(course) else None,
                # A computed quiz day has no stored entry to carry a link, so
                # every quiz links to the course's one quiz folder.
                "link": quiz_link if lesson is QUIZ_ITEM else lesson.get("link"),
                "extra_materials": lesson.get("extra_materials"),
            })
        calendar.append(entry)
    return calendar, leftover


_UNSET = object()


def set_day(course, date_str, type=_UNSET, note=_UNSET, quiz=_UNSET, self_grading=_UNSET,
            teacher_out=_UNSET):
    """Change an existing school day's type, note, and/or quiz override in
    place. Changing the type is how a day is spent (Instruction -> No
    School/Other, an assembly or snow day) or earned back (Flex ->
    Instruction).

    `quiz` overrides the Wednesday rule on this one day -- "none",
    "paired", or "full" (see QUIZ_OVERRIDES) -- and `quiz=None` removes
    the override so the rule decides again. Quizzes themselves are still
    never stored; render() computes them, honoring this. Moving a quiz is
    two calls: quiz="none" on its Wednesday, quiz="full" on the new day.

    `self_grading="paired"` puts test self-grading in this day's period
    alongside its lesson (see SELF_GRADING_OVERRIDES); `None` removes it.

    `teacher_out` marks a day the teacher is out, for the page's "Mr. Beach
    is out today": True for every period of this course, or which ones as
    words ("4th period") when only some are. `None` removes it. Nothing
    moves -- a sub runs the day's plan.

    Omit an argument to leave it unchanged; pass `note=None` explicitly
    to clear an existing note (e.g. undoing an assembly note)."""
    if type is not _UNSET and type not in VALID_DAY_TYPES:
        raise ValueError(f"not a valid day type: {type!r} (want one of {sorted(VALID_DAY_TYPES)})")
    if quiz is not _UNSET and quiz is not None and quiz not in QUIZ_OVERRIDES:
        raise ValueError(f"not a valid quiz override: {quiz!r} (want one of {sorted(QUIZ_OVERRIDES)}, or None)")
    if teacher_out is not _UNSET and not (teacher_out is None or teacher_out is True
                                          or (isinstance(teacher_out, str) and teacher_out.strip())):
        raise ValueError(f"teacher_out is True, the periods as words, or None, got {teacher_out!r}")
    if self_grading is not _UNSET and self_grading is not None and self_grading not in SELF_GRADING_OVERRIDES:
        raise ValueError(f"not a valid self_grading override: {self_grading!r} "
                         f"(want one of {sorted(SELF_GRADING_OVERRIDES)}, or None)")
    for day in course["school_days"]:
        if day["date"] == date_str:
            new_type = day["type"] if type is _UNSET else type
            new_sg = day.get("self_grading") if self_grading is _UNSET else self_grading
            if new_sg and new_type != "Instruction":
                raise ValueError(f"{date_str} would be a '{new_type}' day -- self-grading needs an Instruction day")
            new_quiz = day.get("quiz") if quiz is _UNSET else quiz
            if new_quiz in ("paired", "full") and new_type != "Instruction":
                raise ValueError(f"{date_str} would be a '{new_type}' day -- a quiz needs an Instruction day")
            new_out = day.get("teacher_out") if teacher_out is _UNSET else teacher_out
            if new_out and new_type == "No School":
                raise ValueError(f"{date_str} is a 'No School' day -- there's no class to be out of")
            day["type"] = new_type
            if note is not _UNSET:
                day["note"] = note
            if new_quiz is None:
                day.pop("quiz", None)
            else:
                day["quiz"] = new_quiz
            if new_sg is None:
                day.pop("self_grading", None)
            else:
                day["self_grading"] = new_sg
            if new_out is None:
                day.pop("teacher_out", None)
            else:
                day["teacher_out"] = new_out.strip() if isinstance(new_out, str) else new_out
            return day
    raise ValueError(f"no school day dated {date_str}")


# --- v2: calendars stored apart from their school's days ---------------
#
# In v2 (SPEC-v2.md, "Data model") a school's days are stored once and
# shared, and a calendar stores only its own differences from them, in
# "day_changes": {date: that whole day as this calendar has it}. These
# turn one into the course dict every function here takes, and back.


def course_for_render(school_days, doc):
    """A course dict from a school's days and a v2 calendar document:
    the school's days, with this calendar's own changed days in place of
    the school's."""
    changes = doc.get("day_changes") or {}
    dates = {d["date"] for d in school_days}
    stray = sorted(set(changes) - dates)
    if stray:
        raise ValueError(f"day_changes for dates that aren't school days: {stray}")
    course = {k: v for k, v in doc.items() if k != "day_changes"}
    course["school_days"] = [dict(changes.get(d["date"], d)) for d in school_days]
    return course


def split_course(course, school_days):
    """The inverse of course_for_render: a course dict as a v2 calendar
    document, keeping only the days that differ from the school's."""
    if [d["date"] for d in course["school_days"]] != [d["date"] for d in school_days]:
        raise ValueError("the course's days and the school's days aren't the same dates")
    doc = {k: v for k, v in course.items() if k != "school_days"}
    doc["day_changes"] = {d["date"]: dict(d) for d, s in zip(course["school_days"], school_days)
                          if d != s}
    return doc


# What a copy of a course keeps (SPEC-v2, Phase 1: "start from a copy of my
# Math 6 sequence"): the district's sequence and the I-can targets, nothing
# that points at the original teacher's accounts or is her own planning.
# "credits": the attribution its licensed content requires (a curriculum's
# publisher targets), which has to travel with them.
_TEMPLATE_KEEPS = ("course", "school_year", "quiz_rhythm_start", "show_classwork", "credits",
                   "focus_current_unit", "daily_materials", "due_notes", "review_before_test")
_TEMPLATE_LESSON_KEEPS = ("topic", "lesson_code", "district_title", "kind", "target")


def school_record(*courses):
    """A school's shared days, from course dicts at that school: every
    closure ('No School') they all agree on, with its note, and every other
    day a plain Instruction day. Flex, testing, and 'Other' days aren't in
    it: they differ by course (where a teacher put her Flex days, which day
    her class tests), so each calendar keeps its own as day changes.
    Raises ValueError if the courses disagree on a closure."""
    first = courses[0]["school_days"]
    for course in courses[1:]:
        if [d["date"] for d in course["school_days"]] != [d["date"] for d in first]:
            raise ValueError(f"{course.get('course')!r} has different dates from {courses[0].get('course')!r}")
    record = []
    for days in zip(*(c["school_days"] for c in courses)):
        closed = {(d["type"] == "No School", d["note"] if d["type"] == "No School" else None) for d in days}
        if len(closed) > 1:
            raise ValueError(f"the courses disagree on whether {days[0]['date']} is a closure")
        is_closed, note = closed.pop()
        record.append({"date": days[0]["date"], "weekday": days[0]["weekday"],
                       "type": "No School" if is_closed else "Instruction", "note": note})
    return record


def template_from(course, school_days=None):
    """A new v2 calendar document copied from `course` (any calendar --
    "start from Math 7/8"): lesson codes, titles, kinds, and targets, with
    links, class work, homework, and extra materials cleared. Drops the
    change log, the teacher's name, and every link (quiz_link,
    answer_key_link, quiz_rule's link).

    With `school_days` (the new calendar's school record), it also copies
    the source's Flex, Testing, and 'Other' days, with their notes, as
    the new calendar's day changes. It never copies the source teacher's
    own planning: quiz and self-grading overrides, or her notes on class
    days."""
    doc = {k: course[k] for k in _TEMPLATE_KEEPS if k in course}
    if course.get("quiz_rule"):
        doc["quiz_rule"] = {k: v for k, v in course["quiz_rule"].items() if k != "link"}
    doc["sequence"] = [
        {**{k: entry.get(k) for k in _TEMPLATE_LESSON_KEEPS},
         "homework": None, "link": None, "classwork": None, "extra_materials": None}
        for entry in course["sequence"]
    ]
    doc["changes"] = []
    doc["day_changes"] = {}
    if school_days is not None:
        school = {d["date"]: d for d in school_days}
        for d in course["school_days"]:
            s = school.get(d["date"])
            if s and s["type"] == "Instruction" and d["type"] in ("Flex", "Testing", "Other"):
                doc["day_changes"][d["date"]] = {"date": d["date"], "weekday": d["weekday"],
                                                 "type": d["type"], "note": d["note"]}
    return doc


def set_daily_materials(course, items):
    """Replace the course-wide baseline materials list (course['daily_materials'])
    -- what a student needs every school day, regardless of lesson (a
    Chromebook, a pencil), as opposed to a specific lesson's
    `extra_materials`. Rare to change; rewrites the whole list rather than
    adding/removing one item at a time."""
    course["daily_materials"] = list(items)


def _check_index(seq, index, inserting=False):
    """Raise IndexError unless `index` is a sequence position -- or, when
    `inserting`, one past the end."""
    last = len(seq) if inserting else len(seq) - 1
    if not 0 <= index <= last:
        raise IndexError(f"sequence index {index} out of range (0-{last})")


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
    taps the day, never on its row or month square. Both are optional.

    `homework` is a list of assignments given on this day, each
    {"text": ..., "due": "YYYY-MM-DD"} (see normalize_homework). Each is
    stored only here, on the day it's assigned -- render() also shows it on
    its due date, so never repeat it on later days. Omit or pass `[]`/`None`
    for a day with nothing assigned.

    `link` is an optional URL to a student-facing resource for that day --
    not the lesson-builder deck itself (Aaron isn't sharing those), but
    something like a Savvas key-concept excerpt for that lesson. OneDrive
    share links work well since his students are already on Outlook
    accounts; a relative path to a file committed under docs/ also works
    for anything simple enough to keep in this repo. Rendered as the "Open the
    lesson" button in the day's details; omit it for a day with nothing to attach.

    `extra_materials` is an optional list of strings -- items needed for
    this lesson specifically (scissors, glue stick for a cut-and-paste
    activity), on top of the daily baseline in `course["daily_materials"]`.
    Omit it for a lesson that needs nothing beyond the daily baseline."""
    kind = lesson.get("kind", "Lesson")
    if kind not in VALID_LESSON_KINDS:
        raise ValueError(f"not a valid lesson kind: {kind!r} (want one of {sorted(VALID_LESSON_KINDS)})")
    if kind == "Quiz":
        raise ValueError('quizzes are computed by render(), never stored in the sequence -- see module docstring')
    if kind == SELF_GRADING_ITEM["kind"]:
        raise ValueError('self-grading days are computed by render(), never stored in the sequence -- see module docstring')
    entry = {
        "topic": lesson.get("topic"),
        "lesson_code": lesson.get("lesson_code"),
        "district_title": lesson["district_title"],
        "kind": kind,
        "target": lesson.get("target"),
        "classwork": lesson.get("classwork"),
        "homework": normalize_homework(lesson.get("homework")),
        "link": lesson.get("link"),
        "extra_materials": lesson.get("extra_materials"),
    }
    _check_index(course["sequence"], index, inserting=True)
    course["sequence"].insert(index, entry)
    return entry


def cut_lesson(course, index):
    """Remove one entry from the sequence (an "earn" per PLANNING.md's day
    budget -- cutting an Opener, a 3-Act, or a duplicate lesson day)."""
    _check_index(course["sequence"], index)
    return course["sequence"].pop(index)


def edit_lesson(course, index, **fields):
    """Update fields (district_title, homework, target, classwork, link,
    ...) on an existing sequence entry in place. Content only -- no
    day-budget effect."""
    _check_index(course["sequence"], index)
    entry = course["sequence"][index]
    for key, value in fields.items():
        if key not in entry:
            raise ValueError(f"not a sequence field: {key!r} (want one of {sorted(entry)})")
        if key == "kind" and value not in VALID_LESSON_KINDS:
            raise ValueError(f"not a valid lesson kind: {value!r} (want one of {sorted(VALID_LESSON_KINDS)})")
        if key == "homework":
            value = normalize_homework(value)
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


# --- Changes families have already seen (PLANNING.md, "When the calendar
# changes") ------------------------------------------------------------------

# A changed day gets its own tag on the page when it's one of the
# next this-many class days. Further out, only test/quiz days and homework
# get a tag; the rest is covered by the entry's one summary line.
CHANGE_TAG_CLASS_DAYS = 5
SCHOOL_TZ = "America/Los_Angeles"


def school_today():
    """Today at school -- not the machine's date, which is UTC on a cloud
    session or a build and turns into tomorrow in the evening."""
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
        return datetime.now(ZoneInfo(SCHOOL_TZ)).date()
    except Exception:  # no time zone data on this machine
        return date.today()


def _seen_title(day):
    """A day's title as a family sees it, or None for a lesson day with
    nothing planned yet (filling that in later isn't a change)."""
    if day["type"] != "Instruction":
        return day["display"]
    if day["lesson_text"] in (None, NO_LESSON):
        return None
    return (day["lesson_text"] + (" + Quiz" if day.get("quiz_paired") else "")
            + (" + Test self-grading" if day.get("self_grading_paired") else ""))


def _is_quiz_or_test(day):
    return day["kind"] in ("Quiz", "Test") or bool(day.get("quiz_paired"))


def _is_assessment(day):
    return (day["kind"] in ASSESSMENT_KINDS
            or bool(day.get("quiz_paired")) or bool(day.get("self_grading_paired")))


# What filling in a day adds. `display` and `title` are left out: the
# lesson's name is there from the start of the year.
_CONTENT_FIELDS = ("target", "classwork", "link", "extra_materials", "teacher_out")


def _content_added(before_day, after_day):
    """Whether something was added to a day that keeps its lesson: a field
    that was blank and isn't now, or a new assignment given that day."""
    if any(not before_day[f] and after_day[f] for f in _CONTENT_FIELDS):
        return True
    def given(day):
        return {(h["text"], h["due"]) for h in day["homework"] or []}
    return (bool(given(after_day) - given(before_day))
            and len(after_day["homework"] or []) > len(before_day["homework"] or []))


def _same_occurrence(title, date_, from_calendar, to_calendar, today):
    """The date in `to_calendar` of the same occurrence of `title` that
    `from_calendar` has on `date_` -- matched by order, so the second day of
    a two-day lesson or project maps to its new second day, not its first.
    None if it's gone, past, or on the same date."""
    k = sum(1 for d in from_calendar if d["date"] < date_ and d["lesson_text"] == title)
    dates = [d["date"] for d in to_calendar if d["lesson_text"] == title]
    if k >= len(dates) or dates[k] < today or dates[k] == date_:
        return None
    return dates[k]


def _moved_to(before_day, before_calendar, after_calendar, date_, today):
    """Where the lesson that was on `date_` is now, if it's still on the
    calendar from today on. None for a quiz or self-grading day (each looks
    alike) or a closed day."""
    if before_day["type"] != "Instruction" or before_day["kind"] in ("Quiz", "Self-Grading"):
        return None
    return _same_occurrence(before_day["lesson_text"], date_, before_calendar, after_calendar, today)


def _moved_from(after_day, before_calendar, after_calendar, date_, today):
    """Where a test or project that's on `date_` now used to be, from today
    on -- so the day it arrives on can say so. Only tests and projects:
    that's where the new date is the news. None otherwise."""
    if after_day["kind"] not in ("Test", "Project"):
        return None
    return _same_occurrence(after_day["lesson_text"], date_, after_calendar, before_calendar, today)


def _due_changes(before_calendar, after_calendar, today, small_fix=False, through=None):
    """Assignments whose due date moved, that were reworded, or that were
    dropped, as change details on the date families were told (or the new
    one, if that one's past). Compared across the whole calendar by (text,
    due), not day by day: the day an assignment is given moves with its
    lesson, and that alone isn't news -- its due date is fixed, and a moved
    due date is. A reworded assignment is matched by its unchanged due
    date; `small_fix` skips those. With `through` (the course's set-through
    date), an assignment given on a planned day is skipped: planned
    homework can change quietly."""
    given_on = {}
    for d in before_calendar:
        for h in d["homework"] or []:
            given_on.setdefault((h["text"], h["due"]), d["date"])

    def items(calendar):
        out = []
        for d in calendar:
            out += [(h["text"], h["due"]) for h in d["homework"] or [] if h["due"]]
        return out
    before, after = items(before_calendar), items(after_calendar)
    removed, added = list(before), []
    for it in after:
        if it in removed:
            removed.remove(it)
        else:
            added.append(it)
    changes = []
    for text, was_due in removed:
        now = next(((t, due) for t, due in added if t == text), None)  # due date moved
        if now is None:
            now = next(((t, due) for t, due in added if due == was_due), None)  # reworded
            if now is not None and small_fix:
                added.remove(now)
                continue
        if now is not None:
            added.remove(now)
        if max(was_due, now[1] if now else was_due) < today:
            continue
        if through is not None and given_on.get((text, was_due), "") > through:
            continue
        changes.append({
            "date": was_due if was_due >= today else now[1], "what": "homework",
            "was": f"{text} (due {month_day(was_due)})",
            "now": f"{now[0]} (due {month_day(now[1])})" if now else None,
            "kind": "dropped" if now is None else "changed" if now[1] == was_due else "due moved",
        })
    return changes


def record_change(course, before_calendar, summary, reason=None, small_fix=False, today=None):
    """Log one confirmed edit's visible changes in course["changes"], which
    the page turns into "Updated" tags and its Recent changes list.

    Call render() before editing (the same snapshot diff_impact takes), make
    the edit, then call this with a one-line `summary` in Aaron's words
    ("Tuesday lost to an assembly; lessons from Tuesday on moved one day
    later") and his `reason` if he gave one. One call per confirmed edit,
    however many days it moved: families read one line per change.

    What counts is what a family could already have seen, from today on:
    a day's title (its lesson, quiz, test, or closure), its class work when
    the lesson itself didn't change, and each assignment's due date. Filling
    in something that was blank isn't a change. `small_fix=True` is for
    typo-level fixes: it skips changed class-work text and reworded
    assignments. It never skips a changed title or a moved or dropped
    assignment.

    Each tagged day's `kind` says what happened, for its details line
    (the tag itself is always "Updated"):
    "moved" (its lesson or test is now on `moved_to`, and/or the test or
    project now on it came from `moved_from`), "due moved" (an
    assignment's due date), "dropped" (an assignment is gone), or
    "changed" (anything else).

    Which changed days get their own tag (`days`): any within the next
    CHANGE_TAG_CLASS_DAYS class days, plus quiz, test, and project days and
    moved or dropped due dates anywhere. The rest is covered by `summary`
    alone.

    A course with a set-through date (set_through) works differently:
    only days that were set before the edit count. Their changed title,
    class work, target, or link is tagged, and a moved or dropped
    assignment given on one. Planned days change silently -- no tags, and
    no Recent changes line if nothing else changed -- except quizzes and
    tests through the current unit's test: their dates count as set as soon
    as they're on the calendar, so one appearing, disappearing, or moving
    there is tagged. A test months out isn't. The next-few-class-days
    window doesn't apply.

    Content added to a day that keeps its lesson (a target, class work, a
    link, a new assignment) isn't a change, but it's news: those dates go
    in the entry's `updated`, which the page tags "Updated" too, for the
    same 2 class days (set days only, in a course with a set-through date).
    `changed` says whether anything seen changed; an entry that only
    updated isn't listed under Recent changes.

    Returns the entry it logged, or None if nothing changed or was added
    (and then logs nothing)."""
    today = (today or school_today()).isoformat()
    after_calendar, _ = render(course)
    before = {d["date"]: d for d in before_calendar}
    upcoming_class = [d["date"] for d in after_calendar
                      if d["date"] >= today and d["type"] == "Instruction"]
    window_end = upcoming_class[min(CHANGE_TAG_CLASS_DAYS, len(upcoming_class)) - 1] if upcoming_class else today
    through = set_through(course)
    if through is not None:
        through = max(through, set_floor(date.fromisoformat(today)))
        window_end = through
        # The current unit runs through its test -- the later of where the
        # next test was and where it is now, if this edit moved it.
        unit_end = max((next((d["date"] for d in cal if d["date"] >= today and d["kind"] == "Test"), "")
                        for cal in (before_calendar, after_calendar)))
    # The fields a set day's lesson can change without changing its title.
    details = ("classwork",) if through is None else ("classwork", "target", "link")
    any_change, tagged, updated = False, [], []
    for after_day in after_calendar:
        date_ = after_day["date"]
        if date_ < today or date_ not in before:
            continue
        before_day = before[date_]
        was_set = through is None or before_day.get("set", False) or date_ <= through
        if through is None:
            assessment = _is_assessment(before_day) or _is_assessment(after_day)
        else:  # quizzes and tests only, and only through the current unit's test
            assessment = date_ <= unit_end and (_is_quiz_or_test(before_day) or _is_quiz_or_test(after_day))
        was, now = _seen_title(before_day), _seen_title(after_day)
        if was == now and was_set and _content_added(before_day, after_day):
            updated.append(date_)
        changed_detail = next((f for f in details if not small_fix and was == now
                               and before_day[f] and before_day[f] != after_day[f]), None)
        if was is not None and was != now:
            what = "title"
        elif changed_detail:
            what, was, now = changed_detail.replace("classwork", "class work"), \
                before_day[changed_detail], after_day[changed_detail]
        else:
            continue
        if not (was_set or (what == "title" and assessment)):
            continue  # a planned day: it changes quietly
        any_change = True
        if date_ <= window_end or assessment:
            detail = {"date": date_, "what": what, "was": was, "now": now, "kind": "changed"}
            moved_to = what == "title" and _moved_to(before_day, before_calendar, after_calendar, date_, today)
            if moved_to:
                detail.update(kind="moved", moved_to=moved_to)
            moved_from = what == "title" and _moved_from(after_day, before_calendar, after_calendar, date_, today)
            if moved_from:
                detail.update(kind="moved", moved_from=moved_from)
            tagged.append(detail)
    dues = _due_changes(before_calendar, after_calendar, today, small_fix, through)
    changed = any_change or bool(dues)
    if not changed and not updated:
        return None
    # A moved or dropped due date is tagged wherever it is; a reworded
    # assignment only inside the window, like class work.
    tagged += [d for d in dues if d["kind"] != "changed" or d["date"] <= window_end or through]
    tagged.sort(key=lambda d: d["date"])
    tagged_dates = {d["date"] for d in tagged}
    entry = {"logged": today, "summary": summary, "reason": reason, "changed": changed,
             "days": tagged, "updated": [d for d in updated if d not in tagged_dates]}
    course.setdefault("changes", []).append(entry)
    return entry


def check_set_through_current(course, today=None):
    """Flag a set-through date that's fallen behind the week students are
    in (set_floor). Those days are treated as set anyway, so nothing goes
    out unnoticed, but the date is how a week gets set on purpose -- and
    on a weekend, next week's days are already in use."""
    through = set_through(course)
    if through is None:
        return []
    floor = set_floor(today)
    if through >= floor:
        return []
    return [f"Set through is {month_day(through)}, behind the week students are in (through "
            f"{month_day(floor)}): those days count as set anyway, but set the week -- a week "
            f"file for it, or ask"]


def check_test_placement(course):
    """Flag Tests landing somewhere PLANNING.md says to avoid. These aren't
    auto-fixed -- resolving one is an editorial call (what moves, and to
    where), so this just surfaces them for a human to decide."""
    return_weeks = _break_return_weeks(course["school_days"])

    warnings = []
    for day, item in place(course)[0]:
        if not item or item["kind"] != "Test":
            continue
        d = date.fromisoformat(day["date"])
        if d.weekday() == 0:
            warnings.append(f"{day['date']}: Test lands on a Monday")
        elif week_monday(day["date"]) in return_weeks and d.weekday() in (0, 1, 2):
            warnings.append(f"{day['date']}: Test lands in the first Mon-Wed back from a break")
    return warnings


def check_self_grading(course):
    """Flag a test whose following week has no self-grading day: that
    Wednesday is closed or has no quiz slot (a holiday, a `quiz` override,
    another test that week), so there's no quiz to take the place of, and
    no lesson that week shares its period with it (`self_grading="paired"`).
    Not auto-fixed -- which day gives up its time is Aaron's call."""
    rule = quiz_rule(course)
    if not (rule["enabled"] and rule["self_grading"]):
        return []
    placements, _, _, shared_sg = _placement(course)
    by_date = {day["date"]: (day, item) for day, item in placements}
    warnings = []
    for day, item in placements:
        if not item or item["kind"] != "Test":
            continue
        wed = _self_grading_day(week_monday(day["date"]), rule["weekday"])
        if wed > course["school_days"][-1]["date"]:
            continue
        wday, witem = by_date.get(wed, (None, None))
        if witem is SELF_GRADING_ITEM or wed in shared_sg:
            continue
        week = week_monday(wed)
        if any(i is SELF_GRADING_ITEM and week_monday(d["date"]) == week for d, i in placements):
            continue  # a "full" self-grading day elsewhere that week
        if any(d.get("self_grading") == "paired" and _is_stored_lesson(i)
               and week_monday(d["date"]) == week
               for d, i in placements):
            continue
        why = ("isn't a school day" if wday is None
               else f"is '{wday['note'] or wday['type']}'" if wday["type"] != "Instruction"
               else "has no quiz slot to replace")
        warnings.append(f"{day['date']}: '{lesson_title(item)}' has no self-grading day -- "
                        f"the {_WEEKDAY_NAMES[rule['weekday']]} after, {wed}, {why}")
    return warnings


def check_review_before_test(course):
    """Flag a Test whose class day just before it isn't its review day
    (PLANNING.md: a topic test is a review day plus a test day). Closed
    days in between are fine; a quiz or a lesson in between is not. A
    review is recognized by "Review" in its title. Not auto-fixed --
    whether to insert a review day or cut something to make room is
    Aaron's call. A course with "review_before_test": false skips it --
    a teacher whose tests don't get a review day."""
    if not course.get("review_before_test", True):
        return []
    warnings, prev = [], None
    for day, item in place(course)[0]:
        if item is None:
            continue
        if item["kind"] == "Test" and not (
                prev and prev is not QUIZ_ITEM and "review" in prev["district_title"].lower()):
            before = "a quiz" if prev is QUIZ_ITEM else f"'{lesson_title(prev)}'" if prev else "nothing"
            warnings.append(f"{day['date']}: '{lesson_title(item)}' has no review day "
                            f"right before it (the class before is {before})")
        prev = item
    return warnings


def check_leftover_lessons(course):
    """Flag lessons that run past the last instructional day -- the
    sequence is longer than the year, so the last ones never get a date
    and silently drop off the published calendar. Not auto-fixed: what to
    cut (PLANNING.md's cut order) or which Flex day to spend is Aaron's
    call."""
    _, leftover = place(course)
    if not leftover:
        return []
    names = ", ".join(lesson_title(item) for item in course["sequence"][-leftover:])
    return [f"{leftover} lesson(s) have no day left before the year ends: {names}"]


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


def check_homework_due_dates(course):
    """Flag homework due on a day students aren't in school, or due on or
    before the day it's assigned. Due dates are fixed while lessons move,
    so a lost day can push an assignment's lesson up to (or past) its due
    date. Not auto-fixed -- whether to extend the due date or move the
    assignment is Aaron's call."""
    calendar, _ = render(course)
    by_date = {d["date"]: d for d in calendar}
    warnings = []
    for day in calendar:
        for hw in day["homework"] or []:
            due = hw["due"]
            if not due:
                continue
            label = f"'{hw['text']}' (assigned {day['date']}, due {due})"
            if due <= day["date"]:
                warnings.append(f"{label}: due on or before the day it's assigned")
            elif due not in by_date or by_date[due]["type"] == "No School":
                warnings.append(f"{label}: due on a day with no school")
    return warnings


def check_homework_links(course):
    """Flag assignments with no link of their own. Each assignment should open
    its own page in Schoology; without a link it shows as plain text. A
    Practice Log links to its answer-key folder, which is also where
    every assignment in it sends students for the key."""
    calendar, _ = render(course)
    return [f"'{hw['text']}' (assigned {day['date']}, due {hw['due']}): no link"
            + (" (its answer-key folder)" if is_practice_log(hw) else "")
            for day in calendar for hw in day["homework"] or [] if not hw["link"]]


MAX_LOG_ASSIGNMENTS = 5


def check_practice_log_size(course):
    """Flag a Practice Log covering more than MAX_LOG_ASSIGNMENTS assignments.
    A log runs two weeks and has room for five; a sixth means a busy stretch
    of homework, or a log window that crept wider. Not auto-fixed -- whether
    to drop an assignment, move a due date, or split the log is Aaron's call."""
    calendar, _ = render(course)
    return [f"'{hw['text']}' (assigned {day['date']}, due {hw['due']}): "
            f"{len(hw['includes'])} assignments, more than {MAX_LOG_ASSIGNMENTS}"
            for day in calendar for hw in day["homework"] or []
            if is_practice_log(hw) and len(hw.get("includes") or []) > MAX_LOG_ASSIGNMENTS]


def check_practice_log_before_test(course, today=None):
    """Flag a Practice Log assigned before a Test but due on or after it. Its
    assignments get checked against the keys on the log's due date, and that
    should happen before the test -- it's part of studying for it. Logs
    already past are skipped. Not auto-fixed -- the usual fix is moving the
    log's due date to the review day, but which day is Aaron's call."""
    calendar, _ = render(course)
    today = (today or school_today()).isoformat()
    tests = [d["date"] for d in calendar if d["kind"] == "Test"]
    warnings = []
    for day in calendar:
        for hw in day["homework"] or []:
            if not is_practice_log(hw) or not hw["due"] or hw["due"] < today:
                continue
            for t in tests:
                if day["date"] < t <= hw["due"]:
                    warnings.append(f"'{hw['text']}' (assigned {day['date']}, due {hw['due']}): "
                                    f"due on or after the {t} test")
    return warnings


def run_all_checks(course):
    """Every check together, as (label, [warnings]) pairs --
    the one place that knows the full checklist, so nothing added here has
    to be separately wired into the CLI, the import script, and anywhere
    else that wants "is this course file okay?" See PLANNING.md's Sanity
    checks section, which this is meant to mirror."""
    return [
        ("set through", check_set_through_current(course)),
        ("test placement", check_test_placement(course)),
        ("review before test", check_review_before_test(course)),
        ("self-grading", check_self_grading(course)),
        ("leftover lessons", check_leftover_lessons(course)),
        ("unexplained closures", check_unexplained_closures(course)),
        ("lesson shortfall", check_lesson_shortfall(course)),
        ("homework due dates", check_homework_due_dates(course)),
        ("homework links", check_homework_links(course)),
        ("practice log size", check_practice_log_size(course)),
        ("practice log before test", check_practice_log_before_test(course)),
    ]


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "courses/math6.json")
    course = json.loads(path.read_text())
    calendar, _ = render(course)
    for label, warnings in run_all_checks(course):
        for w in warnings:
            print(f"warning ({label}): {w}", file=sys.stderr)
    for day in calendar:
        if day["date"].startswith(sys.argv[2] if len(sys.argv) > 2 else "2026-09"):
            print(day["date"], day["weekday"], "|", day["display"])
