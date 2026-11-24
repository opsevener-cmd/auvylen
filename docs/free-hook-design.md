# Free photo-quality hook — design (proposed, not implemented)

Status: **awaiting approval**. Nothing here is built yet. The items marked **Approval needed**
include a database schema change and a new outbound service, which AGENTS.md says need
explicit sign-off.

## What it does

A signed-in user uploads 1–5 photos and gets them **ranked by photo quality** with short,
practical tips. Six criteria, each scored 1–10:
lighting, sharpness, framing, expression, eye contact, background.

It does **not** judge attractiveness and has no face-shape, jawline, skin or symmetry
scores. It makes no percentile or population claims ("better than 80% of users") and
produces no score derived from SCUT-FBP5500 or any other restricted dataset. The ranking
compares only the user's own photos.

## Model and data use

- **Model:** Gemini 3.5 Flash-Lite through the Gemini Developer API, **Standard paid tier**
  only. The model ID is a setting (`FREE_HOOK_MODEL`, default `gemini-3.5-flash-lite`;
  verify the exact ID in AI Studio).
- **Tiers:** never the free tier, where data may be used to improve Google products. Never
  the Contributor tier, which trades data use for a discount. The API refuses to start
  the hook in production unless `FREE_HOOK_PAID_TIER_CONFIRMED=true`, which the operator
  sets after checking the AI Studio billing page.
- **API key:** stored as a deployment secret, never committed or logged. The provider
  is an adapter behind a provider-neutral `PhotoQualityProvider` interface. With a
  missing key or a disabled adapter the hook reports **unavailable**; it never shows a
  made-up result.
- **Still to verify on Google's pages:** that 3.5 Flash-Lite has a Standard-tier
  "not used to improve products" row, and how long Google keeps paid-tier requests for
  abuse monitoring. The consent text should state that retention period.

## Request flow

1. **Consent.** The user ticks a consent box once per version. It confirms the user is
   18 or older, has the right to use the photos, and agrees that the photos are sent to
   Google for processing and deleted by us afterwards. Adulthood comes from this
   statement, never from appearance.
2. **Upload.** The existing decoding safeguards apply: JPEG/PNG only, size, pixel and
   frame limits. Each photo is re-encoded to JPEG with a 1024 px long edge, which also
   drops EXIF and GPS data.
3. **Limits.** A per-user limit of 30 analyses per UTC day (`FREE_HOOK_USER_DAILY_LIMIT`)
   and the global spend cap (below) are checked before the call.
4. **One Gemini call** for all photos:
   - temperature 0, minimal thinking, image resolution `medium` (560 tokens per photo);
   - **strict JSON** through `responseSchema` (`application/json`);
   - the response is validated with a strict Pydantic model; anything else is a failure.
5. **Ranking.** The server computes each photo's overall score as the mean of the six
   criteria (the model's own overall number is not trusted) and sorts by it.
6. **Cleanup.** Photo bytes are discarded in memory right after the call and are never
   written to disk. We store the result JSON, model ID, token counts, cost and timestamp,
   matching the engine/version/timestamp invariant in AGENTS.md.

The call runs **inside the API request**, at most 4 at a time, with a 30-second timeout.
The worker cannot do it: it is only on the internal `data` network, which has no
internet access.

### JSON returned per photo (schema)

```json
{"photos": [{"index": 0,
  "usable": true, "refusal_reason": null,
  "lighting": 7, "sharpness": 8, "framing": 6,
  "expression": 7, "eye_contact": 5, "background": 6,
  "tips": ["Face the window to soften shadows", "Step back to include the shoulders"]}]}
```

- **Refusals:** `refusal_reason` is one of `no_person`, `multiple_people`, `not_a_photo`,
  `appears_under_18`, `explicit`. A refused photo gets no scores. `appears_under_18` can
  only **block** a photo; nothing ever treats appearance as proof of age.
- **Tips:** at most 2 per photo, 120 characters each, about photo technique only.

## Spend cap

- **Daily budget:** `FREE_HOOK_DAILY_BUDGET_USD`, default 3.00, resets at UTC midnight.
- **Prices are settings:** `FREE_HOOK_PRICE_INPUT_PER_M=0.30` and
  `FREE_HOOK_PRICE_OUTPUT_PER_M=2.50` (Standard paid tier as of 2026-11; verify).
- **Reserve, then settle.** Before each call, the API reserves a worst-case amount
  (twice the estimate) in PostgreSQL, inside a transaction with a row lock, so concurrent
  requests cannot overshoot the cap. After the call, the real cost replaces the
  reservation, using the token counts in the response's `usage_metadata`.
- **Pausing.** When `spent + reserved` would exceed the budget, the hook pauses: the
  page says "Free photo checks are paused until tomorrow." The API returns 503
  `free_hook_paused`. Every pause is logged under a safe event name.
- **Failures.** A failed or invalid call is charged to the budget, because Google still
  bills it, but does not count towards the user's 30 per day.

### Estimated cost (3.5 Flash-Lite: $0.30 per 1M input tokens, $2.50 per 1M output)

| Analysis | Input tokens | Output tokens | Cost |
| --- | ---: | ---: | ---: |
| 1 photo | ~1,160 | ~250 | ≈ $0.001 |
| 5 photos | ~3,400 | ~850 | ≈ $0.003 |

At $3 a day that is about 1,000 five-photo analyses (or 3,000 single-photo ones). Output
tokens cost the most, so the tips are kept short and thinking is minimal.

## Paid report (later)

The same provider and consent. Photo technique plus styling advice: clothing, colour,
grooming and setting. It has the same prohibitions: no attractiveness, jawline, skin or
symmetry scores and no percentiles. You will add the payment method. It costs about
$0.005 per report (~1,500 output tokens).

## Approval needed before implementation

1. **New tables (Alembic migration):** consent records for the hook, daily spend ledger
   rows (append-only, one per call), and per-user daily counters.
2. **New settings:** the `FREE_HOOK_*` variables above, plus the Gemini API key as a
   secret. On the VPS, the API container needs outbound HTTPS to
   `generativelanguage.googleapis.com`.
3. **Consent wording**, after the Google retention period above is confirmed.
4. **Synchronous call from the API**, as described above. The alternative is a separate
   worker with internet access, which needs more containers and memory.
