"""Render a course's data file into a single static HTML calendar page.

Usage:
    python3 render.py courses/math6.json > /tmp/preview.html

Cloudflare Workers Builds renders every course with this on each push to
main, via scripts/build_site.py, and deploys the result to
beach-math.com/<course> (CLAUDE.md, "Hosting"); the output is never
committed. Run it by hand only to preview, and never into docs/index.html
-- that file is the redirect stub for old github.io bookmarks.

The page has three views:

- Upcoming (the default): a "today" card, the homework still open, the next
  quiz and test, then every school day as a list, week by week through
  June. Weeks already over fold away behind "Show earlier weeks". Tapping a
  day opens its details in place, under its row.
- Homework: this topic's assignments so far, each under the Practice Log
  it goes in, with that log's answer-key folder. A topic runs from the day
  after one test through the next. Earlier topics fold away behind "Show
  earlier topics"; the Homework list on Upcoming links here.
- Whole year: Monday-Friday month grids -- two months side by side on a
  wide screen, one on a phone -- with arrows that move one month at a time.
  A day with something due carries a "Due" tag. Tapping a day shows its
  details under the month; otherwise that space lists the months' key
  dates (tests, quizzes, days off).

Everything date-dependent ("today", which weeks are past, which homework is
open) is worked out in the visitor's browser: the page is only rebuilt when
the calendar changes, not daily, so anything baked in at build time would
be stale by the next morning. A day's details are rendered here, once, as
the panel under its row; the today card and the Whole-year detail card
copy that same panel.

Keep this file runnable on older Python 3 (Cloudflare's build image isn't
pinned): no f-strings that nest the same quote character.
"""
import json
import re
import sys
from datetime import date, timedelta
from itertools import groupby
from pathlib import Path

from engine import (ASSESSMENT_KINDS, is_practice_log, quiz_rule, render, run_all_checks,
                    set_through, short_date, week_monday)

# Shown under the course name. A course can name its own teacher ("teacher");
# Aaron's course files don't, so they get this.
TEACHER = "Mr. Beach"
# Color presets a course can pick with "theme" (SPEC-v2 / PLAN-v2-phase1,
# M1). Each one swaps the page's ground, ink, accent, and neutrals; the
# meaning colors -- quiz blue, test orange, today and "soon" yellow, white
# on dark fills -- are the same in every preset, so a student reads them
# the same way on any teacher's page. Presets, not a color picker, so every
# one can be checked for readability (tests/test_themes.py). "teal" is the
# page's own look, written in PAGE's :root; the others override it.
THEMES = {
    "teal": {},
    "plum": {"--bg": "#F5F0F7", "--ink": "#3A1F4D", "--muted": "#5E4870", "--line": "#EAE1EF",
             "--accent": "#83285F", "--closed-bg": "#F6F3F8", "--closed-ink": "#62507A",
             "--dash": "#CDBCD8", "--soft": "#F0E8F4", "--dashed": "#9A84AA"},
    "forest": {"--bg": "#EFF4EA", "--ink": "#1E3324", "--muted": "#435C48", "--line": "#DFE8D9",
               "--accent": "#2D6528", "--closed-bg": "#F3F6F0", "--closed-ink": "#4F6354",
               "--dash": "#B9CBB3", "--soft": "#E6EFE1", "--dashed": "#849B7E"},
    "slate": {"--bg": "#F1F3F5", "--ink": "#1D232B", "--muted": "#4A5461", "--line": "#E2E5E9",
              "--accent": "#2B5AA3", "--closed-bg": "#F4F5F7", "--closed-ink": "#555E6B",
              "--dash": "#BCC3CC", "--soft": "#E8EBEF", "--dashed": "#87909C"},
}


def theme_css(course):
    """The :root override for the course's "theme" (none for "teal", the
    default). Raises ValueError on a theme that isn't a preset."""
    name = course.get("theme") or "teal"
    if name not in THEMES:
        raise ValueError(f"theme must be one of {sorted(THEMES)}, got {name!r}")
    tokens = THEMES[name]
    if not tokens:
        return ""
    return "\n  :root { " + " ".join(f"{k}: {v};" for k, v in tokens.items()) + " }"


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# A displayed lesson code at the start of a title: "T1L2", "M8 T5L1",
# "T5L3 & T5L6" (engine.display_code's output).
CODE_RE = re.compile(r"(?:M8 )?T\d+L\d+(?: & (?:M8 )?T\d+L\d+)*")
CHEVRON = ('<svg class="chev" width="18" height="18" viewBox="0 0 24 24" fill="none" '
           'stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
           'stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"></path></svg>')
ARROW = ' <span aria-hidden="true">↗</span>'
DUE_TAG = '<span class="due-tag">Due</span>'
PAIRED_TAG = '<span class="quiz-tag">+Quiz</span>'
SG_TAG = '<span class="sg-tag">+Self-grade</span>'
EMPTY_CELL = '<span class="cell cell-none"></span>'


def esc(s):
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def to_json(value):
    # </script> can't appear literally inside a script body.
    return json.dumps(value).replace("</", "<\\/")


def long_date(iso):
    """'2026-10-08' -> 'Thursday, October 8'."""
    d = date.fromisoformat(iso)
    return f"{WEEKDAY_NAMES[d.weekday()]}, {MONTH_NAMES[d.month - 1]} {d.day}"


def week_range(first_iso, last_iso):
    """'Oct 5–9', or 'Sep 28–Oct 2' across a month boundary."""
    a, b = date.fromisoformat(first_iso), date.fromisoformat(last_iso)
    start = f"{MONTH_NAMES[a.month - 1][:3]} {a.day}"
    if a == b:
        return start
    end = str(b.day) if a.month == b.month else f"{MONTH_NAMES[b.month - 1][:3]} {b.day}"
    return f"{start}–{end}"


def day_kind(day):
    """The style a day gets: lesson, opener, threeact, quiz, test, project, or closed."""
    if day["type"] != "Instruction":
        return "closed"
    return {"Quiz": "quiz", "Test": "test", "Opener": "opener", "3-Act": "threeact",
            "Project": "project"}.get(
        day["kind"], "lesson")


def split_code(title):
    """('T1L2', 'Fluently Add...') for a coded title, ('', title) otherwise."""
    m = CODE_RE.match(title or "")
    return (m.group(0), title[m.end():].strip()) if m else ("", title or "")


def day_title(day):
    return day["lesson_text"] if day["type"] == "Instruction" else day["display"]


def is_quiz_redo(text):
    lower = text.lower()
    return "quiz" in lower and "redo" in lower


def muted(text):
    return f'<span class="muted">{esc(text)}</span>'


# --- A day's details: the panel under its row --------------------------------

def hw_text(item):
    """An assignment's text, as a link to its own page when it has one."""
    if not item.get("link"):
        return esc(item["text"])
    return (f'<a class="hwlink" href="{esc(item["link"])}" target="_blank" rel="noopener">'
            f'{esc(item["text"])}{ARROW}</a>')


def log_checklist(item):
    """The assignments a Practice Log covers, as a checklist."""
    rows = []
    for c in item.get("includes") or []:
        due = " " + muted(f"(due {short_date(c['due'])})") if c.get("due") else ""
        rows.append(f"<li>{hw_text(c)}{due}</li>")
    return f'<ul class="log">{"".join(rows)}</ul>' if rows else ""


def due_note(due, course):
    """What to do with an assignment on its due date, from the course's
    "due_notes": "practice_log" for the log itself, "in_log" for an
    assignment that goes in a Practice Log. None when the course sets none."""
    notes = course.get("due_notes") or {}
    if is_practice_log(due):
        return notes.get("practice_log")
    if due.get("log_due"):
        return notes.get("in_log")
    return None


def is_planned(day):
    """A lesson day after the course's set-through date (engine.set_through):
    its lesson and homework are the plan, and may still shift. Never an
    assessment day (engine.ASSESSMENT_KINDS): those dates count as set as
    soon as they're on the calendar."""
    return (day["type"] == "Instruction" and not day.get("set", True)
            and day["kind"] not in ASSESSMENT_KINDS)


PLANNED = ' <span class="plan-note" data-plan>(planned)</span>'


def render_panel(day, course):
    parts = []
    planned = is_planned(day)
    if planned:
        parts.append('<p class="pnl-planned" data-plan>Planned: this day may still change.</p>')
    if day.get("quiz_paired"):
        parts.append('<p class="pnl-quiz">+ Quiz today, sharing the period with this lesson</p>')
    if day.get("self_grading_paired"):
        parts.append('<p class="pnl-sg">+ Test self-grading today, sharing the period with this lesson</p>')
    if day["type"] != "Instruction":
        parts.append(f'<p class="pnl-closed">{esc(day["display"])}</p>')
    if day["target"]:
        parts.append(f'<p class="pnl-target">{esc(day["target"])}</p>')
    if day["classwork"]:
        parts.append(f'<div class="field"><span class="lbl">In class</span>{esc(day["classwork"])}</div>')
    if day["type"] == "Instruction" and day["note"]:
        parts.append(f'<p class="pnl-note">{esc(day["note"])}</p>')
    items = []
    for hw in day["homework"] or []:
        due = " " + muted(f"· due {short_date(hw['due'])}") if hw["due"] else ""
        log = (f'<span class="log-tag">Goes in the Practice Log due {short_date(hw["log_due"])}</span>'
               if hw.get("log_due") else "")
        items.append(f"<li>{hw_text(hw)}{due}{PLANNED if planned else ''}{log}</li>")
    if items:
        parts.append('<div class="field pnl-hw"><span class="lbl">Homework given</span>'
                     f'<ul class="hw">{"".join(items)}</ul></div>')
    through = set_through(course)
    items = []
    for due in day["due"] or []:
        # Each due assignment links to its answer key: the folder of the
        # Practice Log it goes in, else the course's answer keys -- except a
        # quiz redo, which has no key and links to the quiz folder instead.
        # A Practice Log with a link is that folder; its own text links there.
        redo = is_quiz_redo(due["text"])
        if redo:
            key = quiz_rule(course)["link"]
        elif is_practice_log(due) and due.get("link"):
            key = None
        else:
            key = due.get("log_link") or course.get("answer_key_link")
        key_html = (f'<a class="keylink" href="{esc(key)}" target="_blank" rel="noopener">'
                    f'{"Weekly quizzes" if redo else "Answer key"}{ARROW}</a>' if key else "")
        given_planned = through is not None and due["assigned"] > through
        given = (f'<span class="given">(given {short_date(due["assigned"])}'
                 f'{"<span data-plan>, planned</span>" if given_planned else ""})</span>')
        note = due_note(due, course)
        note_html = f'<span class="due-note">{esc(note)}</span>' if note else ""
        # Laid out like the Homework list: the assignment, then a dark pill.
        items.append(f'<li class="due-item"><div class="due-body">{hw_text(due)} {given}{note_html}{key_html}'
                     f'{log_checklist(due)}</div><span class="pill pill-today">Due</span></li>')
    if items:
        parts.append(f'<div class="field pnl-due"><span class="lbl">Due this day</span><ul>{"".join(items)}</ul></div>')
    if day["extra_materials"]:
        parts.append('<div class="field pnl-extra"><span class="lbl">Also bring</span>'
                     f'{esc(", ".join(day["extra_materials"]))}</div>')
    if day["link"]:
        label = "Open weekly quizzes" if day["kind"] == "Quiz" else "Open the lesson"
        # A planned day's link is left out of sight, not out of the page:
        # the script shows it if the day is in the week students are in.
        hide = " data-plan hidden" if planned else ""
        parts.append(f'<a class="btn" href="{esc(day["link"])}" target="_blank" rel="noopener"{hide}>'
                     f'{label}{ARROW}</a>')
    return "".join(parts)


