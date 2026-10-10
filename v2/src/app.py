"""v2's routes (PLAN-v2-phase1.md), as plain Python so v2/tests run them.

    GET /<teacher>/<calendar>          the calendar's family page; public
    GET /edit                          signed in: her calendars
    GET /edit/<slug>                   signed in: the editor (editor.html), read-only until M6
    GET /edit/<slug>/ahead             signed in: her look-ahead (decision 7)
    GET /api/calendars                 signed in: her calendars, as JSON
    GET /api/calendars/<slug>          signed in: one of hers, as JSON; 404 if not hers
    GET /api/calendars/<slug>/days     signed in: its rendered year and settings, as the editor reads it
    GET /api/calendars/<slug>/preview/<theme>  signed in: its family page in another color preset
    POST /api/calendars                signed in: start a calendar, {"title", "slug", "start"}
    POST /api/calendars/<slug>/edit    signed in: one edit (ops.py), {"version", "op", "small_fix"}
    POST /api/calendars/<slug>/undo    signed in: undo the last save, {"version"}

A save (M6) loads the calendar, checks it's still at the version the page
was looking at (409 if another tab saved since), applies the edit with
engine.py's functions, logs it for families (engine.record_change),
renders the family page, and stores it with a revision -- all or nothing.
It answers with the new version, a sentence about what changed, and the
rendered year, so the page redraws without asking again.

A POST must be JSON from this site: a form on another site can't send
JSON, and its Origin header won't match, so it can't edit with her
sign-in cookie.

Everything under /edit and /api is signed-in only (decision 4): the
Access token is checked, and its email looked up as a teacher, before the
path is even looked at, so a request that isn't signed in gets the same
403 whatever it asks for. A calendar she doesn't own is a 404, exactly
like one that doesn't exist.

entry.py is the Worker around this; routes in wrangler.jsonc decide which
paths reach it at all.
"""
import html
import json
from pathlib import Path

import access
import engine
import lookahead
import lookahead_page
import ops
import store

