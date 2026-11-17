# Liquid native vs OpenRouter — bench 2026-11-17

Synthetic French corpus (30 messages), same data, targets interleaved per message. No key, no personal data.

- `liquid-native-2026-11-17-run1.jsonl`: 10:59:35 → 11:05:00 (VM clock, UTC), 720 calls
- `liquid-native-2026-11-17-run2.jsonl`: 11:06:53 → 11:12:47 (VM clock, UTC), 720 calls
- `liquid-native-2026-11-17-run3.jsonl`: 11:25:26 → 11:30:57 (VM clock, UTC), 720 calls

## A. Latency ms p50 / p95 / p99 (warm, sequential), errors, cost per call (µUSD), input tokens

| target | mode | latency | errors | µUSD/call | tokens |
|---|---|---|---|---|---|
| liquid d1.2 | judge3 | 321 / 554 / 652  (min 303, max 680, sd 75, n=90) | 0/90 | 3.3 | 167 |
| liquid d1.2 | all6_one_call | 326 / 436 / 740  (min 307, max 967, sd 91, n=90) | 0/90 | 5.6 | 279 |
| liquid d1.2-ultra | judge3 | 344 / 711 / 877  (min 303, max 955, sd 135, n=90) | 0/90 | 7.0 | 167 |
| liquid d1.2-ultra | all6_one_call | 357 / 747 / 834  (min 299, max 881, sd 146, n=90) | 0/90 | 11.7 | 279 |
| openrouter d1.2 | judge3 | 539 / 753 / 886  (min 499, max 1037, sd 83, n=90) | 0/90 | 3.3 | 167 |
| openrouter d1.2 | extract3 | 552 / 847 / 1184  (min 500, max 1227, sd 136, n=90) | 0/90 | 2.9 | 143 |
| openrouter d1.2 | all6_two_routes_parallel | 564 / 874 / 1184  (min 518, max 1228, sd 135, n=90) | 0/90 | 6.2 | 310 |
| openrouter d1.2-ultra | judge3 | 598 / 890 / 1309  (min 487, max 1583, sd 163, n=90) | 0/90 | 7.0 | 167 |
| openrouter d1.2-ultra | extract3 | 602 / 1033 / 1208  (min 499, max 1216, sd 162, n=90) | 0/90 | 6.0 | 143 |
| openrouter d1.2-ultra | all6_two_routes_parallel | 629 / 1051 / 1310  (min 517, max 1583, sd 187, n=90) | 0/90 | 13.0 | 310 |

## A. Quality vs truth (fraction correct, 30 messages x runs)

| target | mode | mail(neg) | urgent | intent | person | amount | due |
|---|---|---|---|---|---|---|---|
| liquid d1.2 | judge3 | 1.00 (90) | 1.00 (90) | 0.89 (90) | - | - | - |
| liquid d1.2 | all6_one_call | 1.00 (90) | 1.00 (90) | 0.86 (90) | 1.00 (90) | 1.00 (90) | 1.00 (90) |
| liquid d1.2-ultra | judge3 | 1.00 (90) | 1.00 (90) | 0.80 (90) | - | - | - |
| liquid d1.2-ultra | all6_one_call | 1.00 (90) | 1.00 (90) | 0.80 (90) | 1.00 (90) | 1.00 (90) | 1.00 (90) |
| openrouter d1.2 | judge3 | 1.00 (90) | 1.00 (90) | 0.88 (90) | - | - | - |
| openrouter d1.2 | extract3 | - | - | - | 1.00 (90) | 1.00 (90) | 1.00 (90) |
| openrouter d1.2-ultra | judge3 | 1.00 (90) | 1.00 (90) | 0.80 (90) | - | - | - |
| openrouter d1.2-ultra | extract3 | - | - | - | 1.00 (90) | 1.00 (90) | 1.00 (90) |

## B. Stability (same input x3): max spread of each probability across repeats (mean over messages)

| target | mail | urgent | top intent |
|---|---|---|---|
| liquid d1.2 | 0.0073 (max 0.0154) | 0.0500 (max 0.1581) | 0.0656 (max 0.1490) |
| liquid d1.2-ultra | 0.0320 (max 0.2163) | 0.0171 (max 0.0808) | 0.0048 (max 0.0154) |
| openrouter d1.2 | 0.0089 (max 0.0308) | 0.0342 (max 0.0815) | 0.0957 (max 0.3812) |
| openrouter d1.2-ultra | 0.0313 (max 0.2096) | 0.0202 (max 0.0808) | 0.0081 (max 0.0333) |

