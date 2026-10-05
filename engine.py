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

A school day's optional `quiz` overrides the rule for that one day (see
QUIZ_OVERRIDES). It's the only override: a day's note is plain
student-facing text and never changes placement.
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

QUIZ_ITEM = {
    "topic": None, "lesson_code": None, "district_title": "Quiz",
    "kind": "Quiz", "target": None, "classwork": None, "homework": None,
    "link": None, "extra_materials": None,
}

# The closed sets from SPEC.md's data model. Edit functions below validate
# against these instead of accepting free text.
VALID_DAY_TYPES = {"Instruction", "Flex", "Testing", "No School", "Other"}
VALID_LESSON_KINDS = {"Lesson", "Opener", "Quiz", "Test", "3-Act", "Project"}

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

def _week_monday(d):
    return d - timedelta(days=d.weekday())


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
    overridden = {d["date"] for d in school_days if d.get("quiz")}
    forced = {d["date"] for d in school_days
              if d.get("quiz") == "full" and d["type"] == "Instruction"}

    quiz_dates = set()
    for _ in range(10):
        placements, _ = _place(school_days, sequence, quiz_dates)
        test_weeks = {
            _week_monday(date.fromisoformat(day["date"]))
            for day, item in placements if item and item["kind"] == "Test"
        }
        new_quiz_dates = forced | {
            wd for wd in wednesdays
            if wd not in overridden
            and wd not in break_return
            and wd != _day_before_thanksgiving(int(wd[:4]))
            and _week_monday(date.fromisoformat(wd)) not in test_weeks
        }
        if new_quiz_dates == quiz_dates:
            return quiz_dates
        quiz_dates = new_quiz_dates
    return quiz_dates  # converges in practice well within 10 iterations


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
    """A Practice Log is the weekly container students record their practice
    in -- recognized by its text, since it's entered like any other homework."""
    return hw["text"].lower().startswith("practice log")


def _practice_log_contents(placements):
    """What each Practice Log covers: every other assignment due from the day
    the log is assigned through the day it's due, soonest first. Derived, not
    stored, so the list follows the homework as it's planned and never needs
    re-entering -- unless the log lists its own "includes" (a log whose
    window doesn't match its contents), whose items pick up the link of the
    assignment they name. Keyed by (assigned date, log text)."""
    assigned = [(day["date"], hw) for day, lesson in placements
                for hw in _homework_with_links(lesson)]
    links = {(hw["text"], hw["due"]): hw["link"] for _, hw in assigned}
    contents = {}
    for start, log in assigned:
        if not is_practice_log(log):
            continue
        if log.get("includes"):
            contents[(start, log["text"])] = [
                {**c, "link": links.get((c["text"], c["due"]))} for c in log["includes"]]
            continue
        if not log["due"]:
            continue
        contents[(start, log["text"])] = sorted(
            ({"text": hw["text"], "due": hw["due"], "link": hw["link"]}
             for _, hw in assigned
             if hw["due"] and not is_practice_log(hw) and start <= hw["due"] <= log["due"]),
            key=lambda hw: hw["due"])
    return contents


def place(course):
    """(placements, leftover): each school day paired with the sequence
    entry, QUIZ_ITEM, or None that lands on it -- the one placement every
    caller shares, so nothing can disagree with render()."""
    school_days, sequence = course["school_days"], course["sequence"]
    quiz_dates = _compute_quiz_dates(school_days, sequence, course.get("quiz_rhythm_start"))
    return _place(school_days, sequence, quiz_dates)


