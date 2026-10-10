"""v2's store: calendars in the database, as the course dicts engine.py takes.

PLAN-v2-phase1.md, M2. The Worker (M3 on) loads a calendar as a course dict
-- its school's days joined with its own day changes
(engine.course_for_render) -- edits it with engine.py's own functions, and
saves it back, split apart again (engine.split_course). Nothing outside
this file writes SQL.

Every lookup that can change or reveal a calendar starts from the
signed-in teacher (a row from teacher_by_email, whose email came from the
verified Access token), and a calendar she doesn't own comes back None,
exactly like one that doesn't exist -- so the Worker answers 404 and never
reveals that it does.

Each save names the version it started from. If someone saved in between
(the same calendar open in two tabs), the save is refused with
StaleVersion and nothing changes. A save and its revision row are written
together, in one batch, or not at all.

The database is reached through an adapter with four async methods --
`all`, `first`, `run`, and `batch` -- the shape of D1's own API. SQLite
(below) is the one the tests use; the Worker's is d1.py. Everything here
is async because D1 is.

A family page is rendered on save and stored (PLAN-v2-phase1.md, decision
6). A calendar whose stored page is missing -- one v2/seed.py added, or
one whose school days seed.py just changed -- is rendered on its next
visit and stored then.
"""
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import engine
import render

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"

# First parts of a beach-math.com path that a teacher's slug can't take:
# v1's pages and apps (served by the current Worker), and v2's own.
# v2/tests check this covers every courses/*.json and apps/* folder.
RESERVED_SLUGS = {"api", "edit", "teacher", "math6", "math78", "tech-quest"}
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class StaleVersion(Exception):
    """The calendar was saved by someone else (another tab) since this
    copy was loaded: reload and redo the edit."""


class SQLite:
    """The adapter over Python's sqlite3, for tests and local runs."""

    def __init__(self, conn):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")  # D1 always enforces them

    @classmethod
    def memory(cls):
        """A fresh in-memory database with v2's schema."""
        db = cls(sqlite3.connect(":memory:"))
        db.conn.executescript(SCHEMA.read_text())
        return db

    async def all(self, sql, *params):
        return [dict(r) for r in self.conn.execute(sql, params)]

    async def first(self, sql, *params):
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    async def run(self, sql, *params):
        """Run one statement; returns how many rows it changed."""
        with self.conn:
            return self.conn.execute(sql, params).rowcount

    async def batch(self, statements):
        """Run (sql, params) pairs in one transaction, as D1's batch does;
        returns each one's changed-row count."""
        with self.conn:
            return [self.conn.execute(sql, params).rowcount for sql, params in statements]


@dataclass
class Calendar:
    """One calendar as loaded: `course` is the dict engine.py edits, and
    `version` the version it was loaded at (save_calendar sends it)."""
    id: int
    slug: str
    type: str
    version: int
    course: dict
    school_days: list = field(repr=False)


def check_slug(slug, teacher=False):
    """Raise ValueError unless `slug` can be part of an address: lower-case
    letters, digits, and single hyphens -- and, for a teacher, not a path
    the site already uses."""
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise ValueError(f"a slug is lower-case letters, digits, and hyphens, got {slug!r}")
    if teacher and slug in RESERVED_SLUGS:
        raise ValueError(f"{slug!r} is already a path on beach-math.com")


async def teacher_by_email(db, email):
    """The teacher row for a verified sign-in email, or None."""
    return await db.first("SELECT * FROM teachers WHERE email = ?", email.strip().lower())


async def school_days(db, school_id):
    """A school's days, in date order, in the shape of a course's school_days."""
    return await db.all("SELECT date, weekday, type, note FROM school_days "
                        "WHERE school_id = ? ORDER BY date", school_id)


async def list_calendars(db, teacher):
    """A teacher's calendars, for her editor's front page."""
    return await db.all("SELECT slug, type, title, version, updated_at FROM calendars "
                        "WHERE owner_id = ? ORDER BY title", teacher["id"])


async def load_calendar(db, teacher, slug):
    """The teacher's calendar `slug`, or None if she has none by that name."""
    row = await db.first("SELECT id, slug, type, version, doc FROM calendars "
                         "WHERE owner_id = ? AND slug = ?", teacher["id"], slug)
    if row is None:
        return None
    days = await school_days(db, teacher["school_id"])
    course = engine.course_for_render(days, json.loads(row["doc"]))
    return Calendar(row["id"], row["slug"], row["type"], row["version"], course, days)


def _doc_json(cal):
    doc = engine.split_course(cal.course, cal.school_days)
    if not doc.get("course"):
        raise ValueError('a calendar needs a title (its "course")')
    return doc["course"], json.dumps(doc, ensure_ascii=False)


