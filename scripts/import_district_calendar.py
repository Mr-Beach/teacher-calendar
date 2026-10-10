"""Read a district sample calendar (PDF) into curricula/<key>.json.

A curriculum file is what a v2 teacher starts a calendar from (v2/src/app.py,
"Start from"): the district's own sequence of its curriculum's lessons, in
the district's order and with its day counts (a lesson the district gives
two days is two entries), and the district's Flex and testing days. It's
shaped like a course file, so engine.template_from takes it as it takes
Aaron's courses. It holds nothing anyone chose for a class: no quizzes
(quiz_rule off), no homework, no links, and no I-can targets yet (those
come from the publisher's own list). Its review-day reminder is off too:
the district's calendars don't plan review days, and whether to is hers.

Each calendar month is a table in the PDF; pdfplumber reads its cells (plain
text extraction scrambles them -- see PLAN-v2-phase1.md, M7 results). A cell
is one school day. Four layouts so far:

    math6     "1.2 / Fluently Add ..." the first day, "1.2" the second
    math78    "1-1 Understand ...", "Math 8 2-3 ...", "5-4 ... & 5-7 ..."
    math8     "Lesson 2.1a / Let's Build: ...", then "Lesson 2.1b"
    algebra1  "09 / Alg1.1 Lesson 1: ..." (the date in the cell), "... AND
              Section A Checkpoint", "Math 8.4.3 ..." (IM grade 8 lessons)

A cell the district merged across days (MAP testing, a two-day test) reads
as None after its first day (pdfplumber), and is that same thing again; an
empty cell of its own reads as "" and is a day with nothing on it. Every date is
checked against the school's calendar (engine.school_record of courses/),
so a misread date fails loudly instead of shifting the year.

Needs pdfplumber (not used anywhere else in the repo):
    python3 -m venv /tmp/pdf && /tmp/pdf/bin/pip install pdfplumber
    /tmp/pdf/bin/python scripts/import_district_calendar.py math8 \\
        data/Sample_Calendar_Math_8_2026-27.pdf
Then review the result (it prints each day) before committing it.
"""
import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402

