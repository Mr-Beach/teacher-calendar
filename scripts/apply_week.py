"""Apply a planned week (inbox/*.json) to a course file -- no AI in the loop.

The routine weekly update is content only: each school day's target, class
work, homework, link, materials, and student-facing note. None of that
re-flows anything, so it doesn't need judgment at apply time -- the judgment
(terse wording, which lines are student-facing, which Savvas lesson a day
really is) happens once, while the week is planned, and lands in a strict
file. This script just applies that file through engine.py's edit functions.

Anything that changes the day budget -- losing a day, cutting or inserting
a lesson -- is deliberately NOT supported here. That's an editorial call
(CLAUDE.md / PLANNING.md) and stays a Claude Code job.

Week file shape (see inbox/README.md for the full contract):

    {
      "course": "math6",
      "week_of": "2026-10-05",
      "days": [
        {
          "date": "2026-10-05",
          "expect": "1.2",
          "target": "I can ...",
          "classwork": "...",
          "homework": [{"text": "...", "due": "2026-10-07"}],
          "link": "https://...",
          "extra_materials": ["scissors"],
          "note": "..."
        }
      ]
    }

Per day: a key that's absent leaves that field alone; a key set to null
clears it. `expect` is required on any day that edits lesson content and
must match the lesson currently rendered on that date (its lesson_code, or
failing that a case-insensitive substring of its title). If the calendar has
shifted since the week was planned, the mismatch stops the whole file --
nothing is half-applied.

Usage:
    python3 scripts/apply_week.py inbox/2026-10-05.json [--dry-run] [--summary out.md]

Exit status: 0 applied (or would apply), 1 the file was rejected.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402

# Lesson-content fields, written onto the sequence entry that renders on the date.
LESSON_FIELDS = ("target", "classwork", "homework", "link", "extra_materials")
# Day fields, written onto the school_days entry itself (always student-facing).
DAY_FIELDS = ("note",)
ALLOWED_DAY_KEYS = {"date", "expect", *LESSON_FIELDS, *DAY_FIELDS}


class WeekError(Exception):
    pass


def _placements_by_date(course):
    """date -> (school_day, sequence index or None, rendered item or None).
    Uses engine's own placement so this can never disagree with render()."""
    quiz_dates = engine._compute_quiz_dates(
        course["school_days"], course["sequence"], course.get("quiz_rhythm_start"))
    placements, _ = engine._place(course["school_days"], course["sequence"], quiz_dates)
    index_of = {id(item): i for i, item in enumerate(course["sequence"])}
    return {
        day["date"]: (day, index_of.get(id(item)) if item is not None else None, item)
        for day, item in placements
    }


def _title(item):
    if item is None:
        return None
    code = item.get("lesson_code")
    return f"{code} {item['district_title']}" if code else item["district_title"]


def _matches(expect, item):
    if item is None:
        return False
    expect = expect.strip()
    # A code-shaped expect ("1.1") must match the code exactly -- a substring
    # test would let "1.1" match "1.10".
    if re.fullmatch(r"\d+\.\d+", expect):
        return item.get("lesson_code") == expect
    return expect.lower() in _title(item).lower()


def _normalize_homework(value):
    # The course file uses null, never [], for "nothing assigned" (SKILL.md).
    try:
        return engine.normalize_homework(value)
    except ValueError as e:
        raise WeekError(str(e)) from None


def _normalize_str_list(value, field):
    if value is None or value == []:
        return None
    if not isinstance(value, list) or not all(isinstance(s, str) and s.strip() for s in value):
        raise WeekError(f"{field} must be a list of non-empty strings, or null")
    return [s.strip() for s in value]


