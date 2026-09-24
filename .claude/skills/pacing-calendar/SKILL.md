---
name: pacing-calendar
description: Update Aaron's Math 6 or Math 7/8 Compacted pacing calendar (courses/math6.json, courses/math78.json) and republish beach-math.com. Use whenever he's updating the pacing calendar, moving a test or quiz, adding or splitting a lesson, adding/losing a week or a day, re-flowing lessons after a lost day, or hands over a week of lesson entries (date, lesson, target, class work, homework, notes) to enter.
---

# Pacing calendar updates

Background this assumes: `SPEC.md` (hard constraints), `PLANNING.md` (day
types, lesson kinds, quiz rules, the day-budget model), `CLAUDE.md` (the
edit-function workflow). This file is the operational playbook for one
recurring job: turning a week Aaron hands over into a committed, re-flowed
calendar. Read PLANNING.md too if a specific rule is unclear — this doesn't
restate all of it.

## Source of truth

One file per course, and the only state: `courses/math6.json` (Math 6,
beach-math.com/math6) and `courses/math78.json` (Math 7/8 Compacted,
beach-math.com/math78). If Aaron doesn't say which class, ask. Two arrays:

`school_days` — one entry per calendar day, pinned to that date:
```json
{
  "date": "2026-09-23",
  "weekday": "Wed",
  "type": "Instruction",
  "note": "No quiz this week — the Topic 2 summative is four days out."
}
```
`type` is one of `Instruction` / `Flex` / `Testing` / `No School` / `Other`.
`note` is a plain string or `null` and is **always rendered to students** —
never a note to self (SPEC.md).

`sequence` — an ordered list of lessons with **no dates of their own**:
```json
{
  "topic": "2",
  "lesson_code": "2.6",
  "district_title": "Find Distances on the Coordinate Plane",
  "kind": "Lesson",
  "homework": [
    {"text": "Topic 2 study guide", "due": "2026-09-29"},
    {"text": "Quiz redo on Schoology (up to 3 attempts)", "due": "2026-09-30"}
  ],
  "link": "https://districtlms.seattleschools.org/course/8516312158/materials?f=1039067898",
  "target": "I can use absolute value to find the distance between two points that share an x- or y-coordinate.",
  "classwork": "Explore and Share (textbook p. 95); workbook pp. 100–102, problems 9–11, 18–21, 23, 29."
}
```
`kind` is one of `Lesson` / `Opener` / `Quiz` / `Test` / `3-Act` — but never
hand-insert `Quiz` (see below). `homework` is a list of the assignments
**given that day** — `{"text", "due"}`, `due` a fixed `YYYY-MM-DD` date —
`null` (not `[]`) when nothing's assigned; see "Input format" below. `link` is an
optional URL to a student resource (Drive/OneDrive link shared "anyone with
the link", or a path under `docs/`), rendered as a button on that day's
detail popup.

**The tile/detail title is always `lesson_code` + `district_title` (the code stored as `1.6`, shown as `T1L6` to match Schoology) — never
`target` or `classwork`.** `target` (the day's I-can statement) and
`classwork` (the activity, with its point value if any) are detail-only:
shown in the popup when a student clicks the day, never on the tile. If the
district's own title is opaque (a generic "Topic N Opener", "Topic N
Assessment"), write a clearer `district_title` instead of relying on
`target` to stand in for it — that's what got this wrong for the week of
9/21 (see below).

Edit only through `engine.py`'s functions (`set_day`, `cut_lesson`,
`insert_lesson`, `edit_lesson`) — never hand-write JSON mutations. Find
indices by reading the live file, not from memory or an earlier read in the
conversation — it changes underneath you.

## Generated — never hand-edit

The published page, produced by `render.py`. It is rendered by Cloudflare
Workers Builds in its own checkout on every push to `main` and served at
beach-math.com — never committed to git (CLAUDE.md, "Hosting").
**`docs/index.html` is not the calendar**: it's a fixed redirect stub for
old github.io bookmarks. Never render into it, overwrite it, or commit it.

## Repo vs. any spreadsheet — who wins

The course file, always. The original Excel workbook was imported once,
proved unreliable, and has been discarded along with its import script
(see SPEC.md, "Import"). Never recreate it or reconcile the repo toward a
spreadsheet. To check a fact against an outside source, use the district's
own documents (at-a-Glance guide, sample calendars, SPS school calendar).

## How re-flow actually works

- Sequence entries get a date purely by position — `render()` lays them
  onto `Instruction` days in order. Cutting or inserting anywhere in the
  sequence shifts every entry after it, forward or back, by that many days.
- `school_days` entries are what's actually pinned to a date (`type`,
  `note`). Spending or earning a day means changing a day's type
  (`set_day`), not touching the sequence.
