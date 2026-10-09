-- v2's database (PLAN-v2-phase1.md, M2; SPEC-v2.md, "Data model").
--
-- D1 is SQLite, and v2/tests run this same file on Python's sqlite3, so
-- keep it to plain SQLite. Apply it to D1 with:
--     npx wrangler d1 execute <database> --remote --file=v2/schema.sql
--
-- A calendar is one JSON document (`calendars.doc`) in the course-file
-- shape -- courses/math6.json minus its "school_days", plus "day_changes"
-- (engine.split_course). Its school's days are stored once, in
-- school_days, and shared by every calendar at that school.

CREATE TABLE schools (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL
);

-- The school record (engine.school_record): closures, with their notes,
-- and every other school day a plain Instruction day. A course's Flex,
-- testing, and "Other" days are its own, in its doc's day_changes.
CREATE TABLE school_days (
  school_id INTEGER NOT NULL REFERENCES schools(id),
  date TEXT NOT NULL,      -- YYYY-MM-DD
  weekday TEXT NOT NULL,   -- Mon..Fri
  type TEXT NOT NULL,
  note TEXT,
  PRIMARY KEY (school_id, date)
);

-- Only Aaron adds teachers (v2/seed.py, or by hand). `email` is the
-- Google sign-in, lower case, matched against the verified Access token,
-- never against anything the page sends. `slug` is the first part of
-- the family address: beach-math.com/<slug>/<calendar>.
CREATE TABLE teachers (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,      -- as families see it: "Mr. Beach"
  slug TEXT NOT NULL UNIQUE,
  school_id INTEGER NOT NULL REFERENCES schools(id),
  is_admin INTEGER NOT NULL DEFAULT 0
);

-- `version` goes up by one on every save; a save names the version it
-- started from and is refused if that's no longer current (two tabs).
-- `title` is the doc's "course", copied here by the store so a list of
-- calendars doesn't parse every doc. `page_html` is the family page,
-- rendered on save and served as is (PLAN-v2-phase1.md, decision 6).
CREATE TABLE calendars (
  id INTEGER PRIMARY KEY,
  owner_id INTEGER NOT NULL REFERENCES teachers(id),
  slug TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'class' CHECK (type IN ('class', 'preschool')),
  title TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  doc TEXT NOT NULL,
  page_html TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (owner_id, slug)
);

-- Every version of every calendar, the current one included: who saved
-- it and when. Undo, recovery from a bad edit, and the record of who
-- changed what.
CREATE TABLE revisions (
  calendar_id INTEGER NOT NULL REFERENCES calendars(id),
  version INTEGER NOT NULL,
  doc TEXT NOT NULL,
  saved_by INTEGER NOT NULL REFERENCES teachers(id),
  saved_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (calendar_id, version)
);
