---
name: check_sensors
description: Called when an error is detected on a machine. Takes a machineID, pulls the last 24 hours of telemetry, looks up the machine model, then compares each sensor reading against the normal operating range for that model. Returns a plain-text summary showing current value, normal range, and NORMAL / HIGH / LOW status for each sensor.
user-invocable: true
---

# Check Sensors

Run when an alarm fires on a specific machine. Assess whether sensor readings are contributing to the fault.

## Input

You will receive a `machineID` (integer, e.g. `42`). Use it exactly as given in all queries.

## Database

Path inside container: `/data/workspace/millbrain.db`

## Normal Ranges by Model (p5–p95 from fleet data)

| Model  | Volt (V)        | Rotate (RPM)    | Pressure (PSI)  | Vibration (VIU) |
|--------|-----------------|-----------------|-----------------|-----------------|
| model1 | 145.54 – 196.63 | 357.82 – 531.43 | 83.85 – 120.94  | 31.88 – 49.55   |
| model2 | 145.57 – 196.57 | 358.81 – 531.57 | 83.81 – 120.92  | 31.87 – 49.39   |
| model3 | 145.67 – 196.56 | 358.59 – 531.28 | 83.69 – 118.74  | 31.88 – 49.39   |
| model4 | 145.61 – 196.47 | 358.94 – 531.23 | 83.59 – 118.77  | 31.83 – 49.28   |

These are exact values — use them as-is in the threshold logic.

## Steps

Run the script below, substituting the actual machineID for `<MACHINE_ID>`.

```bash
python3 << 'PYEOF'
import sqlite3

DB = '/data/workspace/millbrain.db'
MACHINE_ID = <MACHINE_ID>

NORMALS = {
    "model1": {"volt": (145.54, 196.63), "rotate": (357.82, 531.43), "pressure": (83.85, 120.94), "vibration": (31.88, 49.55)},
    "model2": {"volt": (145.57, 196.57), "rotate": (358.81, 531.57), "pressure": (83.81, 120.92), "vibration": (31.87, 49.39)},
    "model3": {"volt": (145.67, 196.56), "rotate": (358.59, 531.28), "pressure": (83.69, 118.74), "vibration": (31.88, 49.39)},
    "model4": {"volt": (145.61, 196.47), "rotate": (358.94, 531.23), "pressure": (83.59, 118.77), "vibration": (31.83, 49.28)},
}

conn = sqlite3.connect(DB)

# Use live_telemetry if the replay simulator is running, else fall back to telemetry
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
has_live = 'live_telemetry' in tables and conn.execute('SELECT COUNT(*) FROM live_telemetry').fetchone()[0] > 0
tbl = 'live_telemetry' if has_live else 'telemetry'

# Look up machine model
machine = conn.execute(
    'SELECT model, age FROM machines WHERE machineID = ?', (MACHINE_ID,)
).fetchone()

if not machine:
    print(f'ERROR: machineID {MACHINE_ID} not found in machines table')
    conn.close()
    exit(1)

model, age = machine
ranges = NORMALS.get(model, {})
print(f'SOURCE_TABLE={tbl}')

# Last 24h of telemetry — average each sensor across that window
row = conn.execute(
    f'''
    SELECT
        AVG(volt)      AS avg_volt,
        AVG(rotate)    AS avg_rotate,
        AVG(pressure)  AS avg_pressure,
        AVG(vibration) AS avg_vibration,
        MAX(datetime)  AS latest_reading,
        COUNT(*)       AS reading_count
    FROM {tbl}
    WHERE machineID = ?
      AND datetime >= datetime((SELECT MAX(datetime) FROM {tbl} WHERE machineID = ?), '-24 hours')
    ''',
    (MACHINE_ID, MACHINE_ID)
).fetchone()

conn.close()

if not row or row[4] is None:
    print(f'ERROR: no telemetry found for machineID {MACHINE_ID}')
    exit(1)

avg_volt, avg_rotate, avg_pressure, avg_vibration, latest_dt, count = row

sensors = {
    "volt":      avg_volt,
    "rotate":    avg_rotate,
    "pressure":  avg_pressure,
    "vibration": avg_vibration,
}

def status(val, lo, hi):
    if val < lo:  return "LOW"
    if val > hi:  return "HIGH"
    return "NORMAL"

print(f'Machine {MACHINE_ID} | Model: {model} | Age: {age} years')
print(f'Latest reading: {latest_dt} ({count} readings in window)')
print()
print(f'{"Sensor":<12} {"Value":>8}  {"Normal Range":>22}  Status')
print('-' * 58)
for sensor, val in sensors.items():
    lo, hi = ranges.get(sensor, (None, None))
    if lo is None:
        print(f'{sensor:<12} {"N/A":>8}  {"no range data":>22}  UNKNOWN')
    else:
        s = status(val, lo, hi)
        print(f'{sensor:<12} {val:>8.2f}  {f"{lo} – {hi}":>22}  {s}')
PYEOF
```

## Output Format

Report the script output verbatim, then add a one-sentence summary:

- If all sensors are NORMAL: "All sensors within normal operating range."
- If any are HIGH or LOW: "Sensor anomalies detected — [list affected sensors]. Recommend cross-checking with active error codes."
- If the script returns an ERROR line: Report the error and stop.
