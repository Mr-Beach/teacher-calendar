"""Tests for sign-in and ownership (PLAN-v2-phase1.md, M4): access.py's
token check and app.py's routes, on sqlite3.

Tokens are signed here with fake_keys.py's throwaway keys, standing in
for Access's.

Run: python3 -m unittest discover -s v2/tests
"""
import base64
import hashlib
import json
import sys
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "v2" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))  # lookahead_page, for /edit/<calendar>/ahead
sys.path.insert(0, str(Path(__file__).resolve().parent))
import access  # noqa: E402
import app  # noqa: E402
import engine  # noqa: E402
import fake_keys  # noqa: E402
import store  # noqa: E402
from test_store import MATH6, add_teacher, seeded  # noqa: E402

TEAM = "https://beach-math.cloudflareaccess.com"
AUD = "test-aud"
ENV = SimpleNamespace(TEAM_DOMAIN=TEAM, ACCESS_AUD=AUD)
NOW = 1_800_000_000


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def jwk(n, kid):
    return {"kty": "RSA", "kid": kid, "alg": "RS256", "e": b64((65537).to_bytes(3, "big")),
            "n": b64(n.to_bytes((n.bit_length() + 7) // 8, "big"))}


def sign(claims, n=fake_keys.N0, d=fake_keys.D0, kid="k0", alg="RS256"):
    head = b64(json.dumps({"alg": alg, "kid": kid}).encode())
    body = b64(json.dumps(claims).encode())
    k = (n.bit_length() + 7) // 8
    digest = access.SHA256_INFO + hashlib.sha256(f"{head}.{body}".encode()).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(digest) - 3) + b"\x00" + digest
    sig = pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")
    return f"{head}.{body}.{b64(sig)}"


def claims(email="teacher@example.com", **over):
    return {"email": email, "aud": [AUD], "iss": TEAM, "iat": NOW - 10,
            "nbf": NOW - 10, "exp": NOW + 3600, **over}


class FakeCerts:
    """The team's certs endpoint, counting fetches. Publishes key 0 only."""

    def __init__(self):
        self.fetches = 0
        self.body = json.dumps({"keys": [jwk(fake_keys.N0, "k0")]})

    async def __call__(self, url):
        assert url == f"{TEAM}/cdn-cgi/access/certs", url
        self.fetches += 1
        return self.body


class TokenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.certs = FakeCerts()
        self.keys = access.Keys(TEAM, self.certs)

    async def verify(self, token, now=NOW):
        return await access.verify(token, self.keys, TEAM, AUD, now=now)

    async def refused(self, token, reason, now=NOW):
        with self.assertRaises(access.Refused) as cm:
            await self.verify(token, now)
        self.assertIn(reason, str(cm.exception))

    async def test_a_good_token_gives_its_email(self):
        self.assertEqual(await self.verify(sign(claims(email=" Teacher@Example.COM"))),
                         "teacher@example.com")

    async def test_no_token(self):
        await self.refused(None, "no token")
        await self.refused("", "no token")

    async def test_malformed(self):
        for token in ("abc", "a.b", "a.b.c.d", "!!!.###.$$$", "e30.e30.e30"):
            with self.assertRaises(access.Refused):
                await self.verify(token)

    async def test_forged_signature(self):
        h, b, s = sign(claims()).split(".")
        await self.refused(f"{h}.{b}.{s[::-1]}", "bad signature")
        # The claims changed under a real signature.
        other = sign(claims(email="someone@else.com")).split(".")[1]
        await self.refused(f"{h}.{other}.{s}", "bad signature")

    async def test_signed_with_a_key_access_never_published(self):
        await self.refused(sign(claims(), fake_keys.N1, fake_keys.D1, kid="k0"), "bad signature")
        await self.refused(sign(claims(), fake_keys.N1, fake_keys.D1, kid="k1"), "no matching")

    async def test_other_algorithms(self):
        await self.refused(sign(claims(), alg="none"), "unexpected alg")
        await self.refused(sign(claims(), alg="HS256"), "unexpected alg")

    async def test_expired_or_not_yet_valid(self):
        await self.refused(sign(claims(exp=NOW - 120)), "expired")
        await self.refused(sign(claims(exp=None)), "expired")
        await self.refused(sign(claims(nbf=NOW + 120)), "not valid yet")
        await self.verify(sign(claims(exp=NOW - 30)))  # inside the clock leeway

    async def test_another_audience_or_issuer(self):
        await self.refused(sign(claims(aud=["another-app"])), "wrong audience")
        await self.refused(sign(claims(aud="another-app")), "wrong audience")
        await self.verify(sign(claims(aud=AUD)))  # a bare string is fine
        await self.refused(sign(claims(iss="https://evil.cloudflareaccess.com")), "wrong issuer")

    async def test_no_email(self):
        await self.refused(sign(claims(email=None)), "no email")
        await self.refused(sign(claims(email="service-token")), "no email")

    async def test_keys_are_kept_and_refetched_sparingly(self):
        await self.verify(sign(claims()))
        await self.verify(sign(claims()))
        self.assertEqual(self.certs.fetches, 1)
        # An unknown key ID right away doesn't fetch again...
        await self.refused(sign(claims(), fake_keys.N1, fake_keys.D1, kid="k1"), "no matching")
        self.assertEqual(self.certs.fetches, 1)
        # ...but after the gap it does, and finds a rotated-in key.
        self.certs.body = json.dumps({"keys": [jwk(fake_keys.N0, "k0"), jwk(fake_keys.N1, "k1")]})
        later = NOW + access.Keys.REFETCH_GAP + 1
        self.assertEqual(await self.verify(sign(claims(exp=later + 60), fake_keys.N1, fake_keys.D1,
                                                kid="k1"), now=later), "teacher@example.com")
        self.assertEqual(self.certs.fetches, 2)


class SignedInCase(unittest.IsolatedAsyncioTestCase):
    """app.handle at the real clock: these tokens are good until 33658
    unless a test says otherwise. teacher@example.com owns "math6";
    other@example.com owns "secret"."""

    async def asyncSetUp(self):
        quiet = unittest.mock.patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)
        self.db = seeded()  # teacher@example.com, slug "beach"
        self.addCleanup(self.db.conn.close)
        self.keys = access.Keys(TEAM, FakeCerts())
        days = await store.school_days(self.db, 1)
        me = await store.teacher_by_email(self.db, "teacher@example.com")
        await store.create_calendar(self.db, me, "math6", engine.course_for_render(days, MATH6))
        other = await add_teacher(self.db, "other@example.com", "other")
        await store.create_calendar(self.db, other, "secret",
                                    engine.course_for_render(days, {**MATH6, "course": "Other's"}))

    async def get(self, path, email="teacher@example.com", token=None, method="GET"):
        if token is None and email:
            token = sign(claims(email=email, nbf=0, exp=10**12))
        return await app.handle(method, path, token, self.db, self.keys, ENV)


class RouteTests(SignedInCase):

    async def test_signed_in_pages_need_a_good_token(self):
        h, b, s = sign(claims(nbf=0, exp=10**12)).split(".")
        for path in ("/edit", "/edit/", "/edit/math6", "/api", "/api/calendars",
                     "/api/calendars/math6", "/api/nothing"):
            for token in (None, f"{h}.{b}.{s[::-1]}", sign(claims(nbf=0, exp=1_700_000_000)),
                          sign(claims(aud=["another-app"], nbf=0, exp=10**12))):
                reply = await app.handle("GET", path, token, self.db, self.keys, ENV)
                self.assertEqual(reply.status, 403, (path, token and token[:20]))
                self.assertNotIn("math6", reply.body)

    async def test_a_signed_in_stranger_is_refused(self):
        reply = await self.get("/api/calendars", email="stranger@example.com")
        self.assertEqual(reply.status, 403)

    async def test_her_own_calendars(self):
        reply = await self.get("/api/calendars")
        self.assertEqual(reply.status, 200)
        self.assertEqual([c["slug"] for c in json.loads(reply.body)], ["math6"])
        reply = await self.get("/api/calendars/math6")
        self.assertEqual((reply.status, json.loads(reply.body)["version"]), (200, 1))
        reply = await self.get("/edit")
        self.assertEqual(reply.status, 200)
        self.assertIn('href="/beach/math6"', reply.body)
        self.assertNotIn("secret", reply.body)

    async def test_another_teachers_calendar_is_a_404_like_a_missing_one(self):
        theirs = await self.get("/api/calendars/secret")
        missing = await self.get("/api/calendars/nothing")
        self.assertEqual((theirs.status, theirs.body), (missing.status, missing.body))
        self.assertEqual(theirs.status, 404)
        # And they see theirs, not hers.
        reply = await self.get("/api/calendars", email="other@example.com")
        self.assertEqual([c["slug"] for c in json.loads(reply.body)], ["secret"])
        self.assertEqual((await self.get("/api/calendars/math6", email="other@example.com")).status, 404)

    async def test_family_pages_stay_public(self):
        reply = await self.get("/beach/math6", email=None)
        self.assertEqual(reply.status, 200)
        self.assertIn("<!doctype html>", reply.body.lower())
        self.assertEqual((await self.get("/beach/nothing", email=None)).status, 404)

    async def test_methods(self):
        # POSTs go to /api only (M6's edits); anything else is refused.
        for method, path in (("POST", "/edit/math6"), ("POST", "/beach/math6"), ("PUT", "/api/calendars/math6"),
                             ("DELETE", "/api/calendars/math6")):
            self.assertEqual((await self.get(path, method=method)).status, 405, (method, path))


if __name__ == "__main__":
    unittest.main()
