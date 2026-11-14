#!/usr/bin/env python3
"""
AA Model Analysis — fetches all models from AA API v2, ranks by category.
Usage: AA_API_KEY=aa_xxx python3 aa_analysis.py [min_intel] [max_price]
"""
import sys, json, urllib.request

API_KEY = sys.argv[1] if len(sys.argv) > 1 else None
if not API_KEY:
    import os
    API_KEY = os.environ.get('AA_API_KEY')
if not API_KEY:
    print("Usage: AA_API_KEY=aa_xxx python3 aa_analysis.py", file=sys.stderr)
    sys.exit(1)

req = urllib.request.Request(
    "https://artificialanalysis.ai/api/v2/data/llms/models",
    headers={"x-api-key": API_KEY}
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())

models = data.get('data', [])

valid = []
for m in models:
    intel = m.get('evaluations', {}).get('artificial_analysis_intelligence_index')
    pricing = m.get('pricing', {})
    p_in = pricing.get('price_1m_input_tokens', 0) or 0
    p_out = pricing.get('price_1m_output_tokens', 0) or 0
    speed = m.get('median_output_tokens_per_second', 0) or 0
    name = m.get('name', '?')
    creator = m.get('model_creator', {}).get('name', '?')
    if intel is None or intel == 0:
        continue
    blended = (p_in * 7 + p_out * 3) / 10
    valid.append({
        'name': name, 'creator': creator,
        'intel': round(intel, 1), 'speed': round(speed, 0),
        'p_in': p_in, 'p_out': p_out, 'blended': round(blended, 2),
        'ratio': round(intel / blended, 1) if blended > 0 else float('inf')
    })

valid.sort(key=lambda x: x['intel'], reverse=True)

def print_table(title, items, cols, n=15):
    print(f"\n{'='*90}")
    print(f"{title}")
    print(f"{'='*90}")
    for i, m in enumerate(items[:n], 1):
        line = f"{i:2}. {m['name']:<45}"
        for col in cols:
            if col == 'intel':
                line += f"  intel={m['intel']:5.1f}"
            elif col == 'blended':
                line += f"  ${m['blended']:6.2f}/M"
            elif col == 'speed':
                line += f"  {m['speed']:6.0f}t/s"
            elif col == 'ratio':
                line += f"  ratio={m['ratio']:6.1f}"
            elif col == 'creator':
                line += f"  [{m['creator']}]"
        print(line)

# 1. Top intelligence
print_table("TOP 15 — INTELLIGENCE PURE (AA Index v4.0)", valid, ['intel', 'blended', 'speed', 'creator'])

# 2. Best intel/price (intel >= 30)
priced = sorted([m for m in valid if m['intel'] >= 30 and m['blended'] > 0], key=lambda x: x['ratio'], reverse=True)
print_table("TOP 15 — MEILLEUR RATIO INTELLIGENCE/PRIX (intel >= 30)", priced, ['intel', 'blended', 'ratio'])

# 3. Fastest (intel >= 25, speed > 50)
fast = sorted([m for m in valid if m['intel'] >= 25 and m['speed'] > 50], key=lambda x: x['speed'], reverse=True)
print_table("TOP 15 — PLUS RAPIDES (intel >= 25, speed > 50t/s)", fast, ['speed', 'intel', 'blended'])

# 4. Budget + fast (<=1$/M, >=80t/s, intel >= 20)
budget = sorted([m for m in valid if m['blended'] <= 1.0 and m['speed'] >= 80 and m['intel'] >= 20], key=lambda x: x['intel'], reverse=True)
print_table("TOP 15 — BUDGET + RAPIDE (<=1$/M, >=80t/s, intel >= 20)", budget, ['intel', 'blended', 'speed'])

# 5. Ultra-budget (<0.30$/M, intel >= 25)
ultra = sorted([m for m in valid if m['blended'] <= 0.30 and m['intel'] >= 25], key=lambda x: x['intel'], reverse=True)
print_table("TOP 15 — ULTRA-BUDGET (<0.30$/M, intel >= 25)", ultra, ['intel', 'blended', 'speed'])

# 6. Reasoning models
reasoning = sorted([m for m in valid if any(kw in m['name'] for kw in ['Reasoning', 'high)', 'xhigh)', 'max)', 'Thinking'])], key=lambda x: x['intel'], reverse=True)
print_table("TOP 15 — REASONING (effort max/high/xhigh)", reasoning, ['intel', 'blended', 'speed', 'creator'])

# 7. Free models
free = sorted([m for m in valid if m['blended'] == 0], key=lambda x: x['intel'], reverse=True)
print_table("TOP 10 — GRATUITS (meilleure intelligence)", free[:10], ['intel', 'speed', 'creator'])

print(f"\nTotal models with intel score: {len(valid)}")
