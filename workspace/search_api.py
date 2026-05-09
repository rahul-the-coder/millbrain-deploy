#!/usr/bin/env python3
"""
search_api.py — Thin HTTP wrapper around search_rag.py.

The OpenClaw container has Python but not chromadb/sentence_transformers.
This server runs on the WSL host (using the millbrain venv) and exposes
the RAG search over HTTP so the container can reach it via host.docker.internal.

Usage:
    source venv_millbrain/bin/activate
    python scripts/search_api.py            # listens on 0.0.0.0:5555
    python scripts/search_api.py --port 5556

From the container:
    curl "http://host.docker.internal:5555/search?q=voltage+anomaly+troubleshooting"
"""

import argparse
from pathlib import Path

import chromadb
from flask import Flask, jsonify, request
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = ROOT / "data" / "chroma_db"
COLLECTION_NAME = "millbrain_docs"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
BGE_PREFIX = "Represent this sentence for searching relevant passages: "
TOP_K = 3
PREVIEW_CHARS = 400

app = Flask(__name__)

# Load model and collection once at startup — not per request
print(f"Loading embedding model ({MODEL_NAME}) ...", flush=True)
_model = SentenceTransformer(MODEL_NAME)

print(f"Connecting to ChromaDB at {CHROMA_DIR} ...", flush=True)
_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
_collection = _client.get_collection(COLLECTION_NAME)
print(f"Ready. Collection has {_collection.count()} chunks.", flush=True)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "chunks": _collection.count()})


@app.get("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Missing query parameter ?q="}), 400

    k = int(request.args.get("k", TOP_K))
    k = max(1, min(k, 10))

    vec = _model.encode(BGE_PREFIX + query).tolist()
    results = _collection.query(
        query_embeddings=[vec],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        preview = doc[:PREVIEW_CHARS].replace("\n", " ")
        if len(doc) > PREVIEW_CHARS:
            preview += "..."
        hits.append({
            "score":   round(1.0 - dist, 4),
            "source":  meta.get("source", ""),
            "title":   meta.get("title", ""),
            "section": meta.get("heading") or "(intro / preamble)",
            "preview": preview,
        })

    return jsonify({"query": query, "results": hits})


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=5555)
    p.add_argument("--host", default="0.0.0.0")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(f"Search API listening on {args.host}:{args.port}", flush=True)
    app.run(host=args.host, port=args.port)
