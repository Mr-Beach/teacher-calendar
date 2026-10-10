"""Teacher-only look-ahead page, published at beach-math.com/teacher.

The same look-ahead as scripts/lookahead.py, built as a web page so Aaron can
open it on his phone without a Claude session. build_site.py writes it on
every push, so it's always current with courses/*.json.

The page carries every day from the build date to the end of the year; a
small script hides days before the viewer's today and shows the next 10
instructional days, with a button for 10 more. Without JavaScript it shows
everything from the build date on, which is still correct, just longer.

Not for students: it shows the content gaps ("needs target & link").
Access to /teacher is restricted at the Cloudflare edge, not in this page --
see the site-hosting skill. Nothing links to it from the student pages.
"""
from datetime import date

import engine
from lookahead import FIELD_LABELS, TAGGED_KINDS, missing_content
from render import esc

WINDOW = 10  # instructional days shown before "Show more"

KIND_CLASS = {"Quiz": "quiz", "Test": "test", "Opener": "opener", "3-Act": "threeact", "Project": "test"}


def render_day(day, course=None):
    d = date.fromisoformat(day["date"])
    when = f'<div class="when"><span>{day["weekday"]}</span>{d.month}/{d.day}</div>'
    if day["type"] != "Instruction":
        return (f'<li class="day closed" data-date="{day["date"]}">{when}'
                f'<div class="what"><div class="title">{esc(day["display"])}</div></div></li>')
    kind = day["kind"]
    needs = missing_content(day, course)
    css = ["day", KIND_CLASS.get(kind, "lesson")]
    if needs:
        css.append("gap")
    badge = f'<span class="badge">{esc(kind)}</span>' if kind in TAGGED_KINDS else ""
    if day["quiz_paired"]:
        badge += '<span class="badge paired">+ Quiz</span>'
    if day.get("self_grading_paired"):
        badge += '<span class="badge">+ Self-grading</span>'
    parts = [f'<div class="title">{badge}{esc(day["lesson_text"])}</div>']
    if day["target"]:
        parts.append(f'<div class="line">{esc(day["target"])}</div>')
    if day["classwork"]:
        parts.append(f'<div class="line"><b>Class work</b> {esc(day["classwork"])}</div>')
    for hw in day["homework"] or []:
        parts.append(f'<div class="line"><b>HW</b> {esc(hw["text"])}</div>')
    if day.get("teacher_out"):
        out = "all periods" if day["teacher_out"] is True else day["teacher_out"]
        parts.append(f'<div class="line note">Out: {esc(out)}</div>')
    if day["note"] and day["note"] != day["classwork"]:
        parts.append(f'<div class="line note">{esc(day["note"])}</div>')
    if needs:
        parts.append(f'<div class="needs">Needs {esc(" & ".join(FIELD_LABELS[f] for f in needs))}</div>')
    gap = ' data-gap="1"' if needs else ""
    return (f'<li class="{" ".join(css)}" data-date="{day["date"]}" data-instr="1"{gap}>'
            f'{when}<div class="what">{"".join(parts)}</div></li>')


def render_checks(course):
    """engine.run_all_checks' warnings for the whole year, above the
    look-ahead -- a cut to make, a missing review day -- so they reach Aaron
    without a Claude session or a build log. Nothing when every check is
    clean."""
    items = "".join(f"<li>{esc(w)}</li>" for _, ws in engine.run_all_checks(course) for w in ws)
    return f'<div class="checks"><b>Needs a decision</b><ul>{items}</ul></div>' if items else ""


def render_course(slug, course, start):
    days = [d for d in engine.render(course)[0] if d["date"] >= start]
    weeks = []
    for day in days:
        monday = engine.week_monday(day["date"])
        if not weeks or weeks[-1][0] != monday:
            weeks.append((monday, []))
        weeks[-1][1].append(day)
    body = "".join(
        f'<section class="week"><h3>Week of {monday.strftime("%b")} {monday.day}</h3>'
        f'<ol>{"".join(render_day(d, course) for d in week)}</ol></section>'
        for monday, week in weeks
    ) or '<p class="empty">No school days left in the calendar.</p>'
    return (f'<article class="course" data-course="{esc(slug)}">'
            f'<header><h2>{esc(course["course"])}</h2><p class="summary"></p></header>'
            f'{render_checks(course)}{body}<button class="more" type="button">Show 10 more days</button></article>')


