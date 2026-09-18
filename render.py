"""Render a course's data file into a single static HTML calendar page.

Usage:
    python3 render.py courses/math6.json > docs/index.html

docs/ is what GitHub Pages serves. A GitHub Action (.github/workflows/
render.yml) runs this automatically and commits the result whenever
courses/*.json (or this file) changes on main -- so pushing a data edit is
enough; you don't have to run this locally first. Still useful to run by
hand to preview a change before committing.
"""
import calendar as calendar_module
import json
import sys
from datetime import date
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


def render_day_cell(day):
    d = date.fromisoformat(day["date"])
    day_num = d.day
    css = ["day"]
    body = ""
    if day["type"] == "Instruction":
        css.append(KIND_CLASS.get(day["kind"], "day--lesson"))
        body += f'<div class="day__lesson">{esc(day["lesson_text"])}</div>'
        if day["homework"]:
            body += f'<div class="day__homework">HW: {esc(day["homework"])}</div>'
        if day["note"]:
            body += f'<div class="day__note">{esc(day["note"])}</div>'
    else:
        css.append(TYPE_CLASS.get(day["type"], "day--other"))
        if day["display"]:
            body += f'<div class="day__note">{esc(day["display"])}</div>'
    # Fixed-size cell with clamped text, not size-to-content: guarantees the
    # cell can never overhang regardless of title length or device font
    # metrics. Tap/click opens the full, untruncated detail.
    return (
        f'<div class="{" ".join(css)}" role="button" tabindex="0" '
        f'data-date="{day["date"]}" aria-label="View details" '
        f'onclick="showDetail(\'{day["date"]}\')" '
        f"onkeydown=\"if(event.key==='Enter'||event.key===' '){{event.preventDefault();showDetail('{day['date']}')}}\">"
        f'<div class="day__num">{day_num}</div><div class="day__body">{body}</div></div>'
    )


def render_agenda_row(day):
    d = date.fromisoformat(day["date"])
    css = ["agenda-row"]
    body = ""
    if day["type"] == "Instruction":
        css.append(KIND_CLASS.get(day["kind"], "day--lesson"))
        body += f'<div class="day__lesson">{esc(day["lesson_text"])}</div>'
        if day["homework"]:
            body += f'<div class="day__homework">HW: {esc(day["homework"])}</div>'
        if day["note"]:
            body += f'<div class="day__note">{esc(day["note"])}</div>'
    else:
        css.append(TYPE_CLASS.get(day["type"], "day--other"))
        if day["display"]:
            body += f'<div class="day__note">{esc(day["display"])}</div>'
    return (
        f'<div class="{" ".join(css)}" data-date="{day["date"]}">'
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
        d = date.fromisoformat(day["date"])
        weekday_full = d.strftime("%A")
        details[day["date"]] = {
            "date": f"{weekday_full}, {MONTH_NAMES[d.month - 1]} {d.day}, {d.year}",
            "title": day["lesson_text"] if day["type"] == "Instruction" else day["display"],
            "homework": day["homework"],
            "note": day["note"] if day["type"] == "Instruction" else None,
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
    padding: 8px 10px; font-size: 0.85rem;
  }}
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
  }}
  .day:hover {{ box-shadow: inset 0 0 0 1px var(--muted); }}
  .day:focus-visible {{ outline: 2px solid var(--lesson-border); outline-offset: 1px; }}
  .day--pad {{ background: transparent; border-color: transparent; cursor: default; }}
  .day--pad:hover {{ box-shadow: none; }}
  .day__num {{ font-size: 0.68rem; color: var(--muted); margin-bottom: 2px; }}
  .day__body {{ overflow: hidden; }}
  /* Line-clamp, not auto-height: the cell's size never depends on content
     length or how a given device/browser measures the font. */
  .day__lesson {{
    font-weight: 600; line-height: 1.25; display: -webkit-box;
    -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden;
  }}
  .day__homework, .day__note {{
    color: var(--muted); margin-top: 2px; display: -webkit-box;
    -webkit-box-orient: vertical; -webkit-line-clamp: 1; overflow: hidden;
  }}
  .day__note {{ font-style: italic; }}
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

  dialog#detail {{
    border: none; border-radius: 10px; padding: 0; max-width: 380px; width: calc(100% - 32px);
    color: var(--text); box-shadow: 0 10px 40px rgba(0,0,0,0.2);
  }}
  dialog#detail::backdrop {{ background: rgba(0,0,0,0.4); }}
  .detail {{ padding: 16px 18px; }}
  .detail__date {{ font-size: 0.8rem; color: var(--muted); margin-bottom: 6px; }}
  .detail__title {{ font-size: 1.05rem; font-weight: 600; margin-bottom: 8px; }}
  .detail__homework, .detail__note {{ font-size: 0.9rem; margin-top: 6px; }}
  .detail__note {{ font-style: italic; color: var(--muted); }}
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
<div class="legend">
  <span><i style="background:var(--lesson-border)"></i>Lesson</span>
  <span><i style="background:var(--opener-border)"></i>Opener</span>
  <span><i style="background:var(--quiz-border)"></i>Quiz (formative)</span>
  <span><i style="background:var(--test-border)"></i>Test (summative)</span>
  <span><i style="background:var(--threeact-border)"></i>3-Act</span>
