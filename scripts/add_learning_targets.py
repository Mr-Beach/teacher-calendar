"""Put a publisher's own I-can targets on a curriculum's lessons.

So far: Illustrative Mathematics v.360 for Algebra 1 (and the IM Grade 8
lessons the district's Algebra 1 calendar borrows). The targets were read
from IM's student "learning targets" pages into
curricula/sources/im-v360-learning-targets.json, with IM's license and
attribution (CC BY-NC 4.0: free to use and adapt, not for paid products,
with credit). This matches each lesson in curricula/algebra1.json to IM's
by unit and lesson, checking the titles agree, instead of putting the
wrong lesson's targets on a day: where the numbers differ (the district
numbers Units 5 and 6 differently from v.360), the title decides. A day with two lessons gets both lessons'
targets. Reviews, checkpoints on their own, readiness checks, and tests
get none.

    python3 scripts/add_learning_targets.py            # report only
    python3 scripts/add_learning_targets.py --write    # update curricula/algebra1.json

Savvas's targets (Math 6, 7/8, 8) aren't public; they'd come from Aaron's
own export, matched by lesson code the same way.
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "curricula" / "sources" / "im-v360-learning-targets.json"


def _norm(title):
    """A title for comparing: case, punctuation, and notes in parentheses
    ("(can be used as the review)") ignored -- but not "(Part 2)", which
    tells two lessons apart."""
    title = re.sub(r"\((?!part)[^)]*\)", "", title.lower())
    return re.sub(r"[^a-z0-9]+", " ", title).strip()


def same_title(a, b):
    """Whether two lesson titles name the same lesson, allowing the
    district's small slips ("What are Percent Squares" for IM's "What Are
    Perfect Squares?")."""
    a, b = _norm(a), _norm(b)
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def find_lesson(unit_lessons, n, title):
    """IM's lesson for the district's "Lesson n: title": by number when the
    titles agree, otherwise the one lesson in the unit with that title (the
    district numbers some units differently from IM v.360). None if
    neither finds it."""
    lesson = unit_lessons.get(n)
    if lesson and same_title(lesson["title"], title):
        return lesson
    # The same title exactly, else nearly ("Part 1" and "Part 2" are nearly
    # the same, so exact goes first).
    for match in (lambda l: _norm(l["title"]) == _norm(title), lambda l: same_title(l["title"], title)):
        by_title = [l for l in unit_lessons.values() if match(l)]
        if by_title:
            return by_title[0] if len(by_title) == 1 else None
    return None


def lesson_refs(entry):
    """[(course, unit, lesson, title)] for the IM lessons on one Algebra 1
    day, read from its title: "Unit 2 Lesson 1: Planning a Party + Lesson
    2: Writing Equations ...", "Unit 7 Lessons 6 & 7: Building ...",
    "Grade 8 Unit 4 Lesson 3: Balanced Moves + ..."."""
    refs, unit = [], entry["topic"]
    for piece in entry["district_title"].split(" + "):
        m = re.match(r"(?:(Grade 8) )?(?:Unit (\d+)(?::)? )?Lessons? (\d+)(?: & (\d+))?: (.*)", piece)
        if not m:
            continue  # a checkpoint, review, readiness check, or test
        course = "grade-8" if m[1] else "algebra-1"
        u = m[2] or unit
        for n in filter(None, (m[3], m[4])):
            refs.append((course, u, n, m[5]))
    return refs


def apply_im(curriculum, source):
    """Set each lesson's target from `source`; returns a list of problems
    (lessons IM doesn't have, or whose titles don't agree)."""
    problems = []
    for entry in curriculum["sequence"]:
        targets = []
        for course, unit, n, title in lesson_refs(entry):
            lesson = find_lesson(source["courses"].get(course, {}).get(unit, {}).get("lessons", {}), n, title)
            if lesson is None:
                # The district's own additions (its "adaptation pack"):
                # left blank rather than given another lesson's targets.
                problems.append(f"{course} unit {unit} lesson {n} ({title}): not an IM v.360 lesson")
                continue
            targets += [t for t in lesson["targets"] if t not in targets]
        entry["target"] = " ".join(targets) or None
    curriculum["credits"] = [source["attribution"]] if any(e["target"] for e in curriculum["sequence"]) else []
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    path = ROOT / "curricula" / "algebra1.json"
    curriculum = json.loads(path.read_text())
    problems = apply_im(curriculum, json.loads(SOURCE.read_text()))
    with_targets = sum(1 for e in curriculum["sequence"] if e["target"])
    print(f"{with_targets} of {len(curriculum['sequence'])} days have targets")
    for p in problems:
        print("  ", p)
    if args.write:
        path.write_text(json.dumps(curriculum, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