# --- Upcoming: the week-by-week list -----------------------------------------

def row_summary(day):
    """The lines under a row's title: what kind of day and what's due, then
    what's given. Due and given get a line each -- each line is cut short to
    fit, and on one shared line a long due item hid the homework given."""
    bits = []
    if day["kind"] == "Opener":
        bits.append("Topic opener")
    elif day["kind"] == "3-Act":
        bits.append("3-Act task")
    if day.get("quiz_paired"):
        bits.append("+ Quiz")
    if day.get("self_grading_paired"):
        bits.append("+ Test self-grading")
    lines = []
    for label, items in (("Due", day["due"]), ("HW", day["homework"])):
        if items:
            more = f" (+{len(items) - 1} more)" if len(items) > 1 else ""
            lines.append(f"{label}: {items[0]['text']}{more}")
    if bits:
        lines[:1] = [" · ".join(bits + lines[:1])]
    return lines


def render_row(day, course):
    d = date.fromisoformat(day["date"])
    kind = day_kind(day)
    when = (f'<span class="when"><span class="when-dow">{d.strftime("%a").upper()}</span>'
            f'<span class="when-num">{d.day}</span></span>')
    if kind == "quiz":
        title = '<span class="tag tag-quiz">Quiz</span>'
    elif kind in ("test", "project"):  # a project is summative too: test colors
        title = f'<span class="tag tag-test">{esc(day["lesson_text"])}</span>'
    else:
        title = esc(day_title(day))
    sub = "".join(f'<span class="row-sub">{esc(line)}</span>' for line in row_summary(day))
    # The same "Due" tag a Whole-year square gets, after the title.
    due = f" {DUE_TAG}" if day["due"] else ""
    main = f'<span class="row-main"><span class="row-title">{title}{due}</span>{sub}</span>'
    # A closed day with nothing due has nothing more to show: no button.
    if kind == "closed" and not day["due"]:
        return (f'<div class="day day-closed" data-date="{day["date"]}">'
                f'<div class="row row-static">{when}{main}</div></div>')
    pid = f"p-{day['date']}"
    planned = " day-planned" if is_planned(day) else ""
    return (f'<div class="day day-{kind}{planned}" data-date="{day["date"]}">'
            f'<button type="button" class="row" aria-expanded="false" aria-controls="{pid}">'
            f'{when}{main}{CHEVRON}</button>'
            f'<div class="panel" id="{pid}" hidden>{render_panel(day, course)}</div></div>')


def render_weeks(calendar, course):
    out, prev_month = [], None
    for monday, days in groupby(calendar, key=lambda d: week_monday(d["date"])):
        days = list(days)
        first, last = days[0]["date"], days[-1]["date"]
        month = int(first[5:7])
        # A month heading on the first week whose first school day is in it.
        heading = f'<h2 class="month-head">{MONTH_NAMES[month - 1]}</h2>' if month != prev_month else ""
        prev_month = month
        rows = "".join(render_row(d, course) for d in days)
        # "Planned" goes by the week's heading, not on each day: the whole
        # week, or "from" its first planned day if only part of it is.
        lessons = [d for d in days if d["type"] == "Instruction" and d["kind"] not in ASSESSMENT_KINDS]
        first_planned = next((d for d in lessons if is_planned(d)), None)
        planned = ""
        if first_planned:
            label = ("Planned" if first_planned is lessons[0]
                     else f"Planned from {first_planned['weekday']}")
            planned = (f' <span class="week-planned" data-plan data-from="{first_planned["date"]}">'
                       f'{label}</span>')
        out.append(
            f'<section class="week" data-monday="{monday.isoformat()}" data-start="{first}" '
            f'data-end="{last}">{heading}<h3 class="week-title"><span class="week-label"></span>'
            f'<span class="week-range">{week_range(first, last)}</span>{planned}</h3>'
            f'<div class="days">{rows}</div></section>')
    return "".join(out)


# --- Whole year: the month grids ---------------------------------------------

def cell_labels(day):
    """(short, code, title): `short` is all a phone-width cell shows; a wide
    cell shows `code` (bold) over `title` (up to two lines, then "...")."""
    kind = day_kind(day)
    if kind == "closed":
        return ("Off" if day["type"] == "No School" else day["note"] or day["type"]), "", day["display"]
    if kind == "quiz":
        return "Quiz", "Quiz", ""
    if kind == "test":
        return "Test", "", day["lesson_text"]
    if kind == "project":
        return "Project", "", day["lesson_text"]
    if day["kind"] == "Self-Grading":
        return "Self-grade", "", day["lesson_text"]
    code, rest = split_code(day["lesson_text"])
    if code:
        return code, code, rest
    if kind == "opener":
        return "Opener", "", day["lesson_text"]
    if kind == "threeact":
        return "3-Act", "", day["lesson_text"]
    return ("Review" if "review" in day["lesson_text"].lower() else "Lesson"), "", day["lesson_text"]


def render_cell(day):
    short, code, title = cell_labels(day)
    label = (f"{long_date(day['date'])}: {day_title(day)}" + (" (something due)" if day["due"] else "")
             + (" (planned)" if is_planned(day) else ""))
    top = (f'<span class="cell-top"><span class="cell-num">{int(day["date"][8:])}</span>'
           f'{DUE_TAG if day["due"] else ""}{PAIRED_TAG if day.get("quiz_paired") else ""}'
           f'{SG_TAG if day.get("self_grading_paired") else ""}</span>')
    code_html = f'<span class="cell-code">{esc(code)}</span>' if code else ""
    title_html = f'<span class="cell-title">{esc(title)}</span>' if title else ""
    planned = " cell-planned" if is_planned(day) else ""
    # A testing, Flex, or other in-school day isn't a day off: it doesn't
    # get a day off's dotted outline.
    if day["type"] not in ("Instruction", "No School"):
        planned += " cell-event"
    return (f'<button type="button" class="cell cell-{day_kind(day)}{planned}" data-date="{day["date"]}" '
            f'aria-label="{esc(label)}">{top}<span class="cell-short">{esc(short)}</span>'
            f'{code_html}{title_html}</button>')


def render_months(calendar):
    by_date = {d["date"]: d for d in calendar}
    heads = "".join(f'<span class="dow">{w}</span>' for w in ("Mon", "Tue", "Wed", "Thu", "Fri"))
    out = []
    for key, days in groupby(calendar, key=lambda d: d["date"][:7]):
        if not any(d["type"] == "Instruction" for d in days):
            continue  # e.g. July: no classes, nothing to show
        y, m = (int(x) for x in key.split("-"))
        first_weekday = date(y, m, 1).weekday()
        # Blanks so the 1st sits under its weekday (none if it's a weekend).
        cells = [EMPTY_CELL] * (first_weekday if first_weekday < 5 else 0)
        cur = date(y, m, 1)
        while cur.month == m:
            if cur.weekday() < 5:
                day = by_date.get(cur.isoformat())
                cells.append(render_cell(day) if day else EMPTY_CELL)
            cur += timedelta(days=1)
        name = MONTH_NAMES[m - 1]
        out.append(f'<section class="month card" data-month="{key}" data-name="{name}">'
                   f'<h2 class="month-name">{name} <span class="muted">{y}</span></h2>'
                   f'<div class="mgrid">{heads}{"".join(cells)}</div></section>')
    return "".join(out)


# --- Homework: each topic's assignments, by Practice Log ---------------------

def topic_name(test_title):
    """'Topic 5 Test (CEA)' -> 'Topic 5': the unit a test closes."""
    m = re.match(r"(.*?)\s+Test\b", test_title or "")
    return m.group(1) if m else (test_title or "")


def topic_spans(calendar):
    """(name, first date, last date) for each unit: from the day after one
    test through the next test -- the same units FOCUS_UNIT uses. School days
    after the last test are a unit of their own."""
    spans, start = [], None
    for d in calendar:
        start = start or d["date"]
        if d["kind"] == "Test":
            spans.append((topic_name(d["lesson_text"]), start, d["date"]))
            start = None
    if start:
        spans.append(("End of the year", start, calendar[-1]["date"]))
    return spans