## C. Concurrency (per-call latency in bursts; wall = time of the whole burst)

| target | burst | latency p50/p95/p99 | errors | mean burst wall ms |
|---|---|---|---|---|
| liquid d1.2 | 8 | 391 / 432 / 981  (min 331, max 998, sd 121, n=48) | 0/48 | 603 |
| liquid d1.2 | 16 | 419 / 479 / 615  (min 340, max 990, sd 67, n=96) | 0/96 | 610 |
| liquid d1.2-ultra | 8 | 491 / 724 / 973  (min 327, max 984, sd 153, n=48) | 0/48 | 729 |
| liquid d1.2-ultra | 16 | 401 / 587 / 740  (min 321, max 963, sd 101, n=96) | 0/96 | 659 |
| openrouter d1.2 | 8 | 577 / 651 / 661  (min 506, max 665, sd 33, n=48) | 0/48 | 640 |
| openrouter d1.2 | 16 | 624 / 666 / 943  (min 514, max 1153, sd 68, n=96) | 0/96 | 803 |
| openrouter d1.2-ultra | 8 | 632 / 897 / 1077  (min 524, max 1236, sd 136, n=48) | 0/48 | 817 |
| openrouter d1.2-ultra | 16 | 682 / 1116 / 1352  (min 525, max 1548, sd 194, n=96) | 0/96 | 1128 |

## D. Question count (same state)

| target | mode | latency | µUSD/call | tokens |
|---|---|---|---|---|
| liquid d1.2 | q1 | 301 / 331 / 336  (min 280, max 337, sd 16, n=15) | 1.3 | 64 |
| liquid d1.2 | q6 | 311 / 346 / 351  (min 300, max 353, sd 14, n=15) | 4.1 | 205 |
| liquid d1.2 | q12 | 322 / 361 / 370  (min 307, max 373, sd 18, n=15) | 7.5 | 377 |
| liquid d1.2 | extract1 | 314 / 331 / 332  (min 303, max 332, sd 9, n=15) | 1.4 | 69 |
| liquid d1.2 | extract3 | 322 / 357 / 372  (min 308, max 375, sd 17, n=15) | 3.0 | 148 |
| liquid d1.2 | extract6 | 321 / 528 / 885  (min 302, max 974, sd 163, n=15) | 5.2 | 260 |
| liquid d1.2-ultra | q1 | 345 / 1364 / 1618  (min 289, max 1682, sd 391, n=15) | 2.7 | 64 |
| liquid d1.2-ultra | q6 | 411 / 640 / 707  (min 298, max 724, sd 110, n=15) | 8.6 | 205 |
| liquid d1.2-ultra | q12 | 414 / 1206 / 1294  (min 312, max 1315, sd 314, n=15) | 15.8 | 377 |
| liquid d1.2-ultra | extract1 | 446 / 744 / 843  (min 302, max 868, sd 156, n=15) | 2.9 | 69 |
| liquid d1.2-ultra | extract3 | 389 / 795 / 815  (min 307, max 820, sd 175, n=15) | 6.2 | 148 |
| liquid d1.2-ultra | extract6 | 370 / 627 / 632  (min 304, max 634, sd 113, n=15) | 10.9 | 260 |
| openrouter d1.2 | q1 | 493 / 945 / 1642  (min 482, max 1816, sd 328, n=15) | 1.3 | 64 |
| openrouter d1.2 | q6 | 521 / 730 / 1075  (min 496, max 1161, sd 160, n=15) | 4.1 | 205 |
| openrouter d1.2 | q12 | 527 / 765 / 1102  (min 496, max 1186, sd 165, n=15) | 7.5 | 377 |
| openrouter d1.2 | extract1 | 534 / 1181 / 1287  (min 499, max 1314, sd 237, n=15) | 1.4 | 69 |
| openrouter d1.2 | extract3 | 524 / 562 / 565  (min 499, max 565, sd 21, n=15) | 3.0 | 148 |
| openrouter d1.2 | extract6 | 528 / 622 / 666  (min 507, max 677, sd 44, n=15) | 5.2 | 260 |
| openrouter d1.2-ultra | q1 | 577 / 812 / 942  (min 480, max 974, sd 124, n=15) | 2.7 | 64 |
| openrouter d1.2-ultra | q6 | 589 / 889 / 964  (min 490, max 983, sd 136, n=15) | 8.6 | 205 |
| openrouter d1.2-ultra | q12 | 652 / 1060 / 1183  (min 490, max 1214, sd 185, n=15) | 15.8 | 377 |
| openrouter d1.2-ultra | extract1 | 638 / 1209 / 1759  (min 494, max 1897, sd 328, n=15) | 2.9 | 69 |
| openrouter d1.2-ultra | extract3 | 587 / 931 / 1001  (min 507, max 1018, sd 147, n=15) | 6.2 | 148 |
| openrouter d1.2-ultra | extract6 | 753 / 1218 / 1298  (min 523, max 1317, sd 228, n=15) | 10.9 | 260 |