HTML = "text/html; charset=utf-8"
JSON = "application/json"
TEXT = "text/plain; charset=utf-8"
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="font: 16px/1.45 Verdana, sans-serif; margin: 12vh auto; max-width: 480px; padding: 0 16px">
{body}
</body></html>
"""
# The editor is one HTML file with plain JavaScript (decision 8); it reads
# the calendar from /api/calendars/<slug>/days.
EDITOR = (Path(__file__).resolve().parent / "editor.html").read_text()
MAX_BODY = 256 * 1024  # a paste of a few weeks is a few KB
# What a new calendar can start from (M7): Aaron's courses, copied with
# engine.template_from -- lessons and targets, none of his links or
# homework. The build copies courses/<key>.json to src/templates/<key>.json.txt
# (wrangler.jsonc: the Worker bundle leaves .json files out); run from the
# repo, they're read where they are.
TEMPLATES = (("math6", "Math 6"), ("math78", "Math 7/8 Compacted"))
HERE = Path(__file__).resolve().parent
MAX_CALENDARS = 20


def template_source(key):
    for path in (HERE / "templates" / f"{key}.json.txt", HERE.parent.parent / "courses" / f"{key}.json"):
        if path.exists():
            return json.loads(path.read_text())
    raise LookupError(f"no template {key!r}")


# Days the engine computes (PLANNING.md): shown in the grid, never editable.
COMPUTED_KINDS = {"Quiz", "Self-Grading"}
HOME = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Your calendars</title>
<style>
  :root {{ color-scheme: light dark; --bg: #f7f7f5; --card: #fff; --text: #1f2328; --muted: #6b7280;
          --border: #e3e3e0; --accent: #6366f1; --accent-text: #fff; --danger: #b91c1c; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #16171a; --card: #1f2126; --text: #e8e8e6;
          --muted: #9ca3af; --border: #2e3036; --accent: #818cf8; --accent-text: #111827; --danger: #f87171; }} }}
  * {{ box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--text); margin: 0 auto; max-width: 560px; padding: 24px 16px;
         font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  a {{ color: var(--accent); }}
  h1 {{ margin: 0 0 4px; font-size: 1.5rem; }}
  h2 {{ font-size: 1.1rem; margin: 28px 0 8px; }}
  .muted, .opt span {{ color: var(--muted); font-size: .9rem; }}
  form {{ display: grid; gap: 14px; background: var(--card); border: 1px solid var(--border);
          border-radius: 14px; padding: 16px; }}
  label.field {{ display: grid; gap: 4px; font-weight: 600; font-size: .9rem; }}
  input[type=text] {{ font: inherit; font-weight: 400; color: var(--text); background: var(--bg);
                      border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; width: 100%; }}
  fieldset {{ border: 0; padding: 0; margin: 0; display: grid; gap: 8px; }}
  legend {{ font-weight: 600; font-size: .9rem; margin-bottom: 6px; }}
  .opt {{ display: block; padding: 8px 10px; border: 1px solid var(--border); border-radius: 10px; cursor: pointer; }}
  .opt span {{ display: block; margin-left: 1.6em; }}
  .addr {{ display: flex; align-items: center; gap: 4px; }}
  .addr span {{ color: var(--muted); white-space: nowrap; font-weight: 400; }}
  button {{ font: inherit; border-radius: 10px; padding: 8px 14px; cursor: pointer;
           background: var(--accent); color: var(--accent-text); border: 1px solid var(--accent); justify-self: start; }}
  button:disabled {{ opacity: .6; }}
  .error {{ color: var(--danger); margin: 0; }}
  .error:empty {{ display: none; }}
</style></head>
<body>
<h1>Your calendars</h1>
<p class="muted">Signed in as {name}.</p>
<ul>
{items}
</ul>
<h2>Start a calendar</h2>
<form id="new" novalidate>
  <label class="field">Class title (families see this)
    <input type="text" name="title" placeholder="Math 6" autocomplete="off" required>
  </label>
  <label class="field">Its address
    <span class="addr"><span>{base}</span><input type="text" name="slug" placeholder="math-6" autocomplete="off"
      autocapitalize="none" spellcheck="false" required></span>
  </label>
  <fieldset><legend>Start from</legend>
    {starts}
  </fieldset>
  <p class="muted">School holidays come from your school's calendar. You can change everything after.</p>
  <p class="error" id="error" role="alert"></p>
  <button type="submit">Start the calendar</button>
</form>
<script>
(function () {{
  var form = document.getElementById("new"), error = document.getElementById("error"), typed = false;
  form.slug.oninput = function () {{ typed = true; }};
  form.title.oninput = function () {{
    if (!typed) form.slug.value = form.title.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
  }};
  form.onsubmit = function (e) {{
    e.preventDefault();
    error.textContent = "";
    var button = form.querySelector("button");
    button.disabled = true;
    fetch("/api/calendars", {{ method: "POST", credentials: "same-origin",
      headers: {{ "content-type": "application/json" }},
      body: JSON.stringify({{ title: form.title.value, slug: form.slug.value.trim(), start: form.start.value }}) }})
      .then(function (r) {{ return r.json().then(function (j) {{
        if (!r.ok) throw new Error(j.error || "That didn't work (" + r.status + "). Try again.");
        location.href = j.editor;
      }}); }})
      .catch(function (err) {{ error.textContent = err.message; button.disabled = false; }});
  }};
}})();
</script>
</body></html>
"""
NOT_FOUND = PAGE.format(title="Not found", body="<h1>Page not found</h1>\n"
                        "<p>Check the address your teacher gave you.</p>")


class Reply:
    def __init__(self, status, content_type, body, headers=None):
        self.status, self.content_type, self.body = status, content_type, body
        self.headers = headers or {}


def page_address(path):
    """(teacher, calendar) for a path like /demo/math6 or /demo/math6/,
    or None."""
    parts = path.strip("/").split("/")
    if len(parts) != 2 or not all(store.SLUG_RE.fullmatch(p) for p in parts):
        return None
    return parts[0], parts[1]


def signed_in_area(path):
    return path in ("/edit", "/api") or path.startswith(("/edit/", "/api/"))


async def signed_in_teacher(db, token, keys, env):
    """The teacher row for a request's Access token; raises access.Refused
    if the token doesn't check out or its email isn't a teacher."""
    email = await access.verify(token, keys, env.TEAM_DOMAIN, env.ACCESS_AUD)
    teacher = await store.teacher_by_email(db, email)
    if teacher is None:
        raise access.Refused(f"{email} is not a teacher here")
    return teacher


