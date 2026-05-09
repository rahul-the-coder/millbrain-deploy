---
name: lookup_maint
description: Look up the full maintenance and failure history for a machine, optionally narrowed to one component. Calculates days since last replacement, total replacements, total failures, and average time between replacements. Use this when you need to know whether a component is overdue or how often it has failed.
user-invocable: true
---

# Look Up Maintenance History

Query the maintenance and failures tables for a specific machine (and optionally one component) and return a structured history summary.

## Input

- `machineID` — required (integer)
- `comp` — optional. One of: `comp1`, `comp2`, `comp3`, `comp4`

If no `comp` is given, summarise all four components for that machine.

## Database

Path inside container: `/data/workspace/millbrain.db`

## Average Replacement Cycles (fleet baseline)

| Component | Avg cycle |
|-----------|-----------|
| comp1     | 61.1 days |
| comp2     | 57.2 days |
| comp3     | 62.0 days |
| comp4     | 61.6 days |

Use these to contextualise whether a component is overdue. Days since last replacement > avg cycle = overdue.

## SQL Queries

Run these exactly. Substitute `<MACHINE_ID>` and, where noted, `<COMP>`.

**All maintenance records for the machine:**
```sql
SELECT datetime, comp
FROM maintenance
WHERE machineID = <MACHINE_ID>
ORDER BY datetime ASC;
```

**Filtered to one component:**
```sql
SELECT datetime, comp
FROM maintenance
WHERE machineID = <MACHINE_ID>
  AND comp = '<COMP>'
ORDER BY datetime ASC;
```

**All failure records for the machine:**
```sql
SELECT datetime, failure
FROM failures
WHERE machineID = <MACHINE_ID>
ORDER BY datetime ASC;
```

**Filtered to one component:**
```sql
SELECT datetime, failure
FROM failures
WHERE machineID = <MACHINE_ID>
  AND failure = '<COMP>'
ORDER BY datetime ASC;
```

## Script

Substitute `<MACHINE_ID>` and set `COMP` to the component name or leave it as `None`.

```bash
python3 << 'PYEOF'
import sqlite3
from datetime import datetime, timedelta

DB         = '/data/workspace/millbrain.db'
MACHINE_ID = <MACHINE_ID>
COMP       = None   # replace with e.g. 'comp1', or leave None for all components

AVG_CYCLES = {"comp1": 61.1, "comp2": 57.2, "comp3": 62.0, "comp4": 61.6}
ALL_COMPS  = ["comp1", "comp2", "comp3", "comp4"]

conn = sqlite3.connect(DB)

# Verify machine exists
machine = conn.execute(
    'SELECT model, age FROM machines WHERE machineID = ?', (MACHINE_ID,)
).fetchone()
if not machine:
    print(f'ERROR: machineID {MACHINE_ID} not found')
    conn.close()
    exit(1)
model, age = machine

# Reference date: max datetime seen in DB (avoids wall-clock confusion with historical data)
ref_dt_str = conn.execute(
    'SELECT MAX(datetime) FROM (SELECT MAX(datetime) AS datetime FROM maintenance UNION ALL SELECT MAX(datetime) FROM failures)'
).fetchone()[0]
ref_dt = datetime.fromisoformat(ref_dt_str) if ref_dt_str else datetime.now()

def analyse_comp(comp):
    maint_rows = conn.execute(
        'SELECT datetime FROM maintenance WHERE machineID = ? AND comp = ? ORDER BY datetime ASC',
        (MACHINE_ID, comp)
    ).fetchall()
    fail_rows = conn.execute(
        'SELECT datetime FROM failures WHERE machineID = ? AND failure = ? ORDER BY datetime ASC',
        (MACHINE_ID, comp)
    ).fetchall()

    maint_dates = [datetime.fromisoformat(r[0]) for r in maint_rows]
    fail_dates  = [datetime.fromisoformat(r[0]) for r in fail_rows]

    total_replacements = len(maint_dates)
    total_failures     = len(fail_dates)
    last_replaced      = maint_dates[-1] if maint_dates else None
    days_since         = (ref_dt - last_replaced).days if last_replaced else None
    avg_cycle          = AVG_CYCLES[comp]
    overdue_by         = (days_since - avg_cycle) if days_since is not None else None

    # Average interval between consecutive replacements
    if len(maint_dates) >= 2:
        intervals = [(maint_dates[i] - maint_dates[i-1]).days for i in range(1, len(maint_dates))]
        avg_interval = sum(intervals) / len(intervals)
    else:
        avg_interval = None

    return {
        "comp":              comp,
        "total_replacements": total_replacements,
        "total_failures":    total_failures,
        "last_replaced":     last_replaced.strftime('%Y-%m-%d %H:%M') if last_replaced else "never",
        "days_since":        days_since,
        "avg_interval":      avg_interval,
        "avg_cycle":         avg_cycle,
        "overdue_by":        overdue_by,
        "maint_dates":       maint_dates,
        "fail_dates":        fail_dates,
    }

def fmt_overdue(r):
    if r["days_since"] is None:
        return "NO HISTORY"
    if r["overdue_by"] is None:
        return ""
    if r["overdue_by"] > 0:
        return f"OVERDUE by {r['overdue_by']:.0f}d"
    else:
        return f"{abs(r['overdue_by']):.0f}d before due"

target_comps = [COMP] if COMP else ALL_COMPS

print(f'Machine {MACHINE_ID} | Model: {model} | Age: {age} years')
print(f'Reference date: {ref_dt.strftime("%Y-%m-%d %H:%M")}')
print()

for comp in target_comps:
    r = analyse_comp(comp)
    print(f'--- {comp.upper()} (avg cycle: {r["avg_cycle"]}d) ---')
    print(f'  Last replaced : {r["last_replaced"]}')
    print(f'  Days since    : {r["days_since"] if r["days_since"] is not None else "N/A"}  {fmt_overdue(r)}')
    print(f'  Replacements  : {r["total_replacements"]}')
    print(f'  Failures      : {r["total_failures"]}')
    if r["avg_interval"] is not None:
        print(f'  Avg interval  : {r["avg_interval"]:.1f}d (based on {r["total_replacements"]} replacements)')
    else:
        print(f'  Avg interval  : N/A (< 2 replacements)')
    if COMP and r["maint_dates"]:
        print()
        print('  Replacement history:')
        for d in r["maint_dates"]:
            print(f'    {d.strftime("%Y-%m-%d %H:%M")}')
    if COMP and r["fail_dates"]:
        print()
        print('  Failure history:')
        for d in r["fail_dates"]:
            print(f'    {d.strftime("%Y-%m-%d %H:%M")}')
    print()

conn.close()
PYEOF
```

## Output Format

Report the script output verbatim. Then add a one-sentence interpretation:

- If any component shows `OVERDUE`: "comp[N] is overdue — replacement should be prioritised."
- If `NO HISTORY`: "No maintenance record found for this component — treat as high risk."
- If all components are within cycle: "All components within expected replacement window."
- If the script returns `ERROR`: Report the error and stop.
