"""v2's edit operations (PLAN-v2-phase1.md, M6 and decision 5).

The editor never sends a calendar or a sequence index. It sends one
operation keyed by date -- "edit 10/20", "add a lesson on 10/21", "10/23 is
no school" -- and apply() finds what's on that date with engine.place()
and changes it with engine.py's own functions, so the engine's validation
(lesson kinds, no stored quizzes, the homework format) guards her edits
the way it guards Aaron's.

An operation is a dict with an "op" and a "date" (YYYY-MM-DD):

    edit       {"fields": {...}}   change the lesson on that date
    add        {"fields": {...}}   a new lesson on that date; it and every
                                   later lesson move one class day later
                                   (on an empty day, the next empty day)
    close      {"note": "..."}     no school that day; lessons re-flow
    open       {}                  class again on a day she closed
    copy_week  {}                  the week starting that Monday: its
                                   lessons again, right after it
    paste      {"rows": [{...}]}   one row of fields per class day from
                                   that date on, quizzes and closed days
                                   skipped; a day with nothing planned
                                   gets a new lesson

"fields" can hold title, kind, target, link, classwork, and homework (a
list of {"text", "due", "link"}). The title is what the grid shows: a
lesson's code (T1L2) stays its code when she leaves it in front.

apply() changes the course dict in place and returns the one-line summary
families see in Recent changes (engine.record_change). Anything she can
fix -- a date with no lesson, a link that isn't a web address -- raises
OpError with a sentence written for her.
"""
import re
from datetime import date as Date, timedelta

import engine

# The kinds she picks from (M6); a lesson that's already an Opener or a
# 3-Act from a copied calendar can keep that kind.
KINDS = ("Lesson", "Test", "Project")
FIELDS = {"title", "kind", "target", "link", "classwork", "homework"}
MAX_PASTE_ROWS = 60
MAX_TEXT = 2000
LINK_RE = re.compile(r"https?://\S+", re.IGNORECASE)


class OpError(ValueError):
    """An edit that can't be made, said so she can fix it."""


def when(iso):
    """'Tue 10/20'."""
    d = Date.fromisoformat(iso)
    return f"{engine.WEEKDAYS[d.weekday()] if d.weekday() < 5 else d.strftime('%a')} {d.month}/{d.day}"


def _placements(course):
    return engine.place(course)[0]


def _placement(course, date_):
    for day, item in _placements(course):
        if day["date"] == date_:
            return day, item
    raise OpError(f"{date_} isn't a school day on this calendar.")


def _index(course, item):
    return next(i for i, entry in enumerate(course["sequence"]) if entry is item)


def _is_computed(item):
    return item is engine.QUIZ_ITEM or item is engine.SELF_GRADING_ITEM


def _lesson_index(course, date_):
    """The sequence index of the lesson on `date_`."""
    day, item = _placement(course, date_)
    if day["type"] != "Instruction":
        raise OpError(f"{when(date_)} isn't a class day.")
    if _is_computed(item):
        raise OpError(f"{when(date_)} is a {item['district_title'].lower()} day, set by your quiz rule.")
    if item is None:
        raise OpError(f"Nothing is planned on {when(date_)} yet. Add a lesson there instead.")
    return _index(course, item)


def _insert_index(course, date_):
    """Where a lesson added on `date_` goes: after every lesson before it."""
    return sum(1 for day, item in _placements(course)
               if day["date"] < date_ and engine._is_stored_lesson(item))


