"""M0 spike: can a Python Worker run engine.py/render.py unchanged, use D1,
and tell who is signed in through Cloudflare Access?

    /v2-spike/          Math 6's page, rendered by render.build_page
    /v2-spike/ahead     the teacher look-ahead (lookahead_page)
    /v2-spike/info      isolate id + request count (cold vs warm), render check
    /v2-spike/db        write a row to D1 and read the count back
    /v2-spike/whoami    the signed-in email, from a verified Access token
"""
import base64
import json
import random
import time

from js import JSON, Object, Uint8Array, crypto, fetch
from pyodide.ffi import to_js
from workers import Response, WorkerEntrypoint

import engine
import lookahead_page
import render
from course_data import MATH6_JSON

ISOLATE = None  # set on the first request; new per cold start
REQUESTS = 0


def _b64url(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _js(obj):
    return to_js(obj, dict_converter=Object.fromEntries)


async def verify_access(token, team_domain, aud):
    """The token's claims if its signature, audience, issuer, and expiry
    check out; raises ValueError otherwise."""
    head_b64, body_b64, sig_b64 = token.split(".")
    header = json.loads(_b64url(head_b64))
    claims = json.loads(_b64url(body_b64))
    if header.get("alg") != "RS256":
        raise ValueError(f"unexpected alg {header.get('alg')}")
    certs = await (await fetch(f"{team_domain}/cdn-cgi/access/certs")).json()
    jwk = next((k for k in certs.keys if k.kid == header.get("kid")), None)
    if jwk is None:
        raise ValueError("no matching signing key")
    algo = _js({"name": "RSASSA-PKCS1-v1_5", "hash": "SHA-256"})
    key = await crypto.subtle.importKey("jwk", jwk, algo, False, _js(["verify"]))
    data = f"{head_b64}.{body_b64}".encode()
    ok = await crypto.subtle.verify(algo, key, Uint8Array.new(_js(_b64url(sig_b64))),
                                    Uint8Array.new(_js(data)))
    if not ok:
        raise ValueError("bad signature")
    auds = claims.get("aud") if isinstance(claims.get("aud"), list) else [claims.get("aud")]
    if aud not in auds:
        raise ValueError("wrong audience")
    if claims.get("iss") != team_domain:
        raise ValueError("wrong issuer")
    if claims.get("exp", 0) < time.time():
        raise ValueError("expired")
    return claims


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global REQUESTS, ISOLATE
        if ISOLATE is None:
            ISOLATE = random.randrange(1 << 30)
        REQUESTS += 1
        path = request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        path = "/" + path.rstrip("/")
        course = json.loads(MATH6_JSON)

        if path == "/v2-spike":
            calendar, _ = engine.render(course)
            return Response(render.build_page(course, calendar),
                            headers={"content-type": "text/html; charset=utf-8"})

        if path == "/v2-spike/ahead":
            return Response(lookahead_page.build_page([("math6", course)]),
                            headers={"content-type": "text/html; charset=utf-8"})

        if path == "/v2-spike/info":
            calendar, leftover = engine.render(course)
            return Response.json({
                "isolate": ISOLATE, "requests_in_isolate": REQUESTS,
                "days": len(calendar), "leftover": leftover,
                "first_lesson": next(d["lesson_text"] for d in calendar if d["lesson_text"]),
                "checks": sum(len(w) for _, w in engine.run_all_checks(course)),
                "ctx_access": hasattr(self.ctx, "access"),
            })

        if path == "/v2-spike/db":
            db = self.env.DB
            await db.prepare("CREATE TABLE IF NOT EXISTS hits (id INTEGER PRIMARY KEY, isolate INTEGER, doc TEXT)").run()
            await db.prepare("INSERT INTO hits (isolate, doc) VALUES (?, ?)").bind(ISOLATE, MATH6_JSON).run()
            row = await db.prepare("SELECT COUNT(*) AS n, MAX(LENGTH(doc)) AS size FROM hits").first()
            back = await db.prepare("SELECT doc FROM hits ORDER BY id DESC LIMIT 1").first()
            same = json.loads(back.doc) == course
            return Response.json({"rows": row.n, "doc_bytes": row.size, "round_trip_equal": same})

        if path == "/v2-spike/whoami":
            token = request.headers.get("cf-access-jwt-assertion")
            result = {"token_present": bool(token), "ctx_access": hasattr(self.ctx, "access")}
            if hasattr(self.ctx, "access") and self.ctx.access:
                try:
                    ident = await self.ctx.access.getIdentity()
                    result["ctx_identity_email"] = ident.email if ident else None
                except Exception as e:
                    result["ctx_identity_error"] = str(e)
            if token:
                try:
                    claims = await verify_access(token, self.env.TEAM_DOMAIN, self.env.POLICY_AUD)
                    result["verified_email"] = claims.get("email")
                except Exception as e:
                    result["verify_error"] = str(e)
            # A forged token must fail: flip the signature and check it's refused.
            if token:
                h, b, s = token.split(".")
                try:
                    await verify_access(f"{h}.{b}.{s[::-1]}", self.env.TEAM_DOMAIN, self.env.POLICY_AUD)
                    result["forged_token"] = "ACCEPTED (bad)"
                except Exception as e:
                    result["forged_token"] = f"refused: {e}"
            return Response.json(result)

        return Response("not found", status=404)