def build_page(courses, today=None, source="from the course files", back=""):
    """`courses` is a list of (slug, course dict), as in build_site.py.
    v2's editor (v2/src/app.py) passes one calendar, so no course tabs,
    its own `source` line, and `back`, a link (HTML) above the heading."""
    # School time, not the build machine's UTC: an evening build would
    # otherwise start tomorrow and leave today off the page.
    start = (today or engine.school_today()).isoformat()
    tabs = "".join(
        f'<button type="button" data-show="{esc(slug)}">{esc(c["course"])}</button>'
        for slug, c in courses
    )
    if len(courses) > 1:
        tabs = ('\n  <div class="tabs" role="group" aria-label="Course">\n'
                f'    <button type="button" data-show="all">Both</button>{tabs}\n  </div>')
    else:
        tabs = ""
    articles = "".join(render_course(slug, c, start) for slug, c in courses)
    built = date.fromisoformat(start)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Look-ahead</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f7f7f5; --card: #ffffff; --text: #1f2328; --muted: #6b7280;
    --border: #e3e3e0; --lesson: #6366f1; --opener: #06b6d4; --quiz: #059669;
    --test: #ef4444; --threeact: #ca8a04; --closed: #f0f0ee;
    --gap-bg: #fff7ed; --gap-text: #9a3412; --today: #eef2ff;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #16171a; --card: #1f2126; --text: #e8e8e6; --muted: #9ca3af;
      --border: #2e3036; --closed: #1a1b1f; --gap-bg: #3a2414;
      --gap-text: #fdba74; --today: #252a45;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text); margin: 0; padding: 16px;
    font: 15px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  .top {{ max-width: 1200px; margin: 0 auto 16px; }}
  h1 {{ font-size: 1.5rem; margin: 0; }}
  .built {{ color: var(--muted); font-size: .85rem; margin: 2px 0 12px; }}
  .tabs {{ display: inline-flex; border: 1px solid var(--border); border-radius: 10px;
           overflow: hidden; background: var(--card); }}
  .tabs button {{ border: 0; background: none; color: var(--text); font: inherit;
                  padding: 8px 14px; cursor: pointer; }}
  .tabs button + button {{ border-left: 1px solid var(--border); }}
  .tabs button[aria-pressed="true"] {{ background: var(--lesson); color: #fff; }}
  main {{ max-width: 1200px; margin: 0 auto; display: grid; gap: 24px;
          grid-template-columns: repeat(auto-fit, minmax(min(100%, 440px), 1fr)); align-items: start; }}
  .course[hidden] {{ display: none; }}
  .course header {{ margin-bottom: 8px; }}
  h2 {{ font-size: 1.2rem; margin: 0; }}
  .summary {{ color: var(--muted); font-size: .9rem; margin: 2px 0 0; }}
  .summary b {{ color: var(--gap-text); font-weight: 600; }}
  .week {{ margin-top: 14px; }}
  h3 {{ font-size: .75rem; text-transform: uppercase; letter-spacing: .06em;
        color: var(--muted); margin: 0 0 6px; }}
  ol {{ list-style: none; margin: 0; padding: 0; background: var(--card);
        border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }}
  .day {{ display: flex; gap: 12px; padding: 10px 12px; border-left: 4px solid var(--lesson); }}
  .day + .day {{ border-top: 1px solid var(--border); }}
  .day.opener {{ border-left-color: var(--opener); }}
  .day.quiz {{ border-left-color: var(--quiz); }}
  .day.test {{ border-left-color: var(--test); }}
  .day.threeact {{ border-left-color: var(--threeact); }}
  .day.closed {{ border-left-color: transparent; background: var(--closed); color: var(--muted);
                 padding-top: 6px; padding-bottom: 6px; }}
  .day.today {{ background: var(--today); }}
  .day.today .when::after {{ content: "Today"; display: block; font-size: .7rem;
                             font-weight: 700; color: var(--lesson); }}
  .when {{ flex: 0 0 44px; font-weight: 600; font-variant-numeric: tabular-nums; }}
  .when span {{ display: block; font-size: .75rem; font-weight: 500; color: var(--muted); }}
  .closed .when span {{ display: inline; margin-right: 4px; }}
  .what {{ min-width: 0; }}
  .title {{ font-weight: 600; }}
  .closed .title {{ font-weight: 400; font-style: italic; }}
  .badge {{ display: inline-block; font-size: .7rem; font-weight: 700; text-transform: uppercase;
            letter-spacing: .04em; color: #fff; background: var(--lesson); border-radius: 4px;
            padding: 1px 6px; margin-right: 6px; vertical-align: 1px; }}
  .opener .badge {{ background: var(--opener); }}
  .quiz .badge, .badge.paired {{ background: var(--quiz); }}
  .test .badge {{ background: var(--test); }}
  .threeact .badge {{ background: var(--threeact); }}
  .line {{ color: var(--muted); font-size: .9rem; margin-top: 2px; }}
  .line b {{ color: var(--text); font-weight: 600; }}
  .note {{ font-style: italic; }}
  .needs {{ display: inline-block; margin-top: 4px; font-size: .8rem; font-weight: 600;
            color: var(--gap-text); background: var(--gap-bg); border-radius: 6px; padding: 2px 8px; }}
  .more {{ margin-top: 12px; width: 100%; padding: 10px; font: inherit; color: var(--text);
           background: var(--card); border: 1px solid var(--border); border-radius: 10px; cursor: pointer; }}
  .more[hidden], .day[hidden], .week[hidden] {{ display: none; }}
  .empty {{ color: var(--muted); }}
  .checks {{ margin-top: 10px; padding: 10px 12px; border-radius: 10px; font-size: .9rem;
             background: var(--gap-bg); color: var(--gap-text); }}
  .checks ul {{ margin: 4px 0 0; padding-left: 18px; }}
  .checks li + li {{ margin-top: 2px; }}
</style>
</head>
<body>
<div class="top">{back}
  <h1>Look-ahead</h1>
  <p class="built">Next {WINDOW} school days &middot; updated {built.strftime("%a")} {built.month}/{built.day} {source}</p>{tabs}
</div>
<main>
{articles}
</main>
<script>
(function () {{
  var d = new Date();
  var today = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" +
              String(d.getDate()).padStart(2, "0");
  var WINDOW = {WINDOW};

  document.querySelectorAll(".course").forEach(function (course) {{
    var shown = WINDOW;
    var days = Array.prototype.slice.call(course.querySelectorAll(".day"));
    var button = course.querySelector(".more");
    function fmt(iso) {{
      var p = iso.split("-");
      return +p[1] + "/" + +p[2];
    }}
    function update() {{
      // Show from today through the shown-th instructional day; drop closed
      // days before the first lesson and after the last one.
      var count = 0, visible = [];
      days.forEach(function (day) {{
        var keep = false;
        if (day.dataset.date >= today) {{
          if (day.dataset.instr) {{ if (count < shown) {{ count++; keep = true; }} }}
          else keep = count > 0 && count < shown;
        }}
        day.hidden = !keep;
        day.classList.toggle("today", day.dataset.date === today);
        if (keep) visible.push(day);
      }});
      course.querySelectorAll(".week").forEach(function (w) {{
        w.hidden = !w.querySelector(".day:not([hidden])");
      }});
      var remaining = days.some(function (day) {{
        return day.dataset.instr && day.hidden && day.dataset.date >= today;
      }});
      button.hidden = !remaining;
      var gaps = visible.filter(function (x) {{ return x.dataset.gap; }}).length;
      var next = visible.find(function (x) {{ return x.classList.contains("test"); }});
      var bits = [];
      bits.push(gaps ? "<b>" + gaps + " day" + (gaps > 1 ? "s" : "") + " need content</b>"
                     : "All days have content");
      if (next) bits.push("next test " + next.querySelector(".when span").textContent + " " +
                          fmt(next.dataset.date));
      course.querySelector(".summary").innerHTML = bits.join(" &middot; ");
    }}
    button.addEventListener("click", function () {{ shown += WINDOW; update(); }});
    update();
  }});

  var buttons = document.querySelectorAll(".tabs button");
  function show(which) {{
    buttons.forEach(function (b) {{ b.setAttribute("aria-pressed", String(b.dataset.show === which)); }});
    document.querySelectorAll(".course").forEach(function (c) {{
      c.hidden = which !== "all" && c.dataset.course !== which;
    }});
    try {{ localStorage.setItem("lookahead-course", which); }} catch (e) {{}}
  }}
  buttons.forEach(function (b) {{ b.addEventListener("click", function () {{ show(b.dataset.show); }}); }});
  var saved = "all";
  try {{ saved = localStorage.getItem("lookahead-course") || "all"; }} catch (e) {{}}
  show(document.querySelector('.tabs button[data-show="' + saved + '"]') ? saved : "all");
}})();
</script>
</body>
</html>
"""
