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
   This lists the upcoming lesson days still missing a target, class work,
   or link. Start from that list: tell me which days are open and ask me
   about them, one course at a time. Don't plan from memory of the
   calendar; dates shift when days are lost.
2. Read inbox/README.md for the week-file format and rules.
3. For each open day, get from me (or work out with me): the I-can
   target, the class work, any homework and its due date, and the link.
4. Write one file per course per week: inbox/<Monday's date>-<course>.json
   (course is math6 or math78). Every lesson day needs "expect" set to the
   lesson code shown for that date in the needs list.
5. Check each file: `python3 scripts/apply_week.py inbox/<file> --dry-run`.
   Fix any error before going on. If it says a lesson doesn't match,
   the calendar has shifted. Re-run the needs list; don't force it.
6. Show me a short summary, day by day: target, class work, homework
   with due date, and whether a link is set. Wait for my OK.
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
- classwork: the activity in a few words, plus the point value if I give
  one. Keep it short; students read it on a phone.
- note: always shown to students. Never put reminders to myself or
  planning reasons there. Leave those out.
- homework: only on the day it's assigned, with a due date. Don't write
  the due date into the text. Homework can be due on a quiz day but not
  assigned on one. Say where it comes from: "Topic 1 Lesson 2 Practice:
  workbook pp. 15-16 #19-33", or the worksheet's title and problems.
- Practice Log: homework whose text starts "Practice Log", assigned
  Monday, due Friday. The calendar lists what it covers on its own:
  every other assignment due from the day it's assigned through its due
  date. Don't list them in its text. If that's the wrong set (I name
  different assignments, or some were due before the log was assigned),
  give the log an "includes" list: each assignment's text and due date,
  copied exactly from where it was assigned. Show me the list either way.
- Quiz redo: name the quiz it's for, e.g. "Topic 2 Quiz 1 redo on
  Schoology (2 more tries)". Keep both words "Quiz" and "redo" in the
  text; that's how the calendar links it to the weekly quizzes folder
  instead of the answer keys.
- Work with no due date is class work, not homework. Put it in
  classwork.
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
  matching target and class work for that day. If not, offer to add them
  to that week's file.
```
