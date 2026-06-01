"""Enrich cached orgs with employee count / volunteers / infotech from IRS 990 XML.

The ProPublica API does NOT expose employee count. It lives only in the raw
IRS 990 e-file XML, distributed as big yearly ZIPs on irs.gov. Those ZIPs serve
HTTP range requests, so we use `remotezip` to pull ONLY the candidate filings'
XML entries instead of downloading multi-GB archives.

IRS files are organized by PROCESSING year = first 4 digits of the object_id,
not the tax year. Only full 990s (formtype 0) carry TotalEmployeeCnt; 990-EZ
and 990-PF are skipped.

Usage:
    python enrich.py                 # enrich everything not yet tried
    python enrich.py --limit 50      # test on a small batch
    python enrich.py --year 2026     # only candidates processed in 2026
"""

import argparse
import re
import struct
import sys
import xml.etree.ElementTree as ET

import inflate64
import requests
from remotezip import RemoteZip

import db

HEADERS = {"User-Agent": "adf-bd-explorer/1.0 (research; contact rb12295@gmail.com)"}
DOWNLOADS_PAGE = "https://www.irs.gov/charities-non-profits/form-990-series-downloads"
ZIP_HREF_RE = re.compile(r'href="(https://apps\.irs\.gov/pub/epostcard/990/xml/(\d{4})/[^"]+\.zip)"')


def zip_urls_for_year(session, year):
    """Scrape the IRS downloads page for all ZIP part URLs for a processing year."""
    r = session.get(DOWNLOADS_PAGE, headers=HEADERS, timeout=60)
    r.raise_for_status()
    urls = [u for (u, y) in ZIP_HREF_RE.findall(r.text) if int(y) == year]
    return sorted(set(urls))


def index_year(conn, session, year):
    """Populate xml_index for a year: object_id -> zip_url. Cached; runs once/year."""
    already = conn.execute(
        "SELECT COUNT(*) FROM xml_index WHERE year=?", (year,)
    ).fetchone()[0]
    if already:
        print(f"[index] year {year} already indexed ({already} entries)")
        return
    urls = zip_urls_for_year(session, year)
    if not urls:
        print(f"[index] WARNING: no ZIP parts found for year {year} on IRS page")
        return
    print(f"[index] year {year}: listing {len(urls)} ZIP parts (central dirs only)...")
    for i, url in enumerate(urls, 1):
        try:
            with RemoteZip(url) as z:
                names = z.namelist()
        except Exception as e:  # noqa: BLE001
            print(f"  part {i}/{len(urls)} FAILED {url.rsplit('/', 1)[-1]}: {e}")
            continue
        rows = []
        for n in names:
            m = re.match(r"(\d+)_public\.xml$", n.rsplit("/", 1)[-1])
            if m:
                rows.append((m.group(1), year, url))
        conn.executemany(
            "INSERT OR IGNORE INTO xml_index(object_id, year, zip_url) VALUES (?,?,?)",
            rows,
        )
        conn.commit()
        print(f"  part {i}/{len(urls)} {url.rsplit('/', 1)[-1]}: {len(rows)} filings",
              flush=True)


def read_entry(z, session, zip_url, entry):
    """Read one ZIP entry. Many IRS entries use Deflate64 (method 9), which
    stdlib zipfile/remotezip can't decompress — for those we range-fetch the raw
    compressed bytes and inflate them with inflate64."""
    info = z.getinfo(entry)
    if info.compress_type != 9:
        return z.read(entry)  # stored or standard deflate
    base = info.header_offset
    hdr = session.get(zip_url, headers={"Range": f"bytes={base}-{base + 29}"},
                      timeout=60).content
    name_len = struct.unpack("<H", hdr[26:28])[0]
    extra_len = struct.unpack("<H", hdr[28:30])[0]
    start = base + 30 + name_len + extra_len
    end = start + info.compress_size - 1
    comp = session.get(zip_url, headers={"Range": f"bytes={start}-{end}"},
                       timeout=60).content
    return inflate64.Inflater().inflate(comp)


def _txt(elem):
    return elem.text.strip() if elem is not None and elem.text else None


def _domain(raw):
    """Normalize a 990 website string to a bare domain, e.g. 'deadwoodhistory.com'."""
    if not raw:
        return None
    s = raw.strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = s.split("/")[0].split("?")[0].strip()
    if not s or "." not in s or " " in s:
        return None  # junk like 'n/a', 'none', 'see schedule o'
    return s


