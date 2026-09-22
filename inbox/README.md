# inbox/ — planned weeks waiting to be applied

The fast path for the routine weekly update. A planning session (Cowork or
chat) writes one JSON file per week here, on a branch named `week/<label>`
(e.g. `week/2026-10-05`), and pushes. `.github/workflows/apply-week.yml`
then runs `scripts/apply_week.py` on it (plain Python, no AI) and opens a
pull request whose description is the plain-language summary. **Merging the
PR is the go-ahead**; the merge republishes the page via `render.yml`.
Applied files move to `weeks/applied/`.

Content only. Anything that moves dates — losing a day, cutting or inserting
a lesson, changing a day's type — is rejected here and stays a Claude Code
job (CLAUDE.md), because it's an editorial call.

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
      "classwork": "Notes + workbook pp. 12-13 (20 points)",
      "homework": ["Lesson 1.2 practice 1-12, due Wed 10/7"],
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

Rules, per day:

- `date` — required, a date in the course calendar.
- `expect` — required whenever the day sets any lesson field. It must match
  the lesson the calendar *currently* shows on that date: its lesson code
  exactly (`"1.2"`), or a piece of its title (`"Topic 2 Review"`). This is
  the guard against a calendar that shifted after the week was planned — a
  mismatch rejects the whole file and changes nothing.
- Lesson fields: `target`, `classwork`, `homework` (list, one item per open
  assignment; `(continued)` entries repeat an earlier assignment with the
  same due date), `link`, `extra_materials` (list).
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
