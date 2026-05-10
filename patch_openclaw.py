import json

PROXY_URL = "https://www.dataexpert.io/api/v1/anthropic"
CONFIG_PATH = "/data/openclaw.json"

with open(CONFIG_PATH, "r") as f:
    cfg = json.load(f)

cfg.setdefault("gateway", {}).setdefault("controlUi", {})
cfg["gateway"]["controlUi"]["dangerouslyDisableDeviceAuth"] = True

cfg.setdefault("models", {})
cfg["models"]["mode"] = "merge"
cfg["models"].setdefault("providers", {})
cfg["models"]["providers"]["anthropic"] = {
    "baseUrl": PROXY_URL,
    "apiKey": "${DATAEXPERT_API_KEY}",
    "auth": "api-key",
    "api": "anthropic-messages",
    "headers": {
        "x-session-id": "openclaw-workshop",
    },
    "models": [
        {
            "id": "claude-sonnet-4-6",
            "name": "Claude Sonnet 4.6",
            "api": "anthropic-messages",
            "reasoning": True,
            "input": ["text", "image"],
            "cost": {"input": 3, "output": 15, "cacheRead": 0.3, "cacheWrite": 3.75},
            "contextWindow": 1000000,
            "maxTokens": 64000,
        },
        {
            "id": "claude-haiku-4-5",
            "name": "Claude Haiku 4.5",
            "api": "anthropic-messages",
            "reasoning": False,
            "input": ["text", "image"],
            "cost": {"input": 1, "output": 5, "cacheRead": 0.1, "cacheWrite": 1.25},
            "contextWindow": 200000,
            "maxTokens": 8192,
        },
    ],
}

with open(CONFIG_PATH, "w") as f:
    json.dump(cfg, f, indent=2)

print("openclaw.json patched OK")