def render(course):
    placements, leftover = place(course)

    # Homework shows twice: on the day it's assigned (with its lesson) and on
    # its due date, which is fixed and independent of where lessons land.
    # A Practice Log carries the assignments it covers ("includes"; the page
    # shows them as a checklist on the log's due date), and each assignment
    # it covers carries that log's due date ("log_due"; the page tags the
    # assignment with it). An assignment in two logs gets the earlier one.
    log_contents = _practice_log_contents(placements)
    log_due_of = {}
    for day, lesson in placements:
        for log in _homework_with_links(lesson):
            covered = log_contents.get((day["date"], log["text"]))
            if not covered or not log["due"]:
                continue
            for c in covered:
                key = (c["text"], c["due"])
                if key not in log_due_of or log["due"] < log_due_of[key]:
                    log_due_of[key] = log["due"]

    def homework_for(day, lesson):
        items = _homework_with_links(lesson)
        for hw in items:
            if (day["date"], hw["text"]) in log_contents:
                hw["includes"] = log_contents[(day["date"], hw["text"])]
            elif (hw["text"], hw["due"]) in log_due_of:
                hw["log_due"] = log_due_of[(hw["text"], hw["due"])]
        return items

    due_by_date = {}
    for day, lesson in placements:
        for hw in homework_for(day, lesson):
            if hw["due"]:
                entry = {"text": hw["text"], "assigned": day["date"], "link": hw["link"]}
                if "includes" in hw:
                    entry["includes"] = hw["includes"]
                due_by_date.setdefault(hw["due"], []).append(entry)

    calendar = []
    for day, lesson in placements:
        note = day["note"]
        if day["type"] == "Instruction":
            if lesson is None:
                base = "(no lesson planned)"
                kind = None
            else:
                base = lesson_title(lesson)
                kind = lesson["kind"]
            # A note on an instructional day is a reminder alongside the lesson
            # (a testing window, a snow-make-up flag), not a replacement for it.
            display = f"{base}\n{note}" if note else base
            calendar.append({
                "date": day["date"], "weekday": day["weekday"], "type": day["type"],
                "display": display, "lesson_text": base, "kind": kind,
                # A quiz sharing the period with this lesson (QUIZ_OVERRIDES).
                "quiz_paired": day.get("quiz") == "paired" and lesson not in (None, QUIZ_ITEM),
                "homework": homework_for(day, lesson) or None,
                "due": due_by_date.get(day["date"]), "note": note,
                "target": lesson.get("target") if lesson else None,
                "classwork": lesson.get("classwork") if lesson else None,
                # A computed quiz day has no stored entry to carry a link, so
                # every quiz links to the course's one quiz folder.
                "link": (course.get("quiz_link") if lesson is QUIZ_ITEM
                         else lesson.get("link") if lesson else None),
                "extra_materials": lesson.get("extra_materials") if lesson else None,
            })
        else:
            # A non-instructional day has no lesson to show alongside, so the
            # note (e.g. "No School (Holiday)") replaces the bare type label.
            calendar.append({
                "date": day["date"], "weekday": day["weekday"], "type": day["type"],
                "display": note or day["type"], "lesson_text": None, "kind": None,
                "quiz_paired": False,
                "homework": None, "due": due_by_date.get(day["date"]), "note": note,
                "target": None, "classwork": None, "link": None, "extra_materials": None,
            })
    return calendar, leftover


_UNSET = object()


def set_day(course, date_str, type=_UNSET, note=_UNSET, quiz=_UNSET):
    """Change an existing school day's type, note, and/or quiz override in
    place. Changing the type is how a day is spent (Instruction -> No
    School/Other, an assembly or snow day) or earned back (Flex ->
    Instruction).

    `quiz` overrides the Wednesday rule on this one day -- "none",
    "paired", or "full" (see QUIZ_OVERRIDES) -- and `quiz=None` removes
    the override so the rule decides again. Quizzes themselves are still
    never stored; render() computes them, honoring this. Moving a quiz is
    two calls: quiz="none" on its Wednesday, quiz="full" on the new day.

    Omit an argument to leave it unchanged; pass `note=None` explicitly
    to clear an existing note (e.g. undoing an assembly note)."""
    if type is not _UNSET and type not in VALID_DAY_TYPES:
        raise ValueError(f"not a valid day type: {type!r} (want one of {sorted(VALID_DAY_TYPES)})")
    if quiz is not _UNSET and quiz is not None and quiz not in QUIZ_OVERRIDES:
        raise ValueError(f"not a valid quiz override: {quiz!r} (want one of {sorted(QUIZ_OVERRIDES)}, or None)")
    for day in course["school_days"]:
        if day["date"] == date_str:
            new_type = day["type"] if type is _UNSET else type
            new_quiz = day.get("quiz") if quiz is _UNSET else quiz
            if new_quiz in ("paired", "full") and new_type != "Instruction":
                raise ValueError(f"{date_str} would be a '{new_type}' day -- a quiz needs an Instruction day")
            day["type"] = new_type
            if note is not _UNSET:
                day["note"] = note
            if new_quiz is None:
                day.pop("quiz", None)
            else:
                day["quiz"] = new_quiz
            return day
    raise ValueError(f"no school day dated {date_str}")