def parse_filing_xml(data):
    """Extract (emp_count, volunteers, infotech_amt, website) from a 990 XML string."""
    root = ET.fromstring(data)

    def find_local(name):
        for el in root.iter():
            if el.tag.rsplit("}", 1)[-1] == name:
                return el
        return None

    emp = _txt(find_local("TotalEmployeeCnt"))
    vol = _txt(find_local("TotalVolunteersCnt"))

    infotech = None
    grp = find_local("InformationTechnologyGrp")  # current schema
    if grp is not None:
        for child in grp:
            if child.tag.rsplit("}", 1)[-1] == "TotalAmt":
                infotech = _txt(child)
                break
    if infotech is None:
        infotech = _txt(find_local("InformationTechnology"))  # legacy schema

    website = _domain(_txt(find_local("WebsiteAddressTxt"))    # current schema
                      or _txt(find_local("WebSite"))           # legacy
                      or _txt(find_local("WebAddress")))

    to_int = lambda v: int(v) if v and v.lstrip("-").isdigit() else None
    to_num = lambda v: float(v) if v and v.lstrip("-").replace(".", "", 1).isdigit() else None
    return to_int(emp), to_int(vol), to_num(infotech), website


def candidates(conn, year=None, limit=None, redo=False):
    sql = ("SELECT ein, latest_object_id FROM orgs "
           "WHERE latest_object_id IS NOT NULL AND formtype = 0 ")
    if not redo:
        sql += "AND enrich_status IS NULL "
    params = []
    if year:
        sql += "AND CAST(substr(latest_object_id,1,4) AS INTEGER) = ? "
        params.append(year)
    sql += "ORDER BY ein"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql, params).fetchall()


def enrich(year=None, limit=None, redo=False):
    conn = db.connect()
    session = requests.Session()

    rows = candidates(conn, year, limit, redo)
    if not rows:
        print("[enrich] no candidates need enrichment "
              "(need formtype=0 full-990 filers; run collector first)")
        return

    # Which processing years do we need indexed?
    years = sorted({int(r["latest_object_id"][:4]) for r in rows})
    print(f"[enrich] {len(rows)} candidates across processing years {years}")
    for y in years:
        index_year(conn, session, y)

    # Group candidates by their ZIP so we open each RemoteZip once.
    by_zip = {}
    missing = 0
    for r in rows:
        oid = r["latest_object_id"]
        hit = conn.execute(
            "SELECT zip_url FROM xml_index WHERE object_id=?", (oid,)
        ).fetchone()
        if not hit:
            conn.execute("UPDATE orgs SET enrich_status='no_xml' WHERE ein=?", (r["ein"],))
            missing += 1
            continue
        by_zip.setdefault(hit["zip_url"], []).append((r["ein"], oid))
    conn.commit()
    if missing:
        print(f"[enrich] {missing} filings had no matching XML entry (marked no_xml)")

    done = ok = 0
    for zip_url, items in by_zip.items():
        try:
            z = RemoteZip(zip_url)
        except Exception as e:  # noqa: BLE001
            print(f"  open failed {zip_url.rsplit('/',1)[-1]}: {e}")
            continue
        with z:
            for ein, oid in items:
                try:
                    data = read_entry(z, session, zip_url, f"{oid}_public.xml")
                    emp, vol, it, web = parse_filing_xml(data)
                    conn.execute(
                        "UPDATE orgs SET emp_count=?, volunteers=?, infotech_amt=?, "
                        "website=?, enrich_status='ok' WHERE ein=?",
                        (emp, vol, it, web, ein),
                    )
                    ok += 1
                except KeyError:
                    conn.execute("UPDATE orgs SET enrich_status='no_xml' WHERE ein=?", (ein,))
                except Exception as e:  # noqa: BLE001
                    conn.execute("UPDATE orgs SET enrich_status='error' WHERE ein=?", (ein,))
                    print(f"    {ein} parse error: {e}")
                done += 1
                if done % 25 == 0:
                    conn.commit()
                    print(f"  {done}/{len(rows)} processed ({ok} ok)", flush=True)
        conn.commit()

    conn.close()
    print(f"[done] processed {done}, {ok} enriched with employee data")


def main(argv=None):
    p = argparse.ArgumentParser(description="Enrich orgs with IRS 990 employee data.")
    p.add_argument("--year", type=int, help="only candidates with this processing year")
    p.add_argument("--limit", type=int, help="cap number of candidates (for testing)")
    p.add_argument("--redo", action="store_true", help="re-enrich even if already tried")
    args = p.parse_args(argv)
    enrich(args.year, args.limit, args.redo)


if __name__ == "__main__":
    sys.exit(main())
