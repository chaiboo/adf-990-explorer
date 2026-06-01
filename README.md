# ADF · ProPublica 990 Explorer

An exploratory tool for finding nonprofit business-development targets for the
Applied Data Fellowship. Pull a broad candidate pool into a local cache once,
then **filter it live** — by employee count, revenue, NTEE, geography, IT spend,
governance ratios — without ever being locked into a pre-filtered dataset.

## Why three pieces

ProPublica's search API only filters by text, **state**, **NTEE major group**,
and **501(c) code**. Everything finer is done locally. And ProPublica's filing
summaries **omit employee count** — that field lives only in raw IRS 990 e-file
XML, which we fetch selectively (HTTP range requests) from the IRS bulk ZIPs.

| Step | Script | What it does |
|------|--------|--------------|
| 1. Collect | `collector.py` | Scoped pull from ProPublica → SQLite (`nonprofits.db`): identity, NTEE, geography, revenue/expenses/assets/comp/contributions. |
| 2. Enrich  | `enrich.py`    | Adds **employee count**, volunteers, IT spend from IRS 990 XML. Optional but required for the 40–50 employee filter. |
| 3. Explore | `app.py`       | Streamlit UI with live sliders/filters over the cache. Re-slice infinitely; export CSV. |

> **How the current dataset was built and what "4,870 orgs" means:** see
> [METHODOLOGY.md](METHODOLOGY.md).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Use

```bash
# 1. Collect a candidate pool (repeat with different scopes to grow the cache)
python collector.py --state NM --ntee 2 --c-code 3      # NM education charities
python collector.py --state NM --ntee 4                 # NM health
python collector.py --query "workforce development" --state TX
#   NTEE major groups: 1 Arts  2 Education  3 Environment  4 Health
#   5 Human Services  6 International  7 Public/Societal  8 Religion
#   9 Membership  10 Unknown
#   --max-pages caps the pull (25 orgs/page); default 20 = up to 500 orgs/scope.

# 2. Enrich with employee data (test small first; the year index is cached)
python enrich.py --limit 25      # quick test
python enrich.py                 # everything not yet enriched

# 3. Explore
streamlit run app.py
```

## Notes & caveats

- **Employee count = W-3 headcount** (990 Part I line 5): anyone issued a W-2
  that year counts as 1, regardless of hours. Pair with `othrsalwages` for a
  capacity read. ~40–50 W-3 employees is often a ~25–40 FTE org.
- Only **full 990 filers (formtype 0)** can be enriched. 990-EZ and 990-PF
  (private foundations) don't report employee count and are skipped — their
  `enrich_status` stays unset and they drop out when you require employee data.
- IRS XML is organized by **processing year** (first 4 digits of the object_id),
  not tax year; `enrich.py` handles this automatically.
- Many IRS entries are **Deflate64**-compressed (stdlib `zipfile` can't read
  them); `enrich.py` range-fetches and decompresses those with `inflate64`.
- First enrichment for a given processing year lists that year's ZIP central
  directories once (cached in the `xml_index` table) — subsequent runs are fast.
- Be polite to the APIs: `collector.py` sleeps between calls (`--sleep`).

## Data model

One row per EIN in `orgs` (latest filing with data). Cryptic IRS field names are
kept verbatim and mapped to readable labels in `constants.py:FIELD_LABELS`.
`scope` records which collection run added each org; `collected_at` is the pull
timestamp.
