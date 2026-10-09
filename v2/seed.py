"""Write the SQL that loads the school record and Aaron's teacher row into D1.

PLAN-v2-phase1.md, M2 (and M3's demo calendar). The school record is engine.school_record() of
courses/math6.json and courses/math78.json: the closures both courses
agree on, and every other day a plain class day. Aaron's row is a teacher
(slug "beach", for his practice calendar in M7b) and the admin.

Usage:
    python3 v2/seed.py --email <Aaron's Google sign-in> --school "<school name>" > /tmp/seed.sql
    npx wrangler d1 execute <database> --remote --file=/tmp/seed.sql

The email is an argument, not written here, because this repo is public.

It also adds the demo: a teacher no one can sign in as (slug "demo") with
one calendar, a template_from copy of Math 6, at beach-math.com/demo/math6.

Safe to run again: the school and teacher are only added if missing, and
the school's days are updated in place. That's how a school-wide change
made in courses/*.json (a snow day) reaches D1 during the trial, while
the school calendar exists twice (SPEC-v2.md, "Hosting and sign-in").
It clears the stored family pages at that school, so each is rendered
again, with the new days, on its next visit (store.published_page).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "v2"))
sys.path.insert(0, str(ROOT / "v2" / "src"))
import engine  # noqa: E402
from store import check_slug  # noqa: E402

COURSES = ("math6", "math78")

# The demo teacher. `.invalid` can't be a real address, so no one can sign
# in as her.
DEMO = {"email": "demo@beach-math.invalid", "name": "Demo Teacher", "slug": "demo"}


def sql_literal(value):
    """A value written into SQL: NULL, a number, or a quoted string."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def seed_sql(school_slug, school_name, days, email, name, teacher_slug):
    """The seed, as SQL statements: the school, its days, and the admin teacher."""
    check_slug(school_slug)
    check_slug(teacher_slug, teacher=True)
    school = f"(SELECT id FROM schools WHERE slug = {sql_literal(school_slug)})"
    rows = ",\n".join(f"  ({school}, {', '.join(sql_literal(d[k]) for k in ('date', 'weekday', 'type', 'note'))})"
                      for d in days)
    return "\n".join([
        f"INSERT INTO schools (slug, name) VALUES ({sql_literal(school_slug)}, {sql_literal(school_name)})"
        " ON CONFLICT (slug) DO NOTHING;",
        "INSERT INTO school_days (school_id, date, weekday, type, note) VALUES",
        rows,
        "ON CONFLICT (school_id, date) DO UPDATE SET"
        " weekday = excluded.weekday, type = excluded.type, note = excluded.note;",
        "INSERT INTO teachers (email, name, slug, school_id, is_admin) VALUES"
        f" ({sql_literal(email.strip().lower())}, {sql_literal(name)}, {sql_literal(teacher_slug)}, {school}, 1)"
        " ON CONFLICT (email) DO NOTHING;",
        f"UPDATE calendars SET page_html = NULL WHERE owner_id IN"
        f" (SELECT id FROM teachers WHERE school_id = {school});",
        "",
    ])


def demo_sql(school_slug, days, source, calendar_slug="math6"):
    """The demo teacher and her one calendar, copied from `source` (a
    course dict) over the school's `days`. Left alone if they exist."""
    check_slug(calendar_slug)
    school = f"(SELECT id FROM schools WHERE slug = {sql_literal(school_slug)})"
    teacher = f"(SELECT id FROM teachers WHERE slug = {sql_literal(DEMO['slug'])})"
    doc = engine.template_from(source, days)
    doc_sql = sql_literal(json.dumps(doc, ensure_ascii=False))
    return "\n".join([
        "INSERT INTO teachers (email, name, slug, school_id) VALUES"
        f" ({sql_literal(DEMO['email'])}, {sql_literal(DEMO['name'])}, {sql_literal(DEMO['slug'])}, {school})"
        " ON CONFLICT (email) DO NOTHING;",
        "INSERT INTO calendars (owner_id, slug, title, doc) VALUES"
        f" ({teacher}, {sql_literal(calendar_slug)}, {sql_literal(doc['course'])}, {doc_sql})"
        " ON CONFLICT (owner_id, slug) DO NOTHING;",
        "INSERT INTO revisions (calendar_id, version, doc, saved_by)"
        f" SELECT id, 1, doc, owner_id FROM calendars WHERE owner_id = {teacher} AND slug = {sql_literal(calendar_slug)}"
        " ON CONFLICT (calendar_id, version) DO NOTHING;",
        "",
    ])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--email", required=True, help="Aaron's Google sign-in email")
    ap.add_argument("--school", required=True, help="the school's name")
    ap.add_argument("--school-slug", default="home", help="a short id for the school (default: home)")
    ap.add_argument("--name", default="Mr. Beach", help="as families see it (default: Mr. Beach)")
    ap.add_argument("--slug", default="beach", help="first part of his v2 addresses (default: beach)")
    args = ap.parse_args(argv)
    courses = [json.loads((ROOT / "courses" / f"{c}.json").read_text()) for c in COURSES]
    days = engine.school_record(*courses)
    sys.stdout.write(seed_sql(args.school_slug, args.school, days, args.email, args.name, args.slug))
    sys.stdout.write(demo_sql(args.school_slug, days, courses[0]))


if __name__ == "__main__":
    main()