</div>
<nav class="months">{"".join(nav_links)}</nav>
{"".join(months)}
<dialog id="detail">
  <div class="detail">
    <button class="detail__close" onclick="document.getElementById('detail').close()" aria-label="Close">&times;</button>
    <div class="detail__date" id="detail-date"></div>
    <div class="detail__title" id="detail-title"></div>
    <div class="detail__homework" id="detail-homework" hidden></div>
    <div class="detail__note" id="detail-note" hidden></div>
  </div>
</dialog>
<script>
  const DETAILS = {details_json};
  function showDetail(dateStr) {{
    const d = DETAILS[dateStr];
    if (!d) return;
    document.getElementById('detail-date').textContent = d.date;
    document.getElementById('detail-title').textContent = d.title || '';
    const hw = document.getElementById('detail-homework');
    hw.textContent = d.homework ? 'HW: ' + d.homework : '';
    hw.hidden = !d.homework;
    const note = document.getElementById('detail-note');
    note.textContent = d.note || '';
    note.hidden = !d.note;
    document.getElementById('detail').showModal();
  }}
  document.getElementById('detail').addEventListener('click', (e) => {{
    if (e.target.id === 'detail') e.target.close();
  }});

  // Mark today's cell and scroll to it. Computed in the visitor's browser,
  // not baked in at render time -- the page is only rebuilt when the
  // calendar data changes, not daily, so a server-side "today" would go
  // stale the very next day.
  function todayISO() {{
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-'
      + String(d.getDate()).padStart(2, '0');
  }}
  function markToday() {{
    const keys = Object.keys(DETAILS); // ascending, same order as the calendar
    const todayStr = todayISO();
    // Weekends, breaks, and summer have no cell for the exact date -- fall
    // back to the nearest upcoming school day, or the last one if the year
    // has ended.
    const target = DETAILS[todayStr] ? todayStr
      : (keys.find((k) => k > todayStr) || keys[keys.length - 1]);
    if (!target) return;
    const matches = document.querySelectorAll(`[data-date="${{target}}"]`);
    matches.forEach((el) => el.classList.add('day--today'));
    const visible = Array.from(matches).find((el) => el.offsetParent !== null);
    (visible || matches[0])?.scrollIntoView({{ block: 'center' }});
  }}
  markToday();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "courses/math6.json")
    course = json.loads(path.read_text())
    calendar, leftover = render(course)
    if leftover:
        print(f"warning: {leftover} lessons have no day left", file=sys.stderr)
    for label, warnings in run_all_checks(course):
        for w in warnings:
            print(f"warning ({label}): {w}", file=sys.stderr)
    print(build_page(course, calendar))