- Quizzes are never stored — computed fresh every render from the Wednesday
  rule plus its exceptions (a test lands that week, first week back from a
  break of 5+ days, the day before Thanksgiving). **A school-day `note`
  containing the word "quiz" (any case) is a manual override that suppresses
  that Wednesday's auto-quiz.** This is the same mechanism PLANNING.md calls
  "pairing" — use it deliberately whenever a week needs no quiz for a reason
  outside the three documented exceptions (e.g. a summative four days out),
  not just for literal pairing.
- Before anything is committed, show Aaron: `engine.diff_impact()` (first
  date that starts differing, leftover-lesson count before/after) and every
  `engine.run_all_checks()` warning (test placement, unexplained closures,
  lesson shortfall). None of these are auto-fixed — surface them as
  editorial questions even when "push everything back" was already the
  instruction. A day-budget shift being intentional doesn't make its
  downstream effects (a later test landing on a Monday, a shortfall/leftover
  at year's end) not worth reporting.

## Build & publish

1. `python3 render.py courses/<course>.json > /tmp/preview.html` — render to
   a scratch path (never `docs/index.html`) and look it over before
   showing Aaron anything.
2. `engine.run_all_checks(course)` — report any warning.
3. Get Aaron's go-ahead on the content — every time, live calendar, no
   exceptions — before committing.
4. Commit the edited course file only, directly on `main`, then push to
   `origin/main` — that's the actual publish step (Cloudflare Workers
   Builds renders every course and deploys to beach-math.com/<course>). Confirm that push
   explicitly, separately from the content go-ahead in step 3.

## Input format Aaron hands over

A week as a plain-text block, one entry per school day: date, lesson name, a
`Target` (I-can statement), `Class work` (activity + point value),
`Homework`, and sometimes `Note` / `Extension` / `Warm up`. Map `Target` →
`target` and `Class work` (plus any `Extension`/`Warm up`) → `classwork`,
terse and matching the file's existing style, not transcribed in full —
both are detail-only, never the tile title (see above). `Homework` →
`homework`, a **list** of `{"text": ..., "due": "YYYY-MM-DD"}` — one item
per assignment **given that day**, stored only on that day. Never repeat
it on later days (no "(continued)" entries): the page shows it on the day
it's assigned, as a separate "Due" badge on its due date, and in the hero
card's "coming due" list until then. Keep the due date out of `text`.
Resolve "due Monday" / "due Wed 10/7" to an actual date from the day it's
assigned, and ask if it's ambiguous. The due date is a fixed calendar date
(how much time students get, not tied to content) — a lost day that shifts
lessons never moves it; `run_all_checks` warns if a shift leaves one due on
or before its assigned day, or on a no-school day. Homework can be *due* on
a quiz day but never *assigned* on one. Collect every `Homework:` line in a
day's block into the list, one item per line; if a single line contains a
semicolon, split it too. A line that only restates an assignment given
earlier ("study guide" on the review day) isn't a new item — drop it.
Finishing class work that wasn't done in class counts as homework like
anything else — give it a due date the way any other assignment gets one.
`homework` is `null` (not an empty list) for a day with nothing assigned. Worked example, verbatim,
from the
week-of-9/21/2026 update:

```
Mon 9/21 - Topic 2 Lesson 4: The Coordinate Plane, Day 1
  Target: I can name the parts of the coordinate plane (x-axis,
    y-axis, origin, quadrants) and plot ordered pairs with negative
    coordinates.
  Class work: Sailboat coordinate graphing (50 points)
  Homework: finish Sailboat if not done
  Note: Topic 2 study guide distributed today.

Tue 9/22 - Topic 2 Lesson 4: The Coordinate Plane, Day 2
  Target: I can name the coordinates of a point on a graph and
    identify which quadrant it falls in.
  Class work: Owl coordinate graphing (96 points)
  Homework: Topic 2 Lesson 4 Practice
  Extension: Desmos graphing activity for early finishers

Wed 9/23 - Topic 2 Lesson 5: Distances on the Coordinate Plane, Day 1
  Target: I can find the distance between two points that share an
    x-coordinate or a y-coordinate.
  Homework: none
  Note: no weekly quiz this week, summative is 4 days out.
    Rocket coordinate graphing (133 points) available as optional
    take-home.

Thu 9/24 - Topic 2 Lesson 5: Distances, Day 2 (notes and work time)
  Target: I can use absolute value to find distances on the
    coordinate plane, including with decimal and fraction
    coordinates.
  Warm up (10 min): axes-choice task, what negative values mean on
    each axis in context.
  Homework: workbook pages 103-104, problems 10-21

Fri 9/25 - Topic 2 Lesson 6: Polygons on the Coordinate Plane
  Target: I can plot a polygon given the coordinates of its
    vertices and connect them in order.
  Homework: workbook page 108, problems 1-6, due Monday
  Note: perimeter and area of figures in the plane moved to after
    the summative.

Mon 9/28 - Topic 2 Review
  Target: I can apply everything in Topic 2 to unfamiliar problems.
  Note: Retrieval practice, not reteach. Includes one context-graph item
    requiring written explanations.
  Homework: study guide

Tue 9/29 - Topic 2 Summative Assessment
  Note: Covers 6.NS.C.5, 6.NS.C.6c, 6.NS.C.7, 6.NS.C.8, 6.G.A.3
  Homework: none
```

