"""Tests for saving edits (PLAN-v2-phase1.md, M6): POST
/api/calendars/<slug>/edit and /undo, on sqlite3 -- versions, revisions,
the change log, the stored family page, and undo.

Run: python3 -m unittest discover -s v2/tests
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_access import ENV, SignedInCase, claims, sign  # noqa: E402
import app  # noqa: E402
import engine  # noqa: E402
import store  # noqa: E402


class SaveTests(SignedInCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.me = await store.teacher_by_email(self.db, "teacher@example.com")
        cal = await store.load_calendar(self.db, self.me, "math6")
        self.lesson = next(d for d in engine.render(cal.course)[0]
                           if d["date"] >= engine.school_today().isoformat()
                           and d["type"] == "Instruction" and d["kind"] == "Lesson")

    async def post(self, path, payload, email="teacher@example.com", same_origin=True, raw=None):
        token = sign(claims(email=email, nbf=0, exp=10**12))
        body = raw if raw is not None else json.dumps(payload)
        return await app.handle("POST", path, token, self.db, self.keys, ENV, body, same_origin)

    async def edit(self, version, fields, **extra):
        return await self.post("/api/calendars/math6/edit", {
            "version": version, "op": {"op": "edit", "date": self.lesson["date"], "fields": fields}, **extra})

    async def current(self):
        return await store.load_calendar(self.db, self.me, "math6")

    async def test_an_edit_is_saved_logged_and_published(self):
        reply = await self.edit(1, {"title": "Renamed for the test"})
        self.assertEqual(reply.status, 200, reply.body)
        data = json.loads(reply.body)
        self.assertEqual(data["version"], 2)
        self.assertIn("Renamed for the test", data["summary"])
        shown = {d["date"]: d for d in data["calendar"]["days"]}
        self.assertEqual(shown[self.lesson["date"]]["lesson_text"], "Renamed for the test")
        self.assertEqual(data["calendar"]["version"], 2)

        cal = await self.current()
        self.assertEqual(cal.version, 2)
        self.assertEqual(cal.course["changes"][-1]["summary"], data["summary"])
        rev = await self.db.first("SELECT doc, saved_by, restored_from FROM revisions "
                                  "WHERE calendar_id = ? AND version = 2", cal.id)
        self.assertEqual((rev["saved_by"], rev["restored_from"]), (self.me["id"], None))
        self.assertIn("Renamed for the test", (await self.get("/beach/math6", email=None)).body)

    async def test_small_fix_is_passed_on(self):
        await self.edit(1, {"target": "First wording."})
        reply = await self.edit(2, {"target": "Second wording."}, small_fix=True)
        self.assertEqual(reply.status, 200)

    async def test_a_stale_version_changes_nothing(self):
        await self.edit(1, {"title": "First tab"})
        reply = await self.edit(1, {"title": "Second tab"})
        self.assertEqual(reply.status, 409)
        self.assertIn("another tab", json.loads(reply.body)["error"])
        cal = await self.current()
        self.assertEqual(cal.version, 2)
        self.assertNotIn("Second tab", json.dumps(cal.course))

    async def test_a_refused_edit_changes_nothing(self):
        reply = await self.edit(1, {"link": "javascript:alert(1)"})
        self.assertEqual(reply.status, 400)
        self.assertIn("web address", json.loads(reply.body)["error"])
        self.assertEqual((await self.current()).version, 1)

    async def test_refusals(self):
        good = {"version": 1, "op": {"op": "edit", "date": self.lesson["date"], "fields": {"title": "x"}}}
        cases = [
            ("/api/calendars/math6/edit", good, {"same_origin": False}, 403),
            ("/api/calendars/secret/edit", good, {}, 404),
            ("/api/calendars/nothing/edit", good, {}, 404),
            ("/api/calendars/math6/delete", good, {}, 404),
            ("/api/calendars/math6/edit", None, {"raw": "not json"}, 400),
            ("/api/calendars/math6/edit", {"op": good["op"]}, {}, 400),
            ("/api/calendars/math6/edit", None, {"raw": "x" * (app.MAX_BODY + 1)}, 400),
            ("/api/calendars/math6/edit", good, {"email": "stranger@example.com"}, 403),
        ]
        for path, payload, kw, status in cases:
            with self.subTest(path=path, kw={k: str(v)[:20] for k, v in kw.items()}):
                self.assertEqual((await self.post(path, payload, **kw)).status, status)
        self.assertEqual((await self.current()).version, 1)
        # And with no token at all.
        reply = await app.handle("POST", "/api/calendars/math6/edit", None, self.db, self.keys, ENV,
                                 json.dumps(good), True)
        self.assertEqual(reply.status, 403)

    async def test_undo_steps_back_never_forward(self):
        original = (await self.current()).course
        await self.edit(1, {"title": "Edit one"})
        await self.edit(2, {"title": "Edit two"})
        undo = "/api/calendars/math6/undo"

        reply = await self.post(undo, {"version": 3})
        self.assertEqual((reply.status, json.loads(reply.body)["version"]), (200, 4))
        self.assertIn("Edit one", json.dumps((await self.current()).course))
        self.assertIn("Edit one", (await self.get("/beach/math6", email=None)).body)

        reply = await self.post(undo, {"version": 4})  # back past edit one, not forward to two
        self.assertEqual(reply.status, 200)
        self.assertEqual((await self.current()).course, original)

        reply = await self.post(undo, {"version": 5})
        self.assertEqual(reply.status, 400)
        self.assertIn("nothing to undo", json.loads(reply.body)["error"])

        # Undo is a save like any other: a stale one is refused.
        self.assertEqual((await self.post(undo, {"version": 3})).status, 409)

    async def test_an_edit_after_an_undo_can_be_undone(self):
        await self.edit(1, {"title": "Edit one"})
        await self.post("/api/calendars/math6/undo", {"version": 2})
        await self.edit(3, {"title": "Edit three"})
        await self.post("/api/calendars/math6/undo", {"version": 4})
        cal = await self.current()
        self.assertEqual(cal.version, 5)
        self.assertNotIn("Edit three", json.dumps(cal.course))
        self.assertNotIn("Edit one", json.dumps(cal.course))


class CreateTests(SignedInCase):
    async def post(self, payload, email="teacher@example.com", same_origin=True):
        token = sign(claims(email=email, nbf=0, exp=10**12))
        return await app.handle("POST", "/api/calendars", token, self.db, self.keys, ENV,
                                json.dumps(payload), same_origin)

    async def test_from_a_template(self):
        reply = await self.post({"title": "Math 7/8, Period 6", "slug": "period-6", "start": "math78"})
        self.assertEqual(reply.status, 200, reply.body)
        self.assertEqual(json.loads(reply.body), {"slug": "period-6", "editor": "/edit/period-6"})
        me = await store.teacher_by_email(self.db, "teacher@example.com")
        cal = await store.load_calendar(self.db, me, "period-6")
        self.assertEqual(cal.course["course"], "Math 7/8, Period 6")
        source = app.template_source("math78")
        self.assertEqual([e["district_title"] for e in cal.course["sequence"]],
                         [e["district_title"] for e in source["sequence"]])
        self.assertTrue(all(e["link"] is None and e["homework"] is None for e in cal.course["sequence"]))
        page = (await self.get("/beach/period-6", email=None)).body
        self.assertIn("Math 7/8, Period 6", page)
        self.assertNotIn("districtlms", page)  # none of Aaron's links come along
        self.assertEqual((await self.get("/edit/period-6")).status, 200)

    async def test_blank(self):
        reply = await self.post({"title": "Advisory", "slug": "advisory", "start": "blank", "theme": "forest"})
        self.assertEqual(reply.status, 200, reply.body)
        me = await store.teacher_by_email(self.db, "teacher@example.com")
        cal = await store.load_calendar(self.db, me, "advisory")
        self.assertEqual((cal.course["sequence"], cal.course["theme"]), ([], "forest"))
        days = json.loads((await self.get("/api/calendars/advisory/days")).body)
        # Nothing planned; the default quiz rule still puts in Wednesday quizzes.
        self.assertTrue(all(d["kind"] is None for d in days["days"] if d["type"] == "Instruction"
                            and not d["computed"]))
        self.assertTrue(any(d["kind"] == "Quiz" for d in days["days"]))

    async def test_refused(self):
        good = {"title": "Math 6", "slug": "new-one", "start": "math6"}
        for bad in ({**good, "slug": "math6"}, {**good, "slug": "Bad Slug"}, {**good, "slug": "x" * 41},
                    {**good, "title": " "}, {**good, "start": "../secret"}, {**good, "start": None}):
            with self.subTest(bad=bad):
                self.assertEqual((await self.post(bad)).status, 400)
        self.assertEqual((await self.post(good, same_origin=False)).status, 403)
        self.assertEqual((await self.post(good, email="stranger@example.com")).status, 403)
        self.assertEqual([c["slug"] for c in json.loads((await self.get("/api/calendars")).body)], ["math6"])

    async def test_the_home_page_offers_the_templates(self):
        body = (await self.get("/edit")).body
        for key, title in app.TEMPLATES:
            self.assertIn(f'value="{key}"', body)
        self.assertIn('value="blank"', body)
        self.assertIn("beach-math.com/beach/", body)


class PreviewTests(SignedInCase):
    async def test_her_page_in_each_preset_saving_nothing(self):
        import render
        for theme in ("teal", "plum", "forest", "slate"):
            reply = await self.get(f"/api/calendars/math6/preview/{theme}")
            self.assertEqual(reply.status, 200)
            if render.THEMES[theme]:
                self.assertIn(render.THEMES[theme]["--accent"], reply.body)
        self.assertEqual((await self.get("/api/calendars/math6/preview/neon")).status, 404)
        self.assertEqual((await self.get("/api/calendars/secret/preview/plum")).status, 404)
        me = await store.teacher_by_email(self.db, "teacher@example.com")
        self.assertEqual((await store.load_calendar(self.db, me, "math6")).version, 1)

    async def test_settings_in_the_days(self):
        data = json.loads((await self.get("/api/calendars/math6/days")).body)
        st = data["settings"]
        self.assertEqual((st["theme"], st["quiz"]["weekday"], st["account_name"]), ("teal", "Wed", "Mr. Beach"))
        self.assertIn("quiz_override", data["days"][0])


if __name__ == "__main__":
    unittest.main()
