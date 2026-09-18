---
name: pacing-calendar
description: Update Aaron's Math 6 pacing calendar (courses/math6.json) and republish docs/index.html. Use whenever he's updating the pacing calendar, moving a test or quiz, adding or splitting a lesson, adding/losing a week or a day, re-flowing lessons after a lost day, or hands over a week of lesson entries (date, lesson, target, class work, homework, notes) to enter.
---

# Pacing calendar updates

Background this assumes: `SPEC.md` (hard constraints), `PLANNING.md` (day
types, lesson kinds, quiz rules, the day-budget model), `CLAUDE.md` (the
edit-function workflow). This file is the operational playbook for one
recurring job: turning a week Aaron hands over into a committed, re-flowed
calendar. Read PLANNING.md too if a specific rule is unclear — this doesn't
restate all of it.

## Source of truth

`courses/math6.json` — the only course file, and the only state. Two arrays:

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
  "student_text": "Warm up: what do negative values mean on each axis? I can use absolute value to find distances, including with decimal and fraction coordinates.",
  "homework": "Workbook pp. 103–104, problems 10–21",
  "link": null
}
```
`kind` is one of `Lesson` / `Opener` / `Quiz` / `Test` / `3-Act` — but never
hand-insert `Quiz` (see below). `link` is an optional URL to a student
resource (Drive link shared "anyone with the link", or a path under `docs/`),
rendered as a button on that day's detail popup.

Edit only through `engine.py`'s functions (`set_day`, `cut_lesson`,
`insert_lesson`, `edit_lesson`) — never hand-write JSON mutations. Find
indices by reading the live file, not from memory or an earlier read in the
conversation — it changes underneath you.

## Generated — never hand-edit

`docs/index.html`, produced by `render.py`. `.github/workflows/render.yml`
regenerates and commits it automatically on any push to `main` touching
`courses/**.json`, `render.py`, or `engine.py` — so it's self-healing even
if you forget to render locally, but render locally anyway to preview
before committing.

## Repo vs. the district workbook — who wins

`courses/math6.json`, always. SPEC.md: after the one-time import, the
workbook is archived, not a live input, and re-running the conversion is
not an expected workflow. Never reconcile the repo toward the workbook; if
they disagree, the repo is right and the workbook is stale.

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

1. `python3 render.py courses/math6.json > docs/index.html` — render and
   look it over before showing Aaron anything.
2. `engine.run_all_checks(course)` — report any warning.
3. Get Aaron's go-ahead on the content — every time, live calendar, no
   exceptions — before committing.
4. Commit `courses/math6.json` + the re-rendered `docs/index.html`.
5. This session's environment assigns a dedicated branch; pushing there
   satisfies the repo's stop-hook but isn't publishing. Pushing that branch
   to `main` is the actual publish step (the Action re-renders, GitHub Pages
   serves `docs/`, live in about a minute). Confirm that push explicitly and
   separately from the content go-ahead in step 3.

## Input format Aaron hands over

A week as a plain-text block, one entry per school day: date, lesson name, a
`Target` (I-can statement), `Class work` (activity + point value),
`Homework`, and sometimes `Note` / `Extension` / `Warm up`. None of those
sub-labels are schema fields — compress them into `student_text` (target +
classwork + extension, terse, matching the file's existing style, not
transcribed in full) and `homework` (close to verbatim). Worked example,
verbatim, from the week-of-9/21/2026 update:

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
  Retrieval practice, not reteach. Includes one context-graph item
    requiring written explanations.
  Homework: study guide

Tue 9/29 - Topic 2 Summative Assessment
  Covers 6.NS.C.5, 6.NS.C.6c, 6.NS.C.7, 6.NS.C.8, 6.G.A.3
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
  code without saying so.
- **"Push everything back" still needs measuring.** Accepting a net
  day-budget spend instead of cutting to offset it doesn't make the
  downstream effects go away — still ran `diff_impact`/`run_all_checks` and
  reported the leftover-lesson change and the new Monday-test placements
  before committing, even though the shift itself was already decided.
- **Re-derive indices from the live file, every time.** Verified the four
  entries about to be replaced by `topic`/`lesson_code`/`kind`/`district_title`
  match immediately before cutting, rather than trusting index numbers from
  an earlier read in the same conversation.
