"""v2's Worker (PLAN-v2-phase1.md): app.py's routes, on D1.

Routes in wrangler.jsonc decide which paths reach this Worker at all;
everything else on beach-math.com stays with v1's Worker.
"""
from urllib.parse import urlsplit

from js import fetch
from workers import Response, WorkerEntrypoint

import access
import app
from d1 import D1

KEYS = None  # access.Keys, made on the first request and kept while the Worker is warm


async def fetch_text(url):
    return await (await fetch(url)).text()


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global KEYS
        if KEYS is None:
            KEYS = access.Keys(self.env.TEAM_DOMAIN, fetch_text)
        url = urlsplit(request.url)
        body, same_origin = None, False
        if request.method == "POST":
            body = await request.text()
            origin = request.headers.get("origin")
            same_origin = ((request.headers.get("content-type") or "").startswith("application/json")
                           and origin is not None and urlsplit(origin).netloc == url.netloc)
        reply = await app.handle(request.method, url.path,
                                 request.headers.get("cf-access-jwt-assertion"),
                                 D1(self.env.DB), KEYS, self.env, body, same_origin)
        headers = {"content-type": reply.content_type, **reply.headers}
        if app.signed_in_area(url.path):
            headers["cache-control"] = "private, no-store"
        return Response(reply.body, status=reply.status, headers=headers)
