"""Tests for v2's database and store (PLAN-v2-phase1.md, M2), on sqlite3.

v2/schema.sql and v2/seed.py's SQL run here exactly as they would on D1.
Not part of tests/: v2 never gates the v1 build (PLAN-v2-phase1.md,
decision 2). GitHub Actions runs these as their own job.

Run: python3 -m unittest discover -s v2/tests
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "v2"))
sys.path.insert(0, str(ROOT / "v2" / "src"))
import engine  # noqa: E402
import seed  # noqa: E402
import store  # noqa: E402

GOLDEN = ROOT / "tests" / "golden"
MATH6 = json.loads((GOLDEN / "math6.json").read_text())
MATH78 = json.loads((GOLDEN / "math78.json").read_text())
SCHOOL = engine.school_record(MATH6, MATH78)


def seeded(email="Teacher@Example.com", name="Mr. Beach", slug="beach"):
    db = store.SQLite.memory()
    db.conn.executescript(seed.seed_sql("home", "Our School", SCHOOL, email, name, slug))
    return db


async def add_teacher(db, email, slug):
    await db.run("INSERT INTO teachers (email, name, slug, school_id) "
                 "SELECT ?, ?, ?, id FROM schools WHERE slug = 'home'", email, slug.title(), slug)
    return await store.teacher_by_email(db, email)


class SeedTests(unittest.IsolatedAsyncioTestCase):
    def seeded(self):
        db = seeded()
        self.addCleanup(db.conn.close)
        return db

    async def test_school_record_and_admin(self):
        db = self.seeded()
        days = await store.school_days(db, 1)
        self.assertEqual(days, SCHOOL)
        me = await store.teacher_by_email(db, "  teacher@example.COM ")
        self.assertEqual((me["slug"], me["name"], me["is_admin"]), ("beach", "Mr. Beach", 1))

    async def test_running_it_again_updates_days_and_adds_nothing(self):
        db = self.seeded()
        school = copy.deepcopy(SCHOOL)
        snow = next(d for d in school if d["type"] == "Instruction" and d["date"] > "2027-01-10")
        snow.update(type="No School", note="Snow day (it's closed)")
        db.conn.executescript(seed.seed_sql("home", "Our School", school, "teacher@example.com",
                                            "Someone Else", "beach"))
        self.assertEqual(await store.school_days(db, 1), school)
        self.assertEqual((await db.first("SELECT COUNT(*) AS n FROM teachers"))["n"], 1)
        self.assertEqual((await store.teacher_by_email(db, "teacher@example.com"))["name"], "Mr. Beach")

    def test_reserved_slugs_cover_every_v1_path(self):
        v1 = {p.stem for p in (ROOT / "courses").glob("*.json")}
        v1 |= {p.name for p in (ROOT / "apps").iterdir() if p.is_dir()}
        self.assertLessEqual(v1 | {"teacher", "edit", "api"}, store.RESERVED_SLUGS)
        with self.assertRaises(ValueError):
            seed.seed_sql("home", "Our School", SCHOOL, "a@b.c", "X", "math6")

    def test_bad_slugs(self):
        for slug in ("", "Math6", "math 6", "-x", "x--y", "x/y", None):
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                store.check_slug(slug)
        store.check_slug("math-7-8")


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = seeded()
        self.addCleanup(self.db.conn.close)
        self.me = await store.teacher_by_email(self.db, "teacher@example.com")
        self.cal = await store.create_calendar(self.db, self.me, "math6", copy.deepcopy(MATH6), "<p>v1</p>")

    async def test_a_course_round_trips(self):
        self.assertEqual((self.cal.version, self.cal.type), (1, "class"))
        self.assertEqual(self.cal.course, MATH6)
        self.assertEqual(engine.render(self.cal.course), engine.render(MATH6))
        # Stored apart from the school's days: only Math 6's own changes.
        doc = json.loads((await self.db.first("SELECT doc FROM calendars"))["doc"])
        self.assertNotIn("school_days", doc)
        self.assertEqual(doc["day_changes"], engine.split_course(MATH6, SCHOOL)["day_changes"])

    async def test_save_moves_the_version_and_keeps_every_revision(self):
        engine.set_day(self.cal.course, "2026-10-20", type="Other", note="Assembly")
        self.assertEqual(await store.save_calendar(self.db, self.me, self.cal, "<p>v2</p>"), 2)
        again = await store.load_calendar(self.db, self.me, "math6")
        self.assertEqual(again.version, 2)
        self.assertEqual(again.course, self.cal.course)
        self.assertEqual(await store.published_page(self.db, "beach", "math6"), "<p>v2</p>")
        revisions = await self.db.all("SELECT version, doc, saved_by FROM revisions ORDER BY version")
        self.assertEqual([r["version"] for r in revisions], [1, 2])
        self.assertEqual({r["saved_by"] for r in revisions}, {self.me["id"]})
        self.assertNotIn("2026-10-20", json.loads(revisions[0]["doc"])["day_changes"])
        self.assertIn("2026-10-20", json.loads(revisions[1]["doc"])["day_changes"])

    async def test_a_stale_save_is_refused_and_changes_nothing(self):
        other_tab = await store.load_calendar(self.db, self.me, "math6")
        engine.set_day(self.cal.course, "2026-10-20", type="Other", note="Assembly")
        await store.save_calendar(self.db, self.me, self.cal, "<p>first tab</p>")
        engine.set_day(other_tab.course, "2026-10-21", type="Other", note="Field trip")
        with self.assertRaises(store.StaleVersion):
            await store.save_calendar(self.db, self.me, other_tab, "<p>second tab</p>")
        self.assertEqual(other_tab.version, 1)
        now = await store.load_calendar(self.db, self.me, "math6")
        self.assertEqual((now.version, now.course), (2, self.cal.course))
        self.assertEqual(await store.published_page(self.db, "beach", "math6"), "<p>first tab</p>")
        self.assertEqual((await self.db.first("SELECT COUNT(*) AS n FROM revisions"))["n"], 2)

    async def test_another_teachers_calendar_is_not_found(self):
        her = await add_teacher(self.db, "her@example.com", "smith")
        self.assertIsNone(await store.load_calendar(self.db, her, "math6"))
        self.assertEqual(await store.list_calendars(self.db, her), [])
        with self.assertRaises(LookupError):
            await store.save_calendar(self.db, her, self.cal, "<p>hers</p>")
        self.assertEqual(await store.published_page(self.db, "beach", "math6"), "<p>v1</p>")
        # Her own calendar can share the slug.
        mine = await store.create_calendar(self.db, her, "math6", copy.deepcopy(MATH6))
        self.assertNotEqual(mine.id, self.cal.id)
        self.assertIn("Smith", await store.published_page(self.db, "smith", "math6"))

    async def test_list_and_duplicates(self):
        course = engine.course_for_render(SCHOOL, engine.template_from(MATH78, SCHOOL))
        await store.create_calendar(self.db, self.me, "math78", course)
        listed = await store.list_calendars(self.db, self.me)
        self.assertEqual([(c["slug"], c["title"], c["version"]) for c in listed],
                         [("math6", "Math 6", 1), ("math78", MATH78["course"], 1)])
        with self.assertRaises(ValueError):
            await store.create_calendar(self.db, self.me, "math6", copy.deepcopy(MATH6))

    async def test_unknown_email_and_page(self):
        self.assertIsNone(await store.teacher_by_email(self.db, "nobody@example.com"))
        self.assertIsNone(await store.published_page(self.db, "beach", "nope"))
        self.assertIsNone(await store.published_page(self.db, "nobody", "math6"))


class PageTests(unittest.IsolatedAsyncioTestCase):
    """M3: the family pages the Worker serves."""

    async def asyncSetUp(self):
        self.db = seeded()
        self.addCleanup(self.db.conn.close)
        self.me = await store.teacher_by_email(self.db, "teacher@example.com")

    async def test_parity_with_the_v1_build(self):
        # Math 6 imported into the store and rendered gives the same bytes
        # build_site.py publishes at beach-math.com/math6.
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_site
        expected = build_site.build_course(Path("math6.json"), copy.deepcopy(MATH6))
        await store.create_calendar(self.db, self.me, "math6", copy.deepcopy(MATH6))
        self.assertEqual(await store.published_page(self.db, "beach", "math6"), expected)
        cal = await store.load_calendar(self.db, self.me, "math6")
        self.assertEqual(store.family_page(cal.course, self.me), expected)

    async def test_a_missing_page_is_rendered_once_and_stored(self):
        await store.create_calendar(self.db, self.me, "math6", copy.deepcopy(MATH6))
        page = await store.published_page(self.db, "beach", "math6")
        self.assertEqual((await self.db.first("SELECT page_html FROM calendars"))["page_html"], page)
        await self.db.run("UPDATE calendars SET page_html = '<p>stored</p>'")
        self.assertEqual(await store.published_page(self.db, "beach", "math6"), "<p>stored</p>")

    async def test_a_new_seed_clears_stored_pages(self):
        await store.create_calendar(self.db, self.me, "math6", copy.deepcopy(MATH6), "<p>old days</p>")
        self.db.conn.executescript(seed.seed_sql("home", "Our School", SCHOOL, "teacher@example.com",
                                                 "Mr. Beach", "beach"))
        self.assertNotEqual(await store.published_page(self.db, "beach", "math6"), "<p>old days</p>")

    async def test_demo_calendar(self):
        sql = seed.demo_sql("home", SCHOOL, MATH6)
        self.db.conn.executescript(sql)
        self.db.conn.executescript(sql)  # again: adds nothing
        demo = await store.teacher_by_email(self.db, seed.DEMO["email"])
        self.assertEqual((demo["slug"], demo["is_admin"]), ("demo", 0))
        cal = await store.load_calendar(self.db, demo, "math6")
        self.assertEqual(cal.course, engine.course_for_render(SCHOOL, engine.template_from(MATH6, SCHOOL)))
        self.assertEqual((await self.db.first("SELECT COUNT(*) AS n FROM revisions"))["n"], 1)
        page = await store.published_page(self.db, "demo", "math6")
        self.assertIn("Demo Teacher", page)
        self.assertNotIn("Mr. Beach", page)


if __name__ == "__main__":
    unittest.main()
