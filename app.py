"""Exploratory ProPublica 990 filter UI.

Reads the local SQLite cache built by collector.py (+ enrich.py for employee
data) and lets you slice it live — nothing is pre-filtered, so you never get
stuck with one frozen dataset.

Run:  streamlit run app.py
"""

import pandas as pd
import streamlit as st

import db
from constants import FIELD_LABELS, FORMTYPE, NTEE_MAJOR

st.set_page_config(page_title="ADF · 990 Explorer", layout="wide")


@st.cache_data(ttl=60)
def load():
    conn = db.connect()
    df = pd.read_sql_query("SELECT * FROM orgs", conn)
    conn.close()
    return df


def slider_range(df, col, label, fmt="%d"):
    """Two-handle slider over a numeric column; returns (lo, hi) or None if empty."""
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if s.empty:
        st.caption(f"· {label}: no data yet")
        return None
    lo, hi = float(s.min()), float(s.max())
    if lo == hi:
        st.caption(f"· {label}: all = {lo:,.0f}")
        return (lo, hi)
    return st.slider(label, lo, hi, (lo, hi), format=fmt)


df = load()
st.title("ADF Business-Development · ProPublica 990 Explorer")

if df.empty:
    st.warning(
        "No data yet. Collect some first, e.g.:\n\n"
        "```\npython collector.py --state NM --ntee 4 --c-code 3\n```\n\n"
        "Then (optional, for employee counts):\n```\npython enrich.py\n```"
    )
    st.stop()

enriched = df["emp_count"].notna().sum()
st.caption(
    f"{len(df):,} orgs cached · {enriched:,} have employee data "
    f"({'run `python enrich.py` to fill the rest' if enriched < len(df) else 'fully enriched'})"
)

# ---- Sidebar filters -------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    states = sorted(df["state"].dropna().unique())
    pick_states = st.multiselect("State", states)

    majors = sorted(df["ntee_major"].dropna().unique())
    pick_major = st.multiselect(
        "NTEE major group", majors, format_func=lambda m: f"{int(m)} · {NTEE_MAJOR.get(int(m), '?')}"
    )

    ntee_prefix = st.text_input("NTEE code starts with", help="e.g. 'P' or 'E2'").strip().upper()

    only_enriched = st.checkbox("Only orgs with employee data", value=False)
    only_web = st.checkbox("Only orgs with a website", value=False)
    web_contains = st.text_input("Domain contains", help="e.g. '.org' or 'foundation'").strip().lower()

    st.subheader("People")
    emp = slider_range(df, "emp_count", FIELD_LABELS["emp_count"])
    vol = slider_range(df, "volunteers", FIELD_LABELS["volunteers"])

    st.subheader("Money")
    rev = slider_range(df, "totrevenue", FIELD_LABELS["totrevenue"], "$%d")
    exp = slider_range(df, "totfuncexpns", FIELD_LABELS["totfuncexpns"], "$%d")
    assets = slider_range(df, "totassetsend", FIELD_LABELS["totassetsend"], "$%d")
    it = slider_range(df, "infotech_amt", FIELD_LABELS["infotech_amt"], "$%d")

    st.subheader("Governance")
    pct = slider_range(df, "pct_compnsatncurrofcr", FIELD_LABELS["pct_compnsatncurrofcr"], "%.3f")

    st.subheader("Filing")
    years = sorted(df["tax_year"].dropna().unique())
    pick_years = st.multiselect("Tax year", [int(y) for y in years])
    forms = sorted(df["formtype"].dropna().unique())
    pick_forms = st.multiselect("Form type", forms,
                                format_func=lambda f: FORMTYPE.get(int(f), str(f)))

# ---- Apply filters ---------------------------------------------------------
m = pd.Series(True, index=df.index)
if pick_states:
    m &= df["state"].isin(pick_states)
if pick_major:
    m &= df["ntee_major"].isin(pick_major)
if ntee_prefix:
    m &= df["ntee_code"].fillna("").str.upper().str.startswith(ntee_prefix)
if only_enriched:
    m &= df["emp_count"].notna()
if only_web:
    m &= df["website"].fillna("").str.len().gt(0)
if web_contains:
    m &= df["website"].fillna("").str.lower().str.contains(web_contains)
if pick_years:
    m &= df["tax_year"].isin(pick_years)
if pick_forms:
    m &= df["formtype"].isin(pick_forms)

for col, rng in [("emp_count", emp), ("volunteers", vol), ("totrevenue", rev),
                 ("totfuncexpns", exp), ("totassetsend", assets),
                 ("infotech_amt", it), ("pct_compnsatncurrofcr", pct)]:
    if rng is not None:
        vals = pd.to_numeric(df[col], errors="coerce")
        m &= vals.between(rng[0], rng[1])  # NaN.between -> False, so nulls drop out

out = df[m].copy()

# ---- Results ---------------------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("Matching orgs", f"{len(out):,}")
c2.metric("Median revenue", f"${pd.to_numeric(out['totrevenue'], errors='coerce').median():,.0f}"
          if len(out) else "—")
c3.metric("Median employees",
          f"{pd.to_numeric(out['emp_count'], errors='coerce').median():,.0f}"
          if out["emp_count"].notna().any() else "—")

out["website_url"] = out["website"].apply(
    lambda d: f"https://{d}" if isinstance(d, str) and d else None)
display_cols = ["ein", "name", "website_url", "city", "state", "ntee_code",
                "emp_count", "volunteers", "totrevenue", "totfuncexpns",
                "infotech_amt", "totassetsend", "pct_compnsatncurrofcr",
                "tax_year", "pdf_url"]
st.dataframe(
    out[display_cols].sort_values("totrevenue", ascending=False, na_position="last"),
    use_container_width=True, hide_index=True,
    column_config={
        "website_url": st.column_config.LinkColumn(
            "Website", display_text=r"https://(.*)"),
        "pdf_url": st.column_config.LinkColumn("990 PDF", display_text="open"),
    },
)

st.download_button("Download filtered CSV", out.to_csv(index=False),
                   "adf_targets.csv", "text/csv")
