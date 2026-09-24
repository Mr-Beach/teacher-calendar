"""Render a course's data file into a single static HTML calendar page.

Usage:
    python3 render.py courses/math6.json > /tmp/preview.html

Cloudflare Workers Builds renders every course with this on each push to
main, via scripts/build_site.py, and deploys the result to
beach-math.com/<course> (CLAUDE.md, "Hosting"); the output is never
committed. Run it by hand only to preview, and never into docs/index.html
-- that file is the redirect stub for old github.io bookmarks.
"""
import calendar as calendar_module
import json
import sys
from datetime import date, timedelta
from itertools import groupby
from pathlib import Path

from engine import render, run_all_checks

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
WEEKDAY_HEADERS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

# CSS class per school-day type, for non-instructional cells.
TYPE_CLASS = {
    "No School": "day--noschool",
    "Flex": "day--flex",
    "Testing": "day--testing",
    "Other": "day--other",
}
# CSS class per lesson kind, for instructional cells.
# Quiz (formative) and Test (summative) get distinct colors -- PLANNING.md:
# "Quizzes are formatives... District topic tests" are the graded summative.
KIND_CLASS = {
    "Quiz": "day--quiz",
    "Test": "day--test",
    "Opener": "day--opener",
    "3-Act": "day--threeact",
    "Lesson": "day--lesson",
}
# Icon per material name, for the hero card's "bring today" row. Presentation
# only -- course["daily_materials"] and a lesson's extra_materials are plain
# strings; unrecognized text just falls back to a generic bullet.
MATERIAL_ICONS = {
    "School work folder": "\U0001f4c1",  # folder
    "Laptop": "\U0001f4bb",  # laptop
    "Pencil": "✏️",  # pencil
    "Calculator": "\U0001f9ee",  # abacus, used loosely for "math tool"
    "Glue stick": "\U0001f9f4",  # closest available shape match
    "Ruler": "\U0001f4cf",  # straight ruler
}
DEFAULT_MATERIAL_ICON = "•"


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


def month_key(day):
    y, m, _ = day["date"].split("-")
    return (int(y), int(m))


def fill_weekends(calendar):
    """Insert a display-only row for each Saturday/Sunday between school
    days. school_days (the engine's source of truth) stays weekdays-only --
    weekends have no bearing on lesson placement -- but the rendered page
    needs a cell for every literal calendar date so "today" can land on the
    actual date, weekend included, instead of snapping to the next school
    day (which mislabels a future day as "TODAY")."""
    filled = []
    prev_date = None
    for day in calendar:
        d = date.fromisoformat(day["date"])
        if prev_date is not None:
            cursor = prev_date + timedelta(days=1)
            while cursor < d:
                filled.append({
                    "date": cursor.isoformat(), "weekday": cursor.strftime("%a"),
                    "type": "Weekend", "display": "", "lesson_text": None,
                    "kind": None, "homework": None, "due": None, "note": None,
                    "target": None, "classwork": None, "link": None,
                    "extra_materials": None,
                })
                cursor += timedelta(days=1)
        filled.append(day)
        prev_date = d
    return filled


def short_date(iso):
    """'2026-09-29' -> 'Tue 9/29', the way due dates read to students."""
    d = date.fromisoformat(iso)
    return f"{d.strftime('%a')} {d.month}/{d.day}"


def render_day_body(day, compact=False):
    """Tile/agenda body, shared by the month grid and the portrait agenda.

    Homework shows on the day it's assigned; its due date gets its own badge
    so "due today" never reads like new homework. A lesson day's note is
    left off both views -- it's shown on the today card and in the day's
    popup -- so it never crowds out the lesson or a due date. (A closed
    day's note stays: it *is* that day's label, e.g. "No School (Holiday)".)

    `compact` is the fixed-height grid tile: homework text and the resource
    link collapse into a strip, returned separately so render_day_cell can
    pin it to the tile's bottom edge, outside the clipped body -- nothing
    can push it out of view. The agenda rows grow with their content, so
    they keep the full homework text. Returns (body, strip)."""
    body = ""
    if day["type"] == "Instruction":
        body += f'<div class="day__lesson">{esc(day["lesson_text"])}</div>'
    elif day["display"]:
        body += f'<div class="day__note">{esc(day["display"])}</div>'
    dues = day.get("due") or []
    if compact and len(dues) > 1:
        body += f'<div class="day__due">Due: {len(dues)} assignments</div>'
    else:
        for due in dues:
            body += f'<div class="day__due">Due: {esc(due["text"])}</div>'
    if day["type"] != "Instruction":
        return body, ""
    homework = day["homework"] or []
    if compact:
        strip = []
        if homework:
            strip.append("\U0001f4dd " + (f"{len(homework)} HW" if len(homework) > 1 else "HW"))
        if day["link"]:
            strip.append("\U0001f517")
        return body, (f'<div class="day__strip">{" · ".join(strip)}</div>' if strip else "")
    for hw in homework:
        body += f'<div class="day__homework">HW: {esc(hw["text"])}</div>'
    if day["link"]:
        body += '<div class="day__link">\U0001f517 Resource</div>'
    return body, ""


