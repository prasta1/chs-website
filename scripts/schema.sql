CREATE TABLE IF NOT EXISTS source (
  id          INTEGER PRIMARY KEY,
  filename    TEXT NOT NULL UNIQUE,
  title       TEXT NOT NULL,
  kind        TEXT NOT NULL,
  pages       INTEGER NOT NULL,
  sha256      TEXT NOT NULL,
  imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appearance (
  id          INTEGER PRIMARY KEY,
  source_id   INTEGER NOT NULL REFERENCES source(id),
  page        INTEGER NOT NULL,
  import_key  TEXT UNIQUE,
  raw_line    TEXT,

  surname     TEXT NOT NULL,
  given       TEXT,
  surname_key TEXT NOT NULL,
  kind        TEXT NOT NULL,
  role        TEXT,
  pair_key    TEXT,
  date_raw    TEXT,
  date_iso    TEXT,
  place       TEXT,
  detail      TEXT,

  origin      TEXT NOT NULL DEFAULT 'imported',
  status      TEXT NOT NULL DEFAULT 'active',
  verified    INTEGER NOT NULL DEFAULT 0,
  note        TEXT,
  edited_at   TEXT,
  edited_by   TEXT
);

CREATE INDEX IF NOT EXISTS idx_appearance_surname     ON appearance(surname);
CREATE INDEX IF NOT EXISTS idx_appearance_surname_key ON appearance(surname_key);
CREATE INDEX IF NOT EXISTS idx_appearance_kind        ON appearance(kind);
CREATE INDEX IF NOT EXISTS idx_appearance_date        ON appearance(date_iso);
CREATE INDEX IF NOT EXISTS idx_appearance_pair        ON appearance(pair_key);

CREATE TABLE IF NOT EXISTS newsletter (
  id         INTEGER PRIMARY KEY,
  filename   TEXT NOT NULL UNIQUE,
  volume     TEXT,
  number     TEXT,
  issue_date TEXT,
  title      TEXT,
  pages      INTEGER NOT NULL,
  sha256     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS newsletter_page (
  newsletter_id INTEGER NOT NULL REFERENCES newsletter(id),
  page          INTEGER NOT NULL,
  text          TEXT NOT NULL,
  PRIMARY KEY (newsletter_id, page)
);
