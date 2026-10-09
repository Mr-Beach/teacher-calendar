# Teacher Calendar — SPEC (v2, draft)

v1 (`SPEC.md`) is done and live: my two courses at beach-math.com, edited
through Claude Code and git. v2 opens the calendar to other teachers. This
file replaces v1's "single user" and "no accounts, no database" constraints;
everything else in `SPEC.md` still holds unless it says otherwise here.

## The problem

Other teachers want what my students get: one page showing what happened in
class, what's due, and what's coming. My setup only works because I edit
through Claude Code and git; theirs has to work from a web page.

The design rule: **build everything the rules can do as ordinary software**
(forms, buttons, the re-flow, the checks). An LLM comes in only where rules
can't reach, such as a change described in plain words, and then it's built
into the editor so seamlessly that nobody has to think about whether
they're using it. No open-ended chatbot, no separate account, nothing to
set up. A short back-and-forth about a proposed edit is fine; it always
ends in an edit the teacher accepts or dismisses.

Two teachers to start, and they need different things:

1. **A colleague at my school teaching the same course.** The page is for
   students and parents, like mine: lessons, class work, homework with due
   dates, links, quizzes, tests, days off. She sets up a week or two at a
   time.
2. **My wife, a preschool Montessori teacher.** The page is for parents
   only: what the class is doing this week and what it did (circle time,
   activities, songs, books, visitors), the unit for the month or season,
   and events coming up. There's no homework, no quizzes, and no tests.
   She plans weekly today, in a table she fills in for the week ahead.

## The editor: a week grid (both calendar types)

Both teachers plan the same way, a week or two at a time, in a table. So
the editor is one grid for both, and only the rows differ:

- **Columns are class days; rows are fields.** A class calendar's rows are
  lesson, class work, homework, and link. A preschool calendar's rows are
  hers (e.g. circle, practical life, song, book), set from the table she
  already uses.
- **How far ahead is a choice**: show and plan 1, 2, or 4 weeks at once.
- **Click a cell to fill it.** Type, or pick from a list: what that row
  has held before, the teacher's own saved lists (her songs, her books),
  and, for a class calendar, the next lesson in the sequence.
- **Fill a whole week at once**, with no AI: copy last week, copy a saved
  template week, or paste a table straight from Word or Google Sheets (the
  pasted columns map onto the rows). "Same week last year" joins these
  once there is a last year.
- **AI fills are Phase 3** (below), and land the same way: as highlighted,
  unsaved cells she keeps or clears.

## Phases

Each phase ships and gets used before the next one starts.

**Phase 1: class calendar with a web editor** (the colleague)
- She signs in and plans in the week grid: lesson name, class work,
  homework (text, due date, link), a lesson link, and the lesson's kind
  (lesson, test, or project). The grid looks dated, but it's a view onto
  her sequence (see "Data model"): filling an empty day adds the next
  lesson, and copying last week adds last week's lessons again as the next
  ones. Marking a day "no school" isn't a lesson; it's a change to the
  day, as in v1. Neither is a quiz (see "Recurring activities").
- Saving publishes right away, with no build step.
- Her students' page uses the same design as mine (Upcoming plus Whole
  year), with her name and class on it.
- Her own rules are settings, not code: her recurring activities (below),
  and whether a test needs a review day the class before.
- Changes families have already seen are marked on the page (see "When the
  calendar changes").
- She can start from a copy of my Math 6 sequence instead of a blank year.
  The copy keeps the lesson codes, titles, kinds, and I-can targets. It
  drops my links (they point at my OneDrive and my Schoology), class work,
  and homework, so nothing on her page depends on my accounts.

**Phase 1b: preschool calendar** (my wife)

> **Unsettled (2026-10-08):** she's not mainly interested in the
> parent-facing side. What she actually needs gets worked out with her
> before Phase 1b is planned. Treat everything below as a first guess.

- The same sign-in and the same week grid, with her table's rows. She
  plans a week or more ahead, and after a day she can change a cell to
  what actually happened. Alongside the grid: the current unit (a month or
  season, with a short description) and events (field trips, picture day,
  closures).
- A different parent page: the current unit at the top, then this week's
  plan, then a recent-days log that reads like a short daily note home,
  then upcoming events. A month view can wait until she asks for it.

## Recurring activities

A quiz is one case of something more general: an activity that comes back
on a rule. All of them are optional; a new calendar has none. Examples:
a Wednesday quiz, a weekly Practice Log due Friday, a homework-help day,
a monthly catch-up day, a preschool "library day."

- **The rule**: a weekday every week, every other week, or a monthly
  position (first Friday, last class day of the month), starting from a
  date.
- **How it sits on the day**: it takes the whole period (lessons flow
  past it, like a full quiz day), it shares the period with that day's
  lesson (like a paired quiz), or it's an assignment due that day (like
  my Practice Log), not a day at all.
- **When it skips**, from a short list: a week with a test, the first
  week back from a break of a week or more, a day before a holiday. These
  are v1's quiz exceptions, made choosable.
