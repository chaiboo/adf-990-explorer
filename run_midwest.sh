#!/usr/bin/env bash
# Collect all-sector 501(c)(3) charities across the 12 Census Midwest states,
# then enrich with IRS employee data. Restartable: collector upserts by EIN,
# enrich skips already-tried orgs.
set -u
cd "$(dirname "$0")"
source .venv/bin/activate

STATES="IL IN IA KS MI MN MO NE ND OH SD WI"
MAXPAGES="${1:-20}"   # 20 => up to 500 orgs/state

echo "=== COLLECT (max-pages=$MAXPAGES) $(date) ==="
for st in $STATES; do
  echo "--- $st ---"
  python collector.py --state "$st" --c-code 3 --max-pages "$MAXPAGES"
done

echo "=== ENRICH $(date) ==="
python enrich.py

echo "=== DONE $(date) ==="
python - <<'PY'
import sqlite3
c=sqlite3.connect("nonprofits.db")
tot=c.execute("SELECT COUNT(*) FROM orgs").fetchone()[0]
enr=c.execute("SELECT COUNT(*) FROM orgs WHERE emp_count IS NOT NULL").fetchone()[0]
band=c.execute("SELECT COUNT(*) FROM orgs WHERE emp_count BETWEEN 40 AND 50").fetchone()[0]
print(f"total orgs={tot}  enriched={enr}  in 40-50 emp band={band}")
PY
