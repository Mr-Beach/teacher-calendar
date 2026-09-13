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

- `Lesson` — regular district lesson
- `Opener` — topic opener
- `Assessment` — quiz, test, or review day
- `3-Act` — 3-Act Math task

## Assessments

**Quizzes go on Wednesdays**, as a standing rhythm.

A quiz covers only what's been taught since the last quiz — never cumulative
unless I say so.

Quizzes are formatives. So are graded assignments. Both go in the gradebook.

Homework is tracked as a **weekly completion grade**, not as individual
formatives.

**District topic tests occupy two days. I split them as one review day plus one
test day**, not two test days. The review day carries no new content.

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

## What I cut first when I need days (assumed)

In order:

1. 3-Act Math tasks
2. Topic Openers
3. Second days on lessons students already have

I don't cut assessments, and I don't cut a lesson that later lessons depend on.

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
- Assessment days are visually flagged.
- **No student names, grades, or anything student-identifying. Ever.**

## Sanity checks after any edit

- Does the last lesson still land on or before the last instructional day?
- Do lessons run out before days do, or the reverse? Report the count either way.
- Did any assessment move off a Wednesday?
- Did a review day end up separated from its test?
