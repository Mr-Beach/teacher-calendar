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
they're using it. No chat window, no separate account, nothing to set up.

Two teachers to start, and they need different things:

1. **A colleague at my school teaching the same course.** The page is for
   students and parents, like mine: lessons, class work, homework with due
   dates, links, quizzes, tests, days off. She sets up a week or two at a
   time.
2. **My wife, a preschool Montessori teacher.** The page is for parents
   only, and it mostly looks back: what the class did today (circle time,
   activities, songs, visitors), plus the unit for the month or season, and
   events coming up. There's no homework, no quizzes, and no tests.

## Phases

Each phase ships and gets used before the next one starts.

**Phase 1: class calendar with a web editor** (the colleague)
- She signs in and fills in a week at a time on a form, one row per day:
  lesson name, class work, homework (text, due date, link), a lesson link,
  and the day's kind (lesson, quiz, test, project, or no school).
- "Copy last week's layout" and "next week" buttons. Saving publishes
  right away, with no build step.
- Her students' page uses the same design as mine (Upcoming plus Whole
  year), with her name and class on it.
- Her own rules are settings, not code: which weekday quizzes go on (or
  none), and whether a test needs a review day the class before.
- She can start from a copy of my Math 6 sequence instead of a blank year.

**Phase 1b: preschool calendar** (my wife)
- The same sign-in and the same kind of editor, with different fields: a
  short "what we did today" entry (circle, activities, a song or book), the
  current unit (a month or season, with a short description), and events
  (field trips, picture day, closures).
- A different parent page: the current unit at the top, then a recent-days
  log that reads like a short daily note home, then upcoming events. A
  month view can wait until she asks for it.

**Phase 2: planning buttons, no AI**
- "Lost this day": every lesson from that day on moves one class day later
  (re-flow, as in v1). It shows what moves before it applies.
- "Add a day" and "remove a day" on a lesson.
- v1's checks as gentle notices in the editor: a test on a Monday, a test
  with no review day, homework due on a day off.

**Phase 3: describe a change** (the LLM's one job)
- One box in the editor, "Describe the change", for requests the buttons
  don't cover ("we lost Tuesday and I want to cut the second review day").
  It proposes an edit as a before and after, and the teacher accepts or
  dismisses it. Nothing is saved without that click.
- It's one more box in the editor. The teacher never picks a model, sees
  a chat, or sets anything up, and every result is the same kind of edit
  the buttons make, previewed the same way.

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
- **Day entry**: one per calendar per date. Phase 1 stores entries by date,
  since that's how a teacher fills in a week. Phase 2's re-flow is an
  operation on those dated entries: it moves them forward along the
  school's class days.
- **Settings** per calendar: quiz weekday or none, review day before a
  test, and the kinds of day it uses. For `preschool`, the labels it uses
  (e.g. "Circle", "Practical life").

## Hosting and sign-in

- It stays on Cloudflare, where beach-math.com already runs. A Worker
  serves both the editor and the family pages, and data lives in Cloudflare
  D1 (a database), not in git.
- Sign-in is Google (Cloudflare Access, the same setup that already guards
  beach-math.com/teacher), with each teacher's Google account, not a
  district Outlook account. It's free for up to 50 people. Only I can add a
  teacher.
- Family pages stay public and read-only, with no login, as in v1.
- **My calendars stay on the current git workflow** until the colleague's
  trial has run a few weeks. Then my courses move to the new system, and
  the git workflow and `render.py` retire. My students' pages are never
  part of the experiment.

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
2. **My wife's school calendar.** Waiting on her: I need her school's
   calendar, and to hear whether she wants a week or month view or just
   the daily log and current unit.
3. **Re-flow for dated entries.** v1 stores lessons as a sequence without
   dates, so they re-flow naturally. v2 stores entries by date. Phase 2 has
   to define exactly which entries move when a day is lost: everything
   after it, or only lessons (not projects and tests with fixed dates)?
4. **The teacher look-ahead** (beach-math.com/teacher): does it become a
   per-teacher page in the editor in Phase 1, or wait?

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
