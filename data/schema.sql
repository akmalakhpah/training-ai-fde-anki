CREATE TABLE IF NOT EXISTS decks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cards (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  deck_id       INTEGER NOT NULL REFERENCES decks(id),
  front         TEXT NOT NULL,
  back          TEXT NOT NULL,
  ease          REAL NOT NULL DEFAULT 2.5,
  interval_days INTEGER NOT NULL DEFAULT 0,
  next_due      TEXT NOT NULL DEFAULT (date('now')),
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reviews (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id     INTEGER NOT NULL REFERENCES cards(id),
  rating      TEXT NOT NULL,          -- 'again' | 'hard' | 'good' | 'easy'
  correct     INTEGER NOT NULL,       -- 1 if rating in ('good','easy') else 0
  reviewed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