def editor_home(teacher, calendars):
    """/edit: her calendars, and starting a new one (M7)."""
    items = "\n".join(
        f'<li><a href="/edit/{c["slug"]}">{html.escape(c["title"])}</a>'
        f' &middot; <a href="/{teacher["slug"]}/{c["slug"]}">family page</a></li>'
        for c in calendars) or "<li>None yet.</li>"
    starts = "".join(
        f'<label class="opt"><input type="radio" name="start" value="{key}"{" checked" if i == 0 else ""}>'
        f' {html.escape(title)} <span>its lessons and I-can targets, on your school\'s days</span></label>'
        for i, (key, title) in enumerate(TEMPLATES))
    starts += ('<label class="opt"><input type="radio" name="start" value="blank"> Blank year'
               ' <span>your school\'s days, nothing planned</span></label>')
    return HOME.format(name=html.escape(teacher["name"]), items=items, starts=starts,
                       base=f"beach-math.com/{teacher['slug']}/")


def calendar_json(c):
    return {k: c[k] for k in ("slug", "type", "title", "version", "updated_at")}


def editor_day(day, course, school_closed=False, quiz_override=None):
    """One rendered day (engine.render) as the grid shows it.
    `school_closed`: closed on the school's calendar, so she can't open it.
    `quiz_override`: the day's own quiz change ("none", "full", "paired"),
    which "back to the quiz rule" clears."""
    out = {k: day[k] for k in ("date", "weekday", "type", "display", "kind", "lesson_text",
                               "target", "link", "note", "teacher_out", "quiz_paired",
                               "self_grading_paired")}
    if out["lesson_text"] == engine.NO_LESSON:
        out["lesson_text"] = None  # an empty day; the grid says "Nothing planned"
    out["classwork"] = day["classwork"] if engine.shows_classwork(course) else None
    out["homework"] = [{k: hw.get(k) for k in ("text", "due", "link")} for hw in day["homework"] or []]
    out["due"] = [hw["text"] for hw in day["due"] or []]
    out["computed"] = day["kind"] in COMPUTED_KINDS
    out["needs"] = [lookahead.FIELD_LABELS[f] for f in lookahead.missing_content(day, course)]
    out["school_closed"] = school_closed
    out["quiz_override"] = quiz_override
    return out


def settings_json(teacher, course):
    """Her calendar's settings, as the settings sheet shows them."""
    rule = engine.quiz_rule(course)
    return {"course": course["course"], "teacher": course.get("teacher") or "",
            "account_name": teacher.get("name") or "", "theme": course.get("theme") or "teal",
            "themes": list(ops.THEMES), "show_classwork": engine.shows_classwork(course),
            "review_before_test": course.get("review_before_test", True),
            "quiz": {k: rule[k] for k in ops.QUIZ_SETTINGS}}


def calendar_days(teacher, cal):
    """/api/calendars/<slug>/days: the whole year, rendered. The editor
    pages through it by week without asking again."""
    calendar, _ = engine.render(cal.course)
    closed = {d["date"] for d in cal.school_days if d["type"] == "No School"}
    overrides = {d["date"]: d.get("quiz") for d in cal.course["school_days"]}
    return {"slug": cal.slug, "title": cal.course["course"], "version": cal.version,
            "family_page": f"/{teacher['slug']}/{cal.slug}",
            "show_classwork": engine.shows_classwork(cal.course),
            "today": engine.school_today().isoformat(),
            "settings": settings_json(teacher, cal.course),
            "days": [editor_day(d, cal.course, d["date"] in closed, overrides.get(d["date"]))
                     for d in calendar]}


def ahead_page(cal):
    return lookahead_page.build_page(
        [(cal.slug, cal.course)], source="from your calendar",
        back=f'\n  <p><a href="/edit/{cal.slug}">&larr; {html.escape(cal.course["course"])}</a></p>')


def error(status, message):
    return Reply(status, JSON, json.dumps({"error": message}))


