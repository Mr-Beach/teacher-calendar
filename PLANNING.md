# Pacing and Planning Rules

How I actually plan a calendar. Reference for anyone (or anything) helping build
or update one.

Items marked **(assumed)** were inferred from how I've planned so far, not stated
outright — correct them if they're wrong.

---

## Day types

Every school day on the Days sheet is one of:

- `Instruction` — a lesson lands here
- `Flex` — available buffer, no lesson assigned
- `Testing` — state or district testing, no lesson
- `No School` — holiday, break, non-attendance day
- `Other` — assembly, field trip, anything else that consumes the period

Only `Instruction` days take lessons. Changing any day's type re-flows every
lesson after it by one position.

## Lesson kinds

- `Lesson` — regular district lesson (a review day also uses this kind — it
  carries no new content, so it isn't an assessment of any kind)
- `Opener` — topic opener
- `Quiz` — formative, graded, visually distinct from a Test
- `Test` — summative, the second of a district topic-test's two days
- `3-Act` — 3-Act Math task

## Assessments

**Quizzes go on Wednesdays.** This is a firm rule, not just a rhythm, with
three exceptions — none of these weeks get a quiz:

1. **A test lands anywhere that week** (Mon-Fri), even if not on the Wednesday
   itself.
2. **It's the first week back from a break of a week or more** (e.g. the week
   school resumes after winter break or spring break).
3. **The day before Thanksgiving.**

Quizzes are **never stored as sequence entries** — the engine computes quiz
placement fresh every render, straight from this rule. That's deliberate:
editing lesson content (adding a day, cutting a day) must never be able to
knock a quiz off Wednesday, and it can't, because quiz placement doesn't
depend on where anything sits in `sequence`.

`course["quiz_rhythm_start"]` is the first date this rule applies from —
the first couple weeks of school (syllabus, routines) aren't quiz weeks even
though they include Wednesdays.

**Test placement** (checked, not auto-fixed — see below): avoid a Test
landing on a Monday, and avoid one landing on the Monday, Tuesday, or
Wednesday immediately after a break of a week or more. When this happens,
fixing it is an editorial call (what moves, and where), so it's surfaced as
a warning rather than silently resolved.

A quiz covers only what's been taught since the last quiz — never cumulative
unless I say so.

Quizzes are formatives. So are graded assignments. Both go in the gradebook.

Homework is tracked as a **weekly completion grade**, not as individual
formatives.

**District topic tests occupy two days. I split them as one review day plus one
test day**, not two test days. The review day carries no new content and uses
kind `Lesson`, not `Test` — only the second day is the actual `Test`.

## The day budget

This is the core arithmetic, and it's what most needs checking.

Every calendar change either **spends** or **earns** instructional days:

Spends:
- inserting a quiz that takes a full period
- giving a lesson an extra day
- losing a day to an assembly, snow day, or assembly-length interruption

Earns:
- cutting a lesson from the district sequence
- being ahead of the district pace already
- collapsing two lesson days into one

**Spent must equal earned, or the whole downstream sequence shifts.** After any
edit, check where the sequence lands relative to the district's review and test
dates. Landing on them is the target.

## What I cut first when I need days

In order:

1. Topic Openers
2. 3-Act Math tasks
3. Second days on lessons students already have

I don't cut assessments, and I don't cut a lesson that later lessons depend on.

Cutting to make room for a run of new quizzes isn't one cut per quiz picked
in isolation — inserting a quiz shifts every quiz-worthy Wednesday after it by
one day too (which day counts as "the Wednesday of a test week" can shift as a
result), so the right way to check this is: apply the cuts and insertions
together, then re-derive which weeks are test weeks from the *result*, not
from where tests were before the edit.

## Pairing (assumed)

When a day is tight, a quiz can share a day with a lesson — the quiz takes part
of the period rather than all of it. Worth doing when it saves the only spare
day left. Not worth doing routinely, since it compresses both.

## Update rhythm

I update the calendar **once a week, two weeks ahead**. The near week is
committed; the following week is a best guess and will move.

## What students see

The calendar is student-facing. That governs everything on it:

- **Notes are student-facing by definition** — testing-window reminders, holiday
  labels. Never teacher-private annotations.
- **Homework / DeltaMath assignments render** alongside the lesson.
- Lesson text is written for a sixth grader, not copied from district titles
  where those are opaque.
- Quiz and Test days are visually flagged, in **different colors** — formative
  vs. summative reads differently at a glance.
- **No student names, grades, or anything student-identifying. Ever.**

## Sanity checks after any edit

- Does the last lesson still land on or before the last instructional day?
- Do lessons run out before days do, or the reverse? Report the count either way.
- Did any **quiz** move off a Wednesday? (Should be structurally impossible
  now that quizzes are computed, not stored — if this ever fires, something's
  actually broken, not just unbalanced.)
- Did a review day end up separated from its test?
- Does `engine.check_test_placement()` report any Monday tests or
  post-break Mon-Wed tests? (Not auto-fixed — flag for a decision.)
