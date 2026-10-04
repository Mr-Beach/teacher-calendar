# Math 7/8 Compacted: curriculum audit findings

Draft 3, 10/4. Draft 2 plus the district's **Math 7/8 Compacted Year at a Glance 26-27** (rev. 8/25/2026, in `data/`), which lists each topic's standards, suggested days, and the CEA assessment windows. It changes the budget: the Glance lists standards that have no lesson on the calendar, and the CEA windows limit how many days can be cut early in the year.

Other sources:
- `audit_export.py math78` (as of Sun 10/4).
- The district sample calendar.
- The Savvas student pages in OneDrive `Lessons_Math 7.8` (none on disk for T9L2–T9L9 or the Math 8 Topic 5 lessons).
- IM's standards-by-lesson lists for Accelerated 6 and 7, plus IM Grade 7 and Grade 8 (im.kendallhunt.com).

Aaron's calibration (10/3):
- Every topic test gets a review day the class right before it.
- IM alone (Medium) is enough to act on, as long as no standard is dropped.
- Topic 5 stays as built. Draft 1's items 5–7 are dropped.
- Items 1–4 stand.

**Decided 10/4: the Year at a Glance is the standard of record.** Every standard it lists gets taught, so rows 9 and 13–16 (T7L7, T2L10, T11L9–L11, T12L4, T12L5) are in. Gap levers (10/4): **(a) fold T12L4 (yes)**. Rows 18–19 (T2L4 + T2L5, T9L3 + T9L4) close the remaining 2. **Budget balanced; ready to apply.**

## What the Glance changes

1. **Standards the Glance lists with no lesson on the calendar.** The calendar follows the district sample calendar, which skips these Savvas lessons, but the Glance lists their standards for this course:
   - **8.EE.A.4** (Topic 2): T2L10 Operations with Numbers in Scientific Notation.
   - **8.G.A.5** (Topic 11): T11L9 Angles, Lines, and Transversals; T11L10 Interior and Exterior Angles of Triangles; T11L11 Angle-Angle Triangle Similarity. The Glance's course overview says it outright: triangle angle sum, and transversals cutting parallel lines.
   - **8.G.7 and 8.G.8** (Topic 12): T12L4 Apply the Pythagorean Theorem; T12L5 Find Distance in the Coordinate Plane.
   - **8.EE.B.5** is listed for both parts of Topic 7. Its "compare two proportional relationships" half is T7L7, which isn't on the calendar, and T7L8 doesn't teach it (checked 10/4).
2. **Not this course's job:** functions (8.F) and bivariate data (8.SP). The Glance says Algebra 1 picks them up through IM's adaptation pack. Draft 2's question about them is answered.
3. **CEA windows.**
   - Topic 5: Oct 22–Nov 12. The test is 10/27; nothing below moves it.
   - Topic 7 Part 2: Jan 26–Feb 23. The test is Fri 1/29, so only about **2** class days can come out before it (net), or it lands before the window opens.
   - Topic 10: Mar 18–Apr 7. The test is Tue 3/23, so about **3** days can come out before it (net).
   - Day counts are approximate. Claude Code should confirm each CEA date after applying.
4. **T13L1 stays unsupported.** The Glance's Topic 10 & 13 list has no surface-area standard beyond 7.G.B.6, and its overview limits surface area to figures made of "triangles, quadrilaterals, polygons, cubes and right prisms."

## Day budget

