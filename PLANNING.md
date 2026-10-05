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
- `Project` — a project work day. Summative, so it's shown in the Test
  colors, but it isn't a Test: it doesn't need a review day, and it
  doesn't stop that week's quiz (turn one off with the day's `quiz`
  override)

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

**Overriding the rule on one day** is a school day's `quiz` field, set with
`engine.set_day(course, date, quiz=...)`:

- `"none"` — no quiz that Wednesday (a week that needs none for a reason
  outside the exceptions above).
- `"paired"` — the quiz shares the period with that day's lesson (see
  Pairing). The lesson still takes the day; the page shows "+ Quiz" on it.
- `"full"` — a full-period quiz day where the rule wouldn't put one.
  Moving a quiz is `"none"` on its Wednesday plus `"full"` on the new day.

A day's note never affects quiz placement — it's only text.

`course["quiz_rhythm_start"]` is the first date this rule applies from —
the first couple weeks of school (syllabus, routines) aren't quiz weeks even
though they include Wednesdays.

`course["quiz_link"]` (optional) is where students find the quizzes (the
course's Weekly Quizzes folder in Schoology). Every quiz day's resource
button opens it, since a computed quiz has no entry of its own to link from.

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
day left. Not worth doing routinely, since it compresses both. Set it with
the day's `quiz: "paired"` override (above).

## Update rhythm

I update the calendar **once a week, two weeks ahead**. The near week is
committed; the following week is a best guess and will move.

## What students see

The calendar is student-facing. That governs everything on it:

- **Notes are student-facing by definition** — testing-window reminders, holiday
  labels. Never teacher-private annotations.
- **Where things show.** The page opens on Upcoming: a today card, the
  homework still open, the next quiz and test, then the school days as a list,
  week by week. Each day's row shows only its title and a one-line summary
  (what's due, what's given); tapping it opens the day's details in place —
  target, class work, homework, what's due, a lesson day's note, and the
  lesson button. Whole year shows Monday–Friday month grids (two months on a
  laptop, one on a phone); a day square carries its title (or just its lesson
  code on a phone) and a "Due" tag when something's due. A closed day's note
  (e.g. "No School (Holiday)") is its label in both views.
- **Homework / DeltaMath assignments render** alongside the lesson on the day
  they're assigned, and again under "Due this day" on their due date. The
  Homework list on Upcoming shows everything given and not yet due, with "due
  today" / "due tomorrow" called out. A due date is a fixed date — it's how much time students have,
  not tied to content, so a lost day never moves it. Homework is never
  assigned on a quiz day, but can be due on one.
- **The current unit is in focus** (`"focus_current_unit": true` in each
  course file). The unit runs from the day after the last unit test
  through the next one. Its days show everything: homework, due dates,
  Due tags, links, details. Class days outside it, past units and future
  ones, show their lesson name, quiz, or test, faded, and nothing else: no
  homework, due dates, or links, and they don't open. One line after the
  test's week says so. The day after the test, the next unit comes into
  focus on its own. The near week is set, the week after can still
  change, and the rest of the unit can change before the test.
- **Class work is off** for both courses (`"show_classwork": false` in
  each course file). Any stored class work stays in the file but isn't
  shown, flagged as missing, or tracked as a change; turning the setting
  back on brings it back.
- Lesson text is written for a sixth grader, not copied from district titles
  where those are opaque.
- Quiz and Test days are visually flagged, in **different colors** — formative
  vs. summative reads differently at a glance.
- **No student names, grades, or anything student-identifying. Ever.**

## When the calendar changes

Students and families who watch the calendar notice when it changes, so the
page says what changed instead of leaving them to spot it. Every confirmed
edit is logged with `engine.record_change` in the course file's `changes`
list, and the page builds two things from that log:

- **A tag on each changed day** that says what happened: "Moved" (its
  lesson or test is on another day now, and the details say which; the
  day a test or project moves to says where it came from),
  "Due date moved", "HW dropped", or "Changed" for anything else. It's a
  dot on the day's Whole-year square, and the old version sits at the top
  of the day's details. The tag shows for 7
  days after the change, or until the day itself is past.
- **Recent changes** on Upcoming: one line per edit, in my words, with the
  reason if I gave one, listed for 7 days.
- **Coming up**: the next quiz or test tile carries the same tag when its
  day changed, and a moved test says where it moved from.

What counts is what someone could already have seen, from today on:

- **A day's title** changed: its lesson, a quiz or test appearing or
  disappearing, a day closed.
- **Class work** changed on a day whose lesson stayed the same.
- **An assignment's due date** moved, or the assignment was dropped.
  Homework moving to a new day along with its lesson isn't news; its due
  date is.
- **Filling in a blank is not a change.** Adding detail to a planned day is
  the calendar working. So is changing a day that's already past.

Which changed days get a tag: any in the next 5 class days, plus quiz,
test, and project days and moved or dropped due dates anywhere. A re-flow that shifts the
rest of the year shows up as its one summary line, not a hundred tags.

A typo fix in class work can be recorded as a small fix
(`small_fix=True`), which doesn't tag it. A changed title or a moved due
date is always tagged.

**"Updated"** is the lighter tag for content added to a day that keeps
its lesson: a target, a link, materials, a new assignment. The lesson's
name doesn't count; it's there from the start of the year. It shows for 2
days, isn't listed under Recent changes, and gives way to a change tag on
the same day. The weekly fill is what usually earns it.

The log starts empty: the changes made before this existed aren't in it.

## Sanity checks after any edit

`engine.run_all_checks()` runs every one of these in one call. None are
auto-fixed — each is an editorial call, surfaced as a warning. They also
show on beach-math.com/teacher under "Needs a decision", and in the
weekly-update PR as standing warnings.

- **Leftover lessons** (`check_leftover_lessons`): does the last lesson still
  land on or before the last instructional day? Lessons past it silently
  drop off the published calendar.
- **Lesson shortfall** (`check_lesson_shortfall`): the mirror image —
  instructional days at the end of the year with nothing planned, because
  the sequence ran out first. Not itself a problem (could be intentional
  wrap-up time), but worth knowing about rather than discovering in June.
- **Review before test** (`check_review_before_test`): every Test has its
  review day as the class right before it (closed days in between are
  fine; a quiz or lesson is not). A review is recognized by "Review" in its
  title.
- **Test placement** (`check_test_placement`): no Monday tests, and none in
  the first Mon-Wed back from a break of a week or more.
- **Unexplained closures** (`check_unexplained_closures`): every real closure
  in this data has a note explaining it — an isolated `No School` (or other
  non-Instruction) day with no note, sandwiched by Instruction days, has
  twice turned out to be a data-entry mistake in the source workbook rather
  than a real day off.
- **Homework due dates** (`check_homework_due_dates`): due dates are fixed
  while lessons move, so a lost day can leave an assignment due on a day
  with no school, or on/before the day it's assigned.
- **Homework links** (`check_homework_links`): every assignment except a
  Practice Log links to its own page in Schoology.

Did any **quiz** move off a Wednesday? That should be structurally
impossible — quizzes are computed, not stored — so if it ever happens,
something's actually broken, not just unbalanced.

Run the checks when setting up a new course file, so it starts from a
known-checked state. Adding a new check means adding it to
`run_all_checks()` and this list, not wiring it into each caller by hand.