- **One-day changes**: turn it off that day, move it, or switch it between
  full and shared. This is v1's `quiz` override, for any activity.
- Like v1's quizzes, these are computed every time the page is built and
  never stored as lessons. Adding or cutting a lesson can't knock one off
  its day.

## When the calendar changes

Families who check the page closely notice when it changes, and changes
they didn't see coming cost trust. So the page says what changed, plainly,
and the editor helps the teacher change things less often.

**What counts as a change.** Something a family could already have seen,
altered or removed: a date moved, a lesson replaced, homework changed or
its due date moved, a day lost. Filling in a blank isn't a change; adding
detail to a planned day is the system working. A typo fix in text can be
saved as "small fix" and isn't flagged; a change to a date, a test, or a
due date can't be.

**What families see:**
- A "Changed" tag on each affected day, with what it was and what it is
  now ("Quiz moved from Wed 10/14 to Thu 10/15").
- One line per save, not one per day: a lost day that moves twenty
  lessons reads "Tuesday lost to an assembly; lessons from Tuesday on
  moved one day later."
- The teacher's reason, when there is one ("assembly", "we needed another
  day on ratios").
- A "Recent changes" list on Upcoming. A tag shows until the changed day
  passes or for 7 days, whichever comes first.
- For a preschool calendar, editing a past day to what actually happened
  is the log working, not a change. Only plans and events families have
  already seen are flagged.

**Best practices the editor nudges toward** (defaults, which a teacher can
change; notices, never blocks):
- **The next 5 class days are settled.** A change inside that window asks
  for a one-line reason, and the editor says before saving how many days
  families have already seen will change. Changes further out are logged
  but tagged only when they touch a test or a due date.
- **Never move a test or a due date earlier** once it's been shown. Later
  is fine, with a reason.
- **Announce a test at least 5 class days ahead.** A test added inside the
  window gets a notice.
- **Save changes together.** Saves made within a few minutes of each other
  count as one change, so a teacher fixing three things reads as one
  update, not three.
- **Watch the count.** If the settled window has changed more than twice
  in a week, the editor says so. That's a sign to plan less far into the
  detail, not to stop telling families.

The record behind this is a change log per calendar: each save that alters
something already published stores what changed, from what, to what, the
reason, and when. Phase 1 builds the tags and the log; the nudges are
Phase 2.

**Phase 2: planning buttons, no AI**
- "Lost this day": the day stops being a class day for that calendar, and
  every lesson from it on moves one class day later (re-flow, as in v1).
  Pinned entries stay put. It shows what moves before it applies.
- "Add a day" and "remove a day" on a lesson.
- v1's checks as gentle notices in the editor: a test on a Monday, a test
  with no review day, homework due on a day off.
- The change nudges from "When the calendar changes".

**Phase 3: AI where the rules can't reach**
- **Describe a change.** One box in the editor for requests the buttons
  don't cover ("we lost Tuesday and I want to cut the second review day").
  It proposes an edit as a before and after. The teacher can reply to
  adjust it ("keep the review day, cut the opener instead"), then accepts
  or dismisses. Nothing is saved without that click.
- **Fill from a source.** Upload a photo or PDF of a paper plan, or a unit
  plan document, and it fills the grid's cells from it.
- **Draft a week.** "Fill next week for the apple unit" drafts cells from
  the unit, her saved lists, and past weeks.
- Every result is the same kind of edit the buttons make: highlighted,
  unsaved cells, kept or cleared one at a time or all at once. The teacher
  never picks a model or sets anything up.

## Data model

- **School**: a shared school calendar of days off, testing windows, and
  early dismissals. It's entered once and used by every teacher at that
  school. My colleague and I share one. My wife's school has its own.
- **Teacher**: a name as shown to families ("Mr. Beach"), a sign-in email,
  and a school.
- **Calendar**: belongs to one teacher, with a type, `class` or
  `preschool`. The type decides which fields the editor shows and which
  page families see. A teacher can have more than one calendar (my Math 6
  and Math 7/8).
- **Class days** per calendar: the school's calendar plus this calendar's
  own changes (an assembly that only hits one class period, a lost day, a
  recurring activity turned off or moved). This is v1's `school_days`.
- **A `class` calendar stores a sequence, not dates.** It keeps v1's model:
  an ordered list of lessons, each placed on the next class day when the
  page is built. That's what makes re-flow free. Losing a day is one change
  to the class days, and every lesson after it moves on its own, with
  nothing to rewrite. Two things don't flow:
  - **Pinned entries.** A lesson can be pinned to a date (a common test, a
    project due date, a field trip). It stays put, and the lessons around
    it flow past it. Pinning is opt-in. A test flows by default, as in v1.
  - **Homework due dates** are fixed dates, as in v1. A lost day can leave
    something due on a day off, which is a notice, not an auto-fix.
  Recurring activities aren't stored as lessons at all; they're computed
  from their rules, as v1's quizzes are.
- **A `preschool` calendar stores dated entries**, one per day per row,
  planned ahead and edited after the day to what happened. Nothing
  re-flows: a lost day's plan is moved or dropped by hand ("move this
  day's plan to Monday" is a Phase 2 button). Units are date ranges and
  events are dates.
