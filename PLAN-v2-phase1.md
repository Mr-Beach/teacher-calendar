# v2 Phase 1 — build plan

How Phase 1 of `SPEC-v2.md` gets built: my colleague signs in, plans in a
week grid, and her students get a page like mine. Read `SPEC-v2.md` first;
this file is the how, not the what. Milestones are in build order, and each
one ends in something that can be checked before the next starts.

**Status (2026-10-08):** plan written; nothing built. Next: M0.

## Decisions

### 1. The Worker runs `engine.py` and `render.py` as they are, with no port

The spec says "port `render()` to the Worker." Instead, the v2 Worker is a
**Python Worker** that imports the same `engine.py`, `render.py`, and
`scripts/lookahead_page.py` this repo already tests. They import only the
standard library (json, re, datetime, pathlib, html), which Python Workers
run, and Python Workers can reach D1.

Why: during the trial my courses (git) and hers (D1) run side by side for
weeks. With one engine, a rule fix (a quiz exception, a Practice Log edge
case) reaches both at once, and the existing tests cover both. A
JavaScript port would be roughly 2,400 lines to keep in step by hand, and
the kind of drift that produces is the kind families notice.

Risk: Python Workers start slower when cold (Cloudflare's own benchmark,
with heavy packages, is about 1 second; ours is standard library only).
M0 measures it. **Fallback**, if M0 finds a blocker: port to TypeScript,
with a test that renders both of my courses in both engines and requires
identical output.

### 2. A separate Worker, in front of the current site

v2 is its own Worker (`v2/`, its own `wrangler.jsonc` and its own Workers
Build), attached by **routes** to `beach-math.com/edit*`, `/api/*`, and one
`/<teacher>/*` route per teacher. Routes run before the current Worker's
custom domain, and everything else (`/math6`, `/math78`, `/teacher`, apps)
still goes to today's Worker, untouched.

Why: my students' pages are never part of the experiment. With two Workers,
a broken v2 deploy can't take down `/math6`, and a failing v2 test can't
block my weekly push. Adding a teacher adds a route line, and only I add
teachers, so that's fine at two or three. www gets the same routes.

### 3. Each calendar is one JSON document in D1, in the course-file shape

A class calendar is stored as the same dict as `courses/math6.json`
(sequence, settings, changes), **minus the school-wide days**, in one row.
Schools, school days, teachers, and ownership are ordinary tables.
Rendering joins them: `school days + this calendar's day changes +
document → course dict → engine.render()`.

Why: every engine function (`render`, `set_day`, `insert_lesson`,
`cut_lesson`, `edit_lesson`, `record_change`, `run_all_checks`) already
takes that dict. Inserting a lesson is a list insert, not renumbering rows.
My courses are about 80 KB each, far under D1's per-row limit.

- **Each save checks the version.** The document has a version number. A
  save sends the version it started from, and a save against a stale
  version is refused ("this calendar changed in another tab; reload"), so
  two open tabs can't overwrite each other.
- **Every save keeps the old document** in a `revisions` table, which gives
  undo, recovery from a bad edit, and a record of who changed what.

### 4. Sign-in: Access decides who gets in; the Worker decides what they can touch

- Add `beach-math.com/edit` and `/api` (and their www versions) to the
  existing Access application that guards `/teacher`, and add her Google
  email to its policy. **Never** use the Worker-level "All traffic" scope
  (see the site-hosting skill; it locked students out on 9/26).
- On every editor and API request, the Worker verifies the
  `Cf-Access-Jwt-Assertion` token (signature against the team's public
  keys, audience, expiry), takes the email from it, looks up the teacher,
  and checks that the teacher owns the calendar. An email or calendar ID
  sent by the page is never trusted. Admin is my email, checked the same
  way.
- M0 finds out whether the Python Worker can get the identity from
  Cloudflare (`ctx.access.getIdentity()`) or must verify the token itself
  through the runtime's Web Crypto.

### 5. The editor sends edits as operations, not documents

