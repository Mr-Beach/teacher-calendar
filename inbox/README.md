# inbox/ — planned weeks waiting to be applied

The fast path for the routine weekly update. A planning session (Cowork or
chat) writes one JSON file per week here, on a branch named `week/<label>`
(e.g. `week/2026-10-05`), and pushes. `.github/workflows/apply-week.yml`
then runs `scripts/apply_week.py` on it (plain Python, no AI) and opens a
pull request whose description is the plain-language summary. **Merging the
PR is the go-ahead**; the merge is a push to `main`, which Cloudflare
Workers Builds deploys to beach-math.com like any other.
Applied files move to `weeks/applied/`.

Content only. Anything that moves dates — losing a day, cutting or inserting
a lesson, changing a day's type — is rejected here and stays a Claude Code
job (CLAUDE.md), because it's an editorial call.

## Start here: what still needs planning

Before planning, pull and list the days still missing content:

```
git pull
python3 scripts/lookahead.py --needs --days 15
```

It prints, per course, each upcoming lesson day with no target or link
(or class work, in a course that shows it), e.g.
`Mon 10/12  T1L2 Fluently Add, ... -- needs target, link`.
Those are the days to ask Aaron about; the lesson code on each line is the
`expect` value for that day. Quizzes and tests are never listed. Raise
`--days` to look further ahead.

## Format

```json
{
  "course": "math6",
  "week_of": "2026-10-05",
  "days": [
    {
      "date": "2026-10-05",
      "expect": "1.2",
      "target": "I can multiply decimals and place the decimal point using estimation.",
      "classwork": "Notes + workbook pg 12-13 (20 points)",
      "homework": [{"text": "Lesson 1.2 practice 1-12", "due": "2026-10-07"}],
      "link": "https://...",
      "extra_materials": ["calculator"]
    },
    {
      "date": "2026-10-07",
      "note": "Quiz covers 1.1-1.2."
    }
  ]
}
```

`course` is required: `math6` or `math78`. A file without it is rejected.

Rules, per day:

- `date` — required, a date in the course calendar.
- `expect` — required whenever the day sets any lesson field. It must match
  the lesson the calendar *currently* shows on that date: its lesson code
  exactly (`"1.2"`, or Schoology-style `"T1L2"`), or a piece of its title (`"Topic 2 Review"`). This is
  the guard against a calendar that shifted after the week was planned — a
  mismatch rejects the whole file and changes nothing.
- Lesson fields: `target`, `classwork`, `homework`, `link`,
  `extra_materials` (list). `classwork` only counts in a course that shows
  class work (`"show_classwork"` in the course file; it's off for both of
  Aaron's courses): otherwise it's skipped, and the summary says so.
- `homework` — a list of the assignments **given that day**, each
  `{"text": ..., "due": "YYYY-MM-DD"}`. Put it only on the day it's
  assigned; don't repeat it on later days. The page shows it on its due
  date and in the "coming due" list on its own. Leave the due date out of
  `text`. Homework can be due on a quiz day but can't be assigned on one.
  Pages are written "pg" (`pg 27`, `pg 15-16`), never "p."/"pp."/"page".
  Each item also takes a `"link"`: the assignment's own page in Schoology
  (the day's `link` is the lesson folder; an assignment doesn't fall back
  to it). An assignment with no link shows as plain text and gets flagged
  ("needs assignment link"). A Practice Log's link is that week's
  answer-key folder in Schoology; every assignment in the log sends
  students there for its key.
  A Practice Log (text starting "Practice Log") automatically lists every
  other assignment due from the day it's assigned through its due date.
  When that window is wrong, give it `"includes"`: the assignments it
  covers, each `{"text", "due"}` copied exactly from where it was assigned.
- Day field: `note` — always shown to students; never a note to self.
- Leave a key out to leave that field alone; set it to `null` to clear it.
  `homework: []` is the same as `null`.
- Quiz days, closed days, and empty days take a `note` only.
- Same wording rules as the pacing-calendar skill: `target` and `classwork`
  are terse and detail-only; teacher-facing planning color is dropped, not
  stored.

Check a file before pushing it:

```
python3 scripts/apply_week.py inbox/2026-10-05.json --dry-run
```
