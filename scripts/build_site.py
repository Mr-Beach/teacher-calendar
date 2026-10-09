"""Render every course into a static site directory for the Cloudflare deploy.

Usage (Cloudflare Workers Builds' build command -- see CLAUDE.md, "Hosting"):
    python3 scripts/build_site.py docs

Each courses/<slug>.json becomes <out>/<slug>/index.html, served at
beach-math.com/<slug>. The site root is a small front page linking to each
course. The course pages don't link to each other or back to it -- students
go straight to their own class's page from Schoology.

The teacher-only look-ahead (scripts/lookahead_page.py) is written to
<out>/teacher/index.html, served at beach-math.com/teacher. Access to it is
restricted at the Cloudflare edge -- see the site-hosting skill.

Each apps/<name>/ folder (student apps like Tech Quest) is copied as-is to
<out>/<name>/, served at beach-math.com/<name>. Apps aren't on the front page.

Runs the tests first (tests/): if any fail, nothing is built and the build
fails, so Cloudflare keeps serving the last good site rather than publishing
a broken one. The same tests run in GitHub Actions on every push to main
(.github/workflows/tests.yml), which is where a failure gets emailed.

Runs in Cloudflare's ephemeral checkout; the output is never committed. To
preview locally, build into a scratch directory, never into docs/ -- the
committed docs/index.html is the redirect stub for old github.io bookmarks.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import render, run_all_checks  # noqa: E402
from render import TEACHER, build_page, esc  # noqa: E402
import lookahead_page  # noqa: E402

TEACHER_PATH = "teacher"  # beach-math.com/teacher; no course or app may use it


def build_course(path, course):
    calendar, _ = render(course)
    for label, warnings in run_all_checks(course):
        for w in warnings:
            print(f"warning ({path.stem}, {label}): {w}", file=sys.stderr)
    return build_page(course, calendar) + "\n"  # same bytes as render.py's print()


def build_front_page(courses):
    """The bare-domain page: one button per course. `courses` is a list of
    (slug, course dict)."""
    years = sorted({c.get("school_year") for _, c in courses if c.get("school_year")})
    buttons = "\n".join(
        f'    <a class="course" href="/{esc(slug)}/">{esc(c["course"])}'
        f'<span class="course__arrow" aria-hidden="true">&rsaquo;</span></a>'
        for slug, c in courses
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(TEACHER)}'s Math</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,800&family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>
  /* Same look as the course pages (render.py). */
  :root {{ color-scheme: light; --bg: #EEF5F3; --card: #FFFFFF; --ink: #1F2555; --muted: #4A5080; }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--ink); margin: 0; padding: 16px;
    font: 16px/1.45 'Atkinson Hyperlegible', Verdana, sans-serif;
  }}
  main {{ max-width: 480px; margin: 12vh auto 0; }}
  h1 {{ font-family: 'Bricolage Grotesque', sans-serif; font-weight: 800; font-size: 2rem; margin: 0 0 4px; }}
  .subtitle {{ color: var(--muted); font-size: 0.95rem; margin: 0 0 24px; }}
  .courses {{ display: flex; flex-direction: column; gap: 14px; }}
  .course {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 18px 20px; border-radius: 16px; text-decoration: none; color: var(--ink);
    font-size: 1.2rem; font-weight: 700; background: var(--card);
    border: 2px solid var(--ink); box-shadow: 4px 4px 0 var(--ink);
  }}
  .course:hover, .course:focus-visible {{ background: #FFF6C9; }}
  .course__arrow {{ font-size: 1.6rem; line-height: 1; }}
</style>
</head>
<body>
<main>
  <h1>{esc(TEACHER)}'s Math</h1>
  <p class="subtitle">Class calendars{(" &middot; " + esc(", ".join(years))) if years else ""}</p>
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
    slugs = {slug for slug, _ in courses}
    if TEACHER_PATH in slugs:
        print(f"error: courses/{TEACHER_PATH}.json collides with the teacher page", file=sys.stderr)
        return 1
    (out / TEACHER_PATH).mkdir(parents=True, exist_ok=True)
    (out / TEACHER_PATH / "index.html").write_text(lookahead_page.build_page(courses))
    print(f"built /{TEACHER_PATH}/ (teacher look-ahead)", file=sys.stderr)
    slugs.add(TEACHER_PATH)
    for app in sorted(p for p in (ROOT / "apps").glob("*") if p.is_dir()):
        if app.name in slugs:
            print(f"error: apps/{app.name} has the same name as a course or the teacher page", file=sys.stderr)
            return 1
        shutil.copytree(app, out / app.name, dirs_exist_ok=True)
        print(f"built /{app.name}/ (app)", file=sys.stderr)
    return 0


def tests_pass():
    return subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                          cwd=ROOT).returncode == 0


if __name__ == "__main__":
    # Only as a script: the tests themselves call main(), and must not recurse.
    if not tests_pass():
        print("error: tests failed -- not building; the live site stays as it was", file=sys.stderr)
        sys.exit(1)
    sys.exit(main(sys.argv))
