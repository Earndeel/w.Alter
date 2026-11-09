"""X Research — PostgreSQL connection and helpers
Schema: x_research in hindsight database (container hindsight-pg)
"""
import psycopg2
import hashlib
import json
from datetime import datetime

PG_DSN = "host=172.17.0.4 port=5432 dbname=hindsight user=hindsight"

def get_conn():
    return psycopg2.connect(PG_DSN)

def create_search(topic, mode, queries):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO x_research.searches (topic, mode, queries) VALUES (%s, %s, %s) RETURNING id",
        (topic, mode, json.dumps(queries))
    )
    sid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return sid

def finish_search(search_id, total_posts, total_threads=0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE x_research.searches SET finished_at=NOW(), total_posts=%s, total_threads=%s, status='done' WHERE id=%s",
        (total_posts, total_threads, search_id)
    )
    conn.commit()
    cur.close()
    conn.close()

def text_hash(text):
    return hashlib.sha256(text[:80].strip().encode()).hexdigest()

def insert_post(search_id, post, source="scraping"):
    conn = get_conn()
    cur = conn.cursor()
    h = text_hash(post.get("text", ""))
    try:
        cur.execute("""
            INSERT INTO x_research.posts 
            (search_id, tweet_id, author, text, text_hash, date, likes, retweets, 
             replies_count, views, url, source, query, sentiment, sentiment_score, 
             themes, language, parent_id, thread_root_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (search_id, text_hash) DO NOTHING
        """, (
            search_id, post.get("tweet_id"), post.get("author", "@unknown"),
            post.get("text", ""), h, post.get("date"), post.get("likes", 0),
            post.get("retweets", 0), post.get("replies", 0), post.get("views", 0),
            post.get("url"), post.get("source", source), post.get("query"),
            post.get("sentiment"), post.get("sentiment_score"),
            json.dumps(post.get("themes", [])), post.get("language"),
            post.get("parent_id"), post.get("thread_root_id"),
        ))
        inserted = cur.rowcount > 0
        conn.commit()
        return inserted
    except Exception as e:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

def bulk_insert(search_id, posts, source="scraping"):
    count = 0
    for p in posts:
        if insert_post(search_id, p, source):
            count += 1
    return count

def insert_snapshot(search_id, stats):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO x_research.snapshots 
        (search_id, total_posts, positive_pct, negative_pct, mixed_pct, neutral_pct,
         avg_likes, top_themes, top_positive, top_negative, languages)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        search_id, stats["total_posts"], stats["positive_pct"], stats["negative_pct"],
        stats["mixed_pct"], stats["neutral_pct"], stats["avg_likes"],
        json.dumps(stats["top_themes"]), json.dumps(stats["top_positive"]),
        json.dumps(stats["top_negative"]), json.dumps(stats["languages"]),
    ))
    conn.commit()
    cur.close()
    conn.close()

def get_analysis(search_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT sentiment, COUNT(*), COALESCE(AVG(likes),0) FROM x_research.posts WHERE search_id=%s GROUP BY sentiment", (search_id,))
    sentiment = {row[0]: {"count": row[1], "avg_likes": round(row[2], 1)} for row in cur.fetchall()}
    cur.execute("SELECT author, likes, views, text, sentiment FROM x_research.posts WHERE search_id=%s ORDER BY likes DESC LIMIT 10", (search_id,))
    top_posts = [{"author": r[0], "likes": r[1], "views": r[2], "text": r[3][:200], "sentiment": r[4]} for r in cur.fetchall()]
    cur.execute("SELECT language, COUNT(*) FROM x_research.posts WHERE search_id=%s GROUP BY language ORDER BY COUNT(*) DESC", (search_id,))
    languages = {row[0] or "unknown": row[1] for row in cur.fetchall()}
    cur.execute("SELECT jsonb_array_elements_text(themes) as theme, COUNT(*) FROM x_research.posts WHERE search_id=%s AND themes IS NOT NULL GROUP BY theme ORDER BY COUNT(*) DESC LIMIT 15", (search_id,))
    themes = {row[0]: row[1] for row in cur.fetchall()}
    cur.execute("SELECT COUNT(DISTINCT author), COUNT(*), MIN(date), MAX(date) FROM x_research.posts WHERE search_id=%s", (search_id,))
    meta = cur.fetchone()
    cur.close()
    conn.close()
    return {
        "meta": {"unique_authors": meta[0], "total_posts": meta[1], "date_from": str(meta[2])[:10] if meta[2] else None, "date_to": str(meta[3])[:10] if meta[3] else None},
        "sentiment": sentiment, "top_posts": top_posts, "languages": languages, "themes": themes,
    }

def search_posts(search_id=None, sentiment=None, min_likes=0, limit=50):
    conn = get_conn()
    cur = conn.cursor()
    where = ["1=1"]
    params = []
    if search_id: where.append("search_id=%s"); params.append(search_id)
    if sentiment: where.append("sentiment=%s"); params.append(sentiment)
    if min_likes: where.append("likes>=%s"); params.append(min_likes)
    cur.execute(f"SELECT author, likes, views, text, sentiment, date, url FROM x_research.posts WHERE {' AND '.join(where)} ORDER BY likes DESC LIMIT %s", params + [limit])
    results = [{"author": r[0], "likes": r[1], "views": r[2], "text": r[3][:300], "sentiment": r[4], "date": str(r[5])[:10] if r[5] else None, "url": r[6]} for r in cur.fetchall()]
    cur.close(); conn.close()
    return results

def fts_query(query, search_id=None, limit=20):
    conn = get_conn()
    cur = conn.cursor()
    where = ["tsv @@ plainto_tsquery('simple', %s)"]
    params = [query]
    if search_id: where.append("search_id=%s"); params.append(search_id)
    cur.execute(f"SELECT author, likes, text, sentiment, date FROM x_research.posts WHERE {' AND '.join(where)} ORDER BY ts_rank(tsv, plainto_tsquery('simple', %s)) DESC, likes DESC LIMIT %s", params + [query, limit])
    results = [{"author": r[0], "likes": r[1], "text": r[2][:300], "sentiment": r[3], "date": str(r[4])[:10] if r[4] else None} for r in cur.fetchall()]
    cur.close(); conn.close()
    return results