- **Saved lists** per calendar and row: the songs, books, or activities a
  teacher picks from when filling a cell.
- **Recurring activities** per calendar: name, rule, how it sits on the
  day, skip conditions, and an optional link (v1's `quiz_link`).
- **Change log** per calendar: one record per save that altered something
  already published (see "When the calendar changes").
- **Settings** per calendar: review day before a test, the change nudges'
  numbers, and the kinds of lesson it uses. For `preschool`, the labels it
  uses (e.g. "Circle", "Practical life").

The editor and the family page both render a class calendar the same way
v1 does: sequence plus class days in, dated days out. Getting `engine.py`'s
`render()` into the Worker is the core of Phase 1, not of Phase 2.
`PLAN-v2-phase1.md` runs it as is in a Python Worker rather than porting
it. Phase 2's
buttons are then small edits to the sequence or the class days, the same
ones `set_day`, `insert_lesson`, and `cut_lesson` make today.

## Hosting and sign-in

- It stays on Cloudflare, where beach-math.com already runs. A Worker
  serves both the editor and the family pages, and data lives in Cloudflare
  D1 (a database), not in git.
- Sign-in is Google (Cloudflare Access, the same setup that already guards
  beach-math.com/teacher), with each teacher's Google account, not a
  district Outlook account. It's free for up to 50 people. Only I can add a
  teacher.
- **Access only decides who reaches the editor, not which calendars they
  can change.** On every editor request and every save, the Worker checks
  the Access sign-in token (`Cf-Access-Jwt-Assertion`: its signature and
  audience), takes the email from it, and checks that the email owns the
  calendar being read or written. It never trusts an email or calendar ID
  sent by the page. Admin rights are a fixed email checked the same way.
- Family pages stay public and read-only, with no login, as in v1.
- **My calendars stay on the current git workflow** until the colleague's
  trial has run a few weeks. Then my courses move to the new system, and
  the git workflow and `render.py` retire. My students' pages are never
  part of the experiment.
- **During the trial, our shared school calendar exists twice**: in
  `courses/*.json` for me and in D1 for her. Her school record is loaded
  once from my `school_days`. Until my courses move, a school-wide change
  (a snow day, a new early dismissal) gets entered in both, and I'm the one
  who does it. That ends when my courses move to D1.

## Addresses

The address a family gets has to keep working all year, since it's linked
from Schoology and from emails home. Proposed:
`beach-math.com/<teacher>/<calendar>`, e.g. `beach-math.com/smith/math6`.
My current `/math6` and `/math78` addresses keep working. If this grows
past a couple of teachers, move to a domain not named after me and send
the old addresses there.

## Constraints

- **No student data, ever.** That's v1's hard constraint, extended. For
  preschool it covers what parents most expect to see: **no children's
  names (first names included), no photos of children, and no work samples
  that identify a child.** "We celebrated a birthday today" is fine; a
  child's name in the entry is not. The editor shows this rule next to the
  entry box.
- **Uploads for an AI fill go to the model provider.** The upload screen
  says so and repeats the no-names rule, since a teacher's own planning
  table can carry children's names (who has a job, who's absent). Uploads
  are read once and not kept.
- Each teacher sees and edits only their own calendars. I can see all of
  them as the admin, and every teacher is told that.
- No grades, attendance, messaging with families, comments, or photo
  galleries. A calendar, not an LMS.
- One school calendar per school. Teachers don't edit it. I do, or one
  person per school does.

## Before building

- Give my admin or tech contact a heads-up that a colleague is trialling
  the calendar I built, and that it holds no student data.
- Agree with the colleague that it's a trial on my personal site, and what
  happens to her calendar if it ends.

## Open questions

1. **Drafts.** Undecided. Phase 1 starts the way mine works: everything
   entered is visible right away. If my colleague finds herself holding
   back entries because students would see a rough plan, add a "visible
   from" date per week then, with her actual use as the guide.
2. **My wife's needs.** First, what she wants from it at all. She isn't
   mainly after a parent page, so Phase 1b's shape is open. Then her
   school's calendar and a copy of the weekly table she uses now.
3. **Phase 3's API key and cost.** The "describe the change" box calls a
   model from the Worker with my key. That needs a per-teacher daily limit
   and a monthly spending cap before anyone but me can reach it.
4. ~~**The teacher look-ahead**~~ Decided 2026-10-08: it's a page in each
   teacher's editor in Phase 1 (`PLAN-v2-phase1.md`, decision 7). My
   `/teacher` stays as it is until my courses move.

## Out of scope for v2

Multi-school or district rollout; payments; iCal feeds; email digests to
families; native apps; importing from Google Classroom, Schoology, or
spreadsheets.

## Definition of done

- **Phase 1:** my colleague publishes two weeks to her students through the
  editor, without my help and without knowing what's behind it, and stops
  keeping her calendar any other way.
- **Phase 1b:** my wife's parents get a month of daily entries and a unit
  page from her, and she enters it all herself.