async def create_calendar(db, teacher, slug, course, page_html=None, calendar_type="class"):
    """Add a calendar for `teacher` from a course dict over her school's
    days (e.g. engine.course_for_render(days, engine.template_from(...))).
    Raises ValueError if she already has one called `slug`."""
    check_slug(slug)
    if await db.first("SELECT 1 FROM calendars WHERE owner_id = ? AND slug = ?", teacher["id"], slug):
        raise ValueError(f"there's already a calendar called {slug!r}")
    days = await school_days(db, teacher["school_id"])
    cal = Calendar(None, slug, calendar_type, 1, course, days)
    title, doc = _doc_json(cal)
    await db.batch([
        ("INSERT INTO calendars (owner_id, slug, type, title, doc, page_html) VALUES (?, ?, ?, ?, ?, ?)",
         (teacher["id"], slug, calendar_type, title, doc, page_html)),
        ("INSERT INTO revisions (calendar_id, version, doc, saved_by) "
         "SELECT id, 1, doc, ? FROM calendars WHERE owner_id = ? AND slug = ?",
         (teacher["id"], teacher["id"], slug)),
    ])
    return await load_calendar(db, teacher, slug)


async def save_calendar(db, teacher, cal, page_html, restored_from=None):
    """Save `cal.course` (and its freshly rendered family page) as the next
    version, if `cal.version` is still current. On success `cal.version`
    moves up to the saved version. Raises StaleVersion if someone saved
    in between, and LookupError if the calendar isn't hers.
    `restored_from` is for undo: the version this save copies."""
    title, doc = _doc_json(cal)
    changed, _ = await db.batch([
        ("UPDATE calendars SET doc = ?, title = ?, page_html = ?, version = version + 1, "
         "updated_at = datetime('now') WHERE id = ? AND owner_id = ? AND version = ?",
         (doc, title, page_html, cal.id, teacher["id"], cal.version)),
        # Copies the row just saved. On a stale save the UPDATE changed
        # nothing, and this either finds no row at that version or finds
        # the other tab's save, whose revision already exists -- IGNORE.
        ("INSERT OR IGNORE INTO revisions (calendar_id, version, doc, saved_by, restored_from) "
         "SELECT id, version, doc, ?, ? FROM calendars WHERE id = ? AND version = ?",
         (teacher["id"], restored_from, cal.id, cal.version + 1)),
    ])
    if changed != 1:
        if await db.first("SELECT 1 FROM calendars WHERE id = ? AND owner_id = ?", cal.id, teacher["id"]):
            raise StaleVersion(f"{cal.slug} changed since version {cal.version}; reload")
        raise LookupError(f"no calendar {cal.slug!r} for this teacher")
    cal.version += 1
    return cal.version


async def undo_target(db, cal):
    """The version an undo of `cal` goes back to, or None if there's
    nothing to undo. Normally the one before it; but a version an undo
    saved is a copy of an earlier one, so undoing it steps back from
    that one instead (undo, undo goes back two saves, never forward)."""
    version = cal.version
    while version > 1:
        row = await db.first("SELECT restored_from FROM revisions WHERE calendar_id = ? AND version = ?",
                             cal.id, version)
        if row is None or row["restored_from"] is None:
            return version - 1
        version = row["restored_from"]
    return None


async def revision_course(db, cal, version):
    """A course dict for `cal` as it was at `version`, over today's
    school days."""
    row = await db.first("SELECT doc FROM revisions WHERE calendar_id = ? AND version = ?",
                         cal.id, version)
    if row is None:
        raise LookupError(f"{cal.slug} has no version {version}")
    return engine.course_for_render(cal.school_days, json.loads(row["doc"]))


def family_page(course, teacher):
    """The page families see, for a course dict: the same bytes
    scripts/build_site.py publishes for v1, with the teacher's name from
    her row unless the calendar names one itself."""
    if not course.get("teacher"):
        course = {**course, "teacher": teacher["name"]}
    calendar, _ = engine.render(course)
    return render.build_page(course, calendar) + "\n"


async def published_page(db, teacher_slug, calendar_slug):
    """The family page for beach-math.com/<teacher>/<calendar>, or None.
    Public: no sign-in, as in v1. A calendar with no stored page is
    rendered now and stored, unless it was saved again meanwhile."""
    row = await db.first("SELECT c.id, c.version, c.doc, c.page_html, t.name, t.school_id "
                         "FROM calendars c JOIN teachers t ON t.id = c.owner_id "
                         "WHERE t.slug = ? AND c.slug = ?", teacher_slug, calendar_slug)
    if row is None:
        return None
    if row["page_html"] is not None:
        return row["page_html"]
    course = engine.course_for_render(await school_days(db, row["school_id"]), json.loads(row["doc"]))
    page = family_page(course, row)
    await db.run("UPDATE calendars SET page_html = ? WHERE id = ? AND version = ? AND page_html IS NULL",
                 page, row["id"], row["version"])
    return page
