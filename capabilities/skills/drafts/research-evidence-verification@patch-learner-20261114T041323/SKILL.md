---
name: research-evidence-verification
description: Use when research needs exact prices or availability. See `references/constraint-ledger-and-live-availability.md` for the constraint ledger, dynamic-OTA protocol, and sub-agent reconciliation checklist. For Google Flights/OTA transport, price tiers, and cache/reparse policy, see `references/google-ota-transport-and-price-cache.md`.
---

# Research Evidence Verification

Use this skill when a web-research task depends on current prices, date-specific availability, inventory, schedules, or any other claim that can be invalidated by a dynamic page. It complements `comparative-research`: that skill ranks candidates; this one determines what is actually evidenced.

## Core rule

Never promote a lead into a confirmed offer. Every factual claim must carry an evidence level:

- **Confirmed** — the primary booking or purchase flow visibly accepts the exact dates, party size, room/product, and price, with availability shown.
- **Live quote** — a source shows a price for the relevant date window and item, but the final booking step or complete availability cannot be verified.
- **Indicative lead** — an aggregator, editorial page, review, cached result, “from” price, or general range suggests a candidate but does not prove the requested transaction.
- **Rejected** — it fails a hard constraint or the source contradicts the claim.

If dates, party size, room type, currency, taxes, or availability are missing, downgrade the claim rather than filling the gap from context.

## Procedure

1. **Freeze the request as testable constraints.** Write the exact date window, number of nights, guests, currency, ceiling/floor, and binary requirements. Distinguish hard constraints (`directly on sand`, `air conditioning in the room`) from preferences (`quiet`, `sea view`, `short transfer`).
2. **Check the live date.** Use the system/tool date, then state the research date and timezone. Do not silently reinterpret “next week”, “August”, or a flexible window. For flexible dates, test each viable start date or clearly say the source was only checked for one representative interval.
3. **Use the source hierarchy.** Prefer, in order: primary property/vendor booking flow; OTA result with the exact dates; metasearch/Google Hotels as a discovery and price-lead layer; reputable transport aggregators and operator pages; editorial guides/reviews; forums and snippets only as leads. A lower-tier source may support a description, but not a final price or availability claim when a higher-tier source disagrees.
4. **Verify page state after interaction.** Before reading a price, record the visible check-in, checkout, guests, currency, room/product, and selected filters. After a date-picker action, take a fresh snapshot and verify both fields; keyboard navigation can alter checkout while leaving check-in unchanged. Treat a URL parameter as a request, not proof that the page applied it.
5. **Reconcile conflicting prices.** Keep the exact displayed value, source, room/product, dates, and whether it is `from`, nightly, total, tax-inclusive, or a package. If Google Hotels says 500 and the property-facing page says “from 1,440”, report the discrepancy and downgrade the 500 value; do not choose the attractive number. Never mix a general monthly range with an exact-date offer.
6. **Test semantic constraints independently.** `Beachfront`/`on the beach` is not the same as `beach access`, `near beach`, `by the sea`, or `steps from the beach`. `Air-conditioned property` is not proof that the requested room has AC. `Sea view` does not prove direct sand access. Record the exact wording and location distance where available.
7. **Audit transport scope.** Separate one-way from return, scheduled route from exact-date inventory, and operator package from separately purchased legs. State whether ferry, terminal transfers, park fees, local taxis, and baggage are included. A fast route page can still be wrong for the requested date if its calendar remains on the default day.
8. **Cross-check independently.** For each top candidate, seek at least one independent confirmation of the critical constraint and one of the price/date. If a dynamic OTA cannot be read reliably, preserve the candidate as a lead and switch to the primary page, a second OTA, a direct call/contact route, or a transparent no-confirmation statement.
9. **Build an evidence matrix.** Use columns such as `candidate`, `hard constraints`, `price/date evidence`, `transport evidence`, `status`, `confidence`, `failure reason`, and `URL`. Keep rejected near-matches in a separate section so marketing wording cannot silently inflate the shortlist.
10. **Stop honestly.** A useful answer can conclude that no exact match was confirmed. Explain the smallest compromise that makes the search viable: raise the budget, move 50–100 m inland, accept fan-only, extend the trip, or choose a less scenic beach.

## Output format

Lead with the verdict, then separate:

1. **Confirmed / live quotes** — only items with evidence at the appropriate level.
2. **Indicative leads to verify** — useful candidates, explicitly not booked.
3. **Rejected near-matches** — which hard constraint failed.
4. **Transport and hidden-cost note** — one-way/return, ferry, local transfers, fees, and date caveats.
5. **Next verification action** — the single check that would turn the best lead into a decision.

