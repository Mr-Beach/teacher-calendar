# v2 Phase 1 — build plan

How Phase 1 of `SPEC-v2.md` gets built: my colleague signs in, plans in a
week grid, and her students get a page like mine. Read `SPEC-v2.md` first;
this file is the how, not the what. Milestones are in build order, and each
one ends in something that can be checked before the next starts.

**Status (2026-10-09):** M0 through M3 done (see "M0 results" through
"M3 results"). M4 in progress ("M4 progress"). Color presets are in M1 and M7, my own trial run is
M7b, and layout choice is in "Later" (end of this file).

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
switches to the TypeScript port.

**M0 results (2026-10-08).** Everything worked, so no port is needed.
- `engine.py`, `render.py`, `lookahead.py`, and `lookahead_page.py` ran
  unchanged in a Python Worker (Python 3.14 runtime). The Math 6 page it
  served was **byte-identical** to `python3 render.py courses/math6.json`,
  apart from `print()`'s trailing newline. The look-ahead page rendered
  too.
- Timing, measured from outside with curl: **0.85–1.5 s cold** (a fresh
  Worker copy; Cloudflare measured startup at 875 ms) and **0.15–0.33 s
  warm**, each including a full-year render and checks. Traffic this low
  sees many cold starts, which is why decision 6 serves stored pages.
- D1: the 77 KB Math 6 document saved and loaded back equal.
- Access: on a path added to the existing "beach-math.com" Access app,
  both `self.ctx.access.getIdentity()` and the Worker's own token check
  (RS256 signature with Web Crypto through Pyodide, audience, issuer,
  expiry) returned my email. A token with a tampered signature was
  refused. **Use the Worker's own check** as the gate, since it pins this
  app's audience whatever way Access is attached.
- Gotchas for the real build:
  - The current runtime expects the Workers SDK to be bundled by
    `pywrangler` (workers-py ≥ 1.9). The spike used the
    `disable_python_external_sdk` flag instead. The real Worker should use
    `uv` + `pywrangler`.
  - No randomness or other entropy at module top level; the runtime
    refuses it at startup. Generate IDs inside a request.
  - Don't parse the path by hand; use `urllib.parse.urlsplit(request.url)`.
- **Not yet checked; moved to M3:** deploying a Python Worker from `v2/`
  through Workers Builds, and whether its build image has `uv`.

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
- Color presets: `render.py` sets its colors as tokens at the top of the
  page, but about a dozen colors are still written out further down. Move
  those into tokens, then add a `theme` setting on the course that picks
  one of a few named presets. A course with no `theme` gets today's colors.
  Each preset is checked for readability before it ships: body text 4.5:1
  against its background, and quizzes and tests told apart by lightness,
  not hue alone, as today. They're presets, not a free color picker, so
  no teacher can make a page students can't read.
- Tests: golden files of both my courses' rendered pages, which must come
  out byte-identical before and after M1. Plus new tests for each recurring
  rule and skip condition.

**M1 results (2026-10-08).** Done; 115 tests pass (85 before M1).
- `tests/test_golden.py` freezes both courses (as of 10/8) and their
  pages and calendars. The engine changes left both byte-identical, and
  every check's warnings matched the old engine's. The color tokens
  changed the page's CSS text but not one color on it; the golden pages
  were regenerated once, on purpose, for that.
- **The quiz rule is settings** (`engine.quiz_rule`, a course's optional
  `quiz_rule`): on or off, weekday, every week or every other, full period
  or shared with the lesson, which skips apply, link, and whether test
  self-grading takes the quiz slot. v1's `quiz_rhythm_start` and
  `quiz_link` still work, so my course files needed no change.
- **Narrowed from the plan:** the spec's other recurring activities
  aren't built. The quiz is the one the colleague needs, and the page
  already knows how to show it. Next in line is **catch-up days** (see
  "Later"). A homework check stays off the calendar: it's a classroom
  routine, and the page already shows what's due.
- `review_before_test`, `teacher`, `theme` (presets `teal` (mine),
  `plum`, `forest`, `slate`; `tests/test_themes.py` checks every text and
  fill pair against WCAG contrast), `template_from`, `course_for_render`,
  `split_course` (the reverse, for importing a course file), and
  `school_record` (the closures every course agrees on).

### M2: the database and the store layer

- `v2/schema.sql`: `schools`, `school_days`, `teachers` (email, display
  name, slug, school), `calendars` (owner, slug, type, title, version, doc
  JSON, published HTML), `revisions`.
- `v2/store.py`: load a calendar, save it with the version check, list a
  teacher's calendars, and an ownership check. It talks to the database
  through a small adapter, so **the tests run on Python's own `sqlite3`**
  (D1 is SQLite) in CI with no Cloudflare involved.
