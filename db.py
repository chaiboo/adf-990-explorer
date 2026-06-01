"""SQLite cache for collected nonprofits. One row per EIN (latest filing)."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "nonprofits.db"

# Financial fields lifted verbatim from ProPublica filings_with_data.
FINANCIAL_FIELDS = [
    "totrevenue", "totfuncexpns", "totassetsend", "totliabend",
    "totnetassetend", "totcntrbgfts", "totprgmrevnue", "invstmntinc",
    "compnsatncurrofcr", "othrsalwages", "pct_compnsatncurrofcr",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (
    ein              INTEGER PRIMARY KEY,
    name             TEXT,
    sub_name         TEXT,
    city             TEXT,
    state            TEXT,
    zipcode          TEXT,
    ntee_code        TEXT,
    ntee_major       INTEGER,
    subsection_code  INTEGER,
    foundation_code  INTEGER,
    ruling_date      TEXT,
    tax_period       TEXT,
    tax_year         INTEGER,
    latest_object_id TEXT,
    formtype         INTEGER,
    pdf_url          TEXT,
    -- financials (latest filing with data)
    totrevenue       REAL,
    totfuncexpns     REAL,
    totassetsend     REAL,
    totliabend       REAL,
    totnetassetend   REAL,
    totcntrbgfts     REAL,
    totprgmrevnue    REAL,
    invstmntinc      REAL,
    compnsatncurrofcr REAL,
    othrsalwages     REAL,
    pct_compnsatncurrofcr REAL,
    -- enrichment (from IRS 990 e-file XML)
    emp_count        INTEGER,
    volunteers       INTEGER,
    infotech_amt     REAL,
    website          TEXT,           -- normalized domain from 990 header WebsiteAddressTxt
    enrich_status    TEXT,           -- NULL=not tried, 'ok', 'no_xml', 'not_990', 'error'
    -- bookkeeping
    scope            TEXT,           -- which collection run added this
    collected_at     TEXT
);

-- object_id -> ZIP part map, cached so we list IRS central directories once.
CREATE TABLE IF NOT EXISTS xml_index (
    object_id  TEXT PRIMARY KEY,
    year       INTEGER,
    zip_url    TEXT
);
CREATE INDEX IF NOT EXISTS idx_orgs_state ON orgs(state);
CREATE INDEX IF NOT EXISTS idx_orgs_emp ON orgs(emp_count);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # Migrate older DBs that predate a column.
    have = {r[1] for r in conn.execute("PRAGMA table_info(orgs)")}
    if "website" not in have:
        conn.execute("ALTER TABLE orgs ADD COLUMN website TEXT")
        conn.commit()
    return conn


def upsert_org(conn, row):
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "ein")
    sql = (
        f"INSERT INTO orgs ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(ein) DO UPDATE SET {updates}"
    )
    conn.execute(sql, [row[c] for c in cols])
