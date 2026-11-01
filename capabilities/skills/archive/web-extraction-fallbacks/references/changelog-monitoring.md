# SPA Changelog Monitoring: Kie.ai

Session-verified notes for monitoring service announcements from `https://kie.ai/changelog`.

## What the page actually does

The page is a Next.js SPA. Its changelog bundle calls this JSON endpoint:

```text
POST https://api.kie.ai/api/v1/common/pageApiAnnouncementList
```

Request body used by the page:

```json
{
  "pageNum": 1,
  "pageSize": 20,
  "language": "en",
  "projectSource": "kie.ai"
}
```

The response is shaped like:

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "records": [
      {
        "apiName": "general",
        "title": "...",
        "content": "...",
        "path": "...",
        "documentPath": "...",
        "createTime": 1780000000000,
        "publishDate": 1780000000000
      }
    ],
    "total": 87,
    "size": 20,
    "current": 1,
    "pages": 5
  }
}
```

The frontend derives a display key equivalent to `apiName + "-" + createTime`. For monitoring, use a stronger idempotency key such as `apiName|createTime|title` and keep `publishDate` as the ordering cursor.

## Push vs polling conclusion

No service-announcement webhook is exposed in the changelog page or its client bundle. Common feed paths such as `/rss.xml`, `/feed.xml`, `/atom.xml`, and `/changelog/rss.xml` returned 404 during verification. The endpoint is used by the website but is not presented as a documented public API, so treat it as an internal contract that may change.

This is separate from Kie generation callbacks: `callBackUrl` is for a submitted generation task, not for announcements about new models, pricing, or API features.

## Recommended monitor

For a Cloudflare-based product:

1. Run a Cron-triggered Worker every 6 hours (hourly if near-real-time matters).
2. POST the request above and read the first page, which is newest-first.
3. Store a cursor and seen announcements in D1; compare `publishDate`/`createTime`.
4. Insert unseen records with a unique key before notifying, so retries do not duplicate alerts.
5. Notify only the new records; persist the full `content` and `path` for auditability.
6. Alert on non-200 responses or schema changes instead of silently reporting "no updates".

Use pagination during initial backfill, and do not scrape the rendered HTML unless this endpoint disappears.