## Hard constraint

No student names, grades, or other student-identifying data in this repo
or its output. Ever — true at every version, not a v1-only cut (SPEC.md).

## What I got wrong / had to figure out this session

- **Teacher-facing planning color isn't a `note`.** The input above included
  "perimeter and area moved to after the summative" and "retrieval practice,
  not reteach" — both read like a note, but SPEC.md defines `note` as always
  rendered and always student-facing. Dropped both rather than store them;
  only genuinely student-facing lines (testing windows, "no quiz this week,"
  "study guide distributed today") belong there. When in doubt, ask rather
  than guess which way a borderline line falls.
- **Lesson codes aren't always given.** "Topic 2 Lesson 6" is Aaron's own
  within-topic numbering, not a schema field. Inferred the district
  `lesson_code` (`2.7`) from the topic's existing numbering gap (2.5, 2.6 →
  next is 2.7) rather than leaving it null — but flagged it explicitly as an
  inference, not something sourced from the input. Don't silently guess a
  code without saying so. **This inference turned out wrong**: Aaron's own
  "Topic 2 Lesson N" numbering doesn't reliably track Savvas's `lesson_code`
  (it was off by one), so the inferred `2.7` became a standalone "Draw
  Polygons" entry that had to be cut later — the actual polygon/perimeter
  content folded into the existing 2.6 Distances Day 2 instead. Ask rather
  than infer a `lesson_code` from a numbering gap.
- **`homework` is a list, not a string.** A day having more than one open
  assignment at once (one from earlier in the week, due Friday, overlapping
  a new one given Thursday/Friday) turned out to be the normal case, not an
  edge case — `homework` is now `list[str] | None` throughout
  `courses/math6.json`, and `render.py` renders each entry on its own line.
  (Later changed again: each item is now `{"text", "due"}`, stored only on
  the day it's assigned — the "(continued)" repeats are gone, since the
  page derives "still open" from the due date.)
  Also: "finish the class work if not done" was ruled out as not-homework
  earlier this session, then reversed later the same session once it came
  with a real due date — a due date is what makes something count as a
  real assignment, not the phrasing used to describe it.
- **Quiz days can't carry content yet, and the suppression mechanism is
  fragile.** `QUIZ_ITEM` in `engine.py` is hardcoded with no
  target/classwork/homework — there's currently no way to store any of
  those for an auto-placed quiz day. The closest option is the school-day
  `note`, but a note is also how the Wednesday-quiz rule gets suppressed
  (any note containing "quiz", case-insensitive) — so a note describing
  quiz content has to avoid that word, or it silently cancels the quiz.
  Recorded as a known limitation in SPEC.md's Later section — don't work
  around it with more note-text tricks.
- **"Push everything back" still needs measuring.** Accepting a net
  day-budget spend instead of cutting to offset it doesn't make the
  downstream effects go away — still ran `diff_impact`/`run_all_checks` and
  reported the leftover-lesson change and the new Monday-test placements
  before committing, even though the shift itself was already decided.
- **Re-derive indices from the live file, every time.** Verified the four
  entries about to be replaced by `topic`/`lesson_code`/`kind`/`district_title`
  match immediately before cutting, rather than trusting index numbers from
  an earlier read in the same conversation.
- **`student_text` (this schema's old single field) doubled as a title
  override, and that broke this week's entries.** `render()` used
  `student_text or district_title` as the tile title, so when this session
  compressed Target + Class work + Extension into `student_text` per the
  guidance above, the full blob became the title instead of "2.5 Represent
  Locations on the Coordinate Plane". A later session split the field into
  `target`/`classwork` (detail-only, never the title) and fixed `render()`
  to always title from `lesson_code` + `district_title`. About two dozen
  older entries (Topic Openers, Reviews, Tests, the Topic 0 days) had been
  using the old override *correctly* — their `district_title` was a genuine
  opaque placeholder like "Topic 2 Assessment" — so that text was migrated
  into `district_title` itself rather than lost.
