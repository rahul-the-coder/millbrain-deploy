---
name: monitor_errors
description: Every 15 minutes, check the MillBrain equipment database for new error events since the last run. Report each new error with its timestamp, machine ID, and error code. On first run, set a baseline so we don't flood the channel with historical data. Never report the same error twice.
user-invocable: false
---

# Monitor Equipment Errors

Run on every heartbeat. Query the MillBrain SQLite database for new error events and report them.

## Database

Path inside container: `/data/workspace/millbrain.db`

## State File

Progress is tracked at: `/data/workspace/skills/monitor_errors/state.json`

```json
{ "last_seen_datetime": "2015-12-30T06:00:00" }
```

This holds the `datetime` value of the most recent error already reported. Only errors with a later datetime are new.

## Steps

1. Run the script below exactly as written.
2. Read every line of stdout.
3. Format and post the result as described in **Output Rules**.
4. Do not add commentary or analysis — just report what the script returned.

## Script

The script queries `live_errors` if the replay simulator is running (table exists and has rows),
otherwise falls back to the static `errors` table. The state file and all logic are identical
either way — only the source table changes.

```bash
python3 << 'PYEOF'
import sqlite3, json, os

DB    = '/data/workspace/millbrain.db'
STATE = '/data/workspace/skills/monitor_errors/state.json'

os.makedirs(os.path.dirname(STATE), exist_ok=True)
state = json.load(open(STATE)) if os.path.exists(STATE) else {}

conn = sqlite3.connect(DB)

# Use live_errors if the replay simulator is active, else fall back to errors
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
has_live = 'live_errors' in tables and conn.execute('SELECT COUNT(*) FROM live_errors').fetchone()[0] > 0
tbl = 'live_errors' if has_live else 'errors'
print(f'SOURCE_TABLE={tbl}')

if not state:
    # First run: set baseline to current max so existing data is not replayed
    max_dt = conn.execute(f'SELECT MAX(datetime) FROM {tbl}').fetchone()[0] or '1970-01-01 00:00:00'
    json.dump({'last_seen_datetime': max_dt}, open(STATE, 'w'))
    print(f'INITIALIZED baseline={max_dt}')
else:
    last_seen = state['last_seen_datetime']
    rows = conn.execute(
        f'SELECT datetime, machineID, errorID FROM {tbl} '
        'WHERE datetime > ? ORDER BY datetime ASC',
        (last_seen,)
    ).fetchall()
    if rows:
        json.dump({'last_seen_datetime': rows[-1][0]}, open(STATE, 'w'))
        print(f'FOUND {len(rows)}')
        for dt, mid, eid in rows:
            print(f'{dt} | Machine {mid} | {eid}')
    else:
        print('NO_NEW_ERRORS')

conn.close()
PYEOF
```

## Output Rules

**Script returns `INITIALIZED baseline=<datetime>`**
Report:
> MillBrain monitor initialised. Watching for errors after `<datetime>`. No action needed.

**Script returns `FOUND N` followed by error lines**
Report each error, then a summary line:
```
New Equipment Errors (N)
<datetime> — Machine <machineID>: <errorID>
<datetime> — Machine <machineID>: <errorID>
...

N new error(s) logged since last check.
```

**Script returns `NO_NEW_ERRORS`**
Report:
> No new errors detected.