def render_topics(calendar):
    """Every unit's homework, grouped under the Practice Log each assignment
    goes in -- all of it, planned or not: the script shows only what's been
    assigned by today, opens on this unit, and folds earlier ones away."""
    logs = {hw["due"]: hw for d in calendar
            for hw in d["homework"] or [] if is_practice_log(hw) and hw["due"]}
    out = []
    for name, start, end in topic_spans(calendar):
        groups = {}
        for d in calendar:
            if not start <= d["date"] <= end:
                continue
            for hw in d["homework"] or []:
                if hw["due"] and not is_practice_log(hw):
                    groups.setdefault(hw.get("log_due"), []).append({**hw, "assigned": d["date"]})
        cards = []
        for log_due in sorted(groups, key=lambda k: (k is None, k or "")):
            log = logs.get(log_due) if log_due else None
            if log:
                key = (f' <a class="keylink" href="{esc(log["link"])}" target="_blank" rel="noopener">'
                       f'Answer keys{ARROW}</a>' if log.get("link") else "")
                head = (f'<div class="log-head"><span class="log-name">Practice Log</span> '
                        f'<span class="muted">due {short_date(log_due)}</span>{key}</div>')
            else:
                head = '<div class="log-head"><span class="log-name">Not in a Practice Log</span></div>'
            rows = "".join(
                f'<li data-assigned="{hw["assigned"]}" data-due="{hw["due"]}">{hw_text(hw)}'
                f'<span class="hw-when">given {short_date(hw["assigned"])} · due {short_date(hw["due"])}</span></li>'
                for hw in sorted(groups[log_due], key=lambda h: (h["due"], h["assigned"])))
            cards.append(f'<div class="card loggroup">{head}'
                         f'<ul class="topic-hw">{rows}</ul></div>')
        out.append(f'<section class="topic" data-start="{start}" data-end="{end}">'
                   f'<h2 class="section-title">{esc(name)} homework</h2>{"".join(cards)}'
                   f'<p class="empty topic-empty" hidden>Nothing assigned yet.</p></section>')
    return "".join(out)


# --- Data the browser needs ---------------------------------------------------

def days_data(calendar):
    """Per school day, what the scripts need to find today, the next quiz or
    test, and the key dates. A day's details live in its panel instead."""
    return [{
        "date": d["date"], "type": d["type"], "kind": d["kind"],
        "title": day_title(d), "paired": bool(d.get("quiz_paired")),
        "extra": d["extra_materials"] or [],
    } for d in calendar]


def homework_data(calendar):
    """Every dated assignment, for the "Homework" list -- the page shows the
    ones already given and not yet due, soonest first."""
    return [{
        "text": hw["text"], "link": hw.get("link"), "assigned": d["date"], "due": hw["due"],
        "includes": [{"text": c["text"], "link": c.get("link"),
                      "due_label": short_date(c["due"]) if c.get("due") else None}
                     for c in hw.get("includes") or []],
    } for d in calendar for hw in d["homework"] or [] if hw["due"]]


def set_line(course):
    """The plain-words line near the top: how far the calendar is set."""
    through = set_through(course)
    if through is None:
        return ""
    return (f'<p class="setline" data-through="{through}"><b>Set through {short_date(through)}.</b> '
            f'Later days are planned and may change.</p>')


