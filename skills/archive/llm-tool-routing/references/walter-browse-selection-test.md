# Walter Browse Selection Test

## Purpose

This note records a real fresh-session comparison for the `walter_browse`
façade. It tests tool selection, not only whether the final answer happens to be
correct.

## Baseline session

Natural request, with no façade name in the prompt:

```text
J’aimerais connaître le nom, le prix et la catégorie du premier produit retourné par cette URL : https://dummyjson.com/products?limit=1
```

Observed behavior:

- Hermes registered `walter_browse`, but progressive Tool Search deferred it.
- The model loaded the generic `web-search-hierarchy` skill.
- It described and called `mcp__scrapling__get` directly.
- The data was correct, but the first-class façade contract was bypassed.

Interpretation: a correct answer does not prove correct architecture. The
competing generic skill's explicit-URL rule had higher practical precedence in
this fresh session.

## Controlled session

Run the same request while preloading the domain-specific skill:

```bash
hermes chat -s universal-web-extraction-router \
  -q 'J’aimerais connaître le nom, le prix et la catégorie du premier produit retourné par cette URL : https://dummyjson.com/products?limit=1' \
  --verbose
```

Observed behavior:

- The model described `walter_browse` before calling it.
- It generated the semantic contract:
  `name` aliases `title`/`name`, `price`, `category`; all three required;
  `min_records=1`; `mode=auto`.
- The façade selected `scrapling` automatically.
- The result contained one valid record, score `86`, and the expected product
  name, price, and category.

Interpretation: the orchestrator is capable of understanding the request and
constructing the contract. The remaining issue is skill activation/precedence,
not the need for a second planning LLM inside the router.

## Regression rule

For any new façade, run both a default fresh-session probe and a preloaded-skill
probe. Compare actual tool names and structured arguments. If only the preloaded
probe selects the façade, fix the generic skill's delegation/precedence rule
before changing the backend router.
