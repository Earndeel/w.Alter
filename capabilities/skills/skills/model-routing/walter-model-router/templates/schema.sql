-- WALTER MODEL ROUTER — PostgreSQL Schema
-- Run: docker exec -i hindsight-pg psql -U hindsight -d hindsight < schema.sql

CREATE SCHEMA IF NOT EXISTS walter_router;

CREATE TABLE IF NOT EXISTS walter_router.models (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    creator TEXT,
    slug TEXT UNIQUE,
    context_window INTEGER,
    release_date DATE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS walter_router.providers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    api_endpoint TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS walter_router.pricing (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES walter_router.models(id),
    provider_id INTEGER REFERENCES walter_router.providers(id),
    price_per_1m_input NUMERIC(14,6),
    price_per_1m_output NUMERIC(14,6),
    price_per_1m_blended NUMERIC(14,6) GENERATED ALWAYS AS (
        price_per_1m_input * 0.7 + price_per_1m_output * 0.3
    ) STORED,
    cost_per_task NUMERIC(14,8),
    currency TEXT DEFAULT 'USD',
    fetched_at TIMESTAMPTZ DEFAULT now(),
    is_current BOOLEAN DEFAULT true,
    UNIQUE(model_id, provider_id, fetched_at)
);

CREATE TABLE IF NOT EXISTS walter_router.benchmarks (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES walter_router.models(id),
    source TEXT NOT NULL DEFAULT 'openrouter_api',
    intelligence_index NUMERIC(5,1),
    coding_index NUMERIC(5,1),
    agentic_index NUMERIC(5,1),
    math_index NUMERIC(5,1),
    gpqa NUMERIC(5,1),
    hle NUMERIC(5,1),
    mmlu_pro NUMERIC(5,1),
    ifbench NUMERIC(5,1),
    tau2 NUMERIC(5,1),
    terminalbench_hard NUMERIC(5,1),
    terminalbench_v2_1 NUMERIC(5,1),
    livecodebench NUMERIC(5,1),
    aime NUMERIC(5,1),
    scicode NUMERIC(5,1),
    lcr NUMERIC(5,1),
    median_tokens_per_second NUMERIC(8,0),
    fetched_at TIMESTAMPTZ DEFAULT now(),
    is_current BOOLEAN DEFAULT true,
    UNIQUE(model_id, source, fetched_at)
);

CREATE TABLE IF NOT EXISTS walter_router.design_arena (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES walter_router.models(id),
    arena TEXT NOT NULL,
    category TEXT NOT NULL,
    elo NUMERIC(6,1),
    win_rate NUMERIC(5,2),
    rank INTEGER,
    fetched_at TIMESTAMPTZ DEFAULT now(),
    is_current BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS walter_router.task_types (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    weight_intel NUMERIC(3,2) DEFAULT 0,
    weight_coding NUMERIC(3,2) DEFAULT 0,
    weight_agentic NUMERIC(3,2) DEFAULT 0,
    weight_cost NUMERIC(3,2) DEFAULT 0,
    weight_speed NUMERIC(3,2) DEFAULT 0,
    weight_design_arena NUMERIC(3,2) DEFAULT 0,
    min_intel NUMERIC(5,1) DEFAULT 20,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS walter_router.router_scores (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES walter_router.models(id),
    provider_id INTEGER REFERENCES walter_router.providers(id),
    task_type_id INTEGER REFERENCES walter_router.task_types(id),
    score NUMERIC(8,2),
    rank INTEGER,
    tier TEXT DEFAULT 'standard',
    computed_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(model_id, provider_id, task_type_id, computed_at)
);

CREATE TABLE IF NOT EXISTS walter_router.change_log (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    model_id INTEGER REFERENCES walter_router.models(id),
    provider_id INTEGER REFERENCES walter_router.providers(id),
    old_value JSONB,
    new_value JSONB,
    detected_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS walter_router.scrape_runs (
    id SERIAL PRIMARY KEY,
    scraper_name TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    models_found INTEGER DEFAULT 0,
    models_updated INTEGER DEFAULT 0,
    changes_detected INTEGER DEFAULT 0,
    error TEXT,
    status TEXT DEFAULT 'running'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_pricing_model_provider ON walter_router.pricing(model_id, provider_id, is_current);
CREATE INDEX IF NOT EXISTS idx_benchmarks_model ON walter_router.benchmarks(model_id, is_current);
CREATE INDEX IF NOT EXISTS idx_design_arena_category ON walter_router.design_arena(category, arena, elo DESC);
CREATE INDEX IF NOT EXISTS idx_router_scores_task ON walter_router.router_scores(task_type_id, rank);
CREATE INDEX IF NOT EXISTS idx_change_log_event ON walter_router.change_log(event_type, detected_at DESC);

-- Seed providers
INSERT INTO walter_router.providers (name, display_name, api_endpoint) VALUES
    ('openrouter', 'OpenRouter', 'https://openrouter.ai/api/v1'),
    ('kie', 'Kie.ai', 'https://api.kie.ai'),
    ('google_ai_studio', 'Google AI Studio', 'https://generativelanguage.googleapis.com'),
    ('nvidia_nim', 'NVIDIA NIM', 'https://integrate.api.nvidia.com/v1')
ON CONFLICT (name) DO NOTHING;

-- Seed task types
INSERT INTO walter_router.task_types (name, description, weight_intel, weight_coding, weight_agentic, weight_cost, weight_speed, min_intel) VALUES
    ('agentic', 'Autonomous agent loop', 0.25, 0.15, 0.35, 0.15, 0.10, 30),
    ('coding', 'Code generation & review', 0.15, 0.45, 0.10, 0.15, 0.15, 25),
    ('extraction', 'JSON / instruction following', 0.10, 0.05, 0.25, 0.40, 0.20, 20),
    ('reasoning', 'Deep analysis GPQA/HLE', 0.40, 0.10, 0.10, 0.25, 0.15, 35),
    ('compression', 'Summarization & context compression', 0.20, 0.05, 0.05, 0.40, 0.30, 20),
    ('tool_calling', 'API & function calling', 0.10, 0.10, 0.30, 0.30, 0.20, 20),
    ('frontend', 'HTML/CSS/UI generation', 0.15, 0.20, 0.10, 0.25, 0.10, 20),
    ('slides', 'PPTX/slides generation', 0.15, 0.20, 0.15, 0.25, 0.10, 20)
ON CONFLICT (name) DO NOTHING;
