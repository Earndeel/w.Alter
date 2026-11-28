#!/usr/bin/env python3
"""
Backfill memories_local Qdrant collection with local embeddings.

Usage:
  python3 backfill_local_embeddings.py              # Full backfill
  python3 backfill_local_embeddings.py --limit 500  # Batch of 500
  python3 backfill_local_embeddings.py --dry-run    # Show what would be synced

Requires: sentence-transformers (pip install sentence-transformers)
"""
import argparse, hashlib, json, subprocess, sys, time
import urllib.request

QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION = "memories_local"
MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 100

def get_facts(limit=None):
    """Get active facts from PG."""
    limit_clause = f"LIMIT {limit}" if limit else ""
    sql = f"SELECT id, content, fact_type, privacy_level, created_at FROM memory_facts WHERE status='active' AND canonical=true AND privacy_level != 'critical' {limit_clause};"
    r = subprocess.run(
        ["docker", "exec", "hindsight-pg", "psql", "-U", "hindsight", "-d", "hindsight", "-t", "-A", "-F", "|||", "-c", sql],
        capture_output=True, text=True, timeout=60
    )
    lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
    facts = []
    for line in lines:
        parts = line.split("|||")
        if len(parts) >= 5:
            facts.append({
                "id": parts[0],
                "content": parts[1][:500],
                "fact_type": parts[2],
                "privacy_level": parts[3],
                "created_at": parts[4],
            })
    return facts

def upsert_batch(points):
    """Upsert a batch of points to Qdrant."""
    data = json.dumps({"points": points}).encode()
    req = urllib.request.Request(
        f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=True",
        data=data, method="PUT",
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)

    facts = get_facts(args.limit)
    print(f"Facts to index: {len(facts)}")

    if args.dry_run:
        for f in facts[:10]:
            print(f"  {f['id'][:12]} | {f['fact_type']:15} | {f['content'][:60]}")
        print(f"  ... ({len(facts)} total)")
        return

    total = 0
    t_start = time.monotonic()

    for i in range(0, len(facts), BATCH_SIZE):
        batch = facts[i:i + BATCH_SIZE]
        texts = [f["content"] for f in batch]
        vectors = model.encode(texts).tolist()

        points = []
        for fact, vec in zip(batch, vectors):
            qdrant_id = hashlib.md5(fact["id"].encode()).hexdigest()
            points.append({
                "id": qdrant_id,
                "vector": {"dense": vec},
                "payload": {
                    "text": fact["content"],
                    "fact_type": fact["fact_type"],
                    "privacy_level": fact["privacy_level"],
                    "created_at": fact["created_at"],
                    "pg_memory_id": fact["id"],
                },
            })

        upsert_batch(points)
        total += len(points)
        elapsed = time.monotonic() - t_start
        rate = total / elapsed if elapsed > 0 else 0
        eta = (len(facts) - total) / rate if rate > 0 else 0
        print(f"  {total}/{len(facts)} ({total * 100 // len(facts)}%) | {rate:.0f}/s | ETA {int(eta)}s")

    elapsed = time.monotonic() - t_start
    print(f"Done: {total} points in {int(elapsed)}s ({total / elapsed:.0f}/s)")

if __name__ == "__main__":
    main()
