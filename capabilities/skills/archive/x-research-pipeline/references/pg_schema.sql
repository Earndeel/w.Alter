-- X Research PostgreSQL Schema
-- Database: hindsight (container: hindsight-pg)
-- User: hindsight

CREATE SCHEMA IF NOT EXISTS x_research;

CREATE TABLE x_research.searches (
    id SERIAL PRIMARY KEY,
    topic TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('veille', 'recherche')),
    queries JSONB,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    total_posts INT DEFAULT 0,
    total_threads INT DEFAULT 0,
    status TEXT DEFAULT 'running' CHECK(status IN ('running', 'done', 'error'))
);

CREATE TABLE x_research.posts (
    id SERIAL PRIMARY KEY,
    search_id INT REFERENCES x_research.searches(id),
    tweet_id TEXT,
    author TEXT NOT NULL,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    date TIMESTAMPTZ,
    likes INT DEFAULT 0,
    retweets INT DEFAULT 0,
    replies_count INT DEFAULT 0,
    views INT DEFAULT 0,
    url TEXT,
    source TEXT,
    query TEXT,
    sentiment TEXT CHECK(sentiment IN ('positive', 'negative', 'mixed', 'neutral')),
    sentiment_score REAL,
    themes JSONB,
    language TEXT,
    parent_id INT,
    thread_root_id INT,
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(search_id, text_hash)
);

CREATE TABLE x_research.themes (
    id SERIAL PRIMARY KEY,
    search_id INT REFERENCES x_research.searches(id),
    name TEXT NOT NULL,
    keywords JSONB NOT NULL,
    post_count INT DEFAULT 0
);

CREATE TABLE x_research.snapshots (
    id SERIAL PRIMARY KEY,
    search_id INT REFERENCES x_research.searches(id),
    snapshot_at TIMESTAMPTZ DEFAULT NOW(),
    total_posts INT,
    positive_pct REAL,
    negative_pct REAL,
    mixed_pct REAL,
    neutral_pct REAL,
    avg_likes REAL,
    top_themes JSONB,
    top_positive JSONB,
    top_negative JSONB,
    languages JSONB
);

-- Indexes
CREATE INDEX idx_posts_search ON x_research.posts(search_id);
CREATE INDEX idx_posts_sentiment ON x_research.posts(sentiment);
CREATE INDEX idx_posts_likes ON x_research.posts(likes DESC);
CREATE INDEX idx_posts_author ON x_research.posts(author);
CREATE INDEX idx_posts_date ON x_research.posts(date);
CREATE INDEX idx_posts_hash ON x_research.posts(text_hash);
CREATE INDEX idx_posts_thread ON x_research.posts(thread_root_id);

-- Full-text search
ALTER TABLE x_research.posts ADD COLUMN tsv tsvector;
CREATE INDEX idx_posts_tsv ON x_research.posts USING GIN(tsv);

CREATE OR REPLACE FUNCTION x_research.update_tsv() RETURNS trigger AS $$
BEGIN
    NEW.tsv := to_tsvector('simple', COALESCE(NEW.text, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_posts_tsv BEFORE INSERT OR UPDATE ON x_research.posts
    FOR EACH ROW EXECUTE FUNCTION x_research.update_tsv();
