"""Collect candidate nonprofits from the ProPublica Nonprofit Explorer API.

The search API filters only by free-text query, state, NTEE major group (1-10),
and 501(c) code. Everything finer (revenue, employees, etc.) is filtered LOCALLY
in the explorer. This collector pulls a broad candidate pool + financials into
SQLite so you can re-slice it any way without re-hitting the network.

Usage:
    python collector.py --state NM --ntee 4 --c-code 3
    python collector.py --state CA --ntee 5 --max-pages 40
    python collector.py --query "food bank" --state TX
"""

import argparse
import datetime as dt
import sys
import time

import requests

import db

API = "https://projects.propublica.org/nonprofits/api/v2"
HEADERS = {"User-Agent": "adf-bd-explorer/1.0 (research; contact rb12295@gmail.com)"}
PAGE_SIZE = 25  # fixed by the API


def search_page(session, page, state=None, ntee=None, c_code=None, query=None):
    params = {"page": page}
    if query:
        params["q"] = query
    if state:
        params["state[id]"] = state
    if ntee:
        params["ntee[id]"] = ntee
    if c_code:
        params["c_code[id]"] = c_code
    r = session.get(f"{API}/search.json", params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_org(session, ein):
    r = session.get(f"{API}/organizations/{ein}.json", headers=HEADERS, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def latest_filing(org_json):
    """Pick the filing with the most recent tax period that actually has data."""
    filings = org_json.get("filings_with_data") or []
    if not filings:
        return None
    return max(filings, key=lambda f: f.get("tax_prd") or 0)


def org_to_row(summary, org_json, scope):
    o = org_json["organization"]
    f = latest_filing(org_json) or {}
    tax_prd = f.get("tax_prd")  # e.g. 202306
    row = {
        "ein": o["ein"],
        "name": o.get("name"),
        "sub_name": o.get("sort_name") or summary.get("sub_name"),
        "city": o.get("city"),
        "state": o.get("state"),
        "zipcode": o.get("zipcode"),
        "ntee_code": o.get("ntee_code") or summary.get("ntee_code"),
        "ntee_major": _ntee_major(o.get("ntee_code") or summary.get("ntee_code")),
        "subsection_code": o.get("subsection_code"),
        "foundation_code": o.get("foundation_code"),
        "ruling_date": o.get("ruling_date"),
        "tax_period": o.get("tax_period"),
        "tax_year": (tax_prd // 100) if tax_prd else None,
        "latest_object_id": o.get("latest_object_id"),
        "formtype": f.get("formtype"),
        "pdf_url": f.get("pdf_url"),
        "scope": scope,
        "collected_at": dt.datetime.utcnow().isoformat(timespec="seconds"),
    }
    for fld in db.FINANCIAL_FIELDS:
        row[fld] = f.get(fld)
    return row


def _ntee_major(ntee_code):
    """Map a letter NTEE code (e.g. 'P210') to ProPublica's 1-10 major group."""
    if not ntee_code:
        return None
    letter = ntee_code[0].upper()
    groups = {
        "A": 1,
        "B": 2,
        "C": 3, "D": 3,
        "E": 4, "F": 4, "G": 4, "H": 4,
        "I": 5, "J": 5, "K": 5, "L": 5, "M": 5, "N": 5, "O": 5, "P": 5,
        "Q": 6,
        "R": 7, "S": 7, "T": 7, "U": 7, "V": 7, "W": 7,
        "X": 8,
        "Y": 9,
        "Z": 10,
    }
    return groups.get(letter)


def collect(state=None, ntee=None, c_code=None, query=None, max_pages=20, sleep=0.34):
    scope = f"state={state};ntee={ntee};c={c_code};q={query}"
    session = requests.Session()
    conn = db.connect()

    first = search_page(session, 0, state, ntee, c_code, query)
    total = first.get("total_results", 0)
    pages = min(max_pages, -(-total // PAGE_SIZE))  # ceil
    print(f"[scope] {scope}")
    print(f"[search] {total} total results; fetching {pages} of "
          f"{-(-total // PAGE_SIZE)} pages ({pages * PAGE_SIZE} orgs max)")

    added = 0
    for page in range(pages):
        data = first if page == 0 else search_page(session, page, state, ntee, c_code, query)
        for summary in data.get("organizations", []):
            ein = summary["ein"]
            org_json = fetch_org(session, ein)
            time.sleep(sleep)
            if not org_json:
                continue
            db.upsert_org(conn, org_to_row(summary, org_json, scope))
            added += 1
        conn.commit()
        print(f"  page {page + 1}/{pages} done — {added} orgs cached", flush=True)
        if page < pages - 1:
            time.sleep(sleep)

    total_rows = conn.execute("SELECT COUNT(*) FROM orgs").fetchone()[0]
    conn.close()
    print(f"[done] {added} orgs from this scope; {total_rows} total in {db.DB_PATH.name}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Collect nonprofits from ProPublica into SQLite.")
    p.add_argument("--state", help="2-letter state code, e.g. NM")
    p.add_argument("--ntee", type=int, choices=range(1, 11), help="NTEE major group 1-10")
    p.add_argument("--c-code", type=int, default=3, dest="c_code",
                   help="501(c) subsection code (default 3 = charities)")
    p.add_argument("--query", help="free-text search")
    p.add_argument("--max-pages", type=int, default=20,
                   help="cap pages fetched (25 orgs/page); guards against huge pulls")
    p.add_argument("--sleep", type=float, default=0.34, help="seconds between API calls")
    args = p.parse_args(argv)

    if not any([args.state, args.ntee, args.query]):
        p.error("give at least one of --state, --ntee, or --query")
    collect(args.state, args.ntee, args.c_code, args.query, args.max_pages, args.sleep)


if __name__ == "__main__":
    sys.exit(main())
