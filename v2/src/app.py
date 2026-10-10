"""v2's routes (PLAN-v2-phase1.md), as plain Python so v2/tests run them.

    GET /<teacher>/<calendar>          the calendar's family page; public
    GET /edit                          signed in: her calendars
    GET /edit/<slug>                   signed in: the editor (editor.html), read-only until M6
    GET /edit/<slug>/ahead             signed in: her look-ahead (decision 7)
    GET /api/calendars                 signed in: her calendars, as JSON
    GET /api/calendars/<slug>          signed in: one of hers, as JSON; 404 if not hers
    GET /api/calendars/<slug>/days     signed in: its rendered year, as the editor reads it

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
# Days the engine computes (PLANNING.md): shown in the grid, never editable.
COMPUTED_KINDS = {"Quiz", "Self-Grading"}
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
    items = "\n".join(
        f'<li><a href="/edit/{c["slug"]}">{html.escape(c["title"])}</a>'
        f' &middot; <a href="/{teacher["slug"]}/{c["slug"]}">family page</a></li>'
        for c in calendars) or "<li>None yet.</li>"
    return PAGE.format(title="Your calendars", body=(
        f"<h1>Your calendars</h1>\n<p>Signed in as {html.escape(teacher['name'])}.</p>\n"
        f"<ul>\n{items}\n</ul>"))


def calendar_json(c):
    return {k: c[k] for k in ("slug", "type", "title", "version", "updated_at")}


def editor_day(day, course):
    """One rendered day (engine.render) as the grid shows it."""
    out = {k: day[k] for k in ("date", "weekday", "type", "display", "kind", "lesson_text",
                               "target", "link", "note", "teacher_out", "quiz_paired",
                               "self_grading_paired")}
    out["classwork"] = day["classwork"] if engine.shows_classwork(course) else None
    out["homework"] = [{k: hw.get(k) for k in ("text", "due", "link")} for hw in day["homework"] or []]
    out["due"] = [hw["text"] for hw in day["due"] or []]
    out["computed"] = day["kind"] in COMPUTED_KINDS
    out["needs"] = [lookahead.FIELD_LABELS[f] for f in lookahead.missing_content(day, course)]
    return out


def calendar_days(teacher, cal):
    """/api/calendars/<slug>/days: the whole year, rendered. The editor
    pages through it by week without asking again."""
    calendar, _ = engine.render(cal.course)
    return {"slug": cal.slug, "title": cal.course["course"], "version": cal.version,
            "family_page": f"/{teacher['slug']}/{cal.slug}",
            "show_classwork": engine.shows_classwork(cal.course),
            "today": engine.school_today().isoformat(),
            "days": [editor_day(d, cal.course) for d in calendar]}


def ahead_page(cal):
    return lookahead_page.build_page(
        [(cal.slug, cal.course)], source="from your calendar",
        back=f'\n  <p><a href="/edit/{cal.slug}">&larr; {html.escape(cal.course["course"])}</a></p>')


async def load_owned(db, teacher, slug):
    """Her calendar `slug`, or None (not hers, missing, or not a slug)."""
    return await store.load_calendar(db, teacher, slug) if store.SLUG_RE.fullmatch(slug) else None


async def handle(method, path, token, db, keys, env):
    """The Reply for one request. `token` is its Cf-Access-Jwt-Assertion
    header (or None); `keys` an access.Keys."""
    if method not in ("GET", "HEAD"):
        return Reply(405, TEXT, "method not allowed", {"allow": "GET, HEAD"})

    if signed_in_area(path):
        try:
            teacher = await signed_in_teacher(db, token, keys, env)
        except access.Refused as e:
            print(f"refused {path}: {e}")
            return Reply(403, TEXT, "Sign in at beach-math.com/edit to see this.")
        parts = path.strip("/").split("/")
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
        return Reply(404, JSON if parts[0] == "api" else HTML,
                     '{"error": "not found"}' if parts[0] == "api" else NOT_FOUND)

    address = page_address(path)
    page = address and await store.published_page(db, *address)
    if page is None:
        return Reply(404, HTML, NOT_FOUND)
    return Reply(200, HTML, page)
