"""The current sequence of a course, topic by topic, for the curriculum audit
(audit/README.md).

Reads courses/<course>.json through engine.place(), so it always matches the
published calendar. Prints markdown: the day budget (lessons that run past
the end of the year, tests missing a review day), then every topic's
lessons in order, with the dates each one takes, how many days, and whether
it's already been taught. Consecutive days of the same lesson are one row
("2 days"); those second days are PLANNING.md's third cut candidate.

Usage:
    python3 scripts/audit_export.py math6
    python3 scripts/audit_export.py math78 --today 2026-10-05
"""
import argparse
import json
import sys
from itertools import groupby
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402


def lesson_runs(course):
    """Consecutive sequence entries for the same lesson, as
    (topic, title, kind, planned days, [dates]) -- fewer dates than planned
    days when some have no day left before the year ends."""
    placements, _ = engine.place(course)
    date_of = {id(item): day["date"] for day, item in placements if item is not None}
    key = lambda e: (e["topic"], e["lesson_code"], e["district_title"], e["kind"])  # noqa: E731
    return [(k[0], engine.lesson_title(group[0]), k[3], len(group),
             [date_of[id(e)] for e in group if id(e) in date_of])
            for k, grp in groupby(course["sequence"], key=key) for group in [list(grp)]]


def export(course, today):
    runs = lesson_runs(course)
    checks = {label: ws for label, ws in engine.run_all_checks(course)}
    leftover = engine.render(course)[1]
    missing_review = checks["review before test"]
    last_day = [d["date"] for d in course["school_days"] if d["type"] == "Instruction"][-1]
    multi = [r for r in runs if r[3] > 1 and (not r[4] or r[4][0] >= today)]

    out = [f"# {course['course']}: current sequence",
           "",
           f"From courses/*.json as of {engine.short_date(today)}. Last instructional day: {engine.short_date(last_day)}.",
           "",
           "## Day budget",
           "",
           f"- Lessons with no day left before the year ends: **{leftover}**"]
    out += [f"  - {w}" for w in checks["leftover lessons"]]
    out.append(f"- Tests with no review day right before them: **{len(missing_review)}** "
               f"(each review day added costs at least one more day)")
    out += [f"  - {w}" for w in missing_review]
    out.append(f"- Lessons not yet taught that take more than one day: **{len(multi)}** "
               f"({sum(r[3] - 1 for r in multi)} extra days in all)")
    out += ["", "Kinds: Lesson, Opener (Topic Opener), 3-Act, Project, Test. Quizzes are placed "
            "automatically every Wednesday and aren't listed. A review day is a Lesson.", ""]

    for topic, topic_runs in groupby(runs, key=lambda r: r[0]):
        topic_runs = list(topic_runs)
        days = sum(r[3] for r in topic_runs)
        out += [f"## Topic {topic or '(none)'}: {days} day(s)", "",
                "| Lesson | Kind | Days | Dates | Status |", "|---|---|---|---|---|"]
        for _, title, kind, planned, dates in topic_runs:
            if not dates:
                when = "none"
            else:
                when = engine.short_date(dates[0]) if len(dates) == 1 else f"{engine.short_date(dates[0])} to {engine.short_date(dates[-1])}"
            status = ("taught" if dates and dates[-1] < today
                      else "in progress" if dates and dates[0] < today else "")
            if len(dates) < planned:
                status = f"**{planned - len(dates)} with no day left**"
            out.append(f"| {title} | {kind} | {planned} | {when} | {status} |")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("course", help="math6 or math78")
    ap.add_argument("--today", default=engine.school_today().isoformat(), help="YYYY-MM-DD (default: today)")
    args = ap.parse_args(argv)
    path = ROOT / "courses" / f"{args.course}.json"
    if not path.exists():
        print(f"no course file {path.relative_to(ROOT)}", file=sys.stderr)
        return 1
    print(export(json.loads(path.read_text()), args.today))
    return 0


if __name__ == "__main__":
    sys.exit(main())