def impact_message(impact, entry):
    """What a save did, for her: where days started changing, whether
    lessons now run past the year, and which days families see tagged."""
    bits = []
    if impact["first_shifted_date"]:
        bits.append(f"Days from {ops.when(impact['first_shifted_date'])} on changed.")
    before, after = impact["leftover_before"], impact["leftover_after"]
    if after > before:
        bits.append(f"{after} lesson{'s' * (after != 1)} now run past the last day of school.")
    elif after < before:
        bits.append(f"{before - after} more lesson{'s' * (before - after != 1)} now fit in the year.")
    tagged = [ops.when(d["date"]) for d in (entry or {}).get("days", [])]
    if len(tagged) > 3:  # a lost day can move every quiz and test after it
        more = len(tagged) - 3
        tagged = tagged[:3] + [f"{more} more day{'s' * (more != 1)}"]
    if tagged:
        bits.append("Families see it marked Updated on " + ", ".join(tagged) + ".")
    return " ".join(bits)


async def save_edit(db, teacher, cal, payload):
    """POST /api/calendars/<slug>/edit."""
    before, before_left = engine.render(cal.course)
    try:
        summary = ops.apply(cal.course, payload.get("op"), cal.school_days)
    except ValueError as e:  # ops.OpError, or the engine's own refusal
        return error(400, str(e))
    entry = engine.record_change(cal.course, before, summary, small_fix=payload.get("small_fix") is True)
    impact = engine.diff_impact(cal.course, before, before_left)
    await store.save_calendar(db, teacher, cal, store.family_page(cal.course, teacher))
    return Reply(200, JSON, json.dumps({
        "version": cal.version, "summary": summary, "message": impact_message(impact, entry),
        "calendar": calendar_days(teacher, cal)}, ensure_ascii=False))


async def save_undo(db, teacher, cal):
    """POST /api/calendars/<slug>/undo."""
    target = await store.undo_target(db, cal)
    if target is None:
        return error(400, "There's nothing to undo.")
    cal.course = await store.revision_course(db, cal, target)
    await store.save_calendar(db, teacher, cal, store.family_page(cal.course, teacher),
                              restored_from=target)
    return Reply(200, JSON, json.dumps({
        "version": cal.version, "summary": "Undone", "message": "Your last save was undone.",
        "calendar": calendar_days(teacher, cal)}, ensure_ascii=False))


async def create(db, teacher, payload):
    """POST /api/calendars: a new calendar from a template or a blank year,
    over her school's days (M7)."""
    title = payload.get("title")
    title = " ".join(title.split()) if isinstance(title, str) else ""
    if not title or len(title) > 80:
        return error(400, "Give the calendar a title (under 80 characters).")
    slug = payload.get("slug")
    try:
        store.check_slug(slug)
    except ValueError:
        return error(400, "The address is lower-case letters, numbers, and single dashes, like math-6.")
    if len(slug) > 40:
        return error(400, "Keep the address under 40 characters.")
    start = payload.get("start")
    if start not in dict(TEMPLATES) and start != "blank":
        return error(400, "Pick what to start from.")
    if len(await store.list_calendars(db, teacher)) >= MAX_CALENDARS:
        return error(400, f"You have {MAX_CALENDARS} calendars, the most there can be.")
    days = await store.school_days(db, teacher["school_id"])
    if not days:
        return error(400, "Your school's calendar isn't set up yet. Ask Mr. Beach.")
    if start == "blank":
        first, last = days[0]["date"][:4], days[-1]["date"][:4]
        doc = {"course": title, "school_year": f"{first}-{last[2:]}" if first != last else first,
               "show_classwork": False, "sequence": [], "changes": [], "day_changes": {}}
    else:
        doc = engine.template_from(template_source(start), days)
    doc["course"] = title
    if payload.get("theme") in ops.THEMES:
        doc["theme"] = payload["theme"]
    course = engine.course_for_render(days, doc)
    try:
        cal = await store.create_calendar(db, teacher, slug, course, store.family_page(course, teacher))
    except ValueError:
        return error(400, f"You already have a calendar at {slug}. Pick another address.")
    return Reply(200, JSON, json.dumps({"slug": cal.slug, "editor": f"/edit/{cal.slug}"}))


