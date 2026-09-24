# Teacher Calendar — SPEC (v1)

## The problem

I teach two courses from district pacing guides. Lessons are sequenced against school days in order. When a day is lost — an assembly, a snow day, a lesson running long — every lesson after it shifts by one day, and I have to manually redo the calendar my students see.

I already solve the re-flow logic in an Excel workbook, one per course:

- **Days sheet**: every school day, tagged with a type — `Instruction`, `Flex`, `Testing`, `No School`, or `Other`.
- **Lessons sheet**: an ordered list of lessons, assigned in order to instructional days.

Changing one day's type re-flows everything after it. v1 must preserve this logic, not redesign it.

## V1 scope — exactly this, nothing else

1. One-time import of the existing Excel workbook (per course) into a plain data file. *(Done; the import script and workbook have since been removed — see "Import" below.)*
2. A render/re-flow engine that reads that data file and computes, for each instructional day, which lesson lands on it — driven purely by day type + ordered lesson list.
3. A rendered calendar web page for **one course**.
4. Deployed somewhere with a stable URL.
5. That URL gets linked in Schoology.

No accounts. No manual-entry UI. No iCal. No imports beyond the one-time Excel conversion.

## Data model

- **School-day calendar**: a standalone object — an ordered list of dates, each tagged with a type (`Instruction` / `Flex` / `Testing` / `No School` / `Other`) and an optional **note**. A note is, by definition, student-facing (a testing-window reminder, a holiday label, a snow-make-up flag) — never a teaching/admin note to self — so it always renders on the page: it replaces the type label on a non-instructional day, and appends under the lesson on an instructional one. Lives independently of any course's lesson sequence, mirroring the Days sheet.
- **Course sequence**: an ordered list of lessons (title, optional homework/DeltaMath text, and whatever other notes/description the existing Lessons sheet carries), with no dates attached directly — lessons get dates by being laid onto the school-day calendar's instructional days, in order. Homework renders alongside the lesson on the page. Each lesson also carries its own **type** — `Lesson` / `Opener` / `Assessment` / `3-Act` (the real categories already used in the workbook's Kind column) — distinct from the school-day type enum, so the rendered page can visually flag assessment days. This is a closed set: a hand-authored sequence uses these same values directly, and adding a genuinely new category is a deliberate schema update, not free text.
- **Engine**: takes (school-day calendar, course sequence) → rendered calendar (date → lesson, or date → day-type label for non-instructional days). This is the one piece of logic worth building well — it's the actual re-flow problem.
- Because a course sequence is just an ordered list feeding the same engine, **authoring a brand-new sequence from scratch is simply hand-writing that input file** — no separate manual-entry feature, ever.
- "Course" is its own named entity wrapping (school-day calendar, sequence), so a second course — and later a second teacher — means adding another instance of that pair, not a schema change. Don't build multi-course or multi-teacher machinery now (no accounts, no per-teacher namespacing) — just don't paint the data model into a single-course-only corner.

## Import (one-time, done — no longer part of the tool)

- A one-time conversion step read the `.xlsx` workbook and wrote out the plain data file(s) described above (school-day calendar + ordered lesson list). That migration is finished.
- **`courses/*.json` is the source of truth.** Everything — engine, rendering, deploy — reads only those files. I edit them going forward; there is no second copy to keep in sync.
- The workbook turned out to be unreliable (it caused bad data at the start of the year) and has been discarded, along with the import script (`scripts/import_workbook.py`, removed 2026-09-23). Do not recreate either or reconcile toward a spreadsheet. When a fact needs checking against an outside reference, use the district's own documents (the at-a-Glance guide, sample calendars, and the SPS school-year calendar kept locally in `data/`).

## Publishing

- Output is a **public, read-only web page** — no login for viewers.
- Must update **instantly** on republish. This rules out iCal/webcal for v1: calendar apps typically poll external feeds only every 12–24 hours, which doesn't fit "I fixed a day, the page must show it now."
- No accounts, no draft/published state — editing `courses/*.json` and pushing is enough; a GitHub Action re-runs the render step and commits the result automatically, and the page reflects it within about a minute.

## Explicit constraints

- **Single user** (me). Configuration lives in a file, not a database.
- **One calendar per course** — no sections/periods concept.
- **No admin or school-wide planning** — out of scope, not something to design around.
- **No student data, ever, in any version** — no student names, no grades, nothing student-identifying. This is a hard constraint, not a v1-only cut.

## Cut from v1 → Later (no dates, no commitment)

User accounts & authentication; hosted multi-tenant SaaS; manual-entry UI; iCal feed; a general recurrence engine; draft-vs-published workflow; third-party imports (Google Classroom/Sheets/Canvas); embed widget; PDF export.

**Planning aid**: a view comparing the live (edited) calendar against the original district scope-and-sequence, showing how far ahead/behind each topic is. The point is to help decide where to condense or where slack exists *before* making a pacing edit, rather than figuring it out from scratch each time. Would need the original district sequence preserved as a separate reference (the district's own at-a-Glance guide and sample calendars in `data/` are the starting point — not the discarded workbook) so there's something fixed to compare the live sequence against.

**Quiz-day content**: quiz days are currently hardcoded to a bare "Quiz" tile with no `target`/`classwork`/`homework` (`QUIZ_ITEM` in `engine.py`), and auto-placement is suppressed by matching the word "quiz" (case-insensitive) in a school-day `note` — a coincidental, fragile mechanism that also means a note describing what's on the quiz can accidentally cancel the quiz if it uses that word. Later: let a quiz day carry real `target`/`classwork` like any other Instruction day (not assigned `homework` — Aaron doesn't assign homework on quiz days, though homework can be *due* on one), and replace the note-text-matching suppression with an explicit flag on the school-day entry.

## Definition of done

I publish a real two-week calendar for one course through this tool and stop maintaining that calendar by hand.