| | Days |
|---|---|
| Reviews before the Topic 7 Part 1, Topic 8, Topic 9 and Math 8 Topic 5 tests | 4 |
| Lessons for Glance standards not on the calendar: T7L7, T2L10, T11L9–L11, T12L5 (T12L4 folded in, no day) | 6 |
| **Needed** | **10** |
| **Found, usable:** rows 1–7, 18–19 (Medium), 17 (Low) | **10** (row 4's day goes to its own review, so it counts once on each side) |
| **Short** | **0** |

Row 8 (T3L2) is Medium but can't be used: it falls before the Topic 7 CEA and would push that test out of its window.

**Closing the gap (your call):**
- **(a) Fold T12L4 into T12L2/T12L3** instead of giving it a day (Low). IM spreads applying the theorem across its lessons (Acc7.8.5–8.8) rather than giving it one. Saves 1.
- **(b) Pair a quiz with a lesson on a tight day** (PLANNING.md, "Pairing"), in May or June. Each pairing saves 1.
- **(c) Reclaim SBA days.** The calendar blanks all of 5/24–5/28. If your class doesn't test all five days, each day you get back closes 1.

(a) plus two of (b) or (c) closes it.

## All changes, ranked

"Days" is + for a day saved and − for a day added. "Apply" marks the set that fits the CEA windows. None of these touches a built deck (built through Fri 10/23) or a merged week file (through the week of 10/19, plus the 10/26 Practice Log on the Topic 5 Review).

| # | Change | Days | Evidence | Confidence | First date affected | Apply |
|---|---|---|---|---|---|---|
| 1 | Cut the second day of T6L7 | +1 | IM teaches inequalities by solving the related equation and testing a point, with no lesson on multiplying or dividing by a negative (Acc7.4.4–4.6: 3 lessons for 7.EE.B.4b) | Medium (IM) | Mon 11/16 | ✓ |
| 2 | Cut the second day of T6L5 | +1 | Same 3 IM lessons. Connecting equations and inequalities is one lesson (Acc7.4.4) | Medium (IM) | Tue 11/10 | ✓ |
| 3 | Cut T6L9's own day (keep T6L8 and the T6L8 & T6L9 day) | +1 | 7.EE.B.4b's form is px + q > r, and Grade 8 has no inequality standard. T6L9 distributes, combines, then solves, which is Algebra 1 (A-REI.B.3). IM folds p(x + q) > r into one lesson (7.6.15). The combined day keeps p(x + q) > r | Medium (IM) | Fri 11/20 | ✓ |
| 4 | Cut the second day of T7L4, and add a Topic 7 Part 1 Review before the Topic 7 Part 1 Test | 0 | IM covers variables on both sides through multistep (8.EE.C.7) in 4 lessons (Acc7.4.12–4.14, 4.16). The topic gives that 6 days | Medium (IM) | Tue 12/8 | ✓ |
| 5 | Cut the second day of T13L1 | +1 | Surface area of cylinders, cones and spheres is in no standard the Glance lists (7.G.B.6 stops at prisms; 8.G.C.9 is volume). IM has no such lesson | Medium (IM, Glance) | Tue 3/9 | ✓ |
| 6 | Combine T9L1 + T9L2 into one day | +1 | IM Accelerated teaches likelihood and theoretical probability (7.SP.C.5, 7a) in one lesson (Acc6.8.13). Full IM Grade 7 uses 3 (7.8.1–8.3) | Medium (IM Acc) | Fri 4/2 | ✓ |
| 7 | Combine T9L6 + T9L7 into one day | +1 | IM Accelerated uses 3 lessons for compound events (Acc6.8.15–8.17) to Savvas's 4 (T9L6–L9). Full IM Grade 7 uses more (7.8.7–8.10) | Medium (IM Acc) | Fri 4/9 | ✓ |
| 8 | Cut the second day of T3L2 | +1 | IM gives unit rates with fractions (7.RP.A.1) no block of its own (Acc6.3.8, 5.4, 5.5, 5.8) | Medium (IM) | Thu 12/17 | ✗ (CEA window) |
| 9 | Add T7L7 Compare Proportional Relationships, before T7L8 | −1 | The Glance lists 8.EE.B.5 for both parts of Topic 7. T7L8 is slope only, and T7L9 has one comparison problem (#13). IM gives it a lesson (8.3.4). It also keeps the Topic 7 CEA in its window with rows 1–3 | Medium (IM, Glance) | Fri 1/15 | ✓ |
| 10 | Add a Topic 8 Review before the Topic 8 Test | −1 | Aaron's rule | — | Wed 3/31 | ✓ |
| 11 | Add a Topic 9 Review before the Topic 9 Test | −1 | Aaron's rule | — | Fri 4/23 | ✓ |
| 12 | Add a Math 8 Topic 5 Review before the Math 8 Topic 5 Test | −1 | Aaron's rule | — | Fri 4/30 | ✓ |
| 13 | Add T2L10 Operations with Numbers in Scientific Notation, after T2L9 | −1 | Glance lists 8.EE.A.4. IM gives it 3 lessons (Acc7.7.13–7.15) | Medium (Glance) | ≈ Thu 5/20 | ✓ |
| 14 | Add T11L9, T11L10, T11L11, after T11L8 | −3 | Glance lists 8.G.A.5. IM gives it about 4 lessons (Acc7.1.12–1.14, 2.13) | Medium (Glance) | ≈ Wed 6/16 | ✓ |
| 15 | Add T12L5 Find Distance in the Coordinate Plane, after T12L3 | −1 | Glance lists 8.G.8. IM: one lesson (Acc7.8.9) | Medium (Glance) | ≈ Fri 6/4 | ✓ |
| 16 | Fold T12L4 Apply the Pythagorean Theorem into the T12L2 and T12L3 days (no new day) | 0 | Glance lists 8.G.7. IM spreads applying the theorem across its lessons (Acc7.8.5–8.8). Aaron chose this 10/4 | Low | Tue 6/1 (content only) | ✓ |
| 17 | Cut the second day of T2L3 | +1 | IM spreads ordering real numbers across its rational-approximation lessons rather than giving it 2 days | Low | Fri 5/7 | ✓ |
| 18 | Combine T2L4 + T2L5 into one day | +1 | IM teaches square and cube roots and solving x² = p, x³ = p together: a square root is the side of a square with a given area (Acc7.8.1–8.4, 8.10). 8.EE.A.2 stays whole. Aaron chose this 10/4 | Medium (IM) | Tue 5/11 | ✓ |
| 19 | Combine T9L3 + T9L4 into one day | +1 | One IM Accelerated lesson covers experimental probability and probability models (Acc6.8.14, 7.SP.C.6–7). With rows 6–7, Topic 9 matches IM Accelerated's 5 lessons. Aaron accepted the thinner probability unit 10/4 | Medium (IM Acc) | Tue 4/6 | ✓ |

With T12L4 folded and rows 18–19, the apply set fits: the year ends Thu 6/17 as now. **Ready to apply.**

**Standards check:** no cut drops a standard.
- 3 keeps p(x + q) > r on the combined day.
- 6 keeps 7.SP.C.5 and 7a; T9L3 (7.SP.C.6) and T9L4 (7.SP.C.7) are untouched.
- 7 keeps 7.SP.C.8a and b; 8c stays on T9L9.
- 17 keeps 8.NS.A.2 on T2L3's first day.
- 18 keeps all of 8.EE.A.2 on the combined day.
- 19 keeps 7.SP.C.6 and 7.SP.C.7 on the combined day.
- 5 drops content outside the Glance.
- Rows 9 and 13–16 add the Glance standards that had no lesson.

**Applying (Claude Code):** apply every row at once, then re-derive the Wednesday quizzes from the result (PLANNING.md, "What I cut first"). Then check that the Topic 7 CEA lands on or after Tue 1/26 and the Topic 10 CEA on or after Thu 3/18. A later snow day only pushes them later, which the windows allow.

## Projects

None needed. Math 6's four projects came from Aaron's own 2025-26 lessons. This course has none, and neither the Glance nor the calendar has project days. The budget is short anyway.

## Glance suggested days vs. the calendar

Checked 10/4 with `engine.place()`. Both total **167** instructional days, and most topics match exactly once the calendar's Wednesday quizzes are counted. The district plan has no weekly quizzes. It spends those days on 3-Acts (10), flex days, and seven second days that the calendar doesn't give:
- T5L2
- T5L6 (its own day)
- T6L1
- T7L1
- T7L10
- T10L3
- T12L2

The calendar's 19 quiz Wednesdays fill those slots.

Where the topic counts differ:
- **Topic 7 Part 1:** calendar 10 days, Glance 11 (no T7L1 second day, no 3-Act).
- **Topic 8:** calendar 6, Glance 7 (the 8-4 3-Act).
- **Topic 2:** calendar 15, Glance 13.

The calendar runs a day or two ahead of the district through the spring, and Topic 2 absorbs that. Those seven second days are cuts the calendar has already made relative to the district.

## By topic

### Topic 5 (as built)
Decided 10/3; see "Topic 5 unit plan" below. No cuts.

### Topic 6 (16 days, 10/28 – 11/24): rows 1–3
- Standards: 7.EE.B.3, 7.EE.B.4a, 7.EE.B.4b. No CEA on this test.
- Equations (T6L1–T6L4, 6 days) ↔ Acc7.3.1–3.11: keep. IM gives p(x + q) = r several lessons of its own (Acc7.3.9–3.11).
- Inequalities (T6L5–T6L9, 8 days) ↔ Acc7.4.4–4.6 (3 lessons). After rows 1–3 the block keeps 5 days. Savvas splits by operation; IM uses one method (solve the related equation, test a point). If you keep the Savvas sign-flip rule, the T6L7 day you keep needs it front and center.
- T6L9 (row 3), checked against the Savvas pages 10/4: its examples are 3(x + 2) + 13 > 55, −3(x + 4) + 3 ≥ 9 and 2(3.5t − 2) + 6t ≥ −2, so it's distribute, combine, then solve. Correction to draft 1: IM Grade 7 does use distributed forms (7.6.15 has 3(x + 4) > 17.4 and −3(x − 4/3) ≤ 6), just not as a separate lesson. The combined day keeps them in. Multi-step inequalities combine Topic 5's distributing and combining with inequalities, which makes it a useful repeat if Topic 5 stays shaky. Topic 7 Part 1 repeats the same moves with equations three weeks later.

### Topic 7 Part 1 (8 days, 11/30 – 12/11): row 4
- Standard: 8.EE.C.7. IM: Acc7.4.12–4.16 (5 lessons), then 4.17 starts systems.

### Topic 7 Part 2 (6 lesson days, 1/15 – 1/26; Review 1/27, CEA Test 1/29)
- Standards: 8.EE.B.5 (graph proportional relationships, slope as unit rate, compare two relationships), 8.EE.B.6 (slope from similar triangles, y = mx and y = mx + b).
- IM: Acc7.5.1–5.10 (10 lessons) to the calendar's 6 days (T7L8, T7L8 & T7L9, T7L9, T7L10, T7L11 ×2). No cut.
- **T7L7 Compare Proportional Relationships (checked 10/4): T7L8 does not cover it.** T7L8's Savvas pages are slope as rise over run and slope as unit rate. None of its problems compares two relationships. The only comparison item in Topic 7 is T7L9's Assessment Practice #13 ("an equation and a graph... which has the greater unit rate?"). Topic 3 practices the constant of proportionality across representations (7.RP.A.2), but 8.EE.B.5's "compare two different proportional relationships represented in different ways" has no lesson.
  - Draft 3 gives it a day (row 9), because the Glance lists 8.EE.B.5 for both parts of Topic 7, and the day keeps the Topic 7 CEA in its window. Use IM 8.3.4 "Comparing Proportional Relationships" for the activity. If you'd rather not add the day, the fallback is to put 8.3.4 in as the T7L9 class activity (1/21) and drop row 3 or row 1 to stay in the window.

### Topic 3 (10 lesson days, 12/14 – 1/12; Review 1/13, Test 1/14): row 8, not in the apply set
- Standards: 7.RP.A.1–3, 7.G.A.1 (scale drawings, T3L8).
- IM: about 11 lessons on proportional relationships (Acc6.5.1–5.9, 5.17–5.18) and 7 on scale drawings (Acc7.2.1–2.7), more than the calendar gives. Row 8 is the only cut. It isn't in the apply set: any more cuts before 1/29 push the Topic 7 CEA before its window opens.

### Topic 4 (6 lesson days, 2/1 – 2/9; Review 2/10, Test 2/11)
- Standard: 7.RP.A.3. IM: Acc6.6, 12 lessons. No cut.
- T5L8 (7.EE.A.2, a + 0.05a = 1.05a) set this up in October; recalling it here is worth a Do Now.

### Topic 10 and Topic 13 (interleaved, 2/12 – 3/23; Topic 10 Review 3/22, CEA Test 3/23): row 5
- Standards: 7.G.A.2 (T10L1–L2), 7.G.B.5 (T10L3), 7.G.B.4 (T10L4–L5), 7.G.A.3 (T10L7), 7.G.B.6 (T10L8–L9), 8.G.C.9 (T13L2–L5).
- IM:
  - triangles: Acc7.1.15–1.17
  - angles: Acc7.1.12, plus 5 lessons in full Grade 7 (7.7.1–7.5)
  - circles: about 9 lessons (Acc6.5.10–5.16, 5.19, 5.20), to the calendar's 4 days
  - cross sections: Acc7.6.11, 6.15
  - prisms: Acc7.6.14–6.17
  - volume of cylinders, cones and spheres: 8 lessons (Acc7.6.18–6.25), to the calendar's 4 days
- No cut except row 5. The circle and volume days are already thin by IM's measure.
- Row 5: T13L1 (3/8–3/9) teaches surface area of cylinders, cones and spheres, between T10L8 and T10L9. Cutting both days is defensible on the Glance, but the second cut would push the Topic 10 CEA before its window (Mar 18), unless a day is added back before 3/23.

### Topic 8 (5 lesson days, 3/24 – 3/30; Test 3/31): row 10
- Standards: 7.SP.A.1–2 (T8L1–L3), 7.SP.B.3–4 (T8L5–L6).
- **Where IM puts it (checked 10/4):** in IM Accelerated, sampling is Acc6.8.8–8.12, at the end of the accelerated 6th-grade year, not Acc 7. Comparing two populations (7.SP.B.3–4) gets almost nothing there: only the capstone touches 7.SP.B.4 (Acc7.9.6). Full IM Grade 7 gives sampling 6 lessons (7.8.12–8.17) and comparing populations 3 (7.8.11, 8.18, 8.19).
- No cut: the calendar gives this topic less time than either IM path. Add the Topic 8 Review before Wed 3/31.

### Topic 9 (8 lesson days, 4/1 – 4/22, across spring break and spring MAP; Test 4/23): rows 6–7 and 11
- Standards: 7.SP.C.5–8.
- **Where IM puts it (checked 10/4):** IM Accelerated, Acc6.8.13–8.17 (5 lessons), right after sampling. Full IM Grade 7: 7.8.1–8.10 (10 lessons).
- Rows 6 and 7 rest on the accelerated path. Against full Grade 7 they would be cuts IM does not make, so they are the most debatable Medium rows.
- No Savvas pages on disk for T9L2–T9L9; titles only.
- T9L8 lands on Wed 4/21, the first day back after break and MAP. Expect to reteach some of T9L6–L7 there.

### Math 8 Topic 5 (4 lesson days, 4/26 – 4/29; Test 4/30): row 12
- Standard: 8.EE.C.8 (inspection, graphing, substitution; no elimination). IM: Acc7.5.11–5.16 (6 lessons). No cut. Add the review before Fri 4/30.
- No Savvas pages on disk for this topic.

### Topic 2 (11 lesson days, 5/3 – 5/19; Review 5/20, Test 5/21)
- Standards (Glance): 8.NS.A.1–2, 8.EE.A.1–4.
- IM: exponents and scientific notation in 15 lessons (Acc7.7), irrational numbers and roots in about 7 (Acc7.8.1–8.4, 8.10–8.12), to the calendar's 11 days. No cut. The Glance lists 8.EE.A.4, so T2L10 gets a day (row 13). The second day of T2L3 (row 17, Low) is the only cut.

### Topic 12 and Topic 11 (6/1 – 6/15; combined Review 6/16, Test 6/17)
- Standards (Glance): 8.G.6–8 (Topic 12, 4 suggested days), 8.G.A.1–5 (Topic 11, 9 suggested days). Rows 14–16 add the lessons for 8.G.A.5, 8.G.7 and 8.G.8.
- IM: Pythagorean theorem in 5 lessons (Acc7.8.5–8.9) to the calendar's 2. Transformations and congruence in 18 (Acc7.1), plus dilations and similarity in 7 (Acc7.2.8–2.14), to the calendar's 7. The year ends thinnest here, even with rows 14–16.

## Direction change (Aaron, 10/3)
The audit is now unit by unit: the district calendar is the spine, and IM Grade 7 and Grade 8 (non-accelerated) supply how to present each idea. For each unit: big idea, dependencies, IM's path, where Savvas and IM differ, likely difficulties, day shape, then a conversation. The cut list (above) is for applying calendar changes; the unit-by-unit conversations shape the lessons.

## Topic 5 unit plan (decided 10/3)
- **What went wrong Friday (T5L2, 10/2):** overload. Students didn't remember how to apply the distributive property or which terms combine, and negatives, fractions and decimals all landed at once.
- **Mon 10/5 = T5L2 + T5L3 together, "Simplify Expressions."** No calendar change: 10/5 is already T5L3. Class work updated to "Why combining like terms works; practice ladder." (applied 10/3).
- **Framing (Aaron's from Math 6):** the distributive property shows why combining like terms works, 3x + 5x = (3 + 5)x. Then the working rule: same variable part, add or subtract the coefficients.
- **Adopted for the whole topic:**
  1. Sign ownership first (IM 7.6.18): subtracting is adding the opposite, and every term keeps the sign in front of it. Daily routine: circle each term with its sign before doing anything else.
  2. One representation: the box (area) diagram for expanding and factoring, including negatives (IM 7.6.19). Drop the algebra tiles after the first use.
  3. Self-check by substitution (use x = 2 or 3, not 0 or 1). A mismatch proves an error; a match at one value isn't proof.
  4. T5L8 (7.EE.A.2) draws on IM percent work (a + 0.05a = 1.05a), which also sets up Topic 4.
- **One difficulty at a time:** practice in rungs: whole numbers, then negatives, then decimals, then fractions, then distribute-then-combine.
- **Watch for:** −(2x − 3); in 5 − 2(3x − x), doing 5 − 2 first; 6x − x = 6; x and x² as like terms; one matching value taken as proof; fraction arithmetic.
- **10/5 materials (10/3):** deck `Math 7.8_10-5_T5L3_Simplify Expressions.pptx`, the Topic 5 Lesson 3 Worksheet (practice ladder) and its key, in `teacher-calendar/Claude outputs/10-5 Math 7.8/`. Fractions are held for 10/6.
- **Prior knowledge:** some students had Aaron's Math 6 last year; his 12/11–12/16 decks (Grade 6 Topic 3) show their language.
- Draft 1's Topic 5 cuts (old items 5–7) are dropped.

## Method notes
- **No last-year evidence.** Every file in OneDrive `2025-2026/Lessons` is Math 6, so nothing can be rated High. Medium = IM supports it; Low = judgment call.
- **IM's accelerated path splits this course across two years.** Accelerated 6 holds Grade 7's proportional relationships, percent, rational-number arithmetic, circles, sampling and probability. Accelerated 7 holds the rest of Grade 7 and all of Grade 8. Where the two IM paths disagree (Topic 9), the item says so.
- **The cheap cuts were already gone.** The calendar drops every 3-Act task, and the course has no Topic Openers, so every item is a second day or a combined day.

## For next year
- Nothing yet. With no Math 7/8 decks from last year there's nothing to compare against. This year's decks will be the evidence.