async def post(db, teacher, parts, body, same_origin):
    """A POST under /api: a new calendar, or an edit or an undo of one of hers."""
    if not same_origin:
        return error(403, "Edits come from the editor on this site.")
    new = parts == ["api", "calendars"]
    if not new and (len(parts) != 4 or parts[:2] != ["api", "calendars"] or parts[3] not in ("edit", "undo")):
        return error(404, "not found")
    if body is None or len(body) > MAX_BODY:
        return error(400, "That edit was empty or too big.")
    try:
        payload = json.loads(body)
    except ValueError:
        payload = None
    if new and isinstance(payload, dict):
        return await create(db, teacher, payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("version"), int):
        return error(400, "That edit didn't come through. Reload and try again.")
    cal = await load_owned(db, teacher, parts[2])
    if cal is None:
        return error(404, "not found")
    if payload["version"] != cal.version:
        return error(409, "This calendar changed in another tab or window. Reload to see the latest.")
    try:
        if parts[3] == "undo":
            return await save_undo(db, teacher, cal)
        return await save_edit(db, teacher, cal, payload)
    except store.StaleVersion:
        return error(409, "This calendar changed in another tab or window. Reload to see the latest.")


async def load_owned(db, teacher, slug):
    """Her calendar `slug`, or None (not hers, missing, or not a slug)."""
    return await store.load_calendar(db, teacher, slug) if store.SLUG_RE.fullmatch(slug) else None


async def handle(method, path, token, db, keys, env, body=None, same_origin=False):
    """The Reply for one request. `token` is its Cf-Access-Jwt-Assertion
    header (or None); `keys` an access.Keys. For a POST, `body` is its
    text and `same_origin` whether it's JSON sent from this site (entry.py
    decides)."""
    if method not in ("GET", "HEAD", "POST") or (method == "POST" and not path.startswith("/api/")):
        return Reply(405, TEXT, "method not allowed", {"allow": "GET, HEAD"})

    if signed_in_area(path):
        try:
            teacher = await signed_in_teacher(db, token, keys, env)
        except access.Refused as e:
            print(f"refused {path}: {e}")
            return Reply(403, TEXT, "Sign in at beach-math.com/edit to see this.")
        parts = path.strip("/").split("/")
        if method == "POST":
            return await post(db, teacher, parts, body, same_origin)
        if parts == ["edit"]:
            return Reply(200, HTML, editor_home(teacher, await store.list_calendars(db, teacher)))
        if parts == ["api", "calendars"]:
            cals = await store.list_calendars(db, teacher)
            return Reply(200, JSON, json.dumps([calendar_json(c) for c in cals]))
        if len(parts) == 3 and parts[:2] == ["api", "calendars"]:
            cals = {c["slug"]: c for c in await store.list_calendars(db, teacher)}
            if parts[2] in cals:
                return Reply(200, JSON, json.dumps(calendar_json(cals[parts[2]])))
        if parts[:1] == ["edit"] and len(parts) in (2, 3) and parts[2:] in ([], ["ahead"]):
            cal = await load_owned(db, teacher, parts[1])
            if cal and len(parts) == 2:
                return Reply(200, HTML, EDITOR)
            if cal:
                return Reply(200, HTML, ahead_page(cal))
        if len(parts) == 4 and parts[:2] == ["api", "calendars"] and parts[3] == "days":
            cal = await load_owned(db, teacher, parts[2])
            if cal:
                return Reply(200, JSON, json.dumps(calendar_days(teacher, cal), ensure_ascii=False))
        if len(parts) == 5 and parts[:2] == ["api", "calendars"] and parts[3] == "preview" \
                and parts[4] in ops.THEMES:
            cal = await load_owned(db, teacher, parts[2])
            if cal:  # her page as it is now, in another preset: nothing saved
                return Reply(200, HTML, store.family_page({**cal.course, "theme": parts[4]}, teacher))
        return Reply(404, JSON if parts[0] == "api" else HTML,
                     '{"error": "not found"}' if parts[0] == "api" else NOT_FOUND)

    address = page_address(path)
    page = address and await store.published_page(db, *address)
    if page is None:
        return Reply(404, HTML, NOT_FOUND)
    return Reply(200, HTML, page)
