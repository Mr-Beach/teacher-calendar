"""Render every course into a static site directory for the Cloudflare deploy.

Usage (Cloudflare Workers Builds' build command -- see CLAUDE.md, "Hosting"):
    python3 scripts/build_site.py docs

Each courses/<slug>.json becomes <out>/<slug>/index.html, served at
beach-math.com/<slug>. The site root also serves Math 6, so the
beach-math.com links already posted in Schoology keep working.

Runs in Cloudflare's ephemeral checkout; the output is never committed. To
preview locally, build into a scratch directory, never into docs/ -- the
committed docs/index.html is the redirect stub for old github.io bookmarks.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import render, run_all_checks  # noqa: E402
from render import build_page, fill_weekends  # noqa: E402

ROOT_COURSE = "math6"


def build_course(path):
    course = json.loads(path.read_text())
    calendar, leftover = render(course)
    if leftover:
        print(f"warning ({path.stem}): {leftover} lessons have no day left", file=sys.stderr)
    for label, warnings in run_all_checks(course):
        for w in warnings:
            print(f"warning ({path.stem}, {label}): {w}", file=sys.stderr)
    return build_page(course, fill_weekends(calendar)) + "\n"  # same bytes as render.py's print()


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[1])
    for path in sorted((ROOT / "courses").glob("*.json")):
        page = build_course(path)
        (out / path.stem).mkdir(parents=True, exist_ok=True)
        (out / path.stem / "index.html").write_text(page)
        if path.stem == ROOT_COURSE:
            (out / "index.html").write_text(page)
        print(f"built /{path.stem}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
