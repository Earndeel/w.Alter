#!/usr/bin/env python3
"""LLM judge for recall_bench.py results: do the first 3 memories answer the question?

  walter-python bench/recall_judge.py RESULTS.json [RESULTS2.json ...]

Same idea as the P3 exit bench (2026-10-01), on saved results so before/after are judged identically. The judge model
is Walter Router's 'memory_extraction' poste via walter_memory.llm (backfill budget); recall output is cloud_allowed.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_memory import llm  # noqa: E402

PROMPT = """Question posée à la mémoire d'un assistant personnel : {q}

Souvenirs retrouvés (les 3 premiers) :
{mems}

Ces souvenirs permettent-ils de répondre correctement à la question ? Réponds en JSON :
{{"verdict": "yes" | "partial" | "no", "useful": <nombre de souvenirs utiles, 0-3>}}"""


def judge(q: str, mems: list[str]) -> dict:
    if not mems:
        return {"verdict": "no", "useful": 0}
    prompt = PROMPT.format(q=q, mems="\n".join(f"{i + 1}. {m[:500]}" for i, m in enumerate(mems[:3])))
    for _ in range(3):
        try:
            c = llm.chat([{"role": "user", "content": prompt}], poste="memory_extraction", processor="bench.recall_judge",
                         privacy_class="cloud_allowed", budget="backfill", purpose="recall bench judge",
                         response_format={"type": "json_object"}, max_tokens=2000)["content"]
            return json.loads(c[c.find("{"):c.rfind("}") + 1])
        except Exception:  # noqa: BLE001 — retry, then count as a miss
            continue
    return {"verdict": "error", "useful": 0}


def main() -> None:
    for path in sys.argv[1:]:
        rows = json.loads(Path(path).read_text())["rows"]
        with ThreadPoolExecutor(6) as ex:
            verdicts = list(ex.map(lambda r: judge(r["q"], r["top"]), rows))
        yes = sum(v.get("verdict") == "yes" for v in verdicts)
        part = sum(v.get("verdict") == "partial" for v in verdicts)
        useful = sum(int(v.get("useful") or 0) for v in verdicts)
        print(f"{Path(path).name}: répond {yes}/{len(rows)} (+{part} partiel) ; souvenirs utiles {useful}/{3 * len(rows)}")
        for r, v in zip(rows, verdicts):
            r["judge"] = v
        Path(path).write_text(json.dumps({**json.loads(Path(path).read_text()), "rows": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