def build_page(course, calendar):
    """The whole page for one course. `calendar` is engine.render(course)[0]."""
    subtitle = " · ".join(x for x in (course.get("teacher") or TEACHER, course.get("school_year")) if x)
    data = (f"const DAYS = {to_json(days_data(calendar))};\n"
            f"const HOMEWORK = {to_json(homework_data(calendar))};\n"
            f"const DAILY_MATERIALS = {to_json(course.get('daily_materials') or [])};\n"
            f"const CHANGES = {to_json(course.get('changes') or [])};\n"
            f"const FOCUS_UNIT = {to_json(bool(course.get('focus_current_unit')))};\n")
    # Placeholders filled one at a time: the page itself is a plain string,
    # so its CSS and JS braces need no escaping.
    page = PAGE
    for key, value in (("%%THEME%%", theme_css(course)),
                       ("%%TITLE%%", esc(course["course"])), ("%%SUBTITLE%%", esc(subtitle)),
                       ("%%SETLINE%%", set_line(course)),
                       ("%%SETCAL%%", " setcal" if set_through(course) else ""),
                       ("%%DATA%%", data), ("%%MONTHS%%", render_months(calendar)),
                       ("%%WEEKS%%", render_weeks(calendar, course)),
                       ("%%TOPICS%%", render_topics(calendar))):
        page = page.replace(key, value)
    return page


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%%TITLE%% Calendar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>
  /* One look across beach-math.com (it matches Tech Quest): navy ink on a
     pale teal ground, white cards with a navy outline. Quizzes are blue and
     tests orange -- told apart by lightness too, not hue alone, since
     red/green is the pair colorblind students most often can't separate. */
  :root {
    color-scheme: light;
    --bg: #EEF5F3; --card: #FFFFFF; --ink: #1F2555; --muted: #4A5080;
    --line: #E2E4F0; --accent: #0E7466; --today: #FFF6C9;
    --quiz-bg: #DCE6FF; --quiz-ink: #1D3FB0; --test-bg: #FFE2CF; --test-ink: #9A3412;
    --closed-bg: #F3F4F8; --closed-ink: #565A80; --dash: #B9BCD6; --soft: #E8EAF6;
    --on-ink: #FFFFFF; --soon: #FFE58A; --dashed: #8C91B8;
    --display: 'Bricolage Grotesque', 'Atkinson Hyperlegible', Verdana, sans-serif;
  }%%THEME%%
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font: 16px/1.45 'Atkinson Hyperlegible', Verdana, sans-serif;
    /* No dark box flashing over whatever a phone taps -- the slide is the
       feedback. Keyboard focus still gets its outline. */
    -webkit-tap-highlight-color: transparent;
  }
  a { color: var(--ink); }
  button { font: inherit; color: inherit; }
  [hidden] { display: none !important; }
  :focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
  .muted { color: var(--muted); font-weight: 400; }
  .wrap { max-width: 1200px; margin: 0 auto; padding: 20px 16px 48px; }
  .card { background: var(--card); border: 2px solid var(--ink); border-radius: 16px; }
  h1, h2, h3 { font-family: var(--display); margin: 0; }

  /* Header and the view switch */
  /* The header stays pinned in both views. Its height is published as
     --head (set by the script) so the pinned side column and anything
     scrolled into view land below it, not under it. */
  .top { position: sticky; top: 0; z-index: 10; background: var(--bg); border-bottom: 2px solid var(--line); }
  .top-in { max-width: 1200px; margin: 0 auto; padding: 12px 16px; display: flex; flex-wrap: wrap; gap: 10px 14px; justify-content: space-between; align-items: center; }
  .top h1 { font-size: 28px; font-weight: 800; line-height: 1; }
  .week, .day, .earlier, .detail { scroll-margin-top: calc(var(--head, 80px) + 12px); }
  .top p { margin: 4px 0 0; font-size: 14px; color: var(--muted); }
  .switch { display: inline-grid; grid-template-columns: 1fr 1fr 1fr; border: 2px solid var(--ink); border-radius: 999px; overflow: hidden; background: var(--card); }
  .switch button { border: 0; background: none; min-height: 44px; padding: 0 18px; font-weight: 700; cursor: pointer; }
  .switch button[aria-pressed="true"] { background: var(--ink); color: var(--on-ink); }
  @media (max-width: 599px) { .switch { width: 100%; } .switch button { padding: 0 8px; } .top h1 { font-size: 24px; } }

  /* Upcoming: side column (today, homework, coming up) + the list */
  .cols { display: grid; grid-template-columns: minmax(0, 1fr); gap: 22px; align-items: start; }
  .list { min-width: 0; }
  @media (min-width: 900px) { .cols { grid-template-columns: 400px minmax(0, 1fr); gap: 32px; } }
  .side { display: flex; flex-direction: column; gap: 20px; min-width: 0; }
  /* Laptop: the side column stays in view while the list scrolls, and
     scrolls on its own if it's taller than the window. Its height is set by
     fitSide() below so it always ends at the window's bottom edge -- the CSS
     value is only the fallback. (Padding keeps the card's offset shadow from
     being clipped.) */
  @media (min-width: 900px) {
    .side { position: sticky; top: calc(var(--head, 80px) + 16px); max-height: calc(100vh - var(--head, 80px) - 32px); overflow-y: auto;
            overscroll-behavior: contain; padding: 0 6px 6px 0; scrollbar-width: thin; }
  }
  .section-title { font-size: 21px; font-weight: 800; margin-bottom: 10px; }

  .today { padding: 18px; box-shadow: 4px 4px 0 var(--ink); display: flex; flex-direction: column; gap: 12px; }
  .eyebrow { font-size: 13px; font-weight: 700; letter-spacing: .06em; color: var(--accent); text-transform: uppercase; }
  .today h2 { font-size: 27px; font-weight: 800; line-height: 1.12; }
  .today p { margin: 0; }
  .today .panel { padding: 0; }
  /* Today's homework, what's due, and extra materials are already under
     Homework and Bring, right next to this card. */
  .today .pnl-hw, .today .pnl-due, .today .pnl-extra { display: none; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .chips .lbl { margin-right: 2px; }
  .chip { border: 1.5px solid var(--ink); border-radius: 999px; padding: 2px 10px; font-size: 14px; }
  .chip-extra { background: var(--ink); color: var(--on-ink); }
  .lbl { display: block; font-size: 12px; font-weight: 700; letter-spacing: .05em; color: var(--muted); text-transform: uppercase; }

  .hwlist { padding: 4px 14px; }
  .hw-item { display: flex; gap: 10px; align-items: flex-start; padding: 10px 0; }
  .hw-item + .hw-item { border-top: 1.5px solid var(--line); }
  .hw-item svg { flex: none; margin-top: 2px; }
  .hw-body { flex: 1; min-width: 0; }
  .pill { flex: none; font-size: 13px; font-weight: 700; border-radius: 999px; padding: 3px 10px; background: var(--soft); white-space: nowrap; }
  .pill-today { background: var(--ink); color: var(--on-ink); }
  .pill-soon { background: var(--soon); }
  .empty { padding: 10px 0; color: var(--muted); }

  .coming { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .tile { border: 2px solid var(--ink); border-radius: 14px; padding: 12px 14px; display: flex; flex-direction: column; text-align: left; cursor: pointer; }
  .tile-quiz { background: var(--quiz-bg); }
  .tile-test { background: var(--test-bg); }
  .tile .k { font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
  .tile-quiz .k { color: var(--quiz-ink); }
  .tile-test .k { color: var(--test-ink); }
  .tile .v { font-family: var(--display); font-weight: 800; font-size: 19px; }
  .tile .w { font-size: 14px; color: var(--muted); }

  /* The list */
  .earlier { width: 100%; min-height: 48px; margin-bottom: 18px; background: var(--card); border: 2px dashed var(--dashed); border-radius: 14px; font-weight: 700; cursor: pointer; }
  .week { margin-bottom: 18px; }
  .backweek { position: fixed; left: 50%; bottom: 16px; transform: translateX(-50%); z-index: 5;
              min-height: 48px; padding: 0 20px; border-radius: 999px; border: 2px solid var(--ink);
              background: var(--ink); color: var(--on-ink); font-weight: 700; cursor: pointer;
              box-shadow: 0 4px 14px rgba(31, 37, 85, .3); }
  .month-head { font-size: 28px; font-weight: 800; border-bottom: 2px solid var(--ink); padding-bottom: 4px; margin: 10px 0 14px; }
  .week-title { font-size: 21px; font-weight: 800; margin-bottom: 8px; display: flex; gap: 10px; align-items: baseline; }
  .week-label:empty { display: none; }
  .week-label:not(:empty) + .week-range { font: 700 15px 'Atkinson Hyperlegible', Verdana, sans-serif; color: var(--muted); }
  .days { background: var(--card); border: 2px solid var(--ink); border-radius: 14px; overflow: hidden; }
  .day + .day { border-top: 1.5px solid var(--line); }
  .row { width: 100%; display: grid; grid-template-columns: 48px minmax(0, 1fr) 20px; gap: 10px; align-items: center; padding: 11px 14px; background: none; border: 0; text-align: left; cursor: pointer; }
  .row-static { grid-template-columns: 48px minmax(0, 1fr); cursor: default; padding-top: 8px; padding-bottom: 8px; }
  .when { text-align: center; }
  .when-dow { display: block; font-size: 12px; font-weight: 700; color: var(--muted); }
  .when-num { display: block; font-family: var(--display); font-weight: 800; font-size: 22px; line-height: 1; }
  .row-main { min-width: 0; }
  .row-title { display: block; font-weight: 700; }
  .row-sub { display: block; font-size: 14px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .chev { color: var(--muted); transition: transform .15s; }
  .row[aria-expanded="true"] .chev { transform: rotate(180deg); color: var(--ink); }
  .day-closed { background: var(--closed-bg); color: var(--closed-ink); }
  .day-closed .row-title { font-weight: 400; font-style: italic; }
  .day-closed .when-dow { color: var(--closed-ink); }
  .day-today { background: var(--today); }
  .day-today .when-dow::after { content: " · TODAY"; }
  .day-past { opacity: .62; }
  .tag { display: inline-block; font-weight: 700; border-radius: 8px; padding: 1px 10px; }
  .tag-quiz { background: var(--quiz-bg); color: var(--quiz-ink); }
  .tag-test { background: var(--test-bg); color: var(--test-ink); }
  .day:has(.row[aria-expanded="true"]) { box-shadow: inset 4px 0 0 var(--ink); }

  /* A day's details: under its row, and copied into the today card and the
     Whole-year detail card */
  .panel { padding: 2px 16px 16px 72px; display: flex; flex-direction: column; gap: 10px; font-size: 15px; }
  @media (max-width: 420px) { .panel { padding-left: 16px; } }
  .panel p { margin: 0; }
  .pnl-quiz { font-weight: 700; color: var(--quiz-ink); }
  .pnl-sg { font-weight: 700; }
  .pnl-note { font-style: italic; color: var(--muted); }
  .pnl-closed { font-style: italic; }
  .hw, .log { margin: 4px 0 0; padding-left: 18px; }
  .hw li + li { margin-top: 6px; }
  .log { list-style: "☐  "; font-size: 14px; }
  .log-tag { display: block; font-size: 13px; color: var(--muted); }
  .hwlink { font-weight: 700; }
  /* What's due: the Homework list's style -- assignment, then a dark pill. */
  .pnl-due ul:not(.log) { list-style: none; margin: 2px 0 0; padding: 0; }
  .due-item { display: flex; gap: 10px; align-items: flex-start; justify-content: space-between; padding: 8px 0; }
  .due-item + .due-item { border-top: 1.5px solid var(--line); }
  .due-body { min-width: 0; }
  .given { color: var(--muted); }
  .due-note { display: block; font-size: 14px; }
  .keylink { display: block; width: fit-content; font-size: 14px; }
  .btn { display: flex; align-items: center; justify-content: center; gap: 6px; min-height: 46px; border-radius: 12px; background: var(--ink); color: var(--on-ink); font-weight: 700; text-decoration: none; }

  /* Whole year */
  .yearnav { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
  .round { width: 44px; height: 44px; border-radius: 999px; border: 2px solid var(--ink); background: var(--card); display: flex; align-items: center; justify-content: center; cursor: pointer; }
  .round:disabled { opacity: .35; cursor: default; }
  .yearnav .range { font-family: var(--display); font-weight: 800; font-size: 22px; flex: 1; text-align: center; }
  .thismonth { min-height: 44px; padding: 0 16px; border-radius: 999px; border: 2px solid var(--ink); background: var(--card); font-weight: 700; cursor: pointer; }
  @media (min-width: 900px) { .yearnav .range { flex: none; min-width: 300px; } }
  @media (max-width: 599px) { .thismonth { order: 3; width: 100%; } }
  .months { display: grid; gap: 20px; align-items: start; overflow-x: clip; }
  @media (min-width: 900px) { .months { grid-template-columns: 1fr 1fr; } }
  .month { padding: 14px 12px; }
  .month-name { font-size: 22px; font-weight: 800; margin-bottom: 10px; }
  /* One month at a time on a phone: the name between the arrows is enough. */
  @media (max-width: 899px) { .month-name { display: none; } }
  .mgrid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 4px; }
  .dow { font-size: 13px; font-weight: 700; color: var(--muted); padding-left: 4px; }
  .cell { height: 64px; border-radius: 10px; padding: 5px 6px; border: 0; background: var(--closed-bg); display: flex; flex-direction: column; gap: 1px; text-align: left; font-size: 13px; line-height: 1.25; overflow: hidden; cursor: pointer; min-width: 0; }
  .cell-none { background: none; cursor: default; }
  /* Later units (FOCUS_UNIT): lesson names only, drawing no attention --
     no Due tags, no details. Past units keep their details, faded. */
  .cell.cell-outside, .cell.cell-past-unit { opacity: .45; }
  .cell-outside .due-tag { display: none; }
  .day-outside .row { cursor: default; }
  .day-outside .row-title { font-weight: 400; color: var(--muted); }
  .day-outside .row-sub, .day-outside .row-title .due-tag, .day-outside .chev { display: none; }
  .day-outside .tag { opacity: .6; }
  /* Homework: this topic's assignments under the Practice Log each goes in */
  .topics { max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
  .topics-intro { margin: 0; color: var(--muted); }
  .topic { display: flex; flex-direction: column; gap: 12px; }
  .topic + .topic, .earlier + .topic { margin-top: 14px; }
  .loggroup { padding: 12px 16px; }
  .log-head { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; }
  .log-name { font-weight: 700; }
  .log-head .keylink { margin-left: auto; font-weight: 700; }
  .topic-hw { list-style: none; margin: 6px 0 0; padding: 0; }
  .topic-hw li { padding: 9px 0; display: flex; flex-direction: column; gap: 2px; }
  .topic-hw li + li { border-top: 1.5px solid var(--line); }
  .hw-when { font-size: 14px; color: var(--muted); }
  .topic-hw li.hw-done .hwlink, .topic-hw li.hw-done > span:first-child { color: var(--muted); }
  #all-hw { align-self: flex-start; margin-top: 4px; }
  .unit-note { margin: 4px 0 18px; padding: 12px 14px; border: 2px dashed var(--dash); border-radius: 14px; color: var(--muted); font-weight: 700; }
  .cell-top { display: flex; align-items: center; gap: 4px; }
  .cell-num { font-weight: 700; font-size: 15px; }
  .due-tag, .quiz-tag { font-size: 11px; font-weight: 700; border-radius: 4px; padding: 0 4px; line-height: 16px; }
  .due-tag { background: var(--ink); color: var(--on-ink); }
  .row-title .due-tag { display: inline-block; vertical-align: 2px; margin-left: 4px; }
  .quiz-tag { background: var(--quiz-bg); color: var(--quiz-ink); }
  /* Too wide for a phone-width square; the day's details say it there. */
  .sg-tag { display: none; font-size: 11px; font-weight: 700; border-radius: 4px; padding: 0 4px; line-height: 16px; border: 1px solid var(--ink); white-space: nowrap; }
  .cell-short { margin-top: auto; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .cell-code, .cell-title { display: none; }
  .cell-quiz { background: var(--quiz-bg); }
  .cell-quiz .cell-short, .cell-quiz .cell-code { font-weight: 700; color: var(--quiz-ink); }
  .cell-test, .cell-project { background: var(--test-bg); }
  .cell-test .cell-short, .cell-test .cell-title,
  .cell-project .cell-short, .cell-project .cell-title { font-weight: 700; color: var(--test-ink); }
  .cell-closed { background: none; border: 1.5px dashed var(--dash); color: var(--closed-ink); }
  .cell-closed .cell-title { font-style: italic; }
  .cell-today { background: var(--today); box-shadow: inset 0 0 0 2px var(--ink); }
  .cell-selected, .cell-selected .cell-short, .cell-selected .cell-code, .cell-selected .cell-title { background: var(--ink); color: var(--on-ink); box-shadow: none; }
  .cell-selected .due-tag { background: var(--on-ink); color: var(--ink); }
  /* Wide screens: room for the code and a title of up to two lines, then "..." */
  @media (min-width: 900px) {
    .cell { height: 92px; padding: 6px 8px; }
    .cell-short { display: none; }
    .cell-code { display: block; font-weight: 700; }
    .sg-tag { display: inline-block; }
    .cell-title { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
  }
  .detail { margin-top: 20px; padding: 16px; display: flex; flex-direction: column; gap: 10px; box-shadow: 4px 4px 0 var(--ink); }
  .detail-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
  .detail h3 { font-size: 21px; font-weight: 800; line-height: 1.15; }
  .detail .panel { padding: 0; }
  .linkbtn { background: none; border: 0; font-weight: 700; text-decoration: underline; min-height: 44px; padding: 0 4px; cursor: pointer; }
  .keydates { list-style: none; margin: 0; padding: 0; }
  /* Changes families have already seen (engine.record_change): a tag on the
     day, the old version in its details, and the Recent changes list. */
  .chg-tag { display: inline-block; vertical-align: 2px; margin-left: 4px; font-size: 11px; font-weight: 700;
             border-radius: 4px; padding: 0 4px; line-height: 16px; background: var(--accent); color: var(--on-ink); }
  /* Content added to a day (a target, a link, new homework): lighter than a
     change, and shown for less time. */
  .upd-tag { display: inline-block; vertical-align: 2px; margin-left: 4px; font-size: 11px; font-weight: 700;
             border-radius: 4px; padding: 0 4px; line-height: 14px; border: 1.5px solid var(--accent); color: var(--accent); }
  .chg-dot { width: 8px; height: 8px; border-radius: 999px; background: var(--accent); flex: none; }
  .cell-selected .chg-dot { background: var(--on-ink); }
  .pnl-changed { border-left: 3px solid var(--accent); padding-left: 10px; font-size: 14px; }
  /* Set and planned days (a course's "set_through"): set days are final;
     planned ones are pencilled in -- readable, but visibly not final. */
  .setline { margin: 0 0 14px; padding: 10px 14px; border: 2px dashed var(--dashed); border-radius: 14px; background: var(--card); }
  .week-planned { margin-left: 8px; font-size: 13px; font-weight: 700; color: var(--muted); border: 1.5px dashed var(--muted); border-radius: 6px; padding: 0 6px; }
  .day-planned .row-title { font-weight: 400; }
  .day-planned .when-num { font-weight: 400; }
  /* Set lesson days are filled, with a firm outline; planned ones are
     white with a faint one, like a plan pencilled in. (.setcal: only in a
     course with a set-through date -- otherwise every day looks as before.) */
  .cell-planned:not(.cell-selected) { background: var(--card); box-shadow: inset 0 0 0 1.5px var(--line); }
  .setcal :is(.cell-lesson, .cell-opener, .cell-threeact):not(.cell-planned):not(.cell-selected):not(.cell-today) {
    box-shadow: inset 0 0 0 1.5px var(--dash); }
  /* Testing, Flex, other in-school days: a soft fill, not a day off's dotted outline. */
  .cell-closed.cell-event { border: 0; }
  .cell-closed.cell-event:not(.cell-selected) { background: var(--soft); }
  .pnl-planned { font-size: 14px; color: var(--muted); font-style: italic; }
  .plan-note { color: var(--muted); font-size: 14px; }
  .pnl-changed b { color: var(--accent); }
  .chglist { padding: 4px 14px; }
  .chg-item { padding: 10px 0; display: flex; flex-direction: column; gap: 4px; }
  .chg-item + .chg-item { border-top: 1.5px solid var(--line); }
  .chg-item p { margin: 0; }
  .chg-days { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 14px; }
  .chg-days a { font-weight: 700; }
  .keydates li { display: flex; gap: 12px; padding: 9px 0; align-items: baseline; }
  .keydates li + li { border-top: 1.5px solid var(--line); }
  .keydates .when-k { flex: none; width: 120px; font-size: 14px; font-weight: 700; }
  .keydates .closed { font-style: italic; color: var(--closed-ink); }
  @media (prefers-reduced-motion: reduce) { .chev { transition: none; } }
</style>
</head>
<body>
<header class="top"><div class="top-in">
    <div>
      <h1>%%TITLE%%</h1>
      <p>%%SUBTITLE%%</p>
    </div>
    <div class="switch" role="group" aria-label="View">
      <button type="button" data-view="upcoming" aria-pressed="true">Upcoming</button>
      <button type="button" data-view="homework" aria-pressed="false">Homework</button>
      <button type="button" data-view="year" aria-pressed="false">Whole year</button>
    </div>
</div></header>
<div class="wrap">%%SETLINE%%

  <main id="view-upcoming">
    <div class="cols">
      <div class="side">
        <section class="card today" id="today" aria-label="Today" hidden></section>
        <section id="homework" hidden>
          <h2 class="section-title">Homework</h2>
          <div class="card hwlist" id="hw-list"></div>
          <button type="button" class="linkbtn" id="all-hw">All homework this topic</button>
        </section>
        <section id="changes" hidden>
          <h2 class="section-title">Recent changes</h2>
          <div class="card chglist" id="chg-list"></div>
        </section>
        <section id="coming" hidden>
          <h2 class="section-title">Coming up</h2>
          <div class="coming" id="coming-tiles"></div>
        </section>
      </div>
      <div class="list">
        <button type="button" class="earlier" id="earlier" hidden></button>
        %%WEEKS%%
      </div>
    </div>
    <button type="button" class="backweek" id="back-week" hidden>Back to this week</button>
  </main>

  <main id="view-homework" hidden>
    <div class="topics" id="topics">
      <p class="topics-intro">Everything assigned so far this topic, grouped by the Practice Log it goes in.</p>
      %%TOPICS%%
      <button type="button" class="earlier" id="earlier-topics" hidden></button>
    </div>
  </main>

  <main id="view-year" hidden>
    <div class="yearnav">
      <button type="button" class="round" id="prev-month" aria-label="Earlier month"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"></path></svg></button>
      <div class="range" id="month-range" aria-live="polite"></div>
      <button type="button" class="round" id="next-month" aria-label="Later month"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"></path></svg></button>
      <button type="button" class="thismonth" id="this-month">This month</button>
    </div>
    <div class="months%%SETCAL%%" id="months">%%MONTHS%%</div>
    <section class="card detail" id="year-detail"></section>
    <div id="detail-spacer" aria-hidden="true"></div>
  </main>
</div>
<script>
%%DATA%%
(function () {
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                  'August', 'September', 'October', 'November', 'December'];
  const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const BY_DATE = Object.fromEntries(DAYS.map((d) => [d.date, d]));
  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const WIDE = window.matchMedia('(min-width: 900px)');
  // One motion for the Whole-year view: the months sliding and the page
  // gliding to a tapped day's card move the same way -- a quick start that
  // settles smoothly into place.
  const MOTION_MS = 600;
  const MOTION_CURVE = [0.2, 0.8, 0.2, 1];

  // Dates are 'YYYY-MM-DD' strings built from local time -- never
  // toISOString, which is UTC and turns into tomorrow in the evening.
  function iso(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function parse(s) { const p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function addDays(s, n) { const d = parse(s); d.setDate(d.getDate() + n); return iso(d); }
  function longDate(s) { const d = parse(s); return WEEKDAYS[d.getDay()] + ', ' + MONTHS[d.getMonth()] + ' ' + d.getDate(); }
  function shortDate(s) { const d = parse(s); return WEEKDAYS[d.getDay()].slice(0, 3) + ' ' + (d.getMonth() + 1) + '/' + d.getDate(); }
  function tileDate(s) { const d = parse(s); return WEEKDAYS[d.getDay()].slice(0, 3) + ', ' + MONTHS[d.getMonth()].slice(0, 3) + ' ' + d.getDate(); }
  function mondayOf(s) { const d = parse(s); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); }
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function bringIntoView(node) { node.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' }); }
  // A day's details, copied from the panel under its row in the list.
  function panelFor(date) {
    const div = el('div', 'panel');
    const src = document.getElementById('p-' + date);
    if (src) div.innerHTML = src.innerHTML;
    return div;
  }

  const TODAY = iso(new Date());
  const THIS_MONDAY = mondayOf(TODAY);
  const NEXT_MONDAY = addDays(THIS_MONDAY, 7);
  // Set and planned days: the week students are in always counts as set
  // (engine.set_floor) -- this week on a weekday, the coming week on a
  // weekend -- even if the course's set-through date wasn't advanced.
  // Its days lose their planned marks, and the top line says so.
  let setThrough = null;  // the effective date, or null: no set-through date
  (function setFloor() {
    const line = document.querySelector('.setline');
    if (!line) return;
    const dow = parse(TODAY).getDay();
    const floor = addDays(TODAY, dow === 6 ? 6 : dow === 0 ? 5 : 5 - dow);
    setThrough = floor > line.dataset.through ? floor : line.dataset.through;
    if (floor <= line.dataset.through) return;
    line.querySelector('b').textContent = 'Set through ' + shortDate(floor) + '.';
    document.querySelectorAll('.day-planned, .cell-planned').forEach((node) => {
      if (node.dataset.date > floor) return;
      node.classList.remove('day-planned', 'cell-planned');
      node.querySelectorAll('[data-plan]').forEach((p) => {
        if (p.tagName === 'A') p.hidden = false; else p.remove();
      });
      if (node.getAttribute('aria-label')) node.setAttribute('aria-label', node.getAttribute('aria-label').replace(' (planned)', ''));
    });
    document.querySelectorAll('.week-planned').forEach((p) => { if (p.dataset.from <= floor) p.remove(); });
  })();
  const isClassDay = (d) => d.type === 'Instruction';
  const nextClass = (after) => DAYS.find((d) => d.date > after && isClassDay(d)) || null;
  // A course can put the current unit in focus (its "focus_current_unit"):
  // the unit runs from the day after the last test through the next one,
  // and its days get everything. Past units keep everything too, faded.
  // Class days in later units show their lesson name, quiz, or test and
  // nothing else -- no homework, due dates, or links. The unit moves on by
  // itself the day after its test.
  const unitTest = FOCUS_UNIT ? DAYS.find((d) => d.date >= TODAY && d.kind === 'Test') : null;
  const lastTest = FOCUS_UNIT ? DAYS.filter((d) => d.date < TODAY && d.kind === 'Test').pop() : null;
  const isClass = (date) => isClassDay(BY_DATE[date] || {});
  const outside = (date) => Boolean(unitTest) && date > unitTest.date && isClass(date);
  const pastUnit = (date) => Boolean(lastTest) && date <= lastTest.date && isClass(date);
  const laterText = unitTest
    ? 'After the ' + unitTest.title + ': lesson names only. Homework, due dates, and links are posted when each unit starts.' : '';

  // ---- The view switch (kept in the address as #year or #homework, so a refresh stays put) ----
  function showView(name) {
    document.getElementById('view-upcoming').hidden = name !== 'upcoming';
    document.getElementById('view-homework').hidden = name !== 'homework';
    document.getElementById('view-year').hidden = name !== 'year';
    document.querySelectorAll('.switch button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.view === name)));
    history.replaceState(null, '', name === 'upcoming' ? location.pathname + location.search : '#' + name);
    updateBackWeek();
    if (name === 'year') fitSpacer();
  }
  document.querySelectorAll('.switch button').forEach((b) => b.addEventListener('click', () => showView(b.dataset.view)));

  // ---- Upcoming: the list ----
  const weeks = Array.from(document.querySelectorAll('.week'));
  const earlier = document.getElementById('earlier');
  weeks.forEach((w) => {
    const m = w.dataset.monday;
    w.querySelector('.week-label').textContent = m === THIS_MONDAY ? 'This week' : m === NEXT_MONDAY ? 'Next week' : '';
  });
  // Weeks already over fold away -- unless the year is over, then show it
  // all. "Show earlier weeks" brings them back and becomes "Hide earlier
  // weeks"; "Back to this week" folds them away again and returns to this
  // week. That button shows once you've scrolled past this week (ahead in
  // the year), or opened earlier weeks and moved away from it -- not just
  // because this week starts below the fold, as it does on a phone, under
  // the today card.
  if (FOCUS_UNIT) {
    document.querySelectorAll('.day').forEach((row) => {
      if (!outside(row.dataset.date)) return;
      row.classList.add('day-outside');
      const btn = row.querySelector('.row[aria-controls]');
      if (btn) btn.disabled = true;  // nothing to open: no details outside the unit
    });
    const testWeek = unitTest && weeks.find((w) => w.dataset.start <= unitTest.date && unitTest.date <= w.dataset.end);
    if (testWeek) testWeek.after(el('p', 'unit-note', laterText));
  }
  const past = weeks.filter((w) => w.dataset.end < TODAY);
  const thisWeek = weeks.find((w) => w.dataset.end >= TODAY) || weeks[weeks.length - 1];
  const foldable = past.length && past.length < weeks.length;
  const showLabel = foldable ? 'Show earlier weeks (' + shortDate(past[0].dataset.start) + ' – ' + shortDate(past[past.length - 1].dataset.end) + ')' : '';
  const backWeek = document.getElementById('back-week');
  let earlierShown = false;
  // Measured on each scroll: is this week on screen (below the pinned
  // header), or already scrolled up past it?
  function updateBackWeek() {
    if (!thisWeek) return;
    const box = thisWeek.getBoundingClientRect();
    const headBottom = document.querySelector('.top').offsetHeight;
    const inView = box.bottom > headBottom && box.top < window.innerHeight;
    const above = box.bottom <= headBottom;
    const away = !inView && (above || earlierShown);
    backWeek.hidden = !away || document.getElementById('view-upcoming').hidden;
  }
  function setEarlier(show) {
    if (!foldable) return;
    earlierShown = show;
    past.forEach((w) => { w.hidden = !show; });
    earlier.textContent = show ? 'Hide earlier weeks' : showLabel;
    updateBackWeek();
  }
  if (foldable) {
    setEarlier(false);
    earlier.hidden = false;
    earlier.addEventListener('click', () => {
      setEarlier(!earlierShown);
      if (!earlierShown) bringIntoView(earlier);
    });
  }
  backWeek.addEventListener('click', () => {
    setEarlier(false);
    bringIntoView(thisWeek);
  });
  window.addEventListener('scroll', updateBackWeek, { passive: true });
  window.addEventListener('resize', updateBackWeek);
  document.querySelectorAll('.day').forEach((row) => {
    if (row.dataset.date === TODAY) row.classList.add('day-today');
    else if (row.dataset.date < TODAY) row.classList.add('day-past');
  });
  // A day's details slide open under its row, and slide shut again, in the
  // Whole-year view's motion. Tapping again partway through turns it
  // around from wherever it got to.
  function togglePanel(btn) {
    const panel = document.getElementById(btn.getAttribute('aria-controls'));
    const open = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!open));
    if (REDUCED || !panel.animate) { panel.hidden = open; return; }
    const pick = (cs) => ({ height: cs.height, paddingTop: cs.paddingTop,
                            paddingBottom: cs.paddingBottom, opacity: cs.opacity });
    const shut = { height: '0px', paddingTop: '0px', paddingBottom: '0px', opacity: 0 };
    const now = panel.hidden ? shut : pick(getComputedStyle(panel));
    panel.getAnimations().forEach((a) => a.cancel());
    panel.hidden = false;
    const full = pick(getComputedStyle(panel));
    panel.style.overflow = 'hidden';
    const anim = panel.animate([now, open ? shut : full],
                               { duration: MOTION_MS, easing: 'cubic-bezier(' + MOTION_CURVE.join(', ') + ')' });
    anim.onfinish = () => { panel.style.overflow = ''; if (open) panel.hidden = true; };
  }
  document.querySelectorAll('.row[aria-controls]').forEach((btn) => {
    btn.addEventListener('click', () => togglePanel(btn));
  });
  // Open a day's row in the list and bring it into view.
  function openDay(date) {
    showView('upcoming');
    const row = document.querySelector('.day[data-date="' + date + '"]');
    if (!row) return;
    if (row.closest('.week').hidden) setEarlier(true);
    const btn = row.querySelector('.row[aria-controls]');
    if (btn && btn.getAttribute('aria-expanded') !== 'true') btn.click();
    bringIntoView(row);
  }

  // ---- Changes families have already seen ----
  // Each entry in CHANGES is one confirmed edit (engine.record_change). It's
  // listed under Recent changes for CHANGE_DAYS days after it was made. Each
  // day it changed is tagged for less: the class day it was made and the
  // next TAG_CLASS_DAYS - 1 class days (a weekend doesn't use any up), or
  // until that day is past. Once students have seen the new plan, a tag is
  // only noise.
  const CHANGE_DAYS = 7;
  const TAG_CLASS_DAYS = 3;
  const CHANGE_LINKS = 5;
  // A tag says what happened to the day, not just that something did.
  const CHANGE_LABELS = { moved: 'Moved', 'due moved': 'Due date moved', dropped: 'HW dropped', changed: 'Changed' };
  const UPDATED_DAYS = 2;
  const within = (c, n) => c.logged <= TODAY && c.logged > addDays(TODAY, -n);
  // Class days since an entry was logged, up to and including today.
  const classDaysSince = (logged) => DAYS.filter((d) => d.date > logged && d.date <= TODAY && isClassDay(d)).length;
  const tagFresh = (c) => classDaysSince(c.logged) < TAG_CLASS_DAYS;
  const byNewest = (a, b) => (a.logged < b.logged ? 1 : a.logged > b.logged ? -1 : 0);
  // An entry that only added content isn't a change (`changed` false).
  // Change tags go on set days only (PLANNING.md, "Set and planned
  // days"): a planned day changes quietly -- even one logged before set
  // days existed -- unless a quiz or test moved there or away within the
  // current unit (through its test). And the newest change to a day's
  // lesson, or to one assignment, replaces an older tag about the same
  // thing: the older one may no longer be true.
  const ASSESSMENT = /\\b(Quiz|Test)\\b/;
  const unitEnd = (DAYS.find((d) => d.date >= TODAY && d.kind === 'Test') || {}).date || '';
  const tagShown = (d) => setThrough === null || d.date <= setThrough
    || ((d.kind === 'moved' || d.kind === 'changed') && d.date <= unitEnd
        && ASSESSMENT.test((d.was || '') + ' ' + (d.now || '')));
  const taggedLater = new Set();
  const recentChanges = CHANGES.map((c, i) => Object.assign({}, c, { order: i }))
    .filter((c) => c.changed !== false && within(c, CHANGE_DAYS))
    .sort((a, b) => byNewest(a, b) || b.order - a.order)
    .map((c) => {
      const about = (d) => d.date + (d.what === 'homework' ? ' hw ' + (d.was || '').replace(/ \\(due [^)]*\\)$/, '') : '');
      const days = tagFresh(c) ? c.days.filter((d) => tagShown(d) && !taggedLater.has(about(d))) : [];
      c.days.forEach((d) => taggedLater.add(about(d)));
      return Object.assign(c, { days: days });
    });
  const recentDetails = [].concat(...recentChanges.map((c) => c.days));
  function changeLine(c, d) {
    const p = el('p', 'pnl-changed');
    p.appendChild(el('b', null, 'Changed ' + shortDate(c.logged) + '. '));
    const end = (t) => (/[.!?]$/.test(t) ? t : t + '.');
    let text;
    if (d.kind === 'moved') {
      // The arrival first: on a test's new day, that's what students came for.
      const parts = [];
      if (d.moved_from) parts.push(end(d.now + ' moved here from ' + longDate(d.moved_from)));
      if (d.moved_to) parts.push(end(d.was + ' moved to ' + longDate(d.moved_to)));
      text = parts.join(' ');
    }
    else if (d.kind === 'dropped') text = end(d.was) + ' No longer assigned.';
    else {
      text = end((d.what === 'class work' ? 'Class work was: ' : 'Was: ') + d.was);
      if (d.what === 'homework' && d.now) text += ' ' + end('Now: ' + d.now);
    }
    if (c.reason) text += ' ' + end('Why: ' + c.reason);
    p.appendChild(document.createTextNode(' ' + text));
    return p;
  }
  function tagChanges() {
    recentChanges.slice().reverse().forEach((c) => c.days.forEach((d) => {
      if (d.date < TODAY) return;
      const row = document.querySelector('.day[data-date="' + d.date + '"]');
      if (row) {
        const title = row.querySelector('.row-title');
        const label = CHANGE_LABELS[d.kind] || 'Changed';
        if (!Array.from(title.querySelectorAll('.chg-tag')).some((t) => t.textContent === label)) {
          title.appendChild(el('span', 'chg-tag', label));
        }
        let panel = document.getElementById('p-' + d.date);
        if (row.querySelector('.row-static')) {
          // A day with no details to open (a closed day with nothing due):
          // the change reads under its row, and is kept in a hidden panel
          // so the Whole-year card can say what changed too.
          row.querySelector('.row-main').appendChild(el('span', 'row-sub', changeLine(c, d).textContent));
          if (!panel) {
            panel = el('div', 'panel');
            panel.id = 'p-' + d.date;
            panel.hidden = true;
            row.appendChild(panel);
          }
        }
        if (panel) panel.insertBefore(changeLine(c, d), panel.firstChild);
      }
      const cell = document.querySelector('.cell[data-date="' + d.date + '"]');
      if (cell && !cell.querySelector('.chg-dot')) {
        cell.querySelector('.cell-top').appendChild(el('span', 'chg-dot'));
        cell.setAttribute('aria-label', cell.getAttribute('aria-label') + ' (changed)');
      }
    }));
  }
  // Days with content added (engine.record_change's `updated`) get a
  // lighter "Updated" tag for UPDATED_DAYS days -- unless they're also
  // tagged as changed, which says more.
  function tagUpdates() {
    CHANGES.filter((c) => within(c, UPDATED_DAYS)).forEach((c) => (c.updated || []).forEach((date) => {
      if (date < TODAY || (setThrough !== null && date > setThrough)) return;
      const title = document.querySelector('.day[data-date="' + date + '"] .row-title');
      if (title && !title.querySelector('.chg-tag, .upd-tag')) title.appendChild(el('span', 'upd-tag', 'Updated'));
    }));
  }
  function renderChanges() {
    if (!recentChanges.length) return;
    const list = document.getElementById('chg-list');
    recentChanges.forEach((c) => {
      const item = el('div', 'chg-item');
      item.appendChild(el('span', 'eyebrow', shortDate(c.logged)));
      item.appendChild(el('p', null, c.summary));
      if (c.reason) item.appendChild(el('p', 'muted', 'Why: ' + c.reason));
      const dates = [...new Set(c.days.map((d) => d.date))].filter((d) => d >= TODAY);
      if (dates.length) {
        const links = el('div', 'chg-days');
        // The first few days as links; a re-flow can touch a dozen test
        // days across the year, and the line shouldn't become a wall.
        dates.slice(0, CHANGE_LINKS).forEach((date) => {
          const a = el('a', null, shortDate(date));
          a.href = '#';
          a.addEventListener('click', (e) => { e.preventDefault(); openDay(date); });
          links.appendChild(a);
        });
        if (dates.length > CHANGE_LINKS) links.appendChild(el('span', 'muted', '+' + (dates.length - CHANGE_LINKS) + ' later days, tagged in the calendar'));
        item.appendChild(links);
      }
      list.appendChild(item);
    });
    document.getElementById('changes').hidden = false;
  }

  // ---- Upcoming: today, homework, coming up ----
  function renderToday() {
    const card = document.getElementById('today');
    const day = BY_DATE[TODAY];
    card.appendChild(el('div', 'eyebrow', 'Today · ' + longDate(TODAY)));
    if (day && isClassDay(day)) {
      card.appendChild(el('h2', null, day.kind === 'Quiz' ? 'Quiz' : day.title));
      if (DAILY_MATERIALS.length || day.extra.length) {
        const chips = el('div', 'chips');
        chips.appendChild(el('span', 'lbl', 'Bring'));
        DAILY_MATERIALS.forEach((m) => chips.appendChild(el('span', 'chip', m)));
        day.extra.forEach((m) => chips.appendChild(el('span', 'chip chip-extra', '+ ' + m)));
        card.appendChild(chips);
      }
      card.appendChild(panelFor(TODAY));
    } else {
      card.appendChild(el('h2', null, 'No class today'));
      if (day) card.appendChild(el('p', 'pnl-note', day.title));
      const next = nextClass(TODAY);
      if (next) {
        const p = el('p');
        p.appendChild(document.createTextNode('Next class: '));
        const a = el('a', null, longDate(next.date) + ' — ' + (next.kind === 'Quiz' ? 'Quiz' : next.title));
        a.href = '#';
        a.addEventListener('click', (e) => { e.preventDefault(); openDay(next.date); });
        p.appendChild(a);
        card.appendChild(p);
      }
    }
    card.hidden = false;
  }

  // How soon, in class days: on a Friday, Monday's homework is "due next class".
  function urgency(due) {
    if (due === TODAY) return ['Due today', 'pill pill-today'];
    const next = nextClass(TODAY);
    if (next && due === next.date) {
      return [due === addDays(TODAY, 1) ? 'Due tomorrow' : 'Due next class · ' + shortDate(due), 'pill pill-soon'];
    }
    return ['Due ' + shortDate(due), 'pill'];
  }
  function linkOrText(item) {
    if (!item.link) return el('span', null, item.text);
    const a = el('a', 'hwlink', item.text + ' ↗');
    a.href = item.link; a.target = '_blank'; a.rel = 'noopener';
    return a;
  }
  const BOX = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4"></rect></svg>';
  // Every assignment already given and not yet due, soonest first. Homework
  // planned for a later day stays out of the list until that day.
  function renderHomework() {
    const list = document.getElementById('hw-list');
    const open = HOMEWORK.filter((h) => h.assigned <= TODAY && h.due >= TODAY)
      .sort((a, b) => (a.due < b.due ? -1 : a.due > b.due ? 1 : 0));
    if (!open.length) list.appendChild(el('div', 'empty', 'Nothing due right now.'));
    open.forEach((h) => {
      const item = el('div', 'hw-item');
      item.insertAdjacentHTML('beforeend', BOX);
      const body = el('div', 'hw-body');
      body.appendChild(linkOrText(h));
      if (h.includes.length) {
        const ul = el('ul', 'log');
        h.includes.forEach((c) => {
          const li = el('li');
          li.appendChild(linkOrText(c));
          if (c.due_label) li.appendChild(document.createTextNode(' (due ' + c.due_label + ')'));
          ul.appendChild(li);
        });
        body.appendChild(ul);
      }
      item.appendChild(body);
      const u = urgency(h.due);
      item.appendChild(el('span', u[1], u[0]));
      list.appendChild(item);
    });
    document.getElementById('homework').hidden = false;
  }

  // ---- Homework: this topic's assignments, earlier topics folded away ----
  // Every unit is on the page with all its homework; only what's been
  // assigned by today shows. The unit today falls in opens; units already
  // over sit behind "Show earlier topics", newest first; later ones stay out.
  function renderTopics() {
    const box = document.getElementById('topics');
    const topics = Array.from(box.querySelectorAll('.topic'));
    topics.forEach((t) => {
      t.querySelectorAll('li[data-assigned]').forEach((li) => {
        li.hidden = li.dataset.assigned > TODAY;
        li.classList.toggle('hw-done', li.dataset.due < TODAY);
      });
      t.querySelectorAll('.loggroup').forEach((g) => {
        g.hidden = !g.querySelector('li:not([hidden])');
      });
      t.querySelector('.topic-empty').hidden = Boolean(t.querySelector('.loggroup:not([hidden])'));
    });
    let cur = topics.findIndex((t) => t.dataset.start <= TODAY && TODAY <= t.dataset.end);
    if (cur < 0) cur = topics.length && TODAY < topics[0].dataset.start ? 0 : topics.length - 1;
    topics.forEach((t, i) => { if (i > cur) t.remove(); });
    const earlierTopics = topics.slice(0, Math.max(cur, 0))
      .filter((t) => t.querySelector('.loggroup:not([hidden])')).reverse();
    const btn = document.getElementById('earlier-topics');
    topics.slice(0, Math.max(cur, 0)).forEach((t) => { if (!earlierTopics.includes(t)) t.remove(); });
    earlierTopics.forEach((t) => { t.hidden = true; box.appendChild(t); });
    if (earlierTopics.length) {
      const show = 'Show earlier topics';
      btn.textContent = show;
      btn.hidden = false;
      box.insertBefore(btn, earlierTopics[0]);
      btn.addEventListener('click', () => {
        const open = earlierTopics[0].hidden;
        earlierTopics.forEach((t) => { t.hidden = !open; });
        btn.textContent = open ? 'Hide earlier topics' : show;
      });
    }
  }
  document.getElementById('all-hw').addEventListener('click', () => { showView('homework'); window.scrollTo(0, 0); });

  function fromNow(date) {
    const days = Math.round((parse(date) - parse(TODAY)) / 86400000);
    if (days === 1) return 'tomorrow';
    if (days < 14) return 'in ' + days + ' days';
    return 'in ' + Math.round(days / 7) + ' weeks';
  }
  function renderComing() {
    const tiles = document.getElementById('coming-tiles');
    const quiz = DAYS.find((d) => d.date > TODAY && !outside(d.date) && (d.kind === 'Quiz' || d.paired));
    const test = DAYS.find((d) => d.date > TODAY && d.kind === 'Test');
    [[quiz, 'quiz', 'Quiz'], [test, 'test', test && test.title]].forEach(([d, kind, label]) => {
      if (!d) return;
      const t = el('button', 'tile tile-' + kind);
      t.type = 'button';
      // A recently moved or changed quiz/test says so on its tile too --
      // this is where students look for the date.
      const change = recentDetails.find((x) => x.date === d.date);
      const k = el('span', 'k', label);
      if (change) k.appendChild(el('span', 'chg-tag', CHANGE_LABELS[change.kind] || 'Changed'));
      t.appendChild(k);
      t.appendChild(el('span', 'v', tileDate(d.date)));
      t.appendChild(el('span', 'w', fromNow(d.date) + (change && change.moved_from ? ' · moved from ' + shortDate(change.moved_from) : '')));
      t.addEventListener('click', () => openDay(d.date));
      tiles.appendChild(t);
    });
    if (tiles.children.length) document.getElementById('coming').hidden = false;
  }

  // ---- Whole year ----
  const months = Array.from(document.querySelectorAll('.month'));
  const detail = document.getElementById('year-detail');
  let first = 0;
  const perView = () => (WIDE.matches ? 2 : 1);
  function homeIndex() {
    const i = months.findIndex((m) => m.dataset.month >= TODAY.slice(0, 7));
    return i === -1 ? months.length - 1 : i;
  }
  // `dir` is +1 (later) or -1 (earlier) when an arrow moved the view: the
  // months slide into place -- one that stays on screen glides from its old
  // spot to its new one, and the newly shown month slides in from that side.
  function showMonths(i, dir) {
    const was = new Map();
    if (dir && !REDUCED) months.filter((m) => !m.hidden).forEach((m) => was.set(m, m.getBoundingClientRect().left));
    first = Math.max(0, Math.min(i, months.length - perView()));
    const shown = months.slice(first, first + perView());
    months.forEach((m) => { m.hidden = !shown.includes(m); });
    if (dir && !REDUCED && shown.some((m) => !was.has(m))) {
      shown.forEach((m) => {
        const box = m.getBoundingClientRect();
        const stayed = was.has(m);
        const dx = stayed ? was.get(m) - box.left : dir * (perView() === 1 ? 80 : box.width + 20);
        m.animate([{ transform: 'translateX(' + dx + 'px)', opacity: stayed ? 1 : 0 },
                   { transform: 'none', opacity: 1 }],
                  { duration: MOTION_MS, easing: 'cubic-bezier(' + MOTION_CURVE.join(', ') + ')' });
      });
    }
    document.getElementById('month-range').textContent = shown.map((m) => m.dataset.name).join(' – ');
    document.getElementById('prev-month').disabled = first === 0;
    document.getElementById('next-month').disabled = first >= months.length - perView();
    showKeyDates();
  }
  // The months on screen: quizzes (one line), tests, and days off --
  // consecutive days off with the same label read as one range.
  // The card under the months. A tapped day's card is centered in the
  // space below the pinned header, so the bottom of the calendar stays in
  // view above it; a card too tall for that lines up just under the header
  // instead. The spacer after it keeps the page tall enough to do that --
  // and never lets the page shrink while you tap from day to day, since a
  // shrinking page makes the browser jump the scroll before it can glide.
  const spacer = document.getElementById('detail-spacer');
  const headHeightNow = () => document.querySelector('.top').offsetHeight;
  function desiredTop(cardHeight) {
    const head = headHeightNow();
    const room = window.innerHeight - head;
    return cardHeight + 24 <= room ? head + (room - cardHeight) / 2 : head + 12;
  }
  function fitSpacer(keepAtLeast) {
    if (document.getElementById('view-year').hidden) return;
    const h = detail.offsetHeight;
    const needed = window.innerHeight - desiredTop(h) - h - 48;  // 48: the page's bottom padding
    spacer.style.height = Math.max(0, needed, keepAtLeast || 0) + 'px';
  }
  // A slower glide than the browser's own smooth scroll (whose speed can't
  // be set): eased in and out. Scrolling or swiping yourself stops it.
  // The glide follows MOTION_CURVE, solved for x by Newton's method (a
  // scroll can't use a CSS easing directly).
  function cubicBezier(x1, y1, x2, y2) {
    const f = (a, b, t) => 3 * a * t * (1 - t) * (1 - t) + 3 * b * t * t * (1 - t) + t * t * t;
    const df = (a, b, t) => 3 * a * (1 - t) * (1 - 3 * t) + 3 * b * t * (2 - 3 * t) + 3 * t * t;
    return (x) => {
      let t = x;
      for (let i = 0; i < 8; i++) {
        const d = df(x1, x2, t);
        if (Math.abs(d) < 1e-6) break;
        t -= (f(x1, x2, t) - x) / d;
      }
      return f(y1, y2, Math.min(1, Math.max(0, t)));
    };
  }
  const EASE = cubicBezier(...MOTION_CURVE);
  let glide = null;
  function stopGlide() { if (glide) { cancelAnimationFrame(glide); glide = null; } }
  ['wheel', 'touchstart'].forEach((t) => window.addEventListener(t, stopGlide, { passive: true }));
  function glideTo(target, duration) {
    stopGlide();
    if (REDUCED) { window.scrollTo(0, target); return; }
    const start = window.scrollY;
    const distance = target - start;
    const began = performance.now();
    const ease = EASE;
    function step(now) {
      const t = Math.min(1, (now - began) / duration);
      window.scrollTo(0, start + distance * ease(t));
      glide = t < 1 ? requestAnimationFrame(step) : null;
    }
    glide = requestAnimationFrame(step);
  }
  function alignDetail() {
    const target = window.scrollY + detail.getBoundingClientRect().top - desiredTop(detail.offsetHeight);
    if (Math.abs(target - window.scrollY) > 2) glideTo(Math.max(0, target), MOTION_MS);
  }
  window.addEventListener('resize', () => fitSpacer());
  // New contents fade in. Before the swap the spacer grows by the old
  // card's height, so whatever the new card's size the page can't get
  // shorter; then it's set to what the new card needs, but never less
  // than keeps the page its old height.
  function swapDetail(...children) {
    const oldCard = detail.offsetHeight;
    const oldSpacer = spacer.offsetHeight;
    spacer.style.height = (oldSpacer + oldCard) + 'px';
    detail.replaceChildren(...children);
    fitSpacer(oldSpacer + oldCard - detail.offsetHeight);
    if (REDUCED || !detail.animate) return;
    children.forEach((c) => c.animate([{ opacity: 0, transform: 'translateY(4px)' }, { opacity: 1, transform: 'none' }],
                                      { duration: 500, easing: 'ease-out' }));
  }
  function showKeyDates() {
    document.querySelectorAll('.cell-selected').forEach((c) => c.classList.remove('cell-selected'));
    const keys = months.filter((m) => !m.hidden).map((m) => m.dataset.month);
    const inView = DAYS.filter((d) => keys.includes(d.date.slice(0, 7)));
    const rows = [];
    const quizzes = inView.filter((d) => d.kind === 'Quiz' || d.paired);
    if (quizzes.length) {
      rows.push({ date: quizzes[0].date, when: 'Quizzes', cls: 'tag tag-quiz',
                  text: quizzes.map((q) => shortDate(q.date).split(' ')[1] + (q.paired ? ' (with lesson)' : '')).join(', ') });
    }
    inView.filter((d) => d.kind === 'Test').forEach((d) => rows.push({ date: d.date, when: shortDate(d.date), text: d.title, cls: 'tag tag-test' }));
    for (let i = 0; i < inView.length; i++) {
      const d = inView[i];
      if (isClassDay(d)) continue;
      let j = i;
      while (j + 1 < inView.length && !isClassDay(inView[j + 1]) && inView[j + 1].title === d.title) j++;
      rows.push({ date: d.date, when: shortDate(d.date) + (j > i ? ' – ' + shortDate(inView[j].date) : ''), text: d.title, cls: 'closed' });
      i = j;
    }
    rows.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    const ul = el('ul', 'keydates');
    rows.forEach((r) => {
      const li = el('li');
      li.appendChild(el('span', 'when-k', r.when));
      const span = el('span');
      span.appendChild(el('span', r.cls, r.text));
      li.appendChild(span);
      ul.appendChild(li);
    });
    if (!rows.length) ul.appendChild(el('li', 'muted', 'Regular class days only.'));
    swapDetail(el('h3', null, 'Key dates'), ul);
  }
  function showDay(cell) {
    const date = cell.dataset.date;
    const d = BY_DATE[date];
    document.querySelectorAll('.cell-selected').forEach((c) => c.classList.remove('cell-selected'));
    cell.classList.add('cell-selected');
    const head = el('div', 'detail-head');
    head.appendChild(el('span', 'eyebrow', longDate(date) + (date === TODAY ? ' · Today' : '')));
    const back = el('button', 'linkbtn', 'Key dates');
    back.type = 'button';
    back.addEventListener('click', () => { showKeyDates(); cell.focus(); });
    head.appendChild(back);
    if (outside(date)) {
      const note = 'Homework, due dates, and links are posted when this unit starts.';
      swapDetail(head, el('h3', null, d.kind === 'Quiz' ? 'Quiz' : d.title), el('p', 'muted', note));
      alignDetail();
      return;
    }
    const panel = panelFor(date);
    if (!panel.childNodes.length) panel.appendChild(el('p', 'muted', 'Nothing more planned for this day yet.'));
    swapDetail(head, el('h3', null, d.kind === 'Quiz' ? 'Quiz' : d.title), panel);
    alignDetail();
  }
  document.querySelectorAll('.cell[data-date]').forEach((c) => {
    if (c.dataset.date === TODAY) c.classList.add('cell-today');
    if (pastUnit(c.dataset.date)) c.classList.add('cell-past-unit');
    if (outside(c.dataset.date)) {
      c.classList.add('cell-outside');
      c.setAttribute('aria-label', longDate(c.dataset.date) + ': ' + BY_DATE[c.dataset.date].title);
    }
    c.addEventListener('click', () => showDay(c));
  });
  document.getElementById('prev-month').addEventListener('click', () => showMonths(first - 1, -1));
  document.getElementById('next-month').addEventListener('click', () => showMonths(first + 1, 1));
  document.getElementById('this-month').addEventListener('click', () => showMonths(homeIndex()));
  WIDE.addEventListener('change', () => showMonths(first));

  // Size the pinned side column to end exactly at the bottom of the window.
  // A fixed height can't: with the page at the top the column starts below
  // the header, so its last part would hang off-screen until you scrolled.
  // (Scroll events already come at most once a frame, so no throttling.)
  const side = document.querySelector('.side');
  const header = document.querySelector('.top');
  function headHeight() { return header.offsetHeight; }
  function setHead() { document.documentElement.style.setProperty('--head', headHeight() + 'px'); }
  window.addEventListener('resize', setHead);
  setHead();
  function fitSide() {
    if (!WIDE.matches) { side.style.maxHeight = ''; return; }
    const top = Math.max(headHeight() + 16, side.getBoundingClientRect().top);
    side.style.maxHeight = (window.innerHeight - top - 16) + 'px';
  }
  window.addEventListener('scroll', fitSide, { passive: true });
  window.addEventListener('resize', fitSide);

  tagChanges();  // first: the today card and Whole-year details copy the tagged panels
  tagUpdates();
  renderToday();
  renderHomework();
  renderChanges();
  renderComing();
  fitSide();
  showMonths(homeIndex());
  renderTopics();
  if (location.hash === '#year') showView('year');
  if (location.hash === '#homework') showView('homework');
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "courses/math6.json")
    course = json.loads(path.read_text())
    for label, warnings in run_all_checks(course):
        for w in warnings:
            print(f"warning ({label}): {w}", file=sys.stderr)
    print(build_page(course, render(course)[0]))
