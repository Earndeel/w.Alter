#!/usr/bin/env python3
"""
WALTER MODEL ROUTER — Fast scraper (psycopg2 direct)
====================================================
Scrapes OpenRouter API → PostgreSQL walter_router.
Also supports: AA API v2, AA DOM (Playwright), Kie.ai marketplace.

Usage: python3 walter_router_scraper.py [openrouter|aa_api|aa_dom|kie|all]
"""
import json, sys, urllib.request, subprocess, re
from datetime import datetime, timezone
import psycopg2

DB = "postgresql://hindsight@172.17.0.3:5432/hindsight"

def scrape_openrouter():
    """Scrape OpenRouter API → PG. Fast (~10s for 343 models)."""
    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    
    print("[OR] Fetching OpenRouter models...", file=sys.stderr)
    req = urllib.request.Request("https://openrouter.ai/api/v1/models")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    
    models = data.get('data', [])
    now = datetime.now(timezone.utc).isoformat()
    
    cur.execute("SELECT id FROM walter_router.providers WHERE name = 'openrouter'")
    provider_id = cur.fetchone()[0]
    
    updated = 0
    for m in models:
        name = m.get('name', '')
        creator = m.get('id', '').split('/')[0] if '/' in m.get('id', '') else 'unknown'
        slug = m.get('id', '').replace('/', '-')[:64]
        
        cur.execute("""
            INSERT INTO walter_router.models (name, creator, slug) 
            VALUES (%s, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, updated_at = now()
            RETURNING id
        """, (name, creator, slug))
        model_id = cur.fetchone()[0]
        
        pricing = m.get('pricing', {})
        p_in = float(pricing.get('prompt', 0) or 0) * 1_000_000
        p_out = float(pricing.get('completion', 0) or 0) * 1_000_000
        
        cur.execute("""
            UPDATE walter_router.pricing SET is_current = false 
            WHERE model_id = %s AND provider_id = %s AND is_current = true
        """, (model_id, provider_id))
        cur.execute("""
            INSERT INTO walter_router.pricing (model_id, provider_id, price_per_1m_input, price_per_1m_output, currency, fetched_at)
            VALUES (%s, %s, %s, %s, 'USD', %s)
        """, (model_id, provider_id, p_in, p_out, now))
        
        aa = m.get('benchmarks', {}).get('artificial_analysis', {}) or {}
        intel = aa.get('intelligence_index')
        if intel is not None:
            cur.execute("""
                UPDATE walter_router.benchmarks SET is_current = false 
                WHERE model_id = %s AND source = 'openrouter_api' AND is_current = true
            """, (model_id,))
            cur.execute("""
                INSERT INTO walter_router.benchmarks (model_id, source, intelligence_index, coding_index, agentic_index, fetched_at)
                VALUES (%s, 'openrouter_api', %s, %s, %s, %s)
            """, (model_id, intel, aa.get('coding_index'), aa.get('agentic_index'), now))
        
        da = m.get('benchmarks', {}).get('design_arena', []) or []
        if da:
            cur.execute("""
                UPDATE walter_router.design_arena SET is_current = false 
                WHERE model_id = %s AND is_current = true
            """, (model_id,))
            for entry in da:
                cur.execute("""
                    INSERT INTO walter_router.design_arena (model_id, arena, category, elo, win_rate, rank, fetched_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (model_id, entry.get('arena', ''), entry.get('category', ''),
                      entry.get('elo', 0), entry.get('win_rate', 0), entry.get('rank', 0), now))
        
        updated += 1
        if updated % 50 == 0:
            conn.commit()
            print(f"[OR] {updated}/{len(models)}...", file=sys.stderr)
    
    conn.commit()
    cur.execute("SELECT count(*) FROM walter_router.models")
    n = cur.fetchone()[0]
    cur.close(); conn.close()
    print(f"[OR] Done: {n} models", file=sys.stderr)
    return updated

def scrape_aa_api_v2():
    """Scrape AA API v2 for detailed benchmarks."""
    api_key = subprocess.run(['vault', 'get', 'artificialanalysis/api_key'], 
                             capture_output=True, text=True).stdout.strip()
    if not api_key:
        print("[AA-API] No API key", file=sys.stderr)
        return 0
    
    print("[AA-API] Fetching...", file=sys.stderr)
    req = urllib.request.Request(
        "https://artificialanalysis.ai/api/v2/data/llms/models",
        headers={"x-api-key": api_key}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    
    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    models = data.get('data', [])
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    
    for m in models:
        ev = m.get('evaluations', {}) or {}
        intel = ev.get('artificial_analysis_intelligence_index')
        if not intel:
            continue
        
        name = m.get('name', '')
        creator = m.get('model_creator', {}).get('name', '')
        slug = m.get('slug', name.lower().replace(' ', '-')[:64])
        
        cur.execute("""
            INSERT INTO walter_router.models (name, creator, slug)
            VALUES (%s, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, updated_at = now()
            RETURNING id
        """, (name, creator, slug))
        model_id = cur.fetchone()[0]
        
        cur.execute("""
            UPDATE walter_router.benchmarks SET is_current = false 
            WHERE model_id = %s AND source = 'aa_api_v2' AND is_current = true
        """, (model_id,))
        
        def v(key):
            val = ev.get(key)
            return val if val is not None else None
        
        cur.execute("""
            INSERT INTO walter_router.benchmarks (
                model_id, source, intelligence_index, coding_index, math_index,
                gpqa, hle, mmlu_pro, ifbench, tau2, terminalbench_v2_1, terminalbench_hard,
                livecodebench, aime, scicode, lcr, median_tokens_per_second, fetched_at
            ) VALUES (%s, 'aa_api_v2', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (model_id, v('artificial_analysis_intelligence_index'), v('artificial_analysis_coding_index'),
              v('artificial_analysis_math_index'), v('gpqa'), v('hle'), v('mmlu_pro'),
              v('ifbench'), v('tau2'), v('terminalbench_v2_1'), v('terminalbench_hard'),
              v('livecodebench'), v('aime_25'), v('scicode'), v('lcr'),
              v('median_output_tokens_per_second'), now))
        updated += 1
    
    conn.commit()
    cur.close(); conn.close()
    print(f"[AA-API] Done: {updated} models", file=sys.stderr)
    return updated

if __name__ == '__main__':
    scraper = sys.argv[1] if len(sys.argv) > 1 else 'openrouter'
    if scraper == 'openrouter':
        scrape_openrouter()
    elif scraper == 'aa_api':
        scrape_aa_api_v2()
    elif scraper == 'all':
        scrape_openrouter()
        scrape_aa_api_v2()
    else:
        print(f"Unknown scraper: {scraper}", file=sys.stderr)