For each candidate, include the exact displayed price and source date, not a smoothed estimate. Keep URLs as plain text or inline code; do not hide them behind marketing labels.

## API and model-pricing comparisons

For current API/model prices, normalize the comparison before ranking it:

1. Freeze one baseline (for video, normally 5 seconds, 16:9, no video input) and state whether the comparison is output-only or includes input materials.
2. Preserve the provider's billing unit: per second, per image, per request, or token-based. Derive a common equivalent only when the source gives enough information; label derived values as approximate.
3. Keep resolution bands semantically separate. `HD`, `FHD`, `720P`, `768P`, `1080P`, and `2K` are not interchangeable merely because they sound similar.
4. Separate text/image-to-video from video-to-video, and no-video-input from video-input prices. Video-input models often apply duration-dependent minimums, so never reuse the no-input rate.
5. Capture hidden or adjacent charges: audio, reference images, input-video duration, regeneration, rounding of partial seconds, free quotas, preview/invitation status, taxes, and reseller margins.
6. Prefer the vendor's pricing page or API reference over marketplace listings. If a static extractor returns only shell/navigation or the extraction backend is search-only, switch to a rendered structured extractor and preserve the raw source URL plus the exact table context.
7. Treat conflicting billing units as an evidence problem, not a conversion problem. If a provider's page simultaneously says `per run`, `per second`, or `per 1M tokens`, preserve each exact label, identify which view produced it, and do not multiply a headline `From` price into a normalized total unless the provider exposes the parameterized formula or quote.
8. For regional first-party providers, preserve the native currency and the official worked examples first. Only convert to USD with a timestamped FX source and label the result approximate; do not let conversion hide a difference between a list price, a temporary promotion, and an adjacent model's price.

### Video-generation benchmark × provider comparison (AA + OpenRouter + Kie.ai)

When Monsieur asks for **all video models**, do not answer with only the models mentioned in the preceding exchange. Build the exhaustive comparison from the live Artificial Analysis video leaderboards, then join provider catalogs:

1. Fetch and parse all three AA tables: `/video/leaderboard/image-to-video`, `/video/leaderboard/text-to-video`, and `/video/leaderboard/video-editing`. Keep rank, Elo, 95% confidence interval, sample count, release month, creator, and AA's displayed API price. Deduplicate only for the cross-model table; retain the per-board scores because a model can be strong in editing but absent from T2V.
2. Fetch OpenRouter's dedicated generation catalog at `https://openrouter.ai/api/v1/videos/models`. Treat `pricing_skus` as discovery metadata, not always as a directly comparable clip tariff. For token-priced models (notably Seedance), fetch the public model page as well and prefer its `displayPricing` tiers, which expose normalized `/second` prices and resolution/audio/input variants. Preserve the raw token SKU in evidence but never invent a clip total from token price alone. Pitfall: the generic `/api/v1/models` list contains NO video models — a "flux" search over it returns zero hits while the videos catalog lists 24 (verified 2026-08-21). Always search the modality-specific catalog. Per-model API contracts are published as `https://openrouter.ai/<model-id>/llms.txt` (endpoint, request fields, job polling, response shape) — read that instead of guessing the wire format.
3. Fetch Kie.ai's public catalog with `POST https://api.kie.ai/client/v1/model-pricing/page`, body `interfaceType: "Video"` (or `"Image"`), `pageSize: 100`, `pageNum: N`. Verified response shape (2026-08-21): rows live in `data.records`; `data.pages` is an INTEGER total-page count, not a list — paginate `pageNum` from 1 to `data.pages` and dedupe rows across pages. Filter by `modelDescription`/`provider`, preserving `usdPrice`, `creditPrice`, `creditUnit`, resolution, audio/input mode, and anchor URL. Kie may expose a family route rather than the exact provider model ID; label those rows as family matches.
4. Freeze one baseline before normalizing: normally 5 seconds, 16:9, no video input, with audio/no-audio stated explicitly. Convert only genuine `/second` rates to a 5-second total. Keep `per video`, `per image`, `video_tokens`, minimum-generation charges, and unspecified-duration rates in their native units; do not call them exact 5-second prices.
5. Report three sets separately: (a) AA models with exact OpenRouter and/or Kie matches, (b) AA models missing from a provider catalog, and (c) provider-only generation models absent from AA, such as a newly listed Seedance version. Do not silently treat a family match as an exact match.
6. The AA video leaderboards are blind-preference Elo benchmarks, not a technical quality guarantee. State whether the page is the default With Audio view, and do not compare an AA model-level score as if it were a resolution-specific provider quote.

