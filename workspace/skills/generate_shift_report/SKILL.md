---
name: generate_shift_report
description: Generates a structured 8-hour shift handover report at each shift change (Day 06:00, Afternoon 14:00, Night 22:00). Queries errors, maintenance, failures, and machine status from the database, then formats and posts the report to the channel. Can also be triggered manually by a supervisor at any time.
user-invocable: true
---

# Generate Shift Handover Report

Compile and post an 8-hour shift report at shift change times, or on demand from a supervisor.

## When to Run

**On heartbeat:** Run the data script. If `SKIP_NOT_SHIFT_CHANGE` is returned, do nothing and do not post anything.

**When invoked by user** (e.g. "generate shift report", "send shift handover"): Always run — ignore the shift-boundary check.

Shift boundaries: **06:00, 14:00, 22:00** (based on database reference time, not wall clock).

## Database

Path: `/data/workspace/millbrain.db`

Tables queried: `live_errors` (or `errors`), `live_telemetry` (or `telemetry`), `maintenance`, `failures`, `machines`

## Script

Run exactly as written. The script determines shift timing, collects all data, and prints structured output. Substitute `FORCE=False` with `FORCE=True` only when the user has explicitly requested the report outside of a shift boundary.

```bash
python3 << 'PYEOF'
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

DB    = '/data/workspace/millbrain.db'
FORCE = False   # set True when user explicitly requests the report

AVG_CYCLES   = {'comp1': 61.1, 'comp2': 57.2, 'comp3': 62.0, 'comp4': 61.6}
SHIFT_HOURS  = {6: 'Day (06:00–14:00)', 14: 'Afternoon (14:00–22:00)', 22: 'Night (22:00–06:00)'}
MODEL_SECTION = {'model1': 'Wet End', 'model2': 'Dry End', 'model3': 'Stock Prep', 'model4': 'Utilities'}

conn = sqlite3.connect(DB)

# Resolve live vs static tables
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
has_live_e = 'live_errors'    in tables and conn.execute('SELECT COUNT(*) FROM live_errors').fetchone()[0]    > 0
has_live_t = 'live_telemetry' in tables and conn.execute('SELECT COUNT(*) FROM live_telemetry').fetchone()[0] > 0
e_tbl = 'live_errors'    if has_live_e else 'errors'
t_tbl = 'live_telemetry' if has_live_t else 'telemetry'

# Reference "now" = latest datetime in the active telemetry table
ref_str = conn.execute(f'SELECT MAX(datetime) FROM {t_tbl}').fetchone()[0]
if not ref_str:
    print('ERROR: no telemetry data found')
    conn.close()
    exit(1)

ref = datetime.fromisoformat(ref_str)

# Shift boundary check (heartbeat mode only)
if not FORCE:
    if ref.hour not in SHIFT_HOURS or ref.minute >= 15:
        print('SKIP_NOT_SHIFT_CHANGE')
        conn.close()
        exit(0)

# Determine shift window
shift_label = SHIFT_HOURS.get(ref.hour, f'{ref.hour:02d}:00 shift')
shift_end   = ref.replace(minute=0, second=0, microsecond=0)
shift_start = shift_end - timedelta(hours=8)
shift_start_str = shift_start.strftime('%Y-%m-%d %H:%M:%S')
shift_end_str   = shift_end.strftime('%Y-%m-%d %H:%M:%S')

print(f'SHIFT={shift_label}')
print(f'DATE={ref.strftime("%Y-%m-%d")}')
print(f'WINDOW={shift_start_str} → {shift_end_str}')
print(f'SOURCE_TABLES={e_tbl},{t_tbl}')
print()

# ── Errors during shift ────────────────────────────────────────────────────
errors = conn.execute(f'''
    SELECT datetime, machineID, errorID FROM {e_tbl}
    WHERE datetime > ? AND datetime <= ?
    ORDER BY datetime ASC
''', (shift_start_str, shift_end_str)).fetchall()

print(f'ERRORS_COUNT={len(errors)}')
for dt, mid, eid in errors:
    print(f'ERROR {dt[:16]} | Machine {mid} | {eid}')
print()

# ── Maintenance completed during shift ────────────────────────────────────
maint = conn.execute('''
    SELECT datetime, machineID, comp FROM maintenance
    WHERE datetime > ? AND datetime <= ?
    ORDER BY datetime ASC
''', (shift_start_str, shift_end_str)).fetchall()

print(f'MAINTENANCE_COUNT={len(maint)}')
for dt, mid, comp in maint:
    print(f'MAINT {dt[:16]} | Machine {mid} | {comp}')
print()

# ── Failures during shift ─────────────────────────────────────────────────
fails = conn.execute('''
    SELECT datetime, machineID, failure FROM failures
    WHERE datetime > ? AND datetime <= ?
    ORDER BY datetime ASC
''', (shift_start_str, shift_end_str)).fetchall()

print(f'FAILURES_COUNT={len(fails)}')
for dt, mid, comp in fails:
    print(f'FAILURE {dt[:16]} | Machine {mid} | {comp}')
print()

# ── Machines with errors during shift (for status summary) ────────────────
alarmed = {mid for _, mid, _ in errors}
print(f'MACHINES_WITH_ALARMS={sorted(alarmed)}')
print()

# ── Upcoming maintenance — machines >85% through replacement cycle ─────────
print('APPROACHING_INTERVAL:')
for comp, avg in AVG_CYCLES.items():
    lo_threshold = avg * 0.85
    hi_threshold = avg * 3.0   # exclude machines with no prior history in dataset
    rows = conn.execute('''
        SELECT m.machineID, m.model,
               MAX(maint.datetime) as last_replaced,
               CAST(julianday(?) - julianday(MAX(maint.datetime)) AS INTEGER) as days_since
        FROM machines m
        JOIN maintenance maint ON m.machineID = maint.machineID AND maint.comp = ?
        WHERE maint.datetime <= ?
        GROUP BY m.machineID
        HAVING days_since BETWEEN ? AND ?
        ORDER BY days_since DESC
        LIMIT 10
    ''', (shift_end_str, comp, shift_end_str, lo_threshold, hi_threshold)).fetchall()
    for mid, model, last_rep, days in rows:
        overdue = days - avg
        flag = 'OVERDUE' if overdue > 0 else 'APPROACHING'
        print(f'  {flag} {comp} | Machine {mid} ({model}/{MODEL_SECTION.get(model,"")}) | {days}d since replacement (avg {avg}d)')
print()

# ── Summary stats ──────────────────────────────────────────────────────────
high_conf_errors = set()
for _, mid, eid in errors:
    # error1→comp1 95.8%, error2/3→comp2 98.8%, error4→comp3 97.7%, error5→comp4 98.3%
    # All above 80% threshold — treat active errors with overdue components as high-confidence
    high_conf_errors.add(mid)

print(f'SUMMARY_ERRORS={len(errors)}')
print(f'SUMMARY_MAINT={len(maint)}')
print(f'SUMMARY_FAILURES={len(fails)}')
print(f'SUMMARY_MACHINES_ALARMED={len(alarmed)}')

conn.close()
PYEOF
```

