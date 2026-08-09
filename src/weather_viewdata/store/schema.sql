--  The place index. Two tables: what a place is, and every string a reader
--  might key to reach it.
--
--  Derived entirely from the GeoNames dump, so it is rebuilt rather than
--  migrated: an import replaces what it finds.

CREATE TABLE IF NOT EXISTS places (
    geoname_id   INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL,
    ascii_name   TEXT    NOT NULL,
    alternate_names TEXT NOT NULL,   -- comma separated, as the dump gives them
    latitude     REAL    NOT NULL,
    longitude    REAL    NOT NULL,
    feature_class TEXT   NOT NULL,
    feature_code TEXT    NOT NULL,
    country      TEXT    NOT NULL,
    admin1       TEXT    NOT NULL,
    population   INTEGER NOT NULL,
    elevation    INTEGER,            -- null where neither column had a reading
    timezone     TEXT    NOT NULL,
    --  Computed once on the way in rather than at every keystroke. A search
    --  frame repaints while the reader is still typing, so the query must be
    --  an indexed range scan and an ORDER BY on a stored column, and nothing
    --  else.
    rank         REAL    NOT NULL
);

--  One row per name a place answers to, folded to the letters a viewdata
--  keypad can send. A place with eight alternate names has eight rows here,
--  which is why a search groups by place before it ranks.
CREATE TABLE IF NOT EXISTS place_keys (
    key         TEXT    NOT NULL,
    geoname_id  INTEGER NOT NULL REFERENCES places(geoname_id) ON DELETE CASCADE,
    PRIMARY KEY (key, geoname_id)
) WITHOUT ROWID;

--  A prefix search is a range scan over the key, and needs no index of its own:
--  the key leads the primary key of a WITHOUT ROWID table, so the table *is*
--  the index. An explicit one over the same columns was written here first, and
--  did nothing but cost every insert twice.
--
--  This one is not optional. Re-importing a place deletes the keys it used to
--  answer to, and every ordering above leads with the key, so that delete was a
--  full scan of a table heading towards two million rows -- once per place, on
--  an import of two hundred thousand. Measured as an import that had not
--  finished after ten minutes; it is seconds with this here.
CREATE INDEX IF NOT EXISTS place_keys_by_place ON place_keys (geoname_id);

CREATE INDEX IF NOT EXISTS places_by_country ON places (country, rank DESC);