def set_daily_materials(course, items):
    """Replace the course-wide baseline materials list (course['daily_materials'])
    -- what a student needs every school day, regardless of lesson (a
    Chromebook, a pencil), as opposed to a specific lesson's
    `extra_materials`. Rare to change; rewrites the whole list rather than
    adding/removing one item at a time."""
    course["daily_materials"] = list(items)


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

# A changed day gets its own "Changed" tag on the page when it's one of the
# next this-many class days. Further out, only test/quiz days and homework
# get a tag; the rest is covered by the entry's one summary line.
CHANGE_TAG_CLASS_DAYS = 5
SCHOOL_TZ = "America/Los_Angeles"


def school_today():
    """Today at school -- not the machine's date, which is UTC on a cloud
    session or a build and turns into tomorrow in the evening."""
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        return datetime.now(ZoneInfo(SCHOOL_TZ)).date()
    except Exception:  # no time zone data on this machine
        return date.today()


def _seen_title(day):
    """A day's title as a family sees it, or None for a lesson day with
    nothing planned yet (filling that in later isn't a change)."""
    if day["type"] != "Instruction":
        return day["display"]
    if day["lesson_text"] in (None, "(no lesson planned)"):
        return None
    return day["lesson_text"] + (" + Quiz" if day.get("quiz_paired") else "")


def _md(iso):
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}"


def _is_assessment(day):
    return day["kind"] in ("Quiz", "Test", "Project") or bool(day.get("quiz_paired"))


def _moved_to(before_day, after_calendar, date_, today):
    """Where the lesson that was on `date_` is now, if it's still on the
    calendar on another day from today on -- the first such day, so a
    two-day lesson points at its new first day. None for a quiz (every quiz
    looks alike) or a closed day."""
    if before_day["type"] != "Instruction" or before_day["kind"] == "Quiz":
        return None
    title = before_day["lesson_text"]
    return next((d["date"] for d in after_calendar
                 if d["date"] >= today and d["date"] != date_ and d["lesson_text"] == title), None)


def _due_changes(before_calendar, after_calendar, today, small_fix=False):
    """Assignments whose due date moved, that were reworded, or that were
    dropped, as change details on the date families were told (or the new
    one, if that one's past). Compared across the whole calendar by (text,
    due), not day by day: the day an assignment is given moves with its
    lesson, and that alone isn't news -- its due date is fixed, and a moved
    due date is. A reworded assignment is matched by its unchanged due
    date; `small_fix` skips those."""
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
        changes.append({
            "date": was_due if was_due >= today else now[1], "what": "homework",
            "was": f"{text} (due {_md(was_due)})",
            "now": f"{now[0]} (due {_md(now[1])})" if now else None,
            "kind": "dropped" if now is None else "changed" if now[1] == was_due else "due moved",
        })
    return changes


