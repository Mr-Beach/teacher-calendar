# teacher-calendar

## What this repo is for

Aaron teaches from district pacing guides. `courses/math6.json` is the
single source of truth for one course's calendar; `docs/index.html` is a
generated, published page students read from Schoology. Losing a day
(assembly, snow day, a lesson running long) re-flows every lesson after it —
the whole point of this tool is that Aaron never re-derives that by hand.
Background: `SPEC.md` (v1 scope and hard constraints), `PLANNING.md` (the
domain rules — day types, lesson kinds, quiz/test placement, the day-budget
model). **Read PLANNING.md before making any edit** — it has the vocabulary
and rules this file assumes.

## The workflow this file exists to support

Aaron doesn't want to hand-edit JSON or think in this schema. He wants to
describe what happened or what he wants to do — "we lost Tuesday to an
assembly," "cut the second review day," "add a 3-Act before Topic 6" — in
his own words, in a Claude Code session (local, or claude.ai/code from his
phone with no laptop involved), and have the session do the rest: translate
that into the right edit(s), apply PLANNING.md's rules, and report back what
changed in plain language — dates, what moved — not schema fields.

If what he's asking for is ambiguous (which lesson exactly, which date),
ask. If he says "I need a day" without saying what to cut, use PLANNING.md's
cut-order preference (Topic Openers, then 3-Act tasks, then second days on
lessons students already have) rather than asking him to pick from the raw
sequence.

## How to make an edit

1. Read `courses/math6.json` (currently the only course).
2. Before editing, capture `engine.render(course)` — you'll diff against it
   after, via `engine.diff_impact`.
3. Use `engine.py`'s edit functions. Don't hand-write JSON mutations:
   - `engine.set_day(course, date, type=..., note=...)` — change a school
     day's type/note. This is how a day is spent (Instruction → No
     School/Other) or earned back (Flex → Instruction). Omit an argument to
     leave it unchanged; pass `note=None` explicitly to clear a note.
   - `engine.cut_lesson(course, index)` — remove a sequence entry (an
     "earn").
   - `engine.insert_lesson(course, index, lesson)` — add a sequence entry (a
     "spend"). `lesson` needs at least `district_title`; `kind` defaults to
     `"Lesson"`.
   - `engine.edit_lesson(course, index, **fields)` — correct content
     (district_title, homework, target, classwork, link) on an existing
     entry. No budget effect.
   - The tile/detail title is always `lesson_code` + `district_title` —
     never `target` or `classwork`. If the district's own title is opaque
     (e.g. a generic "Topic N Opener"), write a clearer `district_title`
     rather than relying on `target` to stand in for it. `target` (the
     day's I-can statement) and `classwork` (the activity, with its point
     value) are detail-only — shown only when a student clicks the day.
   - `link` (on `insert_lesson`/`edit_lesson`) is an optional URL to a
     student-facing resource for that day — **not** a lesson-builder deck
     (Aaron isn't sharing those with students). The current plan is a
     Savvas key-concept excerpt for the lesson, shared from OneDrive (his
     students are already on Outlook accounts, so no extra access setup);
     hand the share link to `engine.edit_lesson(course, index, link=...)`.
     A relative path to a file committed under `docs/` also works for
     anything simple enough to keep in this repo. Renders as a button on
     the day's detail popup. Leave it unset/`None` for a day with nothing
     to attach.
   - Never hand-insert a `"Quiz"`-kind entry — quizzes are computed by
     `render()`, never stored (`insert_lesson` rejects this; see `engine.py`'s
     module docstring for why).
   - Find the right index/date by reading the current rendered calendar or
     the raw JSON — don't guess offsets.
4. Write the course dict back with `json.dump(course, f, indent=2)` plus a
   trailing newline, matching the file's existing style.
5. Render locally so you can see the result before committing:
   `python3 render.py courses/math6.json > docs/index.html`
6. Run `engine.run_all_checks(course)` (test placement, unexplained
   closures, lesson shortfall) and report any warning as an editorial
   question — these are deliberately not auto-fixed (see each check's
   docstring for why).
7. Report the impact using `engine.diff_impact(course, before_calendar,
   before_leftover)` in Aaron's terms — what date things start shifting
   from, whether the leftover/shortfall count changed — not a raw diff.
8. Show Aaron the summary and get a go-ahead before committing. Once
   confirmed, commit `courses/math6.json` and the re-rendered
   `docs/index.html`, and push to `main`. This repo is single-user and the
   whole point is removing friction from this step — but it's a live
   calendar his students read from, so confirm the impact with him first,
   every time.

## Open issue: district firewall blocks github.io (delete this section once resolved)

As of 2026-09-22, the district's Fortinet web filter blocks `*.github.io`
at the network level for staff and students alike (IT, verbatim: "we block
GitHub at the firewall level for all staff for security reasons" — not
specific to this site, the whole domain/category). The `git push` → Pages
pipeline above still works exactly as documented; the problem is that the
published URL is unreachable from the school network, so the link posted
in Schoology is dead for anyone on that WiFi.

Ruled out:
- **Paste the rendered HTML into a Schoology Page / SharePoint page.**
  `docs/index.html` is JS-driven — the detail popup (`<dialog>` +
  `showModal()`), the "today" hero card, and all click handling run from
  the `<script>` block at the end of the file. Rich-text page editors strip
  `<script>` on save as standard XSS hygiene, which would silently kill the
  popups and the today-highlight, leaving a static grid. Not confirmed
  against this specific Schoology instance, but not worth building around
  without testing first.
- **Upload the file to SharePoint/OneDrive and link to it.** Both serve an
  uploaded `.html` file as a forced download rather than rendering it
  inline with script execution — standard behavior for those services, not
  a misconfiguration to request a fix for.

Leading candidate, not yet actioned — needs Aaron:
- **Give GitHub Pages a custom domain.** `docs/` currently has no `CNAME`
  file; the site is on the bare `github.io` domain. Pointing a domain Aaron
  owns at GitHub Pages (a `docs/CNAME` file + a DNS record + enabling it in
  the repo's Pages settings) changes zero code and keeps full JS
  interactivity — it just stops being hostnamed `github.io`, which likely
  sidesteps a hostname/category block that matches IT's own description.
  Needs Aaron to pick/buy a domain and set DNS. Untested — would still fail
  if the filter blocks GitHub's IP ranges rather than the hostname, but
  hostname/category blocking is the far more common implementation and
  matches what IT described.

Fallback if the custom domain is also blocked: host the identical static
file on a different static host (Cloudflare Pages, Netlify, Firebase
Hosting) and have Aaron test reachability from the school network before
committing to one.

## Hard constraints (from SPEC.md — true at every version, not just v1)

- No student names, grades, or student-identifying data. Ever.
- No accounts, no database — `courses/*.json` is the only state.
- Single course, single teacher, single user (Aaron).
