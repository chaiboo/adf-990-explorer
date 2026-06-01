# Methodology — how the dataset was built

This documents exactly how the cached dataset was assembled and what the headline
numbers mean. **Important:** the 4,870 figure is *not* a vetted list of business-
development leads — it is the number of organizations for which we successfully
retrieved employee / financial / website data. Filtering down to actual targets
(e.g. the 40–50 employee band) happens *after* this, in the explorer UI.

## The collection funnel

| Step | Filter applied | Result |
|------|----------------|--------|
| 1. Source | ProPublica Nonprofit Explorer API (`search.json` + `organizations/{ein}.json`) | — |
| 2. Tax status | 501(c)(3) only (`c_code = 3`) | — |
| 3. Geography | 12 U.S. Census **Midwest** states: IL, IN, IA, KS, MI, MN, MO, NE, ND, OH, SD, WI | — |
| 4. Sector | **All** NTEE categories (no sector filter) | — |
| 5. Depth cap | Up to **500 orgs per state** (top of the API's default result ordering) | **5,525 collected** |
| 6. Form type | Keep **full Form 990** only (`formtype = 0`); excludes 990-PF and 990-EZ, which do not report an employee count | **5,082** |
| 7. Enrichment | Filing's raw IRS 990 XML located in the IRS bulk download and parsed | **4,870 enriched** |

Breakdown of what step 6 dropped: 382 private foundations (990-PF), 11 990-EZ
filers, 50 with other/missing form type. Of the 5,082 full-990 filers, 4,870 were
successfully enriched and 212 had no retrievable XML entry.

The 5,525 collected includes 25 New Mexico records left over from an early
pipeline test; the 5,500 Midwest records are the intended population.

## Per-state collected counts

| State | Orgs | | State | Orgs |
|-------|------|-|-------|------|
| IA | 500 | | NE | 500 |
| IL | 500 | | ND | 500 |
| IN | 500 | | OH | 500 |
| KS | 500 | | SD | 500 |
| MI | **125** | | WI | 500 |
| MN | 500 | | MO | **375** |

## Caveats a reader should know

- **Not a ranked lead list.** 4,870 = "orgs we have data for," not "qualified
  prospects." Apply the explorer's filters (employees, revenue, IT spend, sector)
  to get an actual target list.
- **Sampling, not census.** The 500/state cap takes the *first* 500 in the API's
  default order — not a relevance- or size-ranked sample. **Michigan (125) and
  Missouri (375) fell short** because API pagination dropped out mid-pull; both
  states are under-sampled and should be re-collected before relying on them.
- **Employee count = W-3 headcount** (Form 990 Part I, line 5): everyone issued a
  W-2 that year counts as 1, regardless of hours. It is a headcount, not FTE.
- **Website coverage ~89%** of enriched orgs (4,352 of 4,870); the rest either
  left the 990 website field blank or entered non-URL text, which we discard.
- **Latest filing only.** One row per EIN, using the most recent filing with data;
  filing years vary by org.

## Reproducing it

```bash
pip install -r requirements.txt
./run_midwest.sh          # collects the 12 states, then enriches
streamlit run app.py      # interactive explorer over the result
```