def render_day_cell(day):
    d = date.fromisoformat(day["date"])
    day_num = d.day
    if day["type"] == "Weekend":
        # Not clickable, not a "type" from the data model -- just a
        # placeholder cell so the actual date has somewhere to sit.
        return (
            f'<div class="day day--weekend" data-date="{day["date"]}">'
            f'<div class="day__num">{day_num}</div></div>'
        )
    css = ["day"]
    if day["type"] == "Instruction":
        css.append(KIND_CLASS.get(day["kind"], "day--lesson"))
    else:
        css.append(TYPE_CLASS.get(day["type"], "day--other"))
    body, strip = render_day_body(day, compact=True)
    # Fixed-size cell with clamped text, not size-to-content: guarantees the
    # cell can never overhang regardless of title length or device font
    # metrics. Tap/click opens the full, untruncated detail.
    return (
        f'<div class="{" ".join(css)}" role="button" tabindex="0" '
        f'data-date="{day["date"]}" aria-label="View details" '
        f'onclick="showDetail(\'{day["date"]}\')" '
        f"onkeydown=\"if(event.key==='Enter'||event.key===' '){{event.preventDefault();showDetail('{day['date']}')}}\">"
        f'<div class="day__num">{day_num}</div><div class="day__body">{body}</div>{strip}</div>'
    )


def render_agenda_row(day):
    d = date.fromisoformat(day["date"])
    if day["type"] == "Weekend":
        return (
            f'<div class="agenda-row day--weekend" data-date="{day["date"]}">'
            f'<div class="agenda-date">{day["weekday"]}<br>{d.month}/{d.day}</div>'
            f'<div class="agenda-body"></div></div>'
        )
    css = ["agenda-row"]
    if day["type"] == "Instruction":
        css.append(KIND_CLASS.get(day["kind"], "day--lesson"))
    else:
        css.append(TYPE_CLASS.get(day["type"], "day--other"))
    body, _ = render_day_body(day)
    # Tappable like a grid tile: opens the same detail popup.
    return (
        f'<div class="{" ".join(css)}" role="button" tabindex="0" '
        f'data-date="{day["date"]}" aria-label="View details" '
        f'onclick="showDetail(\'{day["date"]}\')" '
        f"onkeydown=\"if(event.key==='Enter'||event.key===' '){{event.preventDefault();showDetail('{day['date']}')}}\">"
        f'<div class="agenda-date">{day["weekday"]}<br>{d.month}/{d.day}</div>'
        f'<div class="agenda-body">{body}</div>'
        f"</div>"
    )


def render_agenda(days):
    return '<div class="agenda">' + "".join(render_agenda_row(d) for d in days) + "</div>"


def render_month(year, month, days):
    # The school-day data only has weekdays (weekends aren't school days at
    # all), so cells must be placed by each date's actual weekday, not by
    # sequentially packing entries into a 7-wide grid.
    by_day_of_month = {date.fromisoformat(d["date"]).day: d for d in days}
    first_weekday = (date(year, month, 1).weekday() + 1) % 7  # Sunday = 0
    _, days_in_month = calendar_module.monthrange(year, month)

    cells = ['<div class="day day--pad"></div>' for _ in range(first_weekday)]
    for day_num in range(1, days_in_month + 1):
        entry = by_day_of_month.get(day_num)
        if entry is not None:
            cells.append(render_day_cell(entry))
        else:
            cells.append(f'<div class="day day--pad"><div class="day__num">{day_num}</div></div>')
    while len(cells) % 7:
        cells.append('<div class="day day--pad"></div>')
    anchor = f"{year}-{month:02d}"
    header = '<div class="grid__header">' + "".join(f"<div>{w}</div>" for w in WEEKDAY_HEADERS) + "</div>"
    return (
        f'<section class="month" id="{anchor}">'
        f'<h2>{MONTH_NAMES[month - 1]} {year}</h2>'
        f"{render_agenda(days)}"
        f'<div class="grid-wrap">{header}<div class="grid">{"".join(cells)}</div></div>'
        f"</section>"
    )


def build_details_map(calendar):
    details = {}
    for day in calendar:
        if day["type"] == "Weekend":
            continue  # not clickable -- nothing to show
        d = date.fromisoformat(day["date"])
        weekday_full = d.strftime("%A")
        details[day["date"]] = {
            "date": f"{weekday_full}, {MONTH_NAMES[d.month - 1]} {d.day}, {d.year}",
            "weekday": day["weekday"],
            "type": day["type"],
            "kind": day["kind"],
            "title": day["lesson_text"] if day["type"] == "Instruction" else day["display"],
            "target": day["target"],
            "classwork": day["classwork"],
            "homework": [
                {"text": hw["text"], "due": hw["due"], "link": hw.get("link"),
                 "due_label": short_date(hw["due"]) if hw["due"] else None}
                for hw in (day["homework"] or [])
            ],
            "due": [
                {"text": due["text"], "link": due.get("link"),
                 "assigned_label": short_date(due["assigned"])}
                for due in (day["due"] or [])
            ],
            "note": day["note"] if day["type"] == "Instruction" else None,
            "link": day["link"],
            "extra_materials": day["extra_materials"],
        }
    return details