def record_change(course, before_calendar, summary, reason=None, small_fix=False, today=None):
    """Log one confirmed edit's visible changes in course["changes"], which
    the page turns into "Changed" tags and its Recent changes list.

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

    Each tagged day's `kind` says what happened, for the page's tag:
    "moved" (its lesson or test is now on `moved_to`), "due moved" (an
    assignment's due date), "dropped" (an assignment is gone), or
    "changed" (anything else).

    Which changed days get their own tag (`days`): any within the next
    CHANGE_TAG_CLASS_DAYS class days, plus quiz, test, and project days and
    moved or dropped due dates anywhere. The rest is covered by `summary`
    alone.

    Returns the entry it logged, or None if nothing seen changed (and then
    logs nothing)."""
    today = (today or school_today()).isoformat()
    after_calendar, _ = render(course)
    before = {d["date"]: d for d in before_calendar}
    upcoming_class = [d["date"] for d in after_calendar
                      if d["date"] >= today and d["type"] == "Instruction"]
    window_end = upcoming_class[min(CHANGE_TAG_CLASS_DAYS, len(upcoming_class)) - 1] if upcoming_class else today
    any_change, tagged = False, []
    for after_day in after_calendar:
        date_ = after_day["date"]
        if date_ < today or date_ not in before:
            continue
        before_day = before[date_]
        was, now = _seen_title(before_day), _seen_title(after_day)
        if was is not None and was != now:
            what = "title"
        elif (not small_fix and was == now and before_day["classwork"]
              and before_day["classwork"] != after_day["classwork"]):
            what, was, now = "class work", before_day["classwork"], after_day["classwork"]
        else:
            continue
        any_change = True
        if date_ <= window_end or _is_assessment(before_day) or _is_assessment(after_day):
            detail = {"date": date_, "what": what, "was": was, "now": now, "kind": "changed"}
            moved_to = what == "title" and _moved_to(before_day, after_calendar, date_, today)
            if moved_to:
                detail.update(kind="moved", moved_to=moved_to)
            tagged.append(detail)
    dues = _due_changes(before_calendar, after_calendar, today, small_fix)
    if not any_change and not dues:
        return None
    # A moved or dropped due date is tagged wherever it is; a reworded
    # assignment only inside the window, like class work.
    tagged += [d for d in dues if d["kind"] != "changed" or d["date"] <= window_end]
    tagged.sort(key=lambda d: d["date"])
    entry = {"logged": today, "summary": summary, "reason": reason, "days": tagged}
    course.setdefault("changes", []).append(entry)
    return entry


def check_test_placement(course):
    """Flag Tests landing somewhere PLANNING.md says to avoid. These aren't
    auto-fixed -- resolving one is an editorial call (what moves, and to
    where), so this just surfaces them for a human to decide."""
    return_weeks = {
        _week_monday(date.fromisoformat(d))
        for d in _break_return_wednesdays(course["school_days"])
    }

    warnings = []
    for day, item in place(course)[0]:
        if not item or item["kind"] != "Test":
            continue
        d = date.fromisoformat(day["date"])
        if d.weekday() == 0:
            warnings.append(f"{day['date']}: Test lands on a Monday")
        elif _week_monday(d) in return_weeks and d.weekday() in (0, 1, 2):
            warnings.append(f"{day['date']}: Test lands in the first Mon-Wed back from a break")
    return warnings


def check_review_before_test(course):
    """Flag a Test whose class day just before it isn't its review day
    (PLANNING.md: a topic test is a review day plus a test day). Closed
    days in between are fine; a quiz or a lesson in between is not. A
    review is recognized by "Review" in its title. Not auto-fixed --
    whether to insert a review day or cut something to make room is
    Aaron's call."""
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
    Practice Log is exempt -- it has no page; the assignments it lists carry
    their own links."""
    calendar, _ = render(course)
    return [f"'{hw['text']}' (assigned {day['date']}, due {hw['due']}): no link"
            for day in calendar for hw in day["homework"] or []
            if not hw["link"] and not is_practice_log(hw)]


def run_all_checks(course):
    """Every check together, as (label, [warnings]) pairs --
    the one place that knows the full checklist, so nothing added here has
    to be separately wired into the CLI, the import script, and anywhere
    else that wants "is this course file okay?" See PLANNING.md's Sanity
    checks section, which this is meant to mirror."""
    return [
        ("test placement", check_test_placement(course)),
        ("review before test", check_review_before_test(course)),
        ("leftover lessons", check_leftover_lessons(course)),
        ("unexplained closures", check_unexplained_closures(course)),
        ("lesson shortfall", check_lesson_shortfall(course)),
        ("homework due dates", check_homework_due_dates(course)),
        ("homework links", check_homework_links(course)),
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
