"""Render every course into a static site directory for the Cloudflare deploy.

Usage (Cloudflare Workers Builds' build command -- see CLAUDE.md, "Hosting"):
    python3 scripts/build_site.py docs

Each courses/<slug>.json becomes <out>/<slug>/index.html, served at
beach-math.com/<slug>. The site root is a small front page linking to each
course. The course pages don't link to each other or back to it -- students
go straight to their own class's page from Schoology.

Runs in Cloudflare's ephemeral checkout; the output is never committed. To
preview locally, build into a scratch directory, never into docs/ -- the
committed docs/index.html is the redirect stub for old github.io bookmarks.
"""
import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import render, run_all_checks  # noqa: E402
from render import build_page, fill_weekends  # noqa: E402


def build_course(path, course):
    calendar, leftover = render(course)
    if leftover:
        print(f"warning ({path.stem}): {leftover} lessons have no day left", file=sys.stderr)
    for label, warnings in run_all_checks(course):
        for w in warnings:
            print(f"warning ({path.stem}, {label}): {w}", file=sys.stderr)
    return build_page(course, fill_weekends(calendar)) + "\n"  # same bytes as render.py's print()


def build_front_page(courses):
    """The bare-domain page: one button per course. `courses` is a list of
    (slug, course dict)."""
    years = sorted({c.get("school_year") for _, c in courses if c.get("school_year")})
    buttons = "\n".join(
        f'    <a class="course" href="/{escape(slug)}/">{escape(c["course"])}'
        f'<span class="course__arrow" aria-hidden="true">&rsaquo;</span></a>'
        for slug, c in courses
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mr. Beach's Math</title>
<style>
  :root {{
    color-scheme: light;
    --bg: #f7f7f5;
    --card: #ffffff;
    --text: #1f2328;
    --muted: #6b7280;
    --border: #e3e3e0;
    --lesson: #eef2ff;
    --lesson-border: #6366f1;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0;
    padding: 16px;
  }}
  main {{ max-width: 480px; margin: 12vh auto 0; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 4px; }}
  .subtitle {{ color: var(--muted); font-size: 0.95rem; margin: 0 0 24px; }}
  .courses {{ display: flex; flex-direction: column; gap: 12px; }}
  .course {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 18px 20px; border-radius: 14px; text-decoration: none;
    color: var(--text); font-size: 1.15rem; font-weight: 600;
    background: var(--lesson); border: 1px solid var(--border);
    border-left: 5px solid var(--lesson-border);
  }}
  .course:hover, .course:focus-visible {{ background: var(--card); }}
  .course__arrow {{ color: var(--lesson-border); font-size: 1.6rem; line-height: 1; }}
</style>
</head>
<body>
<main>
  <h1>Mr. Beach's Math</h1>
  <p class="subtitle">Class calendars{(" &middot; " + escape(", ".join(years))) if years else ""}</p>
  <nav class="courses">
{buttons}
  </nav>
</main>
</body>
</html>
"""


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[1])
    courses = []
    for path in sorted((ROOT / "courses").glob("*.json")):
        course = json.loads(path.read_text())
        (out / path.stem).mkdir(parents=True, exist_ok=True)
        (out / path.stem / "index.html").write_text(build_course(path, course))
        courses.append((path.stem, course))
        print(f"built /{path.stem}/", file=sys.stderr)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(build_front_page(courses))
    print("built / (front page)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
