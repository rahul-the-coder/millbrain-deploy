---
name: search_sop
description: Search the MillBrain RAG knowledge base for troubleshooting procedures, equipment specs, safety requirements, or past incident reports. Call this before responding to any operator alarm — retrieve the relevant documentation first, then formulate your recommendation. Always cite the source document in your response.
user-invocable: true
---

# Search Knowledge Base

Retrieve relevant documentation from the MillBrain vector store before responding to an alarm or operator question.

## When to Call This

- An error code fires and you need the troubleshooting procedure for it
- Maintenance is being planned and you need the lockout/tagout procedure
- You want to check whether a similar failure has occurred on this or other machines before
- An operator asks how to diagnose a specific symptom

## How It Works

The embedding model (`BAAI/bge-small-en-v1.5`) and ChromaDB are not available inside the
container. A lightweight search API server runs on the WSL host and is reachable from the
container via `localhost:5555`. Start it before using this skill:

```bash
# On the WSL host (separate terminal)
source ~/millbrain/venv_millbrain/bin/activate
python ~/millbrain/scripts/search_api.py
```

Verify it is running:
```bash
curl "http://localhost:5555/health"
# → {"chunks": 134, "status": "ok"}
```

## Command

URL-encode the query (replace spaces with `+`):

```bash
curl -s "http://localhost:5555/search?q=<url-encoded-query>" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for i, r in enumerate(data['results'], 1):
    print(f\"Result {i}  |  Score: {r['score']:.3f}\")
    print(f\"  Source  : {r['source']}\")
    print(f\"  Title   : {r['title']}\")
    print(f\"  Section : {r['section']}\")
    print(f\"  {chr(9472)*60}\")
    print(f\"  {r['preview']}\")
    print()
"
```

The BGE query prefix is added automatically by the server — do not add it yourself.

If the server is not running, you will get `curl: (7) Failed to connect`. Start it on the host
and retry — do not guess or skip the knowledge base lookup.

## How to Write a Good Query

Phrase queries as a description of what you are looking for, not a keyword list. The search is semantic — longer, specific phrases retrieve better results than single words.

| Situation | Good query |
|-----------|------------|
| error1 fired, need diagnosis steps | `"voltage anomaly troubleshooting comp1 VFD motor"` |
| error2/error3 both active | `"comp2 bearing rotation fault pressure deviation"` |
| maintenance about to happen | `"lockout tagout procedure motor replacement safety"` |
| want precedent for this failure | `"past incidents comp2 failure bearing replacement"` |
| need refiner vibration spec | `"refiner vibration limits ISO 10816 normal range"` |

## Output

The script prints three results in this format:

```
Result 1  |  Score: 0.74
  Source  : error1_voltage_anomaly.md
  Title   : Error 1 — Voltage Anomaly (comp1)
  Section : Diagnosis Steps
  ────────────────────────────────────────────────────────────
  <400-character preview of the chunk>
```

Score is cosine similarity (0–1). Results above 0.60 are strong matches. Below 0.45, the knowledge base may not have directly relevant content — say so.

## How to Use the Results

1. Read all three chunks before formulating your response.
2. Use the content to inform your recommendation — do not quote it verbatim at length.
3. Always end your response with a **Sources** line citing the document filenames:
   > Sources: `error1_voltage_anomaly.md`, `lockout_tagout_procedure.md`
4. If the top score is below 0.45, note: "No closely matching documentation found — recommendation is based on general knowledge."