- `v2/seed.py`: loads the school calendar and creates my admin row. The
  school days are loaded once, as the spec says, and kept in step by hand
  until my courses move.
- **What's school-wide (settled 10/8).** The school record holds only
  closures: `engine.school_record(math6, math78)` takes the 37 No School
  days both courses agree on (they agree on every one) and makes every
  other day a plain class day. Flex, testing, and "Other" days differ by
  course, so each calendar keeps its own as day changes. Each of my
  courses is then the school record plus its own changes
  (`split_course`), tested to round-trip exactly.

**M2 results (2026-10-09).** Done; 10 tests in `v2/tests` (`sqlite3`).
- `v2/schema.sql` as planned. `revisions` keeps **every** saved version,
  the current one included, each with who saved it and when, rather
  than only the replaced one: undo is "save revision N-1 as new", and
  who-changed-what is one table.
- `v2/store.py` speaks course dicts, not documents: `load_calendar`
  joins the school's days with the calendar's own changes, and
  `save_calendar` splits them apart again, so the Worker only ever
  calls engine functions. Every call starts from the signed-in
  teacher's row, and another teacher's calendar is `None` /
  `LookupError`, never a different error (the 404 in M4). A save and
  its revision are one batch; a stale version changes nothing.
- The adapter is D1's shape (`all`, `first`, `run`, `batch`), async
  because D1 is. Only the `sqlite3` one exists; **the D1 adapter is
  written in M3**, with the Worker, where it can be run.
- `v2/seed.py` prints SQL for `wrangler d1 execute`: the school record
  (37 closures), and my row as teacher (`beach`) and admin. My email is
  an argument, since the repo is public. Running it again updates the
  school's days in place, which is how a snow day entered in
  `courses/*.json` reaches D1 during the trial.
- Teacher slugs can't take an existing path (`RESERVED_SLUGS`; a test
  checks it covers every course and app).
- v2 tests are their own GitHub Actions job, not part of the
  Cloudflare build's test run (decision 2).
- **Not done yet: no D1 database exists.** It's created, given the
  schema, and seeded in M3, alongside the Worker that binds it.

### M3: family pages from the Worker

- Set up `v2/` as its own Workers Build (root directory `v2/`, deploy
  with `pywrangler`), and confirm a push deploys it without touching the
  current site's build.
- `GET /<teacher>/<calendar>` serves the stored page; 404 otherwise.
- A demo calendar (`/demo/math6`, a `template_from` copy) to look at.
- Parity test: importing `math6.json` into the store and rendering it
  produces the same bytes as `build_site.py`.

**M3 results (2026-10-09).** Done; 14 tests in `v2/tests`.
- **Live:** `beach-math.com/demo/math6` (and www) is served by the
  `teacher-calendar-v2` Worker from the `teacher-calendar-v2` D1 database.
  The routes are `/demo/*` only; `/`, `/math6`, `/math78`, apps, and
  `/teacher` (302 to sign-in) checked unchanged after deploy. A cold
  start served the 315 KB demo page in about 1.3-1.9 s, warm 0.2-0.3 s.
- **Workers Build: connected 10/9, in M4.** Through M3 it wasn't: a
  push built only v1 (no trigger, no builds ever), so M3's deploys were
  by hand. Now it's its own build in the dashboard, root directory
  `v2`, branch `main`, deploy command `pip install uv && uv run pywrangler deploy`
  (the build image's Python has pip; `uv` isn't listed as preinstalled),
  watch paths `v2/*`, `engine.py`, `render.py`. `v2/wrangler.jsonc`'s
  build step copies the repo root's `engine.py` and `render.py` into
  `v2/src/` (git-ignored there), so both Workers run one engine.
- `store.py` moved to `v2/src/` with `entry.py` and `d1.py`. The Workers
  SDK wraps the D1 binding and converts None/null and rows to dicts
  itself, so `d1.py` is a thin reshape. **Only reads have run on D1;**
  `batch` (every save) first runs in M6.
- **Pages render on save, and also on a visit when none is stored.**
  Decision 6 missed that a re-seed (a snow day) changes school days
  without any save, so seed.py now clears the school's stored pages and
  each is rendered again, and stored, on its next visit. That's also how
  the seeded demo gets its page.
- The teacher's name on the page comes from her `teachers` row unless
  the calendar names one itself (the demo shows "Demo Teacher").
- Parity: Math 6 through the store renders the same bytes as
  `build_site.py`; the demo page served by the Worker matched the
  CPython render byte for byte.
- The seed loads with `wrangler d1 execute --command`; `--file` failed
  on D1's import API with an authentication error (see `v2/seed.py`).
- The demo teacher's email is `demo@beach-math.invalid`, so no one can
  sign in as her. The school is recorded as "Mr. Beach's school"
  (families never see it).

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

