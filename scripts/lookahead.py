"""Teacher-only look-ahead: the next N instructional days, per course.

Reads courses/*.json through engine.render(), so it can never disagree with
the published calendar. This prints to the terminal for Aaron (or a session
answering "what's coming up?"), and its output can be pasted into Cowork to
build the decks for those days. The same look-ahead is published as a web
page, behind a sign-in, by scripts/lookahead_page.py (beach-math.com/teacher).

Non-instructional days in the window are shown so the gaps are visible, but
only Instruction days count toward N. A lesson day with no target, class
work, or link yet is flagged "needs: ..." -- that's the content the weekly
inbox fills.

--needs prints only those gap days, grouped by course. It's the planning
session's (Cowork's) starting point: it says which days to fill and gives the
lesson each one must `expect` (inbox/README.md).

Deck status is not shown yet: the decks live in OneDrive/Cowork, which this
repo can't see. That waits on deciding how deck existence gets tracked.

Usage:
    python3 scripts/lookahead.py                    # all courses, 10 days from today
    python3 scripts/lookahead.py math6 --days 5
    python3 scripts/lookahead.py --from 2026-10-05
    python3 scripts/lookahead.py --needs --days 15  # just the days still to plan
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402

# Kinds that get a tag; a plain "Lesson" doesn't need one.
TAGGED_KINDS = {"Quiz", "Test", "Opener", "3-Act", "Project"}
# Quizzes and tests carry no target/classwork of their own, so they're never
# flagged as missing content. Quizzes link to the course's quiz folder, and a
# test has nothing for students to open, so neither needs a link either.
CONTENT_EXEMPT_KINDS = {"Quiz", "Test"}
CONTENT_FIELDS = ("target", "classwork", "link")
FIELD_LABELS = {"target": "target", "classwork": "class work", "link": "link",
                "homework_link": "assignment link"}


def lookahead(course, start, days):
    """The rendered calendar from `start` (ISO date, inclusive) through the
    `days`-th Instruction day, as a list of rendered-day dicts. Fewer than
    `days` Instruction days come back if the school year runs out."""
    window, count = [], 0
    for day in engine.render(course)[0]:
        if day["date"] < start:
            continue
        if day["type"] == "Instruction":
            if count == days:
                break
            count += 1
        elif count == 0:
            # Skip non-instructional days before the first lesson in the
            # window (e.g. running this on a weekend-adjacent holiday).
            continue
        window.append(day)
    # Non-instructional days after the last counted lesson belong to the
    # next window; over a break they'd otherwise be a run of "No School".
    while window and window[-1]["type"] != "Instruction":
        window.pop()
    return window


def missing_content(day, course=None):
    """Content fields a lesson day still needs, e.g. ["target", "link"].
    "homework_link" means an assignment given that day has no link of its
    own (a Practice Log's is its week's answer-key folder). Class work isn't needed in a course
    that has it turned off (engine.shows_classwork)."""
    if day["type"] != "Instruction" or day["kind"] is None:
        return []
    fields = [f for f in CONTENT_FIELDS
              if f != "classwork" or course is None or engine.shows_classwork(course)]
    needs = [] if day["kind"] in CONTENT_EXEMPT_KINDS else [f for f in fields if not day[f]]
    if any(not hw["link"] for hw in day["homework"] or []):
        needs.append("homework_link")
    return needs


def when_label(day):
    return f"{day['weekday']} {day['date'][5:7]}/{day['date'][8:10]}"


def format_course(course, window):
    lines = [course["course"]]
    if not window:
        return lines + ["  (no instructional days left in the calendar)"]
    for day in window:
        when = when_label(day)
        if day["type"] != "Instruction":
            lines.append(f"  {when}  -- {day['display']} --")
            continue
        tag = f" [{day['kind']}]" if day["kind"] in TAGGED_KINDS else ""
        lines.append(f"  {when}  {day['lesson_text']}{tag}")
        indent = " " * (len(when) + 4)
        if day["target"]:
            lines.append(f"{indent}{day['target']}")
        if day["note"]:
            lines.append(f"{indent}note: {day['note']}")
        needs = missing_content(day, course)
        if needs:
            lines.append(f"{indent}needs: {', '.join(FIELD_LABELS[f] for f in needs)}")
    return lines


def format_needs(course, window):
    """Only the days in `window` still missing content, one line each."""
    gaps = [(day, missing_content(day, course)) for day in window]
    gaps = [(day, needs) for day, needs in gaps if needs]
    if not window:
        return [f"{course['course']}: no instructional days left in the calendar"]
    through = f"through {when_label(window[-1])}"
    if not gaps:
        return [f"{course['course']}: every lesson day has its content ({through})"]
    count = "1 day needs" if len(gaps) == 1 else f"{len(gaps)} days need"
    lines = [f"{course['course']}: {count} content ({through})"]
    for day, needs in gaps:
        lines.append(f"  {when_label(day)}  {day['lesson_text']}"
                     f" -- needs {', '.join(FIELD_LABELS[f] for f in needs)}")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("courses", nargs="*",
                        help="course slugs (default: every courses/*.json)")
    parser.add_argument("--days", type=int, default=10,
                        help="instructional days to show (default 10)")
    parser.add_argument("--from", dest="start", default=date.today().isoformat(),
                        help="first date, YYYY-MM-DD (default today)")
    parser.add_argument("--needs", action="store_true",
                        help="list only the days still missing target, class work, link, or an assignment link")
    args = parser.parse_args(argv)

    try:
        date.fromisoformat(args.start)
    except ValueError:
        parser.error(f"--from must be YYYY-MM-DD, got {args.start!r}")
    if args.days < 1:
        parser.error("--days must be at least 1")

    slugs = args.courses or sorted(p.stem for p in (ROOT / "courses").glob("*.json"))
    blocks = []
    for slug in slugs:
        path = ROOT / "courses" / f"{slug}.json"
        if not path.exists():
            parser.error(f"no course file {path.relative_to(ROOT)}")
        course = json.loads(path.read_text())
        fmt = format_needs if args.needs else format_course
        blocks.append("\n".join(fmt(course, lookahead(course, args.start, args.days))))
    print("\n\n".join(blocks))


if __name__ == "__main__":
    main()