def _normalize_str(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise WeekError(f"{field} must be a string or null")
    value = value.strip()
    return value or None


def plan_changes(course, week):
    """Validate the whole week against the current course and return the
    list of edits to make. Raises WeekError listing every problem found,
    so one run reports everything wrong, not just the first thing."""
    if not isinstance(week, dict) or not isinstance(week.get("days"), list) or not week["days"]:
        raise WeekError("week file needs a non-empty 'days' list")
    by_date = _placements_by_date(course)
    problems, edits, seen = [], [], set()

    for n, entry in enumerate(week["days"], 1):
        where = f"day {n}"
        if not isinstance(entry, dict) or "date" not in entry:
            problems.append(f"{where}: missing 'date'")
            continue
        date = entry["date"]
        where = date
        if date in seen:
            problems.append(f"{where}: listed twice")
            continue
        seen.add(date)
        unknown = set(entry) - ALLOWED_DAY_KEYS
        if unknown:
            problems.append(f"{where}: unknown field(s) {sorted(unknown)} -- "
                            f"structural changes (day types, cuts, inserts) go through Claude Code")
            continue
        if date not in by_date:
            problems.append(f"{where}: not a date in the course calendar")
            continue
        day, index, item = by_date[date]
        lesson_changes = {k: entry[k] for k in LESSON_FIELDS if k in entry}
        day_changes = {k: entry[k] for k in DAY_FIELDS if k in entry}

        try:
            if "homework" in lesson_changes:
                lesson_changes["homework"] = _normalize_homework(lesson_changes["homework"])
            if "extra_materials" in lesson_changes:
                lesson_changes["extra_materials"] = _normalize_str_list(
                    lesson_changes["extra_materials"], "extra_materials")
            for k in ("target", "classwork", "link"):
                if k in lesson_changes:
                    lesson_changes[k] = _normalize_str(lesson_changes[k], k)
            if "note" in day_changes:
                day_changes["note"] = _normalize_str(day_changes["note"], "note")
        except WeekError as e:
            problems.append(f"{where}: {e}")
            continue

        if lesson_changes:
            if index is None:
                what = "a quiz" if item is engine.QUIZ_ITEM else (
                    f"a '{day['type']}' day" if day["type"] != "Instruction" else "an empty day")
                problems.append(f"{where}: is {what}, so it has no lesson to put "
                                f"{sorted(lesson_changes)} on (a note is fine)")
                continue
            expect = entry.get("expect")
            if not expect:
                problems.append(f"{where}: edits lesson content but has no 'expect' "
                                f"(currently shows '{_title(item)}')")
                continue
            if not _matches(expect, item):
                problems.append(f"{where}: expected '{expect}' but the calendar shows "
                                f"'{_title(item)}' -- the calendar has shifted since this "
                                f"week was planned; re-plan or fix it in Claude Code")
                continue
        elif "expect" in entry and index is not None and not _matches(entry["expect"], item):
            problems.append(f"{where}: expected '{entry['expect']}' but the calendar shows "
                            f"'{_title(item)}'")
            continue

        if lesson_changes:
            old = course["sequence"][index]
            changed = {k: v for k, v in lesson_changes.items() if old.get(k) != v}
            if changed:
                edits.append(("lesson", date, index, _title(item), changed,
                              {k: old.get(k) for k in changed}))
        if day_changes and day.get("note") != day_changes["note"]:
            edits.append(("day", date, None, _title(item) or day["type"], day_changes,
                          {"note": day.get("note")}))

    if problems:
        raise WeekError("\n".join(f"- {p}" for p in problems))
    return edits


def apply_changes(course, edits):
    for kind, date, index, _label, changes, _old in edits:
        if kind == "lesson":
            engine.edit_lesson(course, index, **changes)
        else:
            engine.set_day(course, date, note=changes["note"])


def placement_impact(course, before_calendar, before_leftover):
    """Like engine.diff_impact, but compares which lesson sits on each date
    rather than the displayed text. diff_impact compares `display`, which
    includes the day's note -- so adding a note to a lesson day would read
    as a re-flow when nothing moved."""
    after_calendar, after_leftover = engine.render(course)
    first = next((a["date"] for b, a in zip(before_calendar, after_calendar)
                  if (b["type"], b["lesson_text"], b["kind"]) != (a["type"], a["lesson_text"], a["kind"])),
                 None)
    return {"leftover_before": before_leftover, "leftover_after": after_leftover,
            "first_shifted_date": first}


def _fmt(value):
    if value is None:
        return "_(empty)_"
    if isinstance(value, list):
        return "; ".join(
            (f"{v['text']} (due {v['due']})" if v.get("due") else v["text"])
            if isinstance(v, dict) else v
            for v in value)
    return value


def summarize(edits, impact, warnings, week_of):
    lines = [f"## Week of {week_of}", ""]
    if not edits:
        lines.append("Nothing to change -- the calendar already matches this week file.")
    by_date = {}
    for e in edits:
        by_date.setdefault(e[1], []).append(e)
    for date in sorted(by_date):
        label = by_date[date][0][3]
        lines.append(f"**{date} -- {label}**")
        for _kind, _d, _i, _l, changes, old in by_date[date]:
            for k, v in changes.items():
                lines.append(f"- {k}: {_fmt(v)}")
                if old.get(k) is not None:
                    lines.append(f"  - was: {_fmt(old[k])}")
        lines.append("")
    # Content edits should never re-flow anything; say so loudly if one did.
    if impact["first_shifted_date"] or impact["leftover_after"] != impact["leftover_before"]:
        lines.append(f"**Unexpected re-flow:** calendar differs from "
                     f"{impact['first_shifted_date']}; leftover "
                     f"{impact['leftover_before']} -> {impact['leftover_after']}.")
    else:
        lines.append("No dates moved. (Content-only update.)")
    active = [(label, w) for label, ws in warnings for w in ws]
    if active:
        lines += ["", "Standing warnings (unchanged by this update):"]
        lines += [f"- {label}: {w}" for label, w in active]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("week_file")
    ap.add_argument("--dry-run", action="store_true", help="validate and report; write nothing")
    ap.add_argument("--summary", help="also write the markdown summary to this path")
    args = ap.parse_args(argv)

    week_path = Path(args.week_file)
    try:
        week = json.loads(week_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"could not read {week_path}: {e}", file=sys.stderr)
        return 1
    course_path = ROOT / "courses" / f"{week.get('course', 'math6')}.json"
    if not course_path.exists():
        print(f"no course file {course_path.relative_to(ROOT)}", file=sys.stderr)
        return 1
    course = json.loads(course_path.read_text())

    before_calendar, before_leftover = engine.render(course)
    try:
        edits = plan_changes(course, week)
    except WeekError as e:
        msg = f"Rejected {week_path.name} -- nothing was changed:\n{e}\n"
        print(msg, file=sys.stderr)
        if args.summary:
            Path(args.summary).write_text(msg)
        return 1

    apply_changes(course, edits)
    impact = placement_impact(course, before_calendar, before_leftover)
    summary = summarize(edits, impact, engine.run_all_checks(course),
                        week.get("week_of", week_path.stem))
    print(summary)
    if args.summary:
        Path(args.summary).write_text(summary)
    if not args.dry_run and edits:
        course_path.write_text(json.dumps(course, indent=2) + "\n")  # matches the file's existing encoding
    return 0


if __name__ == "__main__":
    sys.exit(main())
