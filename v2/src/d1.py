"""store.py's database adapter over the Worker's D1 binding.

The same four async methods as store.SQLite -- `all`, `first`, `run`, and
`batch` -- with rows as plain dicts. The Workers SDK does the converting
both ways (None <-> null, objects -> dicts); this only reshapes D1's
results to match.
"""


class D1:
    def __init__(self, binding):
        self.binding = binding

    def _statement(self, sql, params):
        return self.binding.prepare(sql).bind(*params)

    async def all(self, sql, *params):
        return [dict(r) for r in (await self._statement(sql, params).all())["results"]]

    async def first(self, sql, *params):
        row = await self._statement(sql, params).first()
        return dict(row) if row is not None else None

    async def run(self, sql, *params):
        """Run one statement; returns how many rows it changed."""
        return (await self._statement(sql, params).run())["meta"]["changes"]

    async def batch(self, statements):
        """Run (sql, params) pairs in one transaction; returns each one's
        changed-row count."""
        results = await self.binding.batch([self._statement(sql, p) for sql, p in statements])
        return [r["meta"]["changes"] for r in results]