COURSES = {
    "math6": ("Math 6", "math6", "Savvas enVision Mathematics, Grade 6"),
    "math78": ("Math 7/8 Compacted", "math78", "Savvas enVision Mathematics, Grades 7 and 8"),
    "math8": ("Math 8", "math8", "Savvas Experience Math, Grade 8"),
    "algebra1": ("Algebra 1", "algebra1", "Illustrative Mathematics Algebra 1 (with IM Grade 8 lessons)"),
}
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
WEEKDAY_COLUMNS = {"MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, "FRIDAY": 4}


def clean(text):
    """One cell's text on one line, with the district's typos that would
    trip the patterns fixed ("Leson", "Lesson4.1b", "Lets", "Let'")."""
    text = re.sub(r"(?<=\w)-\n(?=\w)", "-", (text or "").replace("’", "'"))  # "Hard-\nWorking"
    text = " ".join(text.split())
    text = re.sub(r"\bLe?s+on ?(?=\d)", "Lesson ", text)
    text = re.sub(r"\bLets\b", "Let's", text)
    text = re.sub(r"\bLet' ", "Let's ", text)
    text = text.replace("ScientificNotation", "Scientific Notation")
    text = re.sub(r"^(\d+)\. (\d+)\b", r"\1.\2", text)  # Math 6's "4. 10"
    for typo, fix in (("Pythagoren", "Pythagorean"), ("Analzying", "Analyzing"), ("Elimation", "Elimination"),
                      ("that Involved Two", "that Involve Two")):
        text = text.replace(typo, fix)
    return text.strip()


# --- What a day is -----------------------------------------------------------

def day_kind(text):
    """(type, note) for a cell that isn't a lesson, or None if it is one.
    The type is a school-day type (engine.VALID_DAY_TYPES)."""
    t = text.lower()
    if "no school" in t:
        return "No School", text
    if "flex" in t:
        return "Flex", "Last Day Early Dismissal" if "last day" in t else \
            "Early Dismissal" if "early dismissal" in t else "Flex Day"
    if re.search(r"\bmap\b", t):
        return "Testing", "MAP Testing"
    if re.search(r"\bsba\b", t):
        return "Testing", "SBA Testing"
    if "snow make up" in t:
        return "Other", "Snow make up if needed"
    if "last day" in t:
        return "Other", "Last Day Early Dismissal"
    if t == "first day of school":
        return "Other", "First Day of School"
    return None


def entry(title, code=None, kind="Lesson", topic=None):
    return {"topic": topic, "lesson_code": code, "district_title": title, "kind": kind,
            "target": None, "classwork": None, "homework": None, "link": None,
            "extra_materials": None}


def _assessment(text):
    return re.search(r"assessment|\btest\b", text, re.I) and not re.search(r"readiness", text, re.I)


def _topic_items(text, seen):
    """Shared by the Savvas layouts: openers, reviews, assessments, and the
    start-of-year days. None if the cell is a lesson."""
    m = re.match(r"(?:First Day of School )?Topic (\d+) Day (\d+)", text)
    if m:
        return [entry(f"Topic {m[1]} Day {m[2]}", topic=m[1])]
    m = re.fullmatch(r"(?:First Day of School )?Topic (\d+)", text)
    if m:  # Math 7/8's "Topic 0" days, unnumbered
        n = seen[f"days {m[1]}"] = seen.get(f"days {m[1]}", 0) + 1
        return [entry(f"Topic {m[1]} Day {n}", topic=m[1])]
    m = re.match(r"Topic (\d+) Opener ?(.*)", text)
    if m:
        name = m[2].strip() if m[2] and not m[2].startswith("-") else ""
        key = f"opener {m[1]}"
        if name or key not in seen:  # its second day reads "Topic 1 Opener"
            seen[key] = entry(f"Topic {m[1]} Opener" + (f": {name}" if name else ""), kind="Opener", topic=m[1])
        return [dict(seen[key])]
    m = re.match(r"(?:CEA #?\d*:? ?)?(Math 8 )?Topic (\d+)(?: and (\d+))? (Review|.*Assessment)", text)
    if m:
        # Math 7/8 teaches some Math 8 topics; "Math 8 Topic 5" isn't its Topic 5.
        m8 = "Math 8 " if m[1] else ""
        topics = f"{m[2]} and {m[3]}" if m[3] else m[2]
        topic = ("M8 " if m8 else "") + m[2]
        cea = re.search(r"CEA #?(\d+)", text)
        if m[4] == "Review":
            return [entry(f"{m8}Topic {topics} Review", topic=topic)]
        return [entry(f"{m8}Topic {topics} Test" + (f" (CEA #{cea[1]})" if cea else ""), kind="Test", topic=topic)]
    m = re.match(r"CEA Topic (\d+) Assessment", text)
    if m:
        return [entry(f"Topic {m[1]} Test (CEA)", kind="Test", topic=m[1])]
    return None


def items_math6(text, seen):
    """Math 6: "1.2 Fluently Add ...", "1.2" (its second day), "1.4 3-Act
    "Stocking Up"", "Topic 2 Lesson 1 Understand Integers"."""
    found = _topic_items(text, seen)
    if found is not None:
        return found
    m = re.match(r"(?:Topic (\d+) Lesson (\d+)|(\d+)\.(\d+))\s*(.*)", text)
    if not m:
        raise ValueError(f"can't read {text!r}")
    topic, n = (m[1], m[2]) if m[1] else (m[3], m[4])
    code, rest = f"{topic}.{n}", m[5].strip()
    if not rest:
        return [dict(seen[code])]  # its second (or third) day
    kind = "Lesson"
    am = re.match(r"3-Act(?: Math)? (.*)", rest)
    if am:
        kind, rest = "3-Act", f"3-Act Math: {am[1]}"
    seen[code] = entry(rest, code=code, kind=kind, topic=topic)
    return [dict(seen[code])]


def items_math78(text, seen):
    """Math 7/8: "1-1 Understand ...", "Math 8 2-3 Solve ...", "5-4 Expand
    Expressions & 5-7 Subtract Expressions", "Topic 3 Review"."""
    found = _topic_items(text, seen)
    if found is not None:
        return found
    parts = re.split(r" & (?=(?:Math 8 )?(?:Topic )?\d+-\d+)", text)
    codes, titles, topic, kind = [], [], None, "Lesson"
    for part in parts:
        m = re.match(r"(Math 8 )?(?:Topic )?(\d+)-(\d+)\s*(.*)", part)
        if not m:
            raise ValueError(f"can't read {text!r}")
        code = ("M8 " if m[1] else "") + f"{m[2]}.{m[3]}"
        rest = m[4].strip()
        pm = re.match(r"Part (\d+) Assessment", rest)
        if pm:  # "7-5 Part 1 Assessment": Topic 7's Part 1 test, not lesson 7.5
            return [entry(f"Topic {m[2]} Part {pm[1]} Test", kind="Test", topic=m[2])]
        if code in seen:  # every day of a lesson reads as its first day does
            rest = seen[code]["district_title"]
        elif not rest:
            raise ValueError(f"{code} has no title before {text!r}")
        if re.search(r"\(3- ?Act\)", rest):
            kind, rest = "3-Act", "3-Act Math: " + re.sub(r"\s*\(3- ?Act\)", "", rest)
        elif code in seen:
            kind = seen[code]["kind"]
        seen[code] = entry(rest, code=code, kind=kind, topic=("M8 " if m[1] else "") + m[2])
        codes.append(code)
        titles.append(rest)
        topic = topic or seen[code]["topic"]
    if len(parts) == 1:
        return [dict(seen[codes[0]])]
    return [entry(" & ".join(titles), code=" & ".join(codes), kind=kind, topic=topic)]


def items_math8(text, seen):
    """Math 8 (Savvas Experience Math): "Lesson 2.1a Let's Build: Combine
    ...", "Lesson 2.1b", "Lesson 2.6 Let's Model in 3 Acts: Powering Down",
    "Topic 2 Opener -Math Walk ...", "Topic 2 End of Topic Assessment"."""
    m = re.match(r"Topic (\d+) Opener", text)
    if m:
        return [entry(f"Topic {m[1]} Opener", kind="Opener", topic=m[1])]
    found = _topic_items(text.replace("End of Topic Assessment", "Assessment")
                         .replace("End of Topic ", ""), seen)
    if found is not None:
        return found
    m = re.match(r"Lesson (\d+)\.(\d+)([a-c]?)\s*(.*)", text)
    if not m:
        raise ValueError(f"can't read {text!r}")
    code, rest = f"{m[1]}.{m[2]}", m[4].strip()
    if not rest:
        if code not in seen:
            raise ValueError(f"{code} has no title before {text!r}")
        return [dict(seen[code])]
    kind = "Lesson"
    am = re.match(r"Let's Model in 3 Acts: (.*)", rest)
    if am:
        kind, rest = "3-Act", f"3-Act Math: {am[1]}"
    else:
        rest = re.sub(r"^Let's (Build|Investigate): ", "", rest)
    seen[code] = entry(rest, code=code, kind=kind, topic=m[1])
    return [dict(seen[code])]


def _algebra_one(part, seen):
    """One activity in an Algebra 1 cell, as (title, kind, unit)."""
    part = re.sub(r"\*", "", part).strip()
    m = re.match(r"(?:Alg1|Algebra 1)\.(\d+) (.*)", part)
    unit = None
    if m:
        unit, part = m[1], m[2].strip()
        if part.startswith("Lesson") and int(unit) < int(seen.get("lesson unit", 0)):
            unit = seen["lesson unit"]  # "Alg1.7 Lesson 6" between Alg1.8's 5 and 7
        seen["unit"] = unit
    unit = unit or seen.get("unit")
    if part.startswith("Lesson"):
        seen["lesson unit"] = unit
    if part == f"Unit {unit}":  # the start-of-year days
        n = seen[f"days {unit}"] = seen.get(f"days {unit}", 0) + 1
        return f"Unit {unit} Day {n}", "Lesson", unit
    m = re.match(r"Lesson (\d+)\s*&\s*(\d+): (.*)", part)
    if m:  # "Lesson 6&7: ..." -- two lessons in one day
        return f"Unit {unit} Lessons {m[1]} & {m[2]}: {m[3]}", "Lesson", unit
    m = re.match(r"Lesson (\d+): (.*)", part)
    if m:
        return f"Unit {unit} Lesson {m[1]}: {m[2]}", "Lesson", unit
    m = re.match(r"Math 8\.(\d+)\.(\d+):? (.*)", part)
    if m:
        return f"Grade 8 Unit {m[1]} Lesson {m[2]}: {m[3]}", "Lesson", unit
    m = re.match(r"Section (?:Checkpoint )?([A-F]) Checkpoint|Section Checkpoint ([A-F])", part)
    if m:
        return f"Section {m[1] or m[2]} Checkpoint", "Lesson", unit
    if re.match(r"(End of Unit |Mid-Unit )?(Unit )?Review", part):
        return f"Unit {unit} Review", "Lesson", unit
    if re.match(r"(End of Unit|Mid-Unit) Assessment", part):
        return f"Unit {unit} {part}", "Test", unit
    if re.match(r"Check Your Readiness", part):
        return f"Unit {unit} Check Your Readiness", "Lesson", unit
    raise ValueError(f"can't read {part!r}")


def items_algebra1(text, seen):
    """Algebra 1 (IM): "Alg1.1 Lesson 3: A Gallery of Data AND Section A
    Checkpoint", "Math 8.4.12 Systems of Equations", "CEA Alg1.2 End of
    Unit Assessment"."""
    cea = text.startswith("CEA ")
    text = text[4:] if cea else text
    pieces = [_algebra_one(p, seen) for p in re.split(r" AND | and (?=Math 8\.)", text)]
    # One unit name in front: "Unit 2 Lesson 1: ... + Lesson 2: ...", or
    # "Unit 7: Section A Checkpoint + Lesson 3: ..." -- unless the pieces
    # are from different units ("Unit 7 Check Your Readiness + Unit 8 ...").
    units = {u for _, _, u in pieces}
    titles = [t for t, _, _ in pieces]
    if len(units) == 1 and len(titles) > 1 and not titles[0].startswith("Grade 8"):
        unit = units.pop()
        rest = [re.sub(rf"^Unit {unit} ", "", t) for t in titles]
        titles = [f"Unit {unit}: {rest[0]}" if rest[0].startswith("Section") else f"Unit {unit} {rest[0]}"] + rest[1:]
    elif len(titles) == 1 and titles[0].startswith("Section"):
        titles = [f"Unit {pieces[0][2]}: {titles[0]}"]
    kind = "Test" if any(k == "Test" for _, k, _ in pieces) else "Lesson"
    title = " + ".join(titles) + (" (CEA)" if cea else "")
    return [entry(title, kind=kind, topic=pieces[0][2])]


ITEMS = {"math6": items_math6, "math78": items_math78, "math8": items_math8, "algebra1": items_algebra1}


# --- Reading the PDF -----------------------------------------------------------

def month_of(page_text):
    m = re.search(r"(" + "|".join(MONTHS) + r")\b.*?(\d{4})", page_text)
    if not m:
        raise ValueError(f"no month on page: {page_text[:80]!r}")
    return MONTHS.index(m[1]) + 1, int(m[2])


def cells(pdf_path):
    """{date: cell text} for every weekday cell with something in it, and
    the set of dates whose cell is merged into the one before."""
    import pdfplumber
    out, merged, spill = {}, set(), {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            month, year = month_of(page.extract_text() or "")
            for found in page.find_tables():
                table = found.extract()
                header = next((i for i, row in enumerate(table) if "MONDAY" in [c or "" for c in row]), None)
                if header is None:
                    continue
                table += _row_below(page, found, header)
                cols = {j: WEEKDAY_COLUMNS[c] for j, c in enumerate(table[header]) if c in WEEKDAY_COLUMNS}
                _read_rows(table[header + 1:], cols, month, year, out, merged, spill)
    for d, text in spill.items():
        out.setdefault(d, text)
    return out, merged


def _row_below(page, found, header):
    """A month's last week, when the PDF draws no line under it: pdfplumber
    ends the table at the last line, and Math 7/8's last weeks sit below
    it. Read one more row there, on the header's columns, if day numbers
    are there to read."""
    edges = sorted({round(x) for cell in found.rows[header].cells if cell for x in (cell[0], cell[2])})
    bottom = found.bbox[3]
    heights = [r.bbox[3] - r.bbox[1] for r in found.rows[header + 1:]]
    if not heights:
        return []
    below = page.crop((found.bbox[0], bottom, found.bbox[2], min(page.height, bottom + max(heights))))
    if not any(re.fullmatch(r"\d{1,2}", w["text"]) for w in below.extract_words()):
        return []
    row = below.extract_table({"vertical_strategy": "explicit", "horizontal_strategy": "explicit",
                               "explicit_vertical_lines": edges,
                               "explicit_horizontal_lines": [bottom, bottom + max(heights)]})
    return [[c or None for c in r] for r in row or []]


def _read_rows(rows, cols, month, year, out, merged, spill):
    """A month's rows, in either layout, row by row: a row of day numbers
    ("05", "06", ...) followed by its content row, or a row whose cells
    start with their day number ("09 / Alg1.1 ..."; Algebra 1, and Math
    7/8's June)."""
    i, monday = 0, None
    while i < len(rows):
        row = rows[i]
        nums = {} if _dated_cells(row, cols) else _day_numbers(row, cols)
        if nums:
            # Its content row, unless the next row is the next week's dates
            # (a spill-over week with nothing in it has no content row).
            has_content = i + 1 < len(rows) and not _day_numbers(rows[i + 1], cols) \
                and not _dated_cells(rows[i + 1], cols)
            content = rows[i + 1] if has_content else [None] * len(row)
            week = {cols[j]: content[j] if j < len(content) else None for j in cols}
            i += 2 if has_content else 1
        else:
            dated = _dated_cells(row, cols)
            i += 1
            if not dated:
                continue
            nums = {wd: str(n) for wd, (n, _) in dated.items()}
            week = {wd: dated.get(wd, (None, None))[1] for wd in range(5)}
        # The first row from its day numbers; each row after it, a week on.
        monday = _monday(nums, month, year) if monday is None else monday + timedelta(days=7)
        prev_text = None
        for wd in range(5):
            d = monday + timedelta(days=wd)
            if wd in nums and int(nums[wd]) != d.day:
                raise ValueError(f"{d}: the calendar says {nums[wd]}")
            raw = week.get(wd)
            text = clean(raw)
            if d.month != month:
                # A day from the month before or after, shown on this page
                # (Algebra 1's April 1-2 are only on the March page). Its
                # own page wins when that has something.
                if text:
                    spill.setdefault(d, text)
                prev_text = None
                continue
            if text:
                out[d] = text
                prev_text = text
            elif raw is None and prev_text:
                merged.add(d)  # pdfplumber's None: covered by the cell before
            else:
                prev_text = None  # "": a cell of its own, empty


def _day_numbers(row, cols):
    return {cols[j]: c.strip() for j, c in enumerate(row)
            if j in cols and c and re.fullmatch(r"\s*\d{1,2}\s*", c)}


def _dated_cells(row, cols):
    """{weekday: (day number, text after it)} for cells that start with their
    day number, as long as at least one has text after it."""
    out = {}
    for j, c in enumerate(row):
        if j in cols and c:
            m = re.match(r"\s*(\d{1,2})[ \t]*(?:\n|$)(.*)", c, re.S)  # "09\nAlg1.1 ...", not "2.4\n3-Act"
            if m:
                out[cols[j]] = (int(m[1]), m[2].strip())
    return out if any(t for _, t in out.values()) else {}


def _monday(nums, month, year):
    """The Monday of a calendar row, from its day numbers ({weekday: "05"}):
    the one month (this page's, or the one before or after it, for days
    spilling over) where that number falls on that weekday."""
    wd, n = min(nums.items())
    found = []
    for dm in (-1, 0, 1):
        m, y = month + dm, year
        if m < 1:
            m, y = 12, year - 1
        elif m > 12:
            m, y = 1, year + 1
        try:
            d = date(y, m, int(n))
        except ValueError:
            continue
        if d.weekday() == wd:
            found.append(d)
    if len(found) > 1:  # Feb 1 and Mar 1 2027 are both Mondays: a month's
        found = [d for d in found if d.month == month]  # first row is its own
    if len(found) != 1:
        raise ValueError(f"can't place day {n} ({['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][wd]}) in {MONTHS[month - 1]} {year}")
    return found[0] - timedelta(days=wd)


# --- Building the curriculum ----------------------------------------------------

def school_days():
    """The school's days (the closures both of Aaron's courses agree on)."""
    courses = [json.loads((ROOT / "courses" / f"{c}.json").read_text()) for c in ("math6", "math78")]
    return engine.school_record(*courses)


def build(key, texts, merged, days):
    """The curriculum dict from {date: cell text}, the merged dates, and the
    school's days. Raises ValueError where the calendar and the school's
    days disagree."""
    title, _, curriculum = COURSES[key]
    item_reader = ITEMS[key]
    seen, sequence, out_days, log, errors = {}, [], [], [], []
    last = None
    for sd in days:
        d = date.fromisoformat(sd["date"])
        text = texts.get(d)
        if sd["type"] == "No School":
            # A merged cell running on past the school year's end (June's
            # "Snow make up" into the 24th) isn't a day; written text is.
            if text and (day_kind(text) or ("",))[0] != "No School":
                raise ValueError(f"{d}: the school is closed, the calendar says {text!r}")
            out_days.append(dict(sd))
            log.append((sd["date"], "closed", sd["note"] or "No School"))
            last = None
            continue
        if d in merged:
            text = last
        if not text:
            out_days.append(dict(sd))
            log.append((sd["date"], "EMPTY", ""))
            last = None
            continue
        kind = day_kind(text)
        if kind and kind[0] == "No School":
            raise ValueError(f"{d}: the calendar says {text!r} but it's a school day")
        if kind:
            out_days.append({**sd, "type": kind[0], "note": kind[1]})
            log.append((sd["date"], kind[0], kind[1] or ""))
        else:
            try:
                items = item_reader(text, seen)
            except ValueError as e:
                errors.append(f"{d}: {e}")
                items = []
            for item in items:
                sequence.append(item)
                log.append((sd["date"], item["kind"], engine.lesson_title(item)))
            out_days.append(dict(sd))
        last = text
    if errors:
        raise ValueError("cells the importer can't read:\n  " + "\n  ".join(errors))
    start = next(i for i, sd in enumerate(out_days) if sd["type"] != "No School")
    year = f"{days[0]['date'][:4]}-{days[-1]['date'][2:4]}"
    return {
        "course": title,
        "school_year": year,
        "curriculum": curriculum,
        "source": f"Seattle Public Schools, {title} Sample Calendar {year}",
        # Nothing a teacher chooses: no quizzes, no review-day reminder,
        # no class-work row (Settings turns any of them on).
        "show_classwork": False,
        "review_before_test": False,
        "quiz_rule": {"enabled": False},
        "school_days": out_days[start:] if start else out_days,
        "sequence": sequence,
        "changes": [],
    }, log


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("key", choices=sorted(COURSES))
    ap.add_argument("pdf")
    ap.add_argument("--write", action="store_true", help="write curricula/<key>.json (default: print only)")
    args = ap.parse_args(argv)
    texts, merged = cells(args.pdf)
    days = school_days()
    curriculum, log = build(args.key, texts, merged, days)
    for line in log:
        print("  ".join(line))
    print(f"{len(curriculum['sequence'])} lessons")
    if args.write:
        out = ROOT / "curricula" / f"{args.key}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(curriculum, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