## E. Cold start (first call of a run and after idle gaps), ms

| target | first call (per run) | after 20 s idle | after 90 s idle |
|---|---|---|---|
| liquid d1.2 | 9125, 9282, 9088 | 462, 322, 338 | 325, 329, 320 |
| liquid d1.2-ultra | 298, 416, 350 | 344, 543, 357 | 324, 394, 326 |
| openrouter d1.2 | 831, 813, 525 | 585, 543, 514 | 808, 820, 859 |
| openrouter d1.2-ultra | 728, 503, 485 | 538, 840, 534 | 780, 577, 523 |

Total reported cost of the bench runs: $0.0127


## F. Cold start after a long idle (7-8 min), single call per target (ms)

| order | Liquid d1.2 | OpenRouter d1.2 | Liquid d1.2-ultra | OpenRouter d1.2-ultra |
|---|---|---|---|---|
| Liquid first (11:25) | **9404** | 772 | 337 | 543 |
| OpenRouter first (11:39) | 394 | **9673** | 342 | 678 |

The ~9.5 s is Liquid's d1.2 backend waking up after ~7 min idle: whoever calls first pays it, native or OpenRouter (OpenRouter forwards to
the same backend). d1.2-ultra showed no cold start in any run.

## G. Feature matrix (real calls, truth known; `liquid-native-2026-11-17-features.jsonl`)

Native = `POST api.liquid.ai/decisions/v1/systemone`. OR = OpenRouter Decisions (judgements, images) / Extractions (values).

| feature | Liquid native d1.2 / ultra | OpenRouter d1.2 / ultra |
|---|---|---|
| noul, choice, score | ok, ok (0.3 s) | ok (0.55 s) |
| choice `multiple` (independent probabilities) | ok: 0.92+0.92 and 1+1 on the two true options | NO: answers one option (0.37+0.62, 0.20+0.79) |
| text / number / date read (with span, found) | ok; number "300 euros" comes back null (text found) → read by Walter | ok via Extractions route |
| value absent → not found | ok (found ~0) | ok |
| date in words ("vendredi prochain") | span found, date null | same; no reference date anywhere (`now` is accepted and ignored) |
| spans | ok (4/4 passages) | ok via Extractions (list) |
| estimate + interval | ok (31 [28,34]) | ok via Extractions |
| image question (3 red squares) | ok (3 [2,3]) | ok (image_url parts in state) for noul/choice; number estimates with image: refused (400) |
| box / boxes | ok, coordinates fractions {top,bottom,left,right}, error ≤ 0.03; exactly ONE image required | NO (400 "does not accept box questions") |
| audio (French/English speech, WAV and MP3) | ok in top-level `audio` field (language, refund intent right); documented `media` field is silently ignored | NO (400) |
| spoken question (audio as instructions) | NO (422 on every shape tried; documented but not working) | NO |
| PDF / document | not an input type (unknown media entries are ignored without error); send text layer in state | NO |
| judgements + values in ONE call | ok (all 6 questions, 0.33 s) | NO: two routes, two calls |
| `stream`, `now` | accepted and ignored | accepted and ignored |
| limits seen | 128 questions, 255 options, `max` ≤ 64, 4.5 MB body, ≤ 8 images/audio | – |

## H. Documentation vs live API (Liquid)

Documented and confirmed: every question type above, `images`, `max`, `step`, `range`, `unit`, JSON state with `path` in answers,
`usage.cost` (USD), 422 validation, 429 + `Retry-After` (never reached: 0 errors in 2 160 bench calls incl. 16-wide bursts).
Documented but WRONG on the live API: audio clips in `media` (live: `audio`, silently ignored otherwise), spoken questions, `GET /decisions/v1/models`
only lists models (`d1.2`, `d1.2-ultra` take text/image/audio; `d1`, `d1.1`, `d1-ultra` text/image and only noul/choice/score).
Docs also say "ask spans on their own for best recall": here all questions in one call returned the passages too, but spans were not benched
against a spans-only call.
