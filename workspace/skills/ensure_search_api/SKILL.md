---
name: ensure_search_api
description: Heartbeat skill — checks if the RAG search API is running on port 5555. If not, starts it. Runs silently; only reports if it had to restart the API or if startup failed.
user-invocable: false
---

# Ensure Search API

Run on every heartbeat before other skills. Start the Flask search API if it is not running.

## Steps

Run the script below exactly as written.

```bash
bash << 'EOF'
if curl -s http://localhost:5555/health > /dev/null 2>&1; then
  echo "API_STATUS=running"
else
  echo "API_STATUS=starting"
  PYTHONPATH=/data/pypkgs nohup python3 /data/workspace/search_api.py \
    --db /data/workspace/chroma_db \
    > /tmp/search_api.log 2>&1 &
  sleep 5
  if curl -s http://localhost:5555/health > /dev/null 2>&1; then
    echo "API_STARTED=ok"
  else
    echo "API_STARTED=failed"
  fi
fi
EOF
```

## Output Rules

- If `API_STATUS=running` — post nothing. Operate silently.
- If `API_STARTED=ok` — post: "Search API restarted successfully."
- If `API_STARTED=failed` — post: "Search API failed to start. RAG-dependent skills (search_sop, answer_question) will not work. Check /tmp/search_api.log."
