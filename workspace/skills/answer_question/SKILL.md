---
name: answer_question
description: Catch-all skill for operator and technician questions about machine history, sensor ranges, maintenance records, error counts, procedures, or past incidents. Decides whether to query the database, search the knowledge base, or both — then synthesises a direct answer with the source cited. Use this for any free-form question that does not trigger a specific diagnostic skill.
user-invocable: true
---

# Answer Operator Question

Handle a general question from an operator or technician. Retrieve the answer from the database, the knowledge base, or both — never guess.

## Step 1 — Classify the Question

Read the question and decide which sources you need:

| Question type | Examples | Source |
|---------------|----------|--------|
| Machine or component history | "When was comp2 last replaced on Machine 47?" | Database |
| Error counts or trends | "How many errors has Machine 22 had this month?" | Database |
| Current or recent sensor readings | "What was the last voltage reading on Machine 5?" | Database |
| Normal operating ranges or specs | "What is the normal pressure range for model3?" | RAG or database |
| Procedures and safety | "What is the lockout procedure for the press section?" | RAG |
| Past incident reports | "What happened last time we had a vibration issue on Machine 12?" | RAG + database |
| Combined context question | "Should we be worried about Machine 33's pressure trend?" | Both |

Use **both** when the question requires factual data from the DB plus procedural or historical context from the docs.

---

## Step 2 — Database Path and Schema

Path inside container: `/data/workspace/millbrain.db`

**Run queries with:**
```bash
sqlite3 /data/workspace/millbrain.db "<SQL here>"
```

Or for multi-line queries:
```bash
sqlite3 /data/workspace/millbrain.db << 'SQL'
SELECT ...;
SQL
```

**Schema reference:**

```
machines    (machineID, model, age)
telemetry   (datetime, machineID, volt, rotate, pressure, vibration)
errors      (datetime, machineID, errorID)
maintenance (datetime, machineID, comp)
failures    (datetime, machineID, failure)
```

All `datetime` columns are ISO-8601 text strings — use `datetime()` and string comparison for filtering.

**Common query patterns:**

```sql
-- Last N records for a machine
SELECT datetime, comp FROM maintenance
WHERE machineID = 47
ORDER BY datetime DESC LIMIT 5;

-- Error count in a date range
SELECT errorID, COUNT(*) AS count FROM errors
WHERE machineID = 22
  AND datetime >= '2015-11-01'
  AND datetime <  '2015-12-01'
GROUP BY errorID
ORDER BY count DESC;

-- Most recent telemetry reading
SELECT datetime, volt, rotate, pressure, vibration FROM telemetry
WHERE machineID = 5
ORDER BY datetime DESC LIMIT 1;

-- Days since last replacement of a specific component
SELECT
  comp,
  MAX(datetime) AS last_replaced,
  CAST(julianday((SELECT MAX(datetime) FROM maintenance)) - julianday(MAX(datetime)) AS INTEGER) AS days_since
FROM maintenance
WHERE machineID = 47 AND comp = 'comp2';
```

---

## Step 3 — Knowledge Base Path and Command

The RAG search runs as an HTTP API on the WSL host (the container lacks the embedding
dependencies). It must be running before knowledge-base queries will work:

```bash
# On WSL host if not already started
source ~/millbrain/venv_millbrain/bin/activate && python ~/millbrain/scripts/search_api.py
```

**Run searches with** (URL-encode spaces as `+`):
```bash
curl -s "http://localhost:5555/search?q=<url-encoded-query>" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for i, r in enumerate(data['results'], 1):
    print(f\"Result {i}  |  Score: {r['score']:.3f}\")
    print(f\"  Source  : {r['source']}\")
    print(f\"  Section : {r['section']}\")
    print(f\"  {r['preview']}\")
    print()
"
```

Scores above 0.60 are strong matches; below 0.45, note that no closely matching documentation was found.

**Phrase queries as descriptions of what you are looking for:**

| Operator question | RAG query to use |
|-------------------|-----------------|
| "What is the lockout procedure?" | `"lockout tagout procedure steps energy isolation"` |
| "What happened with vibration on Machine 12?" | `"past incidents vibration excess comp3 refiner"` |
| "Normal pressure range for model3?" | `"model3 equipment spec normal pressure range"` |
| "How do we diagnose a rotation fault?" | `"rotation fault comp2 bearing diagnosis steps"` |

---

## Step 4 — Synthesise and Respond

Write a direct answer in plain text. Structure:

1. **Answer** — state the fact or recommendation clearly in 1–3 sentences
2. **Detail** — include relevant numbers, dates, or procedure steps as needed
3. **Source** — end with a source line

Source line format:
- For database answers: `Source: millbrain.db — {table name}`
- For RAG answers: `Source: {document filename(s)}`
- For combined: `Sources: millbrain.db — {table}, {document filename}`

**If the answer cannot be found:**

Say explicitly: "I could not find an answer to that in the database or knowledge base." Then state what you checked. Do not estimate or invent values.

---

## Examples

**"When was comp2 last replaced on Machine 47?"**
→ Query `maintenance` table. Return the date and how many days ago that was (relative to DB max datetime). Source: `millbrain.db — maintenance`.

**"What is the normal pressure range for model3?"**
→ Query `SENSOR_NORMALS` from knowledge: pressure p5–p95 for model3 is 83.69–118.74 PSI. This is hardcoded in the scoring logic; also verifiable via `equipment_spec_model3.md`. Source: `equipment_spec_model3.md`.

**"What happened last time we had a vibration issue on Machine 12?"**
→ Query `errors` and `failures` tables for Machine 12 error4 history. Also search RAG for `"past incidents vibration excess Machine 12"`. Combine: report the dates from DB, plus any incident narrative found in docs. Sources: `millbrain.db — errors, failures`, `past_incidents.md`.

**"How many errors has Machine 22 had this month?"**
→ Query `errors` table with the current month range. Report total count and breakdown by errorID. Note: "this month" means the most recent full month present in the database, not the current wall-clock month (the dataset ends early 2016). Source: `millbrain.db — errors`.