The validated extraction recipe, matching notes, and evidence fields are in `references/aa-video-provider-comparison.md`.

### Image-generation price normalization (GPT Image 2 class)

For image models that mix flat marketplace tiers with token-priced native/proxy APIs:

1. Freeze exact output dimensions and quality before comparing. Do not equate Kie `1K/2K/4K` with OpenRouter `low/medium/high`; they are different axes, and Kie’s flat tier does not by itself expose a public quality mapping.
2. Query Kie’s public image catalog with `interfaceType: "Image"`, preserve `creditPrice`, `creditUnit`, `usdPrice`, `discountPrice`, and `falPrice`, and report Kie’s `usdPrice` rather than the reseller/anchor `falPrice`.
3. Query OpenRouter’s dedicated image catalog (`/api/v1/images/models`) and model endpoint, not only the generic text-model list. Record the exact model ID and separate text-input, reference-image-input, and image-output token prices.
4. When OpenRouter has no flat per-image tariff, use the model’s official output-token calculator or a completed `usage.cost`; label derived output-only numbers as estimates and add prompt/reference-image charges separately.
5. State whether the comparison is output-only or all-in. For image-to-image, input reference images can materially change OpenRouter’s cost; never present a text-to-image output estimate as the total edit cost.

The GPT Image 2-specific live endpoints, calculator formula, and 2026-08-11 evidence snapshot are in `references/gpt-image-2-provider-pricing.md`.

## Access is a separate constraint from price

For provider-access decisions, rank two different outputs:

- **Absolute cheapest** — the lowest verified generation tariff, even if signup is region-locked.
- **Cheapest usable** — the lowest tariff available to the user's region with a durable account, supported billing, API access, and no fragile shared/temporary credential.

Verify the access path independently from the price:

1. Inspect the provider's real signup page and record whether it accepts the user's country/phone, email-only signup, or requires enterprise onboarding. A reseller's SMS page is not evidence that the first-party form accepts that country code.
2. Search the same vendor family for an international first-party service or regional endpoint before recommending rented OTP numbers. Verify that it exposes the same model family, exact API model ID, output modes, and billing unit.
3. Include access friction in the recommendation: identity verification, payment availability, account durability, regional terms, and whether an API key can actually be created. Do not recommend shared/recycled SMS numbers as a durable access strategy.
4. Calculate the break-even honestly. If an international first-party route is only a few percent more expensive than a region-locked route, it is normally the cheaper usable option once account risk and setup time are included.
5. State the verdict in the form: `absolute cheapest: X; cheapest usable from the user's region: Y; difference: Z`. Keep the two rankings separate rather than forcing a nominal winner.

See `references/video-model-pricing-normalization.md` for a reusable worksheet and a worked evidence snapshot. For the dated Seedance 2.5 provider-price evidence, including the international BytePlus access route, see `references/seedance-2-5-provider-pricing.md`. For the dated 2026-08-21 FLUX 3 price-and-access evidence (BFL direct Draft vs Standard, OpenRouter, Kie/fal/Replicate absence, Nous promo end), see `references/flux3-video-provider-pricing.md`.

## Pitfalls

- Subagent summaries are reports, not proof: inspect the produced artifact and independently verify the critical source before repeating “confirmed”.
- A page can retain the wrong date after several keyboard operations; never infer the selected date from the last action.
- `from` prices and metasearch snippets are discovery signals, not exact-date inventory.
- A property description can prove beachfront or AC only at property level; room-level evidence is still required.
- Dynamic pages that cannot expose exact state should produce a confidence downgrade, not an invented number.
- If a transport page defaults to today or another date, use it for route structure only and label fares as route-level ranges.
- Do not let one spectacular low price outweigh a contradictory primary-source price.

## Reusable reference

For the dynamic-booking and conflicting-price pattern captured during a Thailand beach search, see `references/evidence-labels-and-dynamic-booking.md`.
For OTA URL parameter formats, tool-specific `wait_until` strategies (Booking.com → domcontentloaded, not load), Thai hotel pricing pitfalls (prices in images, not HTML text), and the tool preference order for OTA verification, see `references/ota-url-patterns.md`.

## Collecter Google Trends et qualifier les lacunes Keyword Planner

