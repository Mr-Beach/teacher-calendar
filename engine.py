"""Re-flow engine: (school-day calendar, course sequence) -> rendered calendar.

Instructional days take the next lesson off the sequence, in date order. Every
other day type renders as itself. This is the one piece of logic that matters:
change a day's type in the course JSON and everything after it shifts on its own.
"""
import json
import sys
from pathlib import Path


def render(course):
    sequence = course["sequence"]
    calendar = []
    slot = 0
    for day in course["school_days"]:
        note = day["note"]
        if day["type"] == "Instruction":
            lesson = sequence[slot] if slot < len(sequence) else None
            slot += 1
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
            calendar.append(
                {
                    "date": day["date"],
                    "weekday": day["weekday"],
                    "type": day["type"],
                    "display": display,
                    "lesson_text": base,
                    "kind": kind,
                    "homework": lesson["homework"] if lesson else None,
                    "note": note,
                }
            )
        else:
            # A non-instructional day has no lesson to show alongside, so the
            # note (e.g. "No School (Holiday)") replaces the bare type label.
            calendar.append(
                {
                    "date": day["date"],
                    "weekday": day["weekday"],
                    "type": day["type"],
                    "display": note or day["type"],
                    "lesson_text": None,
                    "kind": None,
                    "homework": None,
                    "note": note,
                }
            )
    leftover = len(sequence) - slot
    return calendar, leftover


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "courses/math6.json")
    course = json.loads(path.read_text())
    calendar, leftover = render(course)
    print(f"leftover lessons with no day left: {leftover}", file=sys.stderr)
    for day in calendar:
        if day["date"].startswith(sys.argv[2] if len(sys.argv) > 2 else "2026-09"):
            print(day["date"], day["weekday"], "|", day["display"])