## How to Use the Output

Read every line of script output. Then compose and post the shift report using this structure. Fill in all `{placeholder}` fields from the script output. Leave human-only fields (supervisor names, production targets, safety incidents, process/quality notes, utilities) as blank lines or explicit `[Supervisor to complete]` markers — never invent them.

---

```
MILLBRAIN SHIFT HANDOVER REPORT
Paper Manufacturing Plant — Generated by MillBrain
══════════════════════════════════════════════════

SHIFT INFORMATION
─────────────────
Shift Period     : {SHIFT= value}
Date             : {DATE= value}
Window           : {WINDOW= value}
Outgoing Supervisor : [Supervisor to complete]
Incoming Supervisor : [Supervisor to complete]
Handover Time       : [Supervisor to complete]

ERRORS AND ALARMS THIS SHIFT ({ERRORS_COUNT})
──────────────────────────────────────────────
{List each ERROR line as: Time | Machine ID | Error Code}
{If none: "No alarms recorded during this shift."}

Machines alarmed : {MACHINES_WITH_ALARMS}
High-confidence alerts (≥80%) issued : {count — estimate based on errors with overdue components}
Maintenance completed this shift      : {MAINTENANCE_COUNT}
Confirmed failures this shift         : {FAILURES_COUNT}

MAINTENANCE COMPLETED THIS SHIFT ({MAINTENANCE_COUNT})
───────────────────────────────────────────────────────
{List each MAINT line as: Time | Machine ID | Component replaced}
{If none: "No maintenance records logged during this shift."}

CONFIRMED FAILURES THIS SHIFT ({FAILURES_COUNT})
─────────────────────────────────────────────────
{List each FAILURE line as: Time | Machine ID | Component}
{If none: "No failures recorded during this shift."}

UPCOMING MAINTENANCE — APPROACHING OR OVERDUE
──────────────────────────────────────────────
{List each APPROACHING_INTERVAL line. Group by OVERDUE first, then APPROACHING.}
{If none: "No components approaching replacement interval."}

SAFETY
──────
LOTO applied during shift      : [Supervisor to complete]
Injuries / near misses         : [Supervisor to complete]
Any LOTO remaining active      : [Supervisor to complete]

NOTES FOR INCOMING SHIFT
─────────────────────────
{Write 2–4 sentences summarising: what alarmed, what was actioned, what to watch.
 Be specific about machine IDs and components. Do not repeat the tables above —
 focus on what the incoming shift needs to know and do.}
[Outgoing Supervisor to add any process/quality/personnel notes below]

══════════════════════════════════════════════════
MillBrain auto-generated report — supervisor review required before filing.
Data source: {SOURCE_TABLES= value}
══════════════════════════════════════════════════
```

## After Posting

State: "Shift report posted. Supervisors should complete the safety, production, and process sections before filing."

Do not wait for supervisor acknowledgement — post and move on.