**M4 progress (2026-10-09).** The Worker's half is written; 30 tests in
`v2/tests` (16 new in `test_access.py`). Deployed 10/9 by hand (version
`9afa21e1`), since v2 has no Workers Build yet (see M3 results).
- `v2/src/access.py` checks the token itself: RS256 in plain Python (no
  Web Crypto), so the tests run the Worker's own code on CPython. Keys
  are fetched from the team's certs and kept an hour; an unknown key ID
  refetches at most every 5 minutes.
- `v2/src/app.py` holds the routes, outside the Worker shell
  (`entry.py`), so tests run them on sqlite. Everything under `/edit`
  and `/api` checks the token and the teacher before the path, so every
  refusal is the same 403; another teacher's calendar is the same 404 as
  a missing one. For now `/edit` lists her calendars and `/api/calendars`
  (and `/api/calendars/<slug>`) returns them as JSON. M5 replaces `/edit`.
- `wrangler.jsonc` routes `/edit`, `/edit/*`, `/api/*` (both hosts) to
  this Worker, and has `TEAM_DOMAIN` and `ACCESS_AUD`. The AUD is the
  live "beach-math.com" Access app's, checked on 10/9.
- **Curl checks after deploy (10/9):** `/`, `/math6/`, `/math78/`,
  `/tech-quest/`, `/demo/math6` 200 on both hosts; `/teacher` 302 to
  sign-in; `/edit`, `/edit/math6`, `/api/calendars` 403 with no token or
  a junk one, `cache-control: private, no-store`.
- **Left:** add `beach-math.com/edit`, `beach-math.com/api` and their www
  versions to that Access app (dashboard), then sign in at /edit and see
  "Your calendars". Then M4 is done.

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

Her quiz rule (on or off, weekday, every or every other week, full or
shared; turn it off or move it on one day), review day before tests,
display name, and class title.

**Starting a calendar: start from one that exists.** The first screen
asks what she teaches and fills the year from any existing calendar, at
first Math 6 or Math 7/8 Compacted (the district's own pacing guides).
`template_from(source, school_days)` copies its lessons and targets and
its Flex, testing, and "Other" days, and leaves behind my links, homework,
quiz changes, and class-day notes. Closures come from the school record,
so she never enters holidays. "Blank year" is the last choice; uploading
the district calendar instead is in "Later". Picking a color preset, shown as
a small preview of her own page in each one.

### M7b: my trial run

Before she sees it, I set up a calendar from scratch myself, like any
teacher: sign in, start a calendar (blank, then from the Math 6 copy),
pick colors, plan two weeks in the grid, and check the page families
would see. It's a practice calendar (e.g. `beach-math.com/beach/practice`).
My students never see it, and `/math6` and `/math78` stay on git. My Google
account gets a teacher row as well as admin. Anything confusing or slow
gets fixed before M8.

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

## Later: catch-up days

The first recurring activity after the quiz, built after the trial. A
catch-up day is planned slack: a monthly day (e.g. the last Friday) that
lessons flow past, like a Flex day. Its point is what happens when a day
is lost: the editor offers "use your next catch-up day?", and taking it
earns the lost day back without pushing every lesson later. Per SPEC-v2's
"right amount of control", it's offered when there's a reason, after a
lost day or when a teacher's year has no Flex days, not as a setup
option. It needs page design first (how a catch-up day looks to
students).

## Later: setting up from a document, and more curricula

- **Upload the district calendar or pacing guide** and have it fill the
  school days or the sequence. That's reading a PDF or photo into the
  grid, which is Phase 3's "fill from a source", and it lands the same
  way: highlighted, unsaved, kept or cleared.
- **A wider curriculum list.** Publishers' lesson orders aren't freely
  available as data, so the list can't be bought or scraped. It grows
  from teachers instead: a calendar a teacher has finished can become a
  starting sequence for others, with her permission (`template_from`
  already strips anything tied to her accounts). An upload (above) is the
  other way in.

## Later: a choice of page layout

A teacher picking her page's layout at setup, not just its colors. The
three candidates are the 10/3 designs in the "Calendar Redesign Options"
canvas (https://claude.ai/artifact/88si4F4dvfJodcKVu1C12Z): **A · Planner**
(what's live), **B · Week strip**, and **C · Wall calendar**. Not in Phase
1, because each layout is a whole page to build and test on phone and
laptop. Every page feature (homework due dates, Practice Log checklists,
Changed tags, the today card) has to work in each one, and every later
feature then gets built more than once.

When it happens: each layout has to give the same information with a
different style, and has to be airtight. I'll test each one with Claude
before any teacher can pick it. Let the colleague's trial say which layout
is worth building first. The bigger question behind it, that different
kinds of calendar may want different styles, is already partly in the
design: a preschool calendar gets its own page.
