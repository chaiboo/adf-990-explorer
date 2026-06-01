"""Shared reference data and field labels for the ProPublica 990 explorer."""

# ProPublica search.json `ntee[id]` major-group codes (1-10).
NTEE_MAJOR = {
    1: "Arts, Culture & Humanities",
    2: "Education",
    3: "Environment & Animals",
    4: "Health",
    5: "Human Services",
    6: "International, Foreign Affairs",
    7: "Public, Societal Benefit",
    8: "Religion Related",
    9: "Mutual/Membership Benefit",
    10: "Unknown / Unclassified",
}

# 501(c) subsection codes accepted by search.json `c_code[id]`.
C_CODES = {
    3: "501(c)(3) — Charitable / Educational",
    4: "501(c)(4) — Social Welfare",
    6: "501(c)(6) — Business League",
    # The API accepts 1..29; these are the ones that matter for ADF targeting.
}

# IRS filing form types as surfaced in ProPublica `filings_with_data[].formtype`.
# Only formtype 0 (full 990) carries TotalEmployeeCnt in the e-file XML.
FORMTYPE = {0: "990", 1: "990-EZ", 2: "990-PF"}

US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
]

# Human-readable labels for the cryptic IRS field names we store/expose.
FIELD_LABELS = {
    "emp_count": "Employees (W-3 headcount)",
    "volunteers": "Volunteers",
    "infotech_amt": "Information technology expense ($)",
    "totrevenue": "Total revenue ($)",
    "totfuncexpns": "Total functional expenses ($)",
    "totassetsend": "Total assets, EOY ($)",
    "totliabend": "Total liabilities, EOY ($)",
    "totnetassetend": "Net assets, EOY ($)",
    "totcntrbgfts": "Contributions & grants ($)",
    "totprgmrevnue": "Program service revenue ($)",
    "invstmntinc": "Investment income ($)",
    "compnsatncurrofcr": "Officer compensation ($)",
    "othrsalwages": "Other salaries & wages ($)",
    "pct_compnsatncurrofcr": "Officer comp as % of expenses",
}

# IRS e-file XML namespace.
EFILE_NS = "http://www.irs.gov/efile"