def build_page(course, calendar):
    months = []
    nav_links = []
    for (year, month), days in groupby(calendar, key=month_key):
        days = list(days)
        months.append(render_month(year, month, days))
        nav_links.append(
            f'<a href="#{year}-{month:02d}">{MONTH_NAMES[month - 1][:3]} {year}</a>'
        )

    title = esc(course["course"])
    year_label = esc(course.get("school_year") or "")
    # </script> can't appear literally inside a script body.
    details_json = json.dumps(build_details_map(calendar)).replace("</", "<\\/")
    daily_materials_json = json.dumps([
        {"label": m, "icon": MATERIAL_ICONS.get(m, DEFAULT_MATERIAL_ICON)}
        for m in course.get("daily_materials") or []
    ]).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} Calendar</title>
<style>
  :root {{
    color-scheme: light;
    --bg: #f7f7f5;
    --card: #ffffff;
    --text: #1f2328;
    --muted: #6b7280;
    --border: #e3e3e0;
    --lesson: #eef2ff;
    --lesson-border: #6366f1;
    --opener: #ecfeff;
    --opener-border: #06b6d4;
    --quiz: #ecfdf5;
    --quiz-border: #059669;
    --test: #fef2f2;
    --test-border: #ef4444;
    --threeact: #fefce8;
    --threeact-border: #ca8a04;
    --noschool: #f3f4f6;
    --testing: #fff7ed;
    --flex: #f5f3ff;
    /* Homework due: a filled chip, deliberately unlike any lesson-kind color,
       so "due" never reads as another kind of day. */
    --due: #334155;
    --due-text: #ffffff;
    --due-today: #dc2626;
    --due-soon: #f59e0b;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0;
    padding: 16px;
  }}
  header {{ max-width: 900px; margin: 0 auto 16px; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  .subtitle {{ color: var(--muted); font-size: 0.9rem; margin: 0 0 12px; }}
  .hero {{
    max-width: 900px; margin: 0 auto 20px; padding: 20px 22px; border-radius: 14px;
    border: 1px solid var(--border); background: var(--card); border-left: 5px solid var(--muted);
  }}
  .hero--lesson {{ background: var(--lesson); border-left-color: var(--lesson-border); }}
  .hero--opener {{ background: var(--opener); border-left-color: var(--opener-border); }}
  .hero--quiz {{ background: var(--quiz); border-left-color: var(--quiz-border); }}
  .hero--test {{ background: var(--test); border-left-color: var(--test-border); }}
  .hero--threeact {{ background: var(--threeact); border-left-color: var(--threeact-border); }}
  .hero--noschool {{ background: var(--noschool); }}
  .hero--testing {{ background: var(--testing); }}
  .hero--flex {{ background: var(--flex); }}
  .hero--empty {{ background: var(--card); border-left-color: var(--border); }}
  .hero__eyebrow {{
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700;
    color: var(--muted); margin-bottom: 4px;
  }}
  .hero__date {{ font-size: 0.95rem; color: var(--muted); margin-bottom: 6px; }}
  .hero__materials {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
  .hero__material-chip {{
    display: inline-flex; align-items: center; gap: 5px; background: var(--card);
    border: 1px solid var(--border); border-radius: 999px; padding: 3px 11px;
    font-size: 0.8rem; color: var(--text);
  }}
  .hero__material-chip--extra {{
    background: var(--lesson); border-color: var(--lesson-border); font-weight: 600;
  }}
  .hero__title {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 4px; line-height: 1.25; }}
  .hero__row {{ font-size: 0.95rem; margin-top: 10px; }}
  .hero__row--note {{ font-style: italic; color: var(--muted); }}
  .hero__hw {{ margin-top: 4px; }}
  .hero__due {{
    margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--border);
    display: flex; flex-direction: column; gap: 8px;
  }}
  .hero__due-heading {{
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700;
    color: var(--muted);
  }}
  .hero__due-item {{
    display: flex; align-items: baseline; gap: 8px; font-size: 0.95rem;
    color: var(--text); text-decoration: none; cursor: pointer;
  }}
  .hero__due-item:hover .hero__due-text {{ text-decoration: underline; }}
  .due-pill {{
    flex: none; font-size: 0.75rem; font-weight: 700; padding: 2px 9px; border-radius: 999px;
    background: var(--card); border: 1px solid var(--border); color: var(--text); white-space: nowrap;
  }}
  .due-pill--today {{ background: var(--due-today); border-color: var(--due-today); color: #fff; }}
  .due-pill--soon {{ background: var(--due-soon); border-color: var(--due-soon); color: #1f2328; }}
  .hero__due-item--today .hero__due-text {{ font-weight: 700; }}
  .hero__link {{
    display: inline-block; margin-top: 16px; padding: 10px 18px; border-radius: 8px;
    background: var(--lesson-border); color: #fff; text-decoration: none; font-weight: 600; font-size: 0.95rem;
  }}
  .hero__footer {{
    margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--border);
    font-size: 0.9rem; color: var(--muted); display: flex; flex-direction: column; gap: 6px;
  }}
  .hero__footer a {{ color: var(--text); font-weight: 600; text-decoration: none; cursor: pointer; }}
  .hero__footer a:hover {{ text-decoration: underline; }}
  @media (max-width: 480px) {{
    .hero {{ padding: 16px; }}
    .hero__title {{ font-size: 1.2rem; }}
  }}
  nav.months {{
    display: flex; flex-wrap: wrap; gap: 6px; margin: 0 auto 20px; max-width: 900px;
  }}
  nav.months a {{
    font-size: 0.8rem; padding: 4px 8px; border: 1px solid var(--border);
    border-radius: 6px; text-decoration: none; color: var(--text); background: var(--card);
  }}
  .legend {{
    display: flex; flex-wrap: wrap; gap: 12px; max-width: 900px; margin: 0 auto 20px;
    font-size: 0.78rem; color: var(--muted);
  }}
  .legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
  .legend i {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
  .month {{ max-width: 900px; margin: 0 auto 28px; }}
  .month h2 {{ font-size: 1.1rem; margin: 0 0 8px; }}

  /* Portrait (most phones): a stacked agenda list reads better than a
     cramped 7-column grid. Landscape (rotated phones, tablets, desktop):
     there's enough width for the grid, which reads more like a calendar. */
  .grid-wrap {{ display: none; }}
  .agenda {{ display: flex; flex-direction: column; gap: 6px; }}
  @media (orientation: landscape) {{
    .grid-wrap {{ display: block; }}
    .agenda {{ display: none; }}
  }}

  .agenda-row {{
    display: grid; grid-template-columns: 56px 1fr; gap: 10px;
    border: 1px solid var(--border); border-radius: 6px; background: var(--card);
    padding: 8px 10px; font-size: 0.85rem; cursor: pointer; -webkit-tap-highlight-color: transparent;
  }}
  .agenda-row:focus-visible {{ outline: 2px solid var(--lesson-border); outline-offset: 1px; }}
  .agenda-row.day--weekend {{ cursor: default; }}
  .agenda-date {{
    font-size: 0.72rem; color: var(--muted); line-height: 1.3; text-align: center;
    padding-top: 2px;
  }}
  .grid__header {{
    display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px;
    font-size: 0.72rem; color: var(--muted); text-align: center; margin-bottom: 4px;
  }}
  .grid {{
    display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px;
  }}
  .day {{
    height: 96px; min-width: 0; border: 1px solid var(--border); border-radius: 6px;
    background: var(--card); padding: 4px 5px; font-size: 0.72rem;
    overflow-wrap: break-word; overflow: hidden; cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }}
  .day:hover {{ box-shadow: inset 0 0 0 1px var(--muted); }}
  .day:focus-visible {{ outline: 2px solid var(--lesson-border); outline-offset: 1px; }}
  .day--pad {{ background: transparent; border-color: transparent; cursor: default; }}
  .day--pad:hover {{ box-shadow: none; }}
  .day--weekend {{ background: transparent; color: var(--muted); cursor: default; }}
  .day--weekend:hover {{ box-shadow: none; }}
  .agenda-row.day--weekend {{ background: transparent; border-style: dashed; padding: 4px 10px; }}
  .day__num {{ font-size: 0.68rem; color: var(--muted); margin-bottom: 2px; }}
  /* Column layout so the strip sits on the bottom edge no matter how long
     the lesson title is: the body takes the leftover height and clips, the
     strip never does. */
  .day {{ display: flex; flex-direction: column; }}
  .day__body {{ overflow: hidden; flex: 1; min-height: 0; }}
  .day__strip {{
    flex: none; padding-top: 2px; color: var(--muted); font-weight: 600;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  /* Line-clamp, not auto-height: the cell's size never depends on content
     length or how a given device/browser measures the font. */
  .day__lesson {{
    font-weight: 600; line-height: 1.25; display: -webkit-box;
    -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden;
  }}
  .day__homework, .day__note, .day__link {{
    color: var(--muted); margin-top: 2px; display: -webkit-box;
    -webkit-box-orient: vertical; -webkit-line-clamp: 1; overflow: hidden;
  }}
  .day__note {{ font-style: italic; }}
  .day__due {{
    background: var(--due); color: var(--due-text); font-weight: 600; border-radius: 4px;
    padding: 0 4px; margin-top: 2px; display: -webkit-box;
    -webkit-box-orient: vertical; -webkit-line-clamp: 1; overflow: hidden;
  }}
  .agenda-row .day__due {{ width: fit-content; max-width: 100%; padding: 1px 6px; }}
  .day__link {{ font-weight: 600; }}
  .day--lesson {{ background: var(--lesson); border-left: 3px solid var(--lesson-border); }}
  .day--opener {{ background: var(--opener); border-left: 3px solid var(--opener-border); }}
  .day--quiz {{ background: var(--quiz); border-left: 3px solid var(--quiz-border); }}
  .day--test {{ background: var(--test); border-left: 3px solid var(--test-border); }}
  .day--threeact {{ background: var(--threeact); border-left: 3px solid var(--threeact-border); }}
  .day--noschool {{ background: var(--noschool); color: var(--muted); }}
  .day--testing {{ background: var(--testing); }}
  .day--flex {{ background: var(--flex); }}
  /* Today marker: a ring plus a small badge, layered on top of whichever
     kind/type color the cell already has -- must read at a glance without
     fighting that color. */
  .day--today {{ box-shadow: 0 0 0 2px var(--text); }}
  .day--today .day__num::after {{
    content: "TODAY"; margin-left: 6px; font-weight: 700; letter-spacing: 0.03em;
    color: var(--text);
  }}
  .agenda-row.day--today {{ box-shadow: 0 0 0 2px var(--text); }}
  @media (max-width: 480px) {{
    .day {{ font-size: 0.62rem; height: 82px; }}
    .grid, .grid__header {{ gap: 2px; }}
  }}
  /* Phones in landscape: wide enough to trigger the grid, but short enough
     that desktop-scale text overflows narrow columns. Target by height
     (phones in landscape are short), not width, so real desktop windows
     are unaffected. Cell height is fixed here too, just smaller, with the
     lesson clamped to 2 lines instead of 3 to match. */
  @media (orientation: landscape) and (max-height: 500px) {{
    .day {{ font-size: 0.58rem; height: 68px; padding: 3px 4px; }}
    .day__num {{ font-size: 0.54rem; }}
    .day__lesson {{ -webkit-line-clamp: 2; }}
    .grid, .grid__header {{ gap: 2px; }}
  }}

  /* will-change: give the popup its own GPU layer up front, so Safari doesn't
     build one mid-animation (a visible hitch on the heavier grid view). */
  dialog#detail {{
    will-change: transform, opacity;
    border: none; border-radius: 10px; padding: 0; max-width: 380px; width: calc(100% - 32px);
    color: var(--text); box-shadow: 0 10px 40px rgba(0,0,0,0.2);
  }}
  /* The dimming is a plain page element, not the dialog's ::backdrop:
     iOS Safari won't animate ::backdrop, so it snapped dark instantly. A
     normal element fades smoothly everywhere, both ways. It's faded by a
     script animation (fadeDim), not a CSS transition: on the heavier grid
     view, iOS started the transition late and it jumped most of the way
     dark at once. The transparent ::backdrop still catches taps outside
     the popup. */
  dialog#detail::backdrop {{ background: transparent; }}
  #detail-dim {{
    position: fixed; inset: 0; background: rgba(0,0,0,0.4); opacity: 0;
    pointer-events: none; will-change: opacity;
  }}
  .detail {{ padding: 16px 18px; }}
  .detail__date {{ font-size: 0.8rem; color: var(--muted); margin-bottom: 6px; }}
  .detail__title {{ font-size: 1.05rem; font-weight: 600; margin-bottom: 8px; }}
  .detail__target, .detail__classwork, .detail__homework, .detail__note {{
    font-size: 0.9rem; margin-top: 6px;
  }}
  .detail__homework div + div {{ margin-top: 4px; }}
  .detail__due {{ margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }}
  .detail__due[hidden] {{ display: none; }}
  .detail__due div {{
    background: var(--due); color: var(--due-text); border-radius: 6px;
    padding: 6px 10px; font-size: 0.9rem;
  }}
  .detail__due small {{ opacity: 0.8; }}
  .detail__note {{ font-style: italic; color: var(--muted); }}
  .detail__link {{
    display: inline-block; margin-top: 10px; padding: 8px 14px; border-radius: 6px;
    background: var(--lesson-border); color: #fff; text-decoration: none;
    font-size: 0.9rem; font-weight: 600;
  }}
  .detail__link[hidden] {{ display: none; }}
  /* A homework item with its own link (e.g. a study guide kept in a review
     folder) -- the assignment text itself becomes the link. */
  .hw-link {{ color: inherit; font-weight: 600; text-decoration: underline; }}
  .detail__close {{
    position: absolute; top: 10px; right: 12px; border: none; background: none;
    font-size: 1.3rem; line-height: 1; cursor: pointer; color: var(--muted); padding: 4px;
  }}
  .detail {{ position: relative; }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <p class="subtitle">{year_label}</p>
</header>
<section class="hero" id="today-hero" hidden></section>
<div class="legend">
  <span><i style="background:var(--lesson-border)"></i>Lesson</span>
  <span><i style="background:var(--opener-border)"></i>Opener</span>
  <span><i style="background:var(--quiz-border)"></i>Quiz (formative)</span>
  <span><i style="background:var(--test-border)"></i>Test (summative)</span>
  <span><i style="background:var(--threeact-border)"></i>3-Act</span>
  <span><i style="background:var(--due)"></i>Homework due</span>
  <span>&#128221; Homework assigned</span>
  <span>&#128279; Has a linked resource</span>
</div>
<nav class="months">{"".join(nav_links)}</nav>
{"".join(months)}
<div id="detail-dim"></div>
<dialog id="detail">
  <div class="detail">
    <button class="detail__close" onclick="closeDetail()" aria-label="Close">&times;</button>
    <div class="detail__date" id="detail-date"></div>
    <div class="detail__title" id="detail-title"></div>
    <div class="detail__due" id="detail-due" hidden></div>
    <div class="detail__target" id="detail-target" hidden></div>
    <div class="detail__classwork" id="detail-classwork" hidden></div>
    <div class="detail__homework" id="detail-homework" hidden></div>
    <div class="detail__note" id="detail-note" hidden></div>
    <a class="detail__link" id="detail-link" target="_blank" rel="noopener" hidden>Open resource &#8599;</a>
  </div>
</dialog>
<script>
  const DETAILS = {details_json};
  const DAILY_MATERIALS = {daily_materials_json};
  // An assignment's text, as a link to where it lives when it has one.
  function hwText(item) {{
    if (!item.link) return document.createTextNode(item.text);
    const a = document.createElement('a');
    a.className = 'hw-link'; a.href = item.link; a.target = '_blank'; a.rel = 'noopener';
    a.textContent = item.text + ' ↗';
    return a;
  }}
  function showDetail(dateStr) {{
    const d = DETAILS[dateStr];
    if (!d) return;
    document.getElementById('detail-date').textContent = d.date;
    document.getElementById('detail-title').textContent = d.title || '';
    const target = document.getElementById('detail-target');
    target.textContent = d.target ? 'Target: ' + d.target : '';
    target.hidden = !d.target;
    const classwork = document.getElementById('detail-classwork');
    classwork.textContent = d.classwork ? 'Classwork: ' + d.classwork : '';
    classwork.hidden = !d.classwork;
    const due = document.getElementById('detail-due');
    due.replaceChildren();
    for (const item of d.due) {{
      const line = document.createElement('div');
      line.appendChild(document.createTextNode('Due: '));
      line.appendChild(hwText(item));
      line.appendChild(document.createTextNode(' '));
      const when = document.createElement('small');
      when.textContent = '(assigned ' + item.assigned_label + ')';
      line.appendChild(when);
      due.appendChild(line);
    }}
    due.hidden = !d.due.length;
    const hw = document.getElementById('detail-homework');
    hw.replaceChildren();
    for (const item of d.homework) {{
      const line = document.createElement('div');
      line.appendChild(document.createTextNode('HW: '));
      line.appendChild(hwText(item));
      if (item.due_label) line.appendChild(document.createTextNode(' (due ' + item.due_label + ')'));
      hw.appendChild(line);
    }}
    hw.hidden = !d.homework.length;
    const note = document.getElementById('detail-note');
    note.textContent = d.note || '';
    note.hidden = !d.note;
    const link = document.getElementById('detail-link');
    link.href = d.link || '#';
    link.hidden = !d.link;
    const dialog = document.getElementById('detail');
    dialog.showModal();
    fadeDim(true);
    growFrom(dialog, openedFrom, false);
  }}

  // The popup grows out of whatever was tapped (a tile, a list row, a link on
  // the today card) and shrinks back into it on close. `openedFrom` is
  // captured from the click/keypress itself, so showDetail's callers don't
  // have to pass it along. Skipped under "reduce motion", or when the thing
  // tapped is no longer on screen -- then the popup just appears.
  let openedFrom = null;
  const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)');
  ['click', 'keydown'].forEach((type) => document.addEventListener(type, (e) => {{
    if (e.target.closest && !e.target.closest('#detail')) openedFrom = e.target.closest('[data-date], a') || e.target;
  }}, true));
  // One timing for both the popup and the background dim, so the page
  // darkens exactly in step with the popup growing (and lightens as it
  // shrinks back).
  const OPEN_TIMING = {{ duration: 420, easing: 'cubic-bezier(0.33, 1, 0.68, 1)' }};
  const CLOSE_TIMING = {{ duration: 240, easing: 'ease-in' }};
  function growFrom(dialog, origin, reverse, done) {{
    const from = origin && origin.isConnected ? origin.getBoundingClientRect() : null;
    if (REDUCED_MOTION.matches || !dialog.animate || !from || !from.width) {{
      if (done) done();
      return;
    }}
    const to = dialog.getBoundingClientRect();
    const dx = (from.left + from.width / 2) - (to.left + to.width / 2);
    const dy = (from.top + from.height / 2) - (to.top + to.height / 2);
    const frames = [
      {{ transform: `translate(${{dx}}px, ${{dy}}px) scale(${{from.width / to.width}}, ${{from.height / to.height}})`, opacity: 0 }},
      {{ transform: 'none', opacity: 1 }},
    ];
    const anim = dialog.animate(reverse ? frames.slice().reverse() : frames, {{
      ...(reverse ? CLOSE_TIMING : OPEN_TIMING),
    }});
    if (done) anim.onfinish = done;
  }}
  function fadeDim(on) {{
    const dim = document.getElementById('detail-dim');
    const from = getComputedStyle(dim).opacity;  // mid-fade if reopened quickly
    const to = on ? 1 : 0;
    dim.getAnimations().forEach((a) => a.cancel());
    dim.style.opacity = to;
    if (REDUCED_MOTION.matches || !dim.animate) return;
    dim.animate([{{ opacity: from }}, {{ opacity: to }}], {{
      ...(on ? OPEN_TIMING : CLOSE_TIMING),
    }});
  }}
  function closeDetail() {{
    const dialog = document.getElementById('detail');
    if (!dialog.open || dialog.dataset.closing) return;
    dialog.dataset.closing = '1';
    fadeDim(false);
    growFrom(dialog, openedFrom, true, () => {{
      dialog.close();
      delete dialog.dataset.closing;
    }});
  }}
  document.getElementById('detail').addEventListener('click', (e) => {{
    if (e.target.id === 'detail') closeDetail();
  }});
  // Escape: animate the close too, instead of the browser's instant one.
  document.getElementById('detail').addEventListener('cancel', (e) => {{
    e.preventDefault();
    closeDetail();
  }});

  // Mark today's cell. Computed in the visitor's browser,
  // not baked in at render time -- the page is only rebuilt when the
  // calendar data changes, not daily, so a server-side "today" would go
  // stale the very next day.
  function todayISO() {{
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-'
      + String(d.getDate()).padStart(2, '0');
  }}
  // The "today" hero card at the top of the page -- same
  // computed-in-the-browser reasoning as markToday() below.
  const HERO_KIND_CLASS = {{Lesson: 'lesson', Opener: 'opener', Quiz: 'quiz', Test: 'test', '3-Act': 'threeact'}};
  const HERO_TYPE_CLASS = {{Flex: 'flex', Testing: 'testing', 'No School': 'noschool', Other: 'noschool'}};
  function heroEl(tag, cls, text) {{
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }}
  // First DETAILS entry of this `kind` strictly after `afterDate` -- used to
  // keep "upcoming quiz"/"upcoming test" always current, rather than relying
  // on a note someone remembered to write on one particular day.
  function nextByKind(kind, afterDate) {{
    for (const k of Object.keys(DETAILS)) {{ // ascending, same order as the calendar
      if (k > afterDate && DETAILS[k].kind === kind) return k;
    }}
    return null;
  }}
  function appendMaterialsRow(hero, entry) {{
    if (!DAILY_MATERIALS.length && !(entry.extra_materials || []).length) return;
    const row = heroEl('div', 'hero__materials');
    for (const m of DAILY_MATERIALS) {{
      const chip = heroEl('span', 'hero__material-chip');
      chip.textContent = m.icon + ' ' + m.label;
      row.appendChild(chip);
    }}
    for (const extra of (entry.extra_materials || [])) {{
      const chip = heroEl('span', 'hero__material-chip hero__material-chip--extra');
      chip.textContent = '+ ' + extra;
      row.appendChild(chip);
    }}
    hero.appendChild(row);
  }}
  function heroFooterRow(label, key) {{
    const row = heroEl('div', 'hero__footer-row');
    row.appendChild(document.createTextNode(label + ': '));
    const a = document.createElement('a');
    a.href = '#';
    a.textContent = DETAILS[key].date + ' — ' + (DETAILS[key].title || '');
    a.addEventListener('click', (e) => {{ e.preventDefault(); showDetail(key); }});
    row.appendChild(a);
    return row;
  }}
  // How urgent a due date is, counted in class days rather than calendar
  // days: on a Friday, Monday's homework is "due next class".
  function nextClassDay(afterDate) {{
    return Object.keys(DETAILS).find((k) => k > afterDate && DETAILS[k].type === 'Instruction') || null;
  }}
  function tomorrowISO(todayStr) {{
    const d = new Date(todayStr + 'T12:00:00');
    d.setDate(d.getDate() + 1);
    return d.toISOString().slice(0, 10);
  }}
  function dueUrgency(dueDate, dueLabel, todayStr) {{
    if (dueDate === todayStr) return {{ pill: 'Due today', level: 'today' }};
    if (dueDate === nextClassDay(todayStr)) {{
      return dueDate === tomorrowISO(todayStr)
        ? {{ pill: 'Due tomorrow', level: 'soon' }}
        : {{ pill: 'Due next class · ' + dueLabel, level: 'soon' }};
    }}
    return {{ pill: 'Due ' + dueLabel, level: 'later' }};
  }}
  // Every assignment not yet due, soonest first. Homework assigned today is
  // already listed in today's block above, so it's left out here.
  function appendDueList(hero, todayStr, skipAssignedOn) {{
    const items = [];
    for (const [k, d] of Object.entries(DETAILS)) {{
      if (k === skipAssignedOn) continue;
      for (const hw of d.homework) {{
        if (hw.due && hw.due >= todayStr) items.push(hw);
      }}
    }}
    if (!items.length) return;
    items.sort((a, b) => (a.due < b.due ? -1 : a.due > b.due ? 1 : 0));
    const section = heroEl('div', 'hero__due');
    section.appendChild(heroEl('div', 'hero__due-heading', 'Homework coming due'));
    for (const hw of items) {{
      const u = dueUrgency(hw.due, hw.due_label, todayStr);
      const a = heroEl('a', 'hero__due-item hero__due-item--' + u.level);
      a.href = '#';
      a.appendChild(heroEl('span', 'due-pill due-pill--' + u.level, u.pill));
      a.appendChild(heroEl('span', 'hero__due-text', hw.text));
      if (DETAILS[hw.due]) a.addEventListener('click', (e) => {{ e.preventDefault(); showDetail(hw.due); }});
      section.appendChild(a);
    }}
    hero.appendChild(section);
  }}
  function renderTodayHero() {{
    const hero = document.getElementById('today-hero');
    if (!hero) return;
    const todayStr = todayISO();
    const entry = DETAILS[todayStr];
    hero.replaceChildren();
    hero.hidden = false;

    if (entry) {{
      const cls = entry.type === 'Instruction'
        ? 'hero--' + (HERO_KIND_CLASS[entry.kind] || 'lesson')
        : 'hero--' + (HERO_TYPE_CLASS[entry.type] || 'noschool');
      hero.className = 'hero ' + cls;
      hero.appendChild(heroEl('div', 'hero__eyebrow', 'Today'));
      hero.appendChild(heroEl('div', 'hero__date', entry.date));
      if (entry.type !== 'No School') appendMaterialsRow(hero, entry);
      hero.appendChild(heroEl('div', 'hero__title', entry.title || ''));
      if (entry.target) hero.appendChild(heroEl('div', 'hero__row', 'Target: ' + entry.target));
      if (entry.classwork) hero.appendChild(heroEl('div', 'hero__row', 'Classwork: ' + entry.classwork));
      for (const hw of entry.homework) {{
        const row = heroEl('div', 'hero__row hero__hw', 'HW: ');
        row.appendChild(hwText(hw));
        row.appendChild(document.createTextNode(' '));
        if (hw.due) {{
          const u = dueUrgency(hw.due, hw.due_label, todayStr);
          row.appendChild(heroEl('span', 'due-pill due-pill--' + u.level, u.pill));
        }}
        hero.appendChild(row);
      }}
      if (entry.note) hero.appendChild(heroEl('div', 'hero__row hero__row--note', entry.note));
      if (entry.link) {{
        const a = document.createElement('a');
        a.className = 'hero__link'; a.href = entry.link; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = 'Open resource ↗';
        hero.appendChild(a);
      }}
    }} else {{
      hero.className = 'hero hero--empty';
      hero.appendChild(heroEl('div', 'hero__eyebrow', 'Today'));
      const todayLabel = new Date().toLocaleDateString('en-US', {{ weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }});
      hero.appendChild(heroEl('div', 'hero__date', todayLabel));
      hero.appendChild(heroEl('div', 'hero__title', 'No class today'));
    }}
    appendDueList(hero, todayStr, entry ? todayStr : null);

    // Footer: "next up" only when today has no class of its own, plus the
    // next quiz/test -- always, computed fresh, so it's never one day stale
    // the way a hand-written note on a single tile would be.
    const footerRows = [];
    if (!entry) {{
      const keys = Object.keys(DETAILS); // ascending, same order as the calendar
      const nextKey = keys.find((k) => k > todayStr) || keys[keys.length - 1];
      if (nextKey) footerRows.push(heroFooterRow('Next up', nextKey));
    }}
    const quizKey = nextByKind('Quiz', todayStr);
    if (quizKey) footerRows.push(heroFooterRow('Upcoming quiz', quizKey));
    const testKey = nextByKind('Test', todayStr);
    if (testKey) footerRows.push(heroFooterRow('Upcoming test', testKey));
    if (footerRows.length) {{
      const footer = heroEl('div', 'hero__footer');
      footerRows.forEach((row) => footer.appendChild(row));
      hero.appendChild(footer);
    }}
  }}
  function markToday() {{
    const todayStr = todayISO();
    // Every school day and every weekend within the school year has a cell
    // (see fill_weekends in render.py), so the literal date almost always
    // matches. Only before the year starts or after it ends is there no
    // cell at all -- fall back to the nearest upcoming school day, or the
    // last one if the year has ended.
    let matches = document.querySelectorAll(`[data-date="${{todayStr}}"]`);
    if (matches.length === 0) {{
      const keys = Object.keys(DETAILS); // ascending, same order as the calendar
      const target = keys.find((k) => k > todayStr) || keys[keys.length - 1];
      if (!target) return;
      matches = document.querySelectorAll(`[data-date="${{target}}"]`);
    }}
    // Highlight only -- the page opens at the top, on the today card, not
    // scrolled down to this cell.
    matches.forEach((el) => el.classList.add('day--today'));
  }}
  renderTodayHero();
  markToday();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "courses/math6.json")
    course = json.loads(path.read_text())
    calendar, leftover = render(course)
    calendar = fill_weekends(calendar)
    if leftover:
        print(f"warning: {leftover} lessons have no day left", file=sys.stderr)
    for label, warnings in run_all_checks(course):
        for w in warnings:
            print(f"warning ({label}): {w}", file=sys.stderr)
    print(build_page(course, calendar))
