"""v2's Worker (PLAN-v2-phase1.md). M3: family pages.

    GET /<teacher>/<calendar>   the calendar's family page, or 404

Routes in wrangler.jsonc decide which paths reach this Worker at all;
everything else on beach-math.com stays with v1's Worker.
"""
from urllib.parse import urlsplit

from workers import Response, WorkerEntrypoint

import store
from d1 import D1

HTML = {"content-type": "text/html; charset=utf-8"}
NOT_FOUND = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Not found</title></head>
<body style="font: 16px/1.45 Verdana, sans-serif; margin: 12vh auto; max-width: 480px; padding: 0 16px">
<h1>Page not found</h1>
<p>Check the address your teacher gave you.</p>
</body></html>
"""


def page_address(path):
    """(teacher, calendar) for a path like /demo/math6 or /demo/math6/,
    or None."""
    parts = path.strip("/").split("/")
    if len(parts) != 2 or not all(store.SLUG_RE.fullmatch(p) for p in parts):
        return None
    return parts[0], parts[1]


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        if request.method not in ("GET", "HEAD"):
            return Response("method not allowed", status=405, headers={"allow": "GET, HEAD"})
        address = page_address(urlsplit(request.url).path)
        page = address and await store.published_page(D1(self.env.DB), *address)
        if page is None:
            return Response(NOT_FOUND, status=404, headers=HTML)
        return Response(page, headers=HTML)
