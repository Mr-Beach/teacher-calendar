# Curriculum audit (for Cowork)

Aaron's brief for a Cowork session. Kick it off with something like "Read
audit/README.md in the teacher-calendar folder and start the curriculum
audit for Math 6." This file is the whole brief; the session reads it
directly, so nothing needs pasting.

## The goal

The calendar follows the district's Savvas (enVision) sequence. Savvas often
spreads one idea over several lessons, and the calendar gives many lessons
two days. Illustrative Mathematics (IM) teaches the same standards, often in
fewer lessons. Aaron's own lessons from 2025-26 fit the whole year. Find
where Savvas lessons can be **combined or shortened** without losing a
standard, with IM and last year as the evidence. The result is a ranked list
of days saved for each course, that Aaron decides from.

This is research and recommendations only. Don't edit `courses/*.json` or
write week files. Calendar changes happen in Claude Code (see "After the
audit").

## Sources

1. **The current calendar.** In the teacher-calendar folder, run `git pull`,
   then `python3 scripts/audit_export.py math6` (or `math78`). It prints the
   day budget (lessons with no day left before the year ends, tests missing a
   review day), then every topic's lessons with their dates, how many days
   each gets, and what's already taught. Always work from this output, not
   from memory: dates shift.
2. **The district's pacing.** `data/` in the teacher-calendar folder:
   `Math_6_at_a_Glance_26-27.pdf` (topics, standards, and district day counts
   for Math 6), `Sample_Calendar_Math_6_2026-27_Sept-June.pdf`, and
   `Sample_Calendar_Math_7-8_2026-27_Sept-June.pdf`. Use these for which
   standards each topic covers. Any recommendation must still cover all of them.
3. **IM 6-8 Math** (public; im.kendallhunt.com and accessim.org). Math 6
   corresponds to IM Grade 6. Math 7/8 Compacted covers Grade 7 plus part of
   Grade 8. Check whether IM's accelerated sequence covers this same content.
   If it does, it's the most direct comparison, since it's already compressed.
   Check this yourself; don't assume it.
4. **Aaron's lessons from last year**: the SPS OneDrive, folder
   `2025-2026` > `lessons`. If you can't open it, ask Aaron to give this
   session access. Look for how many days each topic actually took, and which
   lessons he combined, skipped, or stretched. A compression he already taught
   is the strongest evidence there is. That folder may hold student work.
   **Never copy a student's name, grade, or anything identifying** into the
   findings.

## Method

Work one course at a time. Go topic by topic, starting with the topics not
yet taught, since that's where days can still be saved.

For each topic:

1. Match each Savvas lesson to its standard(s) and its IM lesson(s).
2. Look for:
   - several Savvas lessons that one IM lesson covers;
   - a Savvas lesson with two days whose IM counterpart is a single lesson;
   - a topic IM teaches in noticeably fewer lessons overall;
   - anything last year's lessons combined or did faster.
3. Follow Aaron's rules (PLANNING.md, "What I cut first"). His cut order
   is Topic Openers, then 3-Act tasks, then second days on lessons. **Never
   cut an assessment**: tests, review days, and quizzes are off the table.
   **Never drop content a later lesson depends on.** Combining two lessons is
   fine; losing what one of them teaches isn't.
4. Check the standards: the topic still covers everything the at-a-Glance
   lists for it.

After the first topic or two, check in with Aaron so he can calibrate how
aggressive to be. Then do the rest.

Taught topics: skip them, except for a short "for next year" note if
something stands out.

## Output

Write `audit/findings/<course>.md` (`math6.md` or `math78.md`):

```markdown
# <Course>: curriculum audit findings

Days needed: <from audit_export's day budget, and why>
Days found: <total of the recommended changes below>

## Recommended changes, best first

| # | Change | Days saved | Evidence | Confidence | First date affected |
|---|---|---|---|---|---|
| 1 | Combine T5L3 + T5L4 into one day | 1 | IM 6.3.5 covers both; combined last year | High | Tue 2/9 |
| 2 | Cut the second day of T8L2 | 1 | IM 6.1.4 is one lesson | Medium | Tue 5/25 |

## By topic

### Topic 5
- T5L3 <title> ↔ IM <grade.unit.lesson> <title>; standards ...
- Last year: ...
- Why the change above works / what to watch for ...

## For next year
...
```

Write every change in calendar terms, so it can be applied directly:
"Combine T#L# + T#L# into one day", "Cut the second day of T#L#", "Cut the
Topic N Opener", "Cut T#L#" (rare; say what covers its content instead).
Use the T#L# labels the export prints. Confidence: **High** means both IM
and last year support it, **Medium** means one does, **Low** means it's a
judgment call. Say which.

## After the audit

Tell Aaron the findings file is ready. He'll bring it to Claude Code (the
teacher-calendar project) to apply the ones he picks, e.g. "apply audit
items 1-3 for Math 6". That session makes the edits, shows him what moves,
and publishes after he OKs it. A combined lesson shows on the calendar as
one day titled with both codes ("T5L3 & T5L4 ...").