- Pour une recherche de demande par pays, collecter séparément les fenêtres 5 ans et 12 mois, les expressions locales et une comparaison internationale utilisant la même expression. Consigner pays, termes exacts, période, catégorie, type de recherche et date de collecte. Ne jamais présenter un indice Trends comme un volume mensuel, un CPC ou une part de marché.
- Lire le contrat du projet avant toute navigation. Réutiliser uniquement la session attribuée ; sur cette VM, le navigateur se pilote avec `/opt/walter-core/bin/walter-browser -s elie-google`. Ne pas créer de compte, campagne ou moyen de paiement pour débloquer Keyword Planner.
- Préparer un répertoire de preuves et lancer une collecte séquentielle, sans multiplier les onglets :
  ```bash
  : "${PROJECT:?Définir le répertoire du projet}"
  mkdir -p "$PROJECT/evidence/trends" "$PROJECT/work/trends"
  W=/opt/walter-core/bin/walter-browser
  SESSION=elie-google
  timeout 45 "$W" -s "$SESSION" url
  timeout 60 "$W" -s "$SESSION" nav 'https://trends.google.com/trends/explore?date=today%205-y&geo=FR&q=diamant%20de%20laboratoire&hl=fr'
  sleep 5
  timeout 45 "$W" -s "$SESSION" eval 'JSON.stringify({url:location.href,title:document.title,text:document.body.innerText})' > "$PROJECT/work/trends/FR_5y.browser.txt"
  timeout 45 "$W" -s "$SESSION" shot "$PROJECT/evidence/trends/FR_5y.png"
  ```
- Remplacer `date=today%205-y` par `date=today%2012-m` pour la seconde fenêtre. Ces fenêtres sont relatives au jour réel de navigation : si la date de référence de l'étude diffère, utiliser des bornes explicites, encodées dans le paramètre `date`, et vérifier les dates effectivement affichées.
- Conserver la sortie brute du navigateur avant transformation. L'interface Explorer observée exposait les données dans `document.body.innerText` sous forme tabulée, avec un en-tête `x\ty1`. Vérifier sa présence avant de parser ; ne pas supposer ce format stable :
  ```bash
  timeout 45 "$W" -s "$SESSION" eval 'JSON.stringify({url:location.href,header:document.body.innerText.indexOf("x\ty1"),preview:document.body.innerText.slice(0,1200)})'
  ```
- Rejeter comme collecte invalide toute page d'erreur, notamment HTTP 429, toute extraction sans tableau attendu, ou tout tableau dont les dates et le nombre de colonnes ne correspondent pas à la requête. Garder les preuves d'échec avec un nom explicite, mais les exclure des agrégations. Ne pas convertir une absence de données en zéro.
- Chaque requête Trends est normalisée séparément. Ne pas classer des pays à partir des moyennes de leurs indices locaux indépendants. Pour les comparaisons géographiques, utiliser une extraction géographique commune et expliquer qu'elle reflète un intérêt relatif, non le nombre absolu de recherches. Distinguer termes de recherche et sujets, et signaler les faibles volumes ainsi que les périodes incomplètes.
- Pour Keyword Planner, tenter uniquement la consultation de l'accès existant :
  ```bash
  timeout 60 "$W" -s "$SESSION" nav 'https://ads.google.com/aw/keywordplanner/home'
  timeout 30 "$W" -s "$SESSION" eval 'JSON.stringify({url:location.href,title:document.title,text:document.body.innerText.slice(0,1500)})'
  ```
  Une navigation expirée ne prouve ni l'absence de compte Google Ads ni l'exigence de paiement. Classer ce résultat comme « accès non vérifié : incident technique ». Ne déclarer « création requise » que si l'interface le montre. Laisser volumes, CPC et concurrence vides lorsqu'ils n'ont pas été obtenus ; ne pas les remplacer par Trends ou des extraits de recherche non vérifiés.
- Après des timeouts répétés, arrêter la collecte et diagnostiquer en lecture seule :
  ```bash
  curl -sS --max-time 10 http://127.0.0.1:9377/health
  systemctl is-active camoufox-max
  systemctl status camoufox-max --no-pager | head -20
  journalctl -u camoufox-max --no-pager -n 20
  uptime
  free -m
  ```
  Un service `active` ne garantit pas que son endpoint répond. Ne pas boucler indéfiniment, créer des onglets de secours en série, supprimer des caches, tuer largement des processus ou redémarrer le navigateur partagé. Préserver la session authentifiée, enregistrer le blocage et ne reprendre qu'après rétablissement vérifié.
- Dans les transformations, séparer les champs `country`, `window` et `variant` du nom de fichier : des variantes comme `DEb` ou des noms comportant plusieurs underscores ne sont pas des codes pays. Valider les mappings avant agrégation et reconstruire les sorties après exclusion des collectes invalides.
