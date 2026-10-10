"""Tests for the read-only editor (PLAN-v2-phase1.md, M5): /edit/<calendar>,
its look-ahead, and the days the grid reads, on sqlite3.

The grid itself is editor.html's JavaScript; these check what it's served
and what it reads.

Run: python3 -m unittest discover -s v2/tests
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_access import ENV, MATH6, SignedInCase, claims, sign  # noqa: E402
import app  # noqa: E402
import engine  # noqa: E402
import store  # noqa: E402


class EditorTests(SignedInCase):

    async def test_signed_in_only(self):
        h, b, s = sign(claims(nbf=0, exp=10**12)).split(".")
        for path in ("/edit/math6", "/edit/math6/ahead", "/api/calendars/math6/days"):
            for token in (None, f"{h}.{b}.{s[::-1]}"):
                reply = await app.handle("GET", path, token, self.db, self.keys, ENV)
                self.assertEqual(reply.status, 403, path)
                self.assertNotIn("Topic", reply.body)

    async def test_the_editor(self):
        reply = await self.get("/edit/math6")
        self.assertEqual((reply.status, reply.body), (200, app.EDITOR))
        self.assertEqual((await self.get("/edit/math6/")).status, 200)
        home = (await self.get("/edit")).body
        self.assertIn('href="/edit/math6"', home)
        self.assertIn('href="/beach/math6"', home)

    async def test_another_teachers_calendar_is_a_404_like_a_missing_one(self):
        for tail in ("", "/ahead"):
            theirs = await self.get(f"/edit/secret{tail}")
            missing = await self.get(f"/edit/nothing{tail}")
            self.assertEqual((theirs.status, theirs.body), (404, missing.body))
        theirs = await self.get("/api/calendars/secret/days")
        missing = await self.get("/api/calendars/nothing/days")
        self.assertEqual((theirs.status, theirs.body), (404, missing.body))
        for path in ("/edit/math6/other", "/edit/math6/ahead/x", "/edit/Math6", "/api/calendars/math6/x"):
            self.assertEqual((await self.get(path)).status, 404, path)

    async def test_days(self):
        reply = await self.get("/api/calendars/math6/days")
        self.assertEqual(reply.status, 200)
        data = json.loads(reply.body)
        self.assertEqual((data["slug"], data["title"], data["version"], data["family_page"]),
                         ("math6", MATH6["course"], 1, "/beach/math6"))
        self.assertIs(data["show_classwork"], engine.shows_classwork(MATH6))
        self.assertEqual(data["today"], engine.school_today().isoformat())

        cal = await self.load("math6")
        rendered = engine.render(cal.course)[0]
        self.assertEqual([d["date"] for d in data["days"]], [d["date"] for d in rendered])
        days = {d["date"]: d for d in data["days"]}
        for day in rendered:
            got = days[day["date"]]
            shown = None if day["lesson_text"] == engine.NO_LESSON else day["lesson_text"]
            self.assertEqual((got["type"], got["kind"], got["lesson_text"], got["link"]),
                             (day["type"], day["kind"], shown, day["link"]))
            self.assertEqual(got["computed"], day["kind"] in ("Quiz", "Self-Grading"))
            self.assertEqual([h["text"] for h in got["homework"]],
                             [h["text"] for h in day["homework"] or []])
            self.assertEqual(got["due"], [h["text"] for h in day["due"] or []])
        self.assertTrue(any(d["computed"] for d in data["days"]))
        self.assertTrue(any(d["homework"] and d["homework"][0]["due"] for d in data["days"]))

    async def test_days_hide_class_work_when_the_calendar_does(self):
        cal = await self.load("math6")
        cal.course["show_classwork"] = False
        data = app.calendar_days({"slug": "beach"}, cal)
        self.assertFalse(data["show_classwork"])
        self.assertTrue(all(d["classwork"] is None for d in data["days"]))
        self.assertTrue(all("class work" not in d["needs"] for d in data["days"]))

    async def test_look_ahead(self):
        reply = await self.get("/edit/math6/ahead")
        self.assertEqual(reply.status, 200)
        self.assertIn("<h1>Look-ahead</h1>", reply.body)
        self.assertIn('data-course="math6"', reply.body)
        self.assertIn('href="/edit/math6"', reply.body)
        self.assertIn("from your calendar", reply.body)
        self.assertNotIn(">Both</button>", reply.body)  # one calendar, no tabs

    async def load(self, slug):
        me = await store.teacher_by_email(self.db, "teacher@example.com")
        return await store.load_calendar(self.db, me, slug)

if __name__ == "__main__":
    unittest.main()
