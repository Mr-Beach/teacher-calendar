# teacher-calendar

## What this repo is for

Aaron teaches from district pacing guides. `courses/math6.json` is the
single source of truth for one course's calendar. The published page
students read from Schoology is **beach-math.com**, hosted on Cloudflare
Workers, auto-built from `courses/math6.json` on every push to `main` (see
"Hosting" below) — it is not `docs/index.html`, which is a static redirect
stub kept only for old bookmarks pointing at the original `github.io` URL.
Losing a day
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
5. Render locally so you can see the result before committing — write to a
   scratch path, **not** `docs/index.html` (that file is a fixed redirect
   stub now; see "Hosting" below, do not overwrite or commit over it):
   `python3 render.py courses/math6.json > /tmp/preview.html`
6. Run `engine.run_all_checks(course)` (test placement, unexplained
   closures, lesson shortfall) and report any warning as an editorial
   question — these are deliberately not auto-fixed (see each check's
   docstring for why).
7. Report the impact using `engine.diff_impact(course, before_calendar,
   before_leftover)` in Aaron's terms — what date things start shifting
   from, whether the leftover/shortfall count changed — not a raw diff.
8. Show Aaron the summary and get a go-ahead before committing. Once
   confirmed, commit `courses/math6.json` (only — leave `docs/index.html`
   alone) and push to `main`. This repo is single-user and the whole point
   is removing friction from this step — but it's a live calendar his
   students read from, so confirm the impact with him first, every time.
   The push alone republishes the site — see "Hosting" below.

## Hosting

The published site is **beach-math.com**, served by a Cloudflare Worker
(static assets), not GitHub Pages. This exists because the district's
Fortinet web filter blocks `*.github.io` at the network level for staff and
students (IT, verbatim: "we block GitHub at the firewall level for all
staff for security reasons"); moving the actual serving off GitHub's
infrastructure entirely (not just the hostname) removes any risk that the
filter is blocking GitHub's IP ranges rather than just the hostname.
Confirmed 2026-09-23 via direct DNS/header check: `beach-math.com` and
`www.beach-math.com` resolve to Cloudflare IPs and respond with
`server: cloudflare` — nothing in the serving path touches GitHub anymore.

- **Auto-deploy**: a Cloudflare Workers Builds project (`teacher-calendar`,
  in Aaron's Cloudflare account) is connected via the Cloudflare GitHub App
  to `Mr-Beach/teacher-calendar`, scoped to that repo only. Every push to
  `main` triggers: build command `python3 render.py courses/math6.json >
  docs/index.html` (run in Cloudflare's own ephemeral checkout — this
  never gets committed back to git), then `npx wrangler deploy`. No
  `wrangler.jsonc` is committed to this repo; Cloudflare's dashboard
  manages the Worker's build/deploy config directly.
- **Domain**: `beach-math.com` was registered through Cloudflare Registrar
  and its DNS zone lives on Cloudflare. `beach-math.com` and
  `www.beach-math.com` are attached to the Worker as Custom Domains
  (Worker's **Domains** tab), which is what makes Cloudflare own and manage
  their DNS records and TLS certs — there are no manually-managed DNS
  records for this site.
- **`docs/index.html` in this repo** is now a small static redirect stub
  (meta-refresh + link to `beach-math.com`) so `mr-beach.github.io` — the
  original address, still enabled via GitHub Pages — keeps working for
  anyone with it bookmarked, instead of going dead or serving a stale
  calendar. It is committed once and should never be overwritten by the
  normal edit workflow (see step 5 above). `docs/CNAME` was removed since
  GitHub Pages no longer owns the custom domain.
- **If this ever needs rebuilding from scratch**: Cloudflare dashboard →
  Workers & Pages → `teacher-calendar` → Settings → Builds, for build/
  deploy commands and the GitHub connection; → Domains tab, for the custom
  domain attachments.

## Hard constraints (from SPEC.md — true at every version, not just v1)

- No student names, grades, or student-identifying data. Ever.
- No accounts, no database — `courses/*.json` is the only state.
- Single course, single teacher, single user (Aaron).
