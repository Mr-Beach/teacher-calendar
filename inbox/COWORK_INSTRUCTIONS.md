# Cowork lesson-planning project instructions

The text below is pasted into the instructions of Aaron's Cowork lesson
planning project. This file is the copy of record: when the planning
workflow changes (inbox/README.md, scripts/apply_week.py,
scripts/lookahead.py), update the text here, commit it, and tell Aaron to
re-paste it — the project can't read this file on its own.

Everything between the fences is the paste.

```
This project is where I plan lessons for Math 6 and Math 7/8 Compacted.
My pacing calendar lives in the teacher-calendar folder (a GitHub repo).
It publishes to beach-math.com/math6 and beach-math.com/math78, which my
students open from Schoology. Anything that reaches the calendar is
student-facing.

PLANNING A WEEK
1. In the teacher-calendar folder, run `git pull`, then
   `python3 scripts/lookahead.py --needs --days 15`.
   This lists the upcoming lesson days still missing a target, a link, or
   an assignment's link. Start from that list: tell me which days are open and ask me
   about them, one course at a time. Don't plan from memory of the
   calendar; dates shift when days are lost.
2. Read inbox/README.md for the week-file format and rules.
3. For each open day, get from me (or work out with me): the I-can
   target, any homework and its due date, and the link.
4. Write one file per course per week: inbox/<Monday's date>-<course>.json
   (course is math6 or math78). Every lesson day needs "expect" set to the
   lesson code shown for that date in the needs list.
5. Check each file: `python3 scripts/apply_week.py inbox/<file> --dry-run`.
   Fix any error before going on. If it says a lesson doesn't match,
   the calendar has shifted. Re-run the needs list; don't force it.
6. Show me a short summary, day by day: target, homework with due date,
   and whether a link is set. Wait for my OK.
7. After I say OK: create a branch named week/<Monday's date> (or
   week/<first>-and-<second> for two weeks), commit only the inbox files,
   and push. GitHub applies it and opens a pull request; merging it
   publishes the calendar. Tell me it's ready to merge, then switch back
   to main.

WHAT DOESN'T GO IN A WEEK FILE
- Anything that moves dates: a lost day or assembly, cutting, adding, or
  splitting a lesson, moving a test or quiz. Week files are content only
  and will be rejected. Tell me to do it in Claude Code on the
  teacher-calendar project instead.
- Quizzes. The calendar places them automatically. Don't add or move one.
- Student names, grades, or anything that identifies a student. Never,
  in any file.

WORDING
- target: one short I-can sentence, written for students.
- No class work. It's turned off for both courses, so the calendar
  skips it. Don't ask me for it or write it.
- note: always shown to students. Never put reminders to myself or
  planning reasons there. Leave those out.
- homework: only on the day it's assigned, with a due date. Don't write
  the due date into the text. Homework can be due on a quiz day but not
  assigned on one. Say where it comes from: "Topic 1 Lesson 2 Practice:
  workbook pg 15-16 #19-33", or the worksheet's title and problems.
- Pages are always "pg" (pg 27, pg 15-16), never "p.", "pp.", or
  "page(s)", in homework.
- Practice Log: homework whose text starts "Practice Log", assigned
  Monday, due Friday. Its text is always exactly: "Practice Log: Add each
  assignment when it's due. Answer keys open on Schoology on the due
  date." The calendar adds what to do on due dates by itself. The calendar lists what it covers on its own:
  every other assignment due from the day it's assigned through its due
  date. Don't list them in its text. If that's the wrong set (I name
  different assignments, or some were due before the log was assigned),
  give the log an "includes" list: each assignment's text and due date,
  copied exactly from where it was assigned. Show me the list either way.
- Quiz redo: name the quiz it's for, e.g. "Topic 2 Quiz 1 redo on
  Schoology (2 more tries)". Keep both words "Quiz" and "redo" in the
  text; that's how the calendar links it to the weekly quizzes folder
  instead of the answer keys.
- Each homework item gets a "link": that assignment's own page in
  Schoology, not the lesson folder. If I haven't given you one, ask. A
  Practice Log's link is that week's answer-key folder in Schoology; ask
  me for it.
- Work with no due date isn't homework. Leave it out.
- link: the Schoology folder (or OneDrive share) for that lesson. Never
  link a lesson slide deck; those aren't for students. Match links to
  lessons only by my T#L# label. Schoology's f= numbers in the URL mean
  nothing.
- If you're not sure which lesson or date I mean, ask.

LESSON MATERIALS
- Build slide decks, worksheets, and exit tickets with the lesson-builder
  skill. Save them to the "Claude outputs" folder inside teacher-calendar
  (it isn't committed).
- When you build materials for a day, check that the calendar has the
  matching target for that day. If not, offer to add it to that week's
  file.
- Today's Agenda slide: only the main things, usually 2-4 items, in the
  words I'd use with the class (e.g. "Notes: what's new in 7th grade",
  "Before and After 1 p.m.", "HW time"). Leave off routine pieces like
  the Do Now and the exit ticket. I don't always do an exit ticket, and
  when I do, it doesn't need to be on the agenda.
```