def _text(value, what, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise OpError(f"The {what} should be text.")
    value = " ".join(value.split())
    if len(value) > MAX_TEXT:
        raise OpError(f"The {what} is too long (over {MAX_TEXT} characters).")
    if required and not value:
        raise OpError(f"A lesson needs a {what}.")
    return value or None


def _link(value, what="link"):
    """A web address, or None. Anything else (javascript:, a file path)
    would end up on the family page, so it's refused."""
    value = _text(value, what)
    if value and not LINK_RE.fullmatch(value):
        raise OpError(f"The {what} should be a web address starting with https://")
    return value


def _homework(value):
    if value in (None, ""):
        return None
    if not isinstance(value, list) or len(value) > 10:
        raise OpError("Homework should be a list of up to 10 assignments.")
    items = []
    for hw in value:
        if not isinstance(hw, dict):
            raise OpError("Each assignment needs its text.")
        text = _text(hw.get("text"), "assignment")
        if not text:
            continue  # an empty row in the form
        due = hw.get("due") or None
        if due is not None:
            try:
                Date.fromisoformat(due)
            except (TypeError, ValueError):
                raise OpError(f"{due!r} isn't a date.") from None
        item = {"text": text, "due": due}
        link = _link(hw.get("link"), "assignment's link")
        if link:
            item["link"] = link
        items.append(item)
    return engine.normalize_homework(items)


def _title_fields(title, item):
    """district_title (and lesson_code) from the title she typed. A
    lesson with a code keeps it when the title still starts with it as
    shown ("T1L2 ..."); otherwise the title is all hers."""
    title = _text(title, "title", required=True)
    code = item and item.get("lesson_code")
    if code:
        shown = engine.display_code(code) + " "
        if title.startswith(shown) and title[len(shown):].strip():
            return {"lesson_code": code, "district_title": title[len(shown):].strip()}
    return {"lesson_code": None, "district_title": title}


def _fields(fields, item=None):
    """The sequence fields for `fields` as the page sent them, checked.
    `item` is the lesson being edited (None for a new one)."""
    if not isinstance(fields, dict) or not fields:
        raise OpError("Nothing to change.")
    unknown = set(fields) - FIELDS
    if unknown:
        raise OpError(f"Unknown field: {sorted(unknown)[0]}")
    out = {}
    if "title" in fields:
        out.update(_title_fields(fields["title"], item))
    elif item is None:
        raise OpError("A lesson needs a title.")
    if "kind" in fields:
        kind = fields["kind"]
        if kind not in KINDS and not (item and kind == item["kind"]):
            raise OpError(f"A day's kind is one of {', '.join(KINDS)}.")
        out["kind"] = kind
    for key in ("target", "classwork"):
        if key in fields:
            out[key] = _text(fields[key], "I-can target" if key == "target" else "class work")
    if "link" in fields:
        out["link"] = _link(fields["link"])
    if "homework" in fields:
        out["homework"] = _homework(fields["homework"])
    return out


def _title(entry):
    return engine.lesson_title(entry)


def _date_of(course, entry):
    return next(day["date"] for day, item in _placements(course) if item is entry)


def _edit(course, op):
    i = _lesson_index(course, op["date"])
    entry = engine.edit_lesson(course, i, **_fields(op.get("fields"), course["sequence"][i]))
    return f"Plans for {when(op['date'])} updated: {_title(entry)}"


def _add(course, op):
    i = _insert_index(course, op["date"])
    moves = i < len(course["sequence"])
    entry = engine.insert_lesson(course, i, _fields(op.get("fields")))
    landed = _date_of(course, entry) if any(item is entry for _, item in _placements(course)) else None
    if landed is None:
        raise OpError("There's no class day left in the year for another lesson.")
    summary = f"{_title(entry)} added on {when(landed)}"
    return summary + ("; later lessons each move one class day later" if moves else "")


def _school_day(school_days, date_):
    return next((d for d in school_days if d["date"] == date_), None)


def _close(course, op, school_days):
    day, _ = _placement(course, op["date"])
    if day["type"] == "No School":
        raise OpError(f"{when(op['date'])} is already no school.")
    note = _text(op.get("note"), "note") or "No school"
    engine.set_day(course, op["date"], type="No School", note=note,
                   quiz=None, self_grading=None, teacher_out=None)
    return f"No school {when(op['date'])} ({note}); lessons from then on move one class day later"


def _open(course, op, school_days):
    day, _ = _placement(course, op["date"])
    school = _school_day(school_days, op["date"])
    if school and school["type"] == "No School":
        raise OpError(f"{when(op['date'])} is closed on the school's calendar ({school['note'] or 'No School'}).")
    if day["type"] == "Instruction":
        raise OpError(f"{when(op['date'])} is already a class day.")
    engine.set_day(course, op["date"], type="Instruction", note=None)
    return f"Class is back on {when(op['date'])}; lessons from then on move one class day earlier"


def _copy_week(course, op):
    monday = engine.week_monday(op["date"]).isoformat()
    friday = (Date.fromisoformat(monday) + timedelta(days=4)).isoformat()
    week = [(day, item) for day, item in _placements(course)
            if monday <= day["date"] <= friday and engine._is_stored_lesson(item)]
    if not week:
        raise OpError(f"The week of {when(monday)} has no lessons to repeat.")
    at = _index(course, week[-1][1]) + 1
    copies = []
    for k, (day, item) in enumerate(week):
        copy = {key: item[key] for key in ("topic", "lesson_code", "district_title", "kind",
                                           "target", "classwork", "link", "extra_materials")}
        copies.append((day["date"], item.get("homework"),
                       engine.insert_lesson(course, at + k, copy)))
    # An assignment's due date is a date, not "two days later", so each
    # copy's homework is due as many days after its new date as before.
    for old_date, homework, entry in copies:
        if not homework:
            continue
        new_date = _date_of(course, entry) if any(i is entry for _, i in _placements(course)) else None
        if new_date is None:
            continue
        shift = Date.fromisoformat(new_date) - Date.fromisoformat(old_date)
        entry["homework"] = engine.normalize_homework([
            {**hw, "due": (Date.fromisoformat(hw["due"]) + shift).isoformat() if hw["due"] else None}
            for hw in homework if "includes" not in hw])
    return f"The week of {when(monday)} repeated: {len(copies)} lesson{'s' * (len(copies) != 1)} added after it"


def _paste(course, op):
    rows = op.get("rows")
    if not isinstance(rows, list) or not rows:
        raise OpError("Nothing was pasted.")
    if len(rows) > MAX_PASTE_ROWS:
        raise OpError(f"That's more than {MAX_PASTE_ROWS} days at once. Paste a few weeks at a time.")
    if not all(isinstance(row, dict) for row in rows):
        raise OpError("That paste didn't come through. Try again.")
    date_, filled = op["date"], []
    for row in rows:
        # The next class day from date_ that isn't a quiz or self-grading day.
        nxt = next(((day, item) for day, item in _placements(course)
                    if day["date"] >= date_ and day["type"] == "Instruction" and not _is_computed(item)),
                   None)
        if nxt is None:
            raise OpError("The pasted rows run past the last class day of the year.")
        day, item = nxt
        date_ = day["date"]
        fields = {k: v for k, v in row.items() if v not in (None, "", [])}
        if fields:
            if item is None:
                engine.insert_lesson(course, _insert_index(course, date_), _fields(fields))
            else:
                engine.edit_lesson(course, _index(course, item), **_fields(fields, item))
            filled.append(date_)
        date_ = (Date.fromisoformat(date_) + timedelta(days=1)).isoformat()
    if not filled:
        raise OpError("The pasted rows were empty.")
    return f"Plans pasted for {len(filled)} day{'s' * (len(filled) != 1)} from {when(filled[0])} to {when(filled[-1])}"


OPS = {"edit": _edit, "add": _add, "copy_week": _copy_week, "paste": _paste}
DAY_OPS = {"close": _close, "open": _open}


def apply(course, op, school_days):
    """Apply one operation to `course` in place; returns its summary.
    `school_days` is the school's record, which a teacher can't reopen."""
    if not isinstance(op, dict):
        raise OpError("That edit didn't come through. Reload and try again.")
    name, date_ = op.get("op"), op.get("date")
    try:
        Date.fromisoformat(date_)
    except (TypeError, ValueError):
        raise OpError("That edit has no date. Reload and try again.") from None
    if name in OPS:
        return OPS[name](course, op)
    if name in DAY_OPS:
        return DAY_OPS[name](course, op, school_days)
    raise OpError(f"Unknown edit: {name!r}")