The page never sends a whole calendar or a sequence index. It sends an
operation keyed by date ("set the homework on 10/20", "add a lesson on
10/21", "10/23 is no school"), plus the version it was looking at. The
Worker loads the current document, finds the sequence entry on that date
with `engine.place()`, applies the matching engine function, records the
change with `engine.record_change`, renders, and saves. The engine's own
validation (lesson kinds, no stored quizzes, the homework format) then
guards her edits the same way it guards mine.

### 6. Pages are rendered on save, not per visit

A save renders the family page with `render.build_page` and stores the
HTML. A visit serves the stored HTML, which is fast and doesn't run Python
on the busy path. This works because the page bakes in no dates: "today,"
past weeks, and Changed tags are all worked out in the browser (see
`render.py`'s docstring). So no nightly rebuild is needed.

### 7. Her look-ahead is a page in her editor

`/edit/<calendar>/ahead` shows her next 10 class days with gaps flagged
and the checks above them: `lookahead_page.render_course`, scoped to her
calendars. This settles the spec's open question 4. My `/teacher` stays as
it is until my courses move.

### 8. The editor is one HTML file with plain JavaScript

There's no build step, like `apps/`. It's served by the Worker and talks
JSON to `/api`.

## Milestones

### M0: spike (decides 1 and 4)

A throwaway Python Worker on a test route (`beach-math.com/v2-spike*`,
deleted after) that:
- imports `engine` and `render` and serves Math 6 from a bundled JSON;
- reads and writes a D1 table;
- gets the signed-in email, behind a test Access path;
- records cold-start and warm timings (`wrangler tail` or observability).

Done when: each item works, or the blocker is written up and decision 1
switches to the TypeScript port. Also confirm here how Workers Builds
deploys a Python Worker from a subdirectory.

### M1: engine prep, in this repo, nothing live changes

- `render.py`: take the teacher's name from the course (`"teacher"`),
  defaulting to "Mr. Beach".
- Recurring activities (SPEC-v2, "Recurring activities"): generalize the
  Wednesday quiz rule into a `recurring` list on the course: rule (weekday,
  every or every other week, or a monthly position), how it sits on the day
  (whole period, shared, or due date), skip conditions, and link. **A
  course with no `recurring` key behaves exactly as today.**
- Settings: `review_before_test` (on or off) for `check_review_before_test`.
- `engine.template_from(course)`: the "start from my Math 6" copy. It keeps
  codes, titles, kinds, and targets, and drops links, class work, homework,
  changes, and day overrides.
- `engine.course_for_render(school_days, calendar_doc)`: joins school days
  with a calendar's own day changes.
- Tests: golden files of both my courses' rendered pages, which must come
  out byte-identical before and after M1. Plus new tests for each recurring
  rule and skip condition.

### M2: the database and the store layer

- `v2/schema.sql`: `schools`, `school_days`, `teachers` (email, display
  name, slug, school), `calendars` (owner, slug, type, title, version, doc
  JSON, published HTML), `revisions`.
- `v2/store.py`: load a calendar, save it with the version check, list a
  teacher's calendars, and an ownership check. It talks to the database
  through a small adapter, so **the tests run on Python's own `sqlite3`**
  (D1 is SQLite) in CI with no Cloudflare involved.
- `v2/seed.py`: loads the school calendar from `math6.json`'s school days
  and creates my admin row. The school days are loaded once, as the spec
  says, and kept in step by hand until my courses move.

### M3: family pages from the Worker

- `GET /<teacher>/<calendar>` serves the stored page; 404 otherwise.
- A demo calendar (`/demo/math6`, a `template_from` copy) to look at.
- Parity test: importing `math6.json` into the store and rendering it
  produces the same bytes as `build_site.py`.

### M4: sign-in and ownership

- Access paths added (I do this in the dashboard; the Cloudflare
  connection can't change Access).
- The Worker's token check and ownership check on every `/edit` and `/api`
  request.
- Tests: no token is refused, a forged or expired token is refused, a
  token for another audience is refused, and a teacher asking for another
  teacher's calendar is refused (404, so the request doesn't reveal that
  it exists). Then the curl checks from the site-hosting skill: student
  pages 200, `/teacher` 302.

### M5: the editor, read-only

- `/edit` lists her calendars. `/edit/<calendar>` shows the week grid:
  1, 2, or 4 weeks, columns are class days, rows are lesson, homework, and
  link (class work only if her calendar turns it on). Quizzes and other
  recurring activities show as computed, not editable cells.
- `/edit/<calendar>/ahead` is the look-ahead (decision 7).

### M6: editing

Each operation is one API call, and each save re-renders the page, logs
the change, and keeps a revision.
- Edit a cell: lesson title, I-can target, homework (text, due date,
  link), lesson link, kind (lesson, test, or project).
- Fill an empty day: adds the next lesson to the sequence at that point.
- Mark a day "no school" or turn it back on, with a note. This is a day
  change, as `set_day` makes, so later lessons re-flow.
- Copy last week: its lessons are added again as the next lessons.
- Paste a table from Word or Google Sheets, with the pasted columns mapped
  onto the rows. It's shown highlighted and unsaved until she keeps it.
- Pick from a list: what the row has held before, and the next lesson in
  the sequence.
- "Small fix" checkbox on a save, as in `record_change(small_fix=True)`.
- Undo the last save (from `revisions`).

### M7: settings

Her recurring activities (add, edit, turn off on one day), review day
before tests, display name, and class title. Starting a new calendar from
a blank year or from my Math 6 template.

### M8: ready for the trial

- The spec's "Before building" items are done: the admin heads-up and the
  agreement with her.
- I add her: teacher row, route line, Access email.
- A one-page "how to" for her, written for someone who never sees what's
  behind it.
- Backups: confirm D1's point-in-time restore covers us, and the
  `revisions` table covers a single bad edit.
- Phase 1 is done when she publishes two weeks to her students without my
  help (spec, "Definition of done").

## Testing

- Every engine change keeps my two courses' pages byte-identical (golden
  files) unless the change means to alter them.
- The store, the operations, and the ownership checks are tested on
  `sqlite3` in the existing GitHub Actions run.
- One end-to-end check on a preview deploy before each live v2 deploy:
  sign in, make an edit, see the family page change.
- v2 tests never gate my v1 build, and the reverse holds too (decision 2).
  Engine tests run in both.

## Not in Phase 1

Phase 2's buttons (lost day with preview, add or remove a day), the change
nudges, the "save changes together" grouping, drafts (open question 1),
anything preschool (Phase 1b), and anything AI (Phase 3).
