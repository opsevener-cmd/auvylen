# Photo check

A signed-in user uploads 1–5 photos of themselves at `/photo-check`. The check has two stages,
from a single Gemini call:

1. **Photo technique**, always shown.
2. **Appearance**: the "What suits you" section, the AI impression and the roast. Shown only
   when the photo's technique score (the mean of the six criteria, 1–10) is at least
   `QUALITY_GATE` = **6.0**. Below that, the page shows "Photo quality X/10. Retake it with
   the tips above, then check your look." with a "Try another photo" button. Stage 2 output
   for that photo is thrown away in `ranked_photos()` and is never returned or stored. Each
   photo carries `quality_passed` in the API response. Ranking is still by technique score.

In detail, they get:
- the photos **ranked on photo technique**: lighting, sharpness, framing, expression, eye
  contact and background, each 1–10, with up to two tips per photo;
- **"What suits you"**: constructive appearance feedback (what's working, what flatters
  them in photos, and tips on styling, hair, grooming and posing);
- an **AI impression** in one of four bands, hidden until they press "Show my AI
  impression" and always labelled "AI impression for fun, not an objective rating";
- from their second check, an optional **"Roast me 🔥"** (Gentle or Spicy): one or two
  jokes about the photo and a vibe.

The rules come from the owner's decision of 2026-11-25 (AGENTS.md). No SCUT-FBP5500 or other
restricted dataset is involved anywhere.

## Models

| Check paid by | Model (setting) | Price per 1M tokens (input / output incl. thinking) |
| --- | --- | --- |
| Free checks (signup and weekly) | `GEMINI_MODEL`, default `gemini-3.5-flash-lite` | $0.30 / $2.50 |
| Credits, and the Owner | `GEMINI_MODEL_ADVANCED`, default `gemini-4-hydrogen` | $1.50 / $7.50 |

- **Same rules for both.** Both models get the same prompt, safety filter, refusals and quality
  gate. Results from the advanced model show a small "Advanced analysis" / "进阶分析" label,
  and the API returns `advanced: true`.
- **Per-model cost.** The daily-budget reservation and the final cost use the chosen model's
  prices. The pause threshold is a full five-photo request on the dearer model (about
  $0.026).
- **Thinking level.** Each model starts at the lowest level, `minimal`. If Gemini rejects that
  level with HTTP 400 (nothing is billed), the check retries once at `low`. It never drops
  thinking control, because a model's default could cost far more.
- **Verify before relying on it.** The `gemini-4-hydrogen` model ID and its prices come from
  the owner and were not checked here. Confirm in AI Studio that it is billed on the
  Standard paid tier, not a Contributor or preview tier that uses data. Then run the
  consistency check with `--model advanced`.

## What it will and won't say

| Area | Rule | Enforced by |
| --- | --- | --- |
| Appearance | Strengths and practical tips only. Never "flaws". No surgery, fillers, medical or diet advice. No comments on race, ethnicity, body weight or age | Prompt, plus `photo_check/safety.py`, which drops any line that still touches these topics |
| AI impression | One of four bands: What🫣🤣 · Average🧐 · Attractive🥹 · Striking😘🤩 (Chinese: 这张没拍出你的状态🫣🤣 · 挺耐看🧐 · 很有魅力🥹 · 让人眼前一亮😘🤩). No decimals, no percentiles, never "颜值打分" | Integer 1–4 validated by the API; labels live in the UI |
| Whose photo | Own face only. "This is me and I'm 18+" is ticked on **every** upload, and the API refuses requests without it | `self_and_adult_confirmed` in the request |
| Refusals | More than one person, a person who may be under 18, or explicit content all get the same neutral "We can't analyse this photo", with no score or band. Adulthood comes from the user's statement; the model's judgement can only refuse | `cannot_analyse` in the API response |
| Roast | Jokes about the photo and situation only: lighting, angle, blur, background, timing, styling choices. Never the body, skin, acne, weight, facial features, age, race, gender, disability or health. Spicy means sharper wit, not meaner targets. If no joke fits, there is no joke | Prompt, plus `safety.py` (a stricter list, including look-alike phrases) |
| Vibe | Always one of 12 fixed styles ("90s Hong Kong film lead", "Indie band frontman", …). Never a real person, and never a claim to identify anyone | JSON-schema enum; anything else is rejected as an invalid response |

Example lines and whether they are shown are listed in `services/api/tests/test_photo_check.py`
(`ROAST_EXAMPLES`, `APPEARANCE_EXAMPLES`).

## Free checks and Credits

1. Each account gets `PHOTO_CHECK_FREE_SIGNUP` (3) free checks for life.
2. After those, `PHOTO_CHECK_FREE_WEEKLY` (1) free check per week. Weeks start Monday 00:00 UTC.
3. After that, each check costs `PHOTO_CHECK_CREDIT_COST` (1) Credits from the existing
   ledger.
   - The `PHOTO_CHECK` debit is taken when the check starts.
   - If Gemini fails, a compensating `PHOTO_CHECK_REFUND` entry returns it, so the net charge
     applies only to a successful result.
   - A failed check never uses a free check either.
4. The Owner is never charged.

The page shows how many free checks are left, the date of the next free check, and the
Credit cost and balance. The old 30-per-day limit is gone. The global daily spend cap stays.

## How it works

| Step | Where |
| --- | --- |
| Consent (once per version, now `gemini-paid-v2`): 18+ and processing for photo technique **and** appearance. Anyone who accepted v1 is asked again | `POST /api/v1/photo-check/consent` |
| The browser shrinks photos to 1024 px JPEG; the server re-decodes them under the normal upload limits, strips metadata and re-encodes | `apps/web/src/lib/photo-check-api.ts`, `photo_check/service.py` |
| Free check or Credits chosen and the cost reserved against the $3/day cap, all in one locked transaction | `photo_check/service.py` |
| One Gemini call (Standard paid tier) to the default or advanced model, chosen by how the check is paid: strict JSON schema, temperature 0, fixed seed, minimal thinking, medium image resolution | `photo_check/gemini.py` |
| The server validates the JSON, filters every appearance and roast line, computes the technique score as the mean of the six criteria, and ranks | `photo_check/service.py`, `photo_check/safety.py` |
| Photos are discarded in memory as soon as the result is ready and are never written to disk | — |

**Data kept** (PostgreSQL, migrations `0012_photo_check` and `0013_photo_check_quota`):

| Table | Contents |
| --- | --- |
| `photo_check_consents` | Who agreed, to which consent version, and when |
| `photo_check_analyses` | One row per call (the spend ledger): model, prompt version, tokens, cost in integer micro-USD, status. Also `funding` (`free_signup`, `free_weekly`, `credits` or `owner`), `credits_charged` and `roast`. The result is cleared after 30 days. Rows from before 0013 have `funding` NULL and never count towards a quota |
| `photo_check_budget_days` | Spent and reserved micro-USD per UTC day |
| `credit_transactions` | `PHOTO_CHECK` debits and `PHOTO_CHECK_REFUND` entries, with durable idempotency keys |

**Spend cap.** Before each call the API reserves a worst-case cost while holding a row
lock on the day's budget row:
- a 5-photo reservation is 4,900 input and 2,550 output tokens, about $0.008;
- after the call, the real cost from Gemini's token counts replaces the reservation;
- once the remaining budget can't cover a full 5-photo reservation, checks pause until the
  next UTC day;
- a reservation left behind by a crash is charged in full after 10 minutes, and any Credits
  it took are refunded.

A PostgreSQL test runs concurrent requests and confirms the cap holds.

**Expected cost** (prices above; output includes thinking):

| Model | One photo | Five photos |
| --- | --- | --- |
| Default (free checks) | ≈ $0.002 | ≈ $0.005 |
| Advanced (Credits) | ≈ $0.007 | ≈ $0.022 |

$3 a day covers roughly 600 five-photo free checks, or about 140 five-photo advanced ones.

**Policy gate.** Every call passes `EngineRegistry.check_policy` with provider metadata.
It is refused unless `FREE_HOOK_PAID_TIER_CONFIRMED=true`. That flag is the operator's
statement that billing is linked and the Standard paid tier is in use; the API cannot
check it. Never use a free-tier or Contributor-tier key.

## Consistency check (run after deploy, with your own photo)

The same photo is sent five times. The script reports each run's band and technique scores,
how many runs agreed on the band, and the spread of each score. It prints numbers only, including
whether each run passed the quality gate and how many runs agree on that. Band agreement
counts only runs that passed, since only those ever show a band. The photo is piped in and
never saved. It costs about $0.01, which is added to today's
budget.

```bash
dc exec -T api python -m aevyra_api.photo_check.consistency --runs 5 < ~/my-photo.jpg
dc exec -T api python -m aevyra_api.photo_check.consistency --model advanced --runs 5 < ~/my-photo.jpg
# Chinese tips: add --language zh-CN
```

It also prints the model, the thinking level actually used, and how many runs returned
valid JSON. An invalid JSON reply counts as a failed run, so you can see whether the lowest
thinking level is enough for each model. If it isn't, set `FREE_HOOK_THINKING_LEVEL=low` or
`GEMINI_ADVANCED_THINKING_LEVEL=low`. A run costs about $0.002 on the default model and about
$0.007 on the advanced one.

## Settings (`.env.production`)

| Variable | Default | Notes |
| --- | --- | --- |
| `FREE_HOOK_ENABLED` | `false` | Master switch |
| `GEMINI_API_KEY` | empty | Secret. Never commit or paste it into chat |
| `FREE_HOOK_PAID_TIER_CONFIRMED` | `false` | Set `true` only after checking AI Studio billing |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Free checks. The old name `FREE_HOOK_MODEL` still works |
| `GEMINI_MODEL_ADVANCED` | `gemini-4-hydrogen` | Checks paid with Credits, and the Owner's |
| `GEMINI_ADVANCED_PRICE_INPUT_PER_M` / `GEMINI_ADVANCED_PRICE_OUTPUT_PER_M` | `1.50` / `7.50` | Advanced model prices, USD per 1M tokens |
| `GEMINI_ADVANCED_THINKING_LEVEL` | `minimal` | Lowest level that gives valid JSON; `low` if needed |
| `PHOTO_CHECK_FREE_SIGNUP` | `3` | Free checks per account, for life |
| `PHOTO_CHECK_FREE_WEEKLY` | `1` | Free checks per week (Monday 00:00 UTC reset); `0` turns them off |
| `PHOTO_CHECK_CREDIT_COST` | `1` | Credits per check after the free ones |
| `FREE_HOOK_DAILY_BUDGET_USD` | `3.00` | Global cap; checks pause when it is reached |
| `FREE_HOOK_PRICE_INPUT_PER_M` / `FREE_HOOK_PRICE_OUTPUT_PER_M` | `0.30` / `2.50` | Default model prices; update them if Google changes prices |
| `FREE_HOOK_THINKING_LEVEL` | `minimal` | Default model; `low` if `minimal` gives invalid JSON, empty to omit `thinkingConfig` |

`FREE_HOOK_USER_DAILY_LIMIT` no longer exists. An old value left in `.env.production` is
ignored.

## Deploy this release (appearance, quota, roast) on `/opt/auvylen-b`

This adds one migration (`0013_photo_check_quota`, three columns), so back up first. No
`.env.production` change is needed; the quota defaults apply.

```bash
export APP_DIR=/opt/auvylen-b COMPOSE_PROJECT_NAME=auvylen-b
cd "$APP_DIR"
dc() { docker compose --env-file .env.production -p auvylen-b -f docker-compose.prod.yml --profile research "$@"; }
BACKUP_PASSPHRASE_FILE=/root/.auvylen-backup-passphrase scripts/backup-prod.sh
git fetch origin && git checkout --detach REVIEWED_COMMIT
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$(git rev-parse --short=12 HEAD)/" .env.production
dc config --quiet && dc build --pull
dc stop proxy web api worker
dc run --rm --no-deps api alembic -c services/api/alembic.ini upgrade head
dc run --rm --no-deps api alembic -c services/api/alembic.ini current   # expect 0013_photo_check_quota (head)
dc run --rm --no-deps api alembic -c services/api/alembic.ini check
dc up -d --wait
curl -fsS https://auvylen.duckdns.org/ready && echo
```

Then open `/photo-check`. You'll be asked to accept the new terms. Check one photo of
yourself, then run the consistency check above. If a check fails, send the
`photo_check_…` line from `dc logs --since 1h api`.

## First-time setup on `/opt/auvylen-b`

This adds three tables, so take a backup first. The API container needs outbound HTTPS
to `generativelanguage.googleapis.com`; it is on the Compose `app` network, which has
internet access.

```bash
export APP_DIR=/opt/auvylen-b
export COMPOSE_PROJECT_NAME=auvylen-b
cd "$APP_DIR"
dc() { docker compose --env-file .env.production -p auvylen-b -f docker-compose.prod.yml --profile research "$@"; }

# 1. Encrypted backup (schema change follows).
BACKUP_PASSPHRASE_FILE=/root/.auvylen-backup-passphrase scripts/backup-prod.sh

# 2. Reviewed release.
git fetch origin
git checkout --detach REVIEWED_COMMIT
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$(git rev-parse --short=12 HEAD)/" .env.production

# 3. Settings. The key is typed at a hidden prompt and never echoed or put in history.
#    Paste the key itself: AI Studio issues "AQ." auth keys (dotted, ~53 characters);
#    older "AIza" keys also work. No quotes around it.
read -rs -p "Gemini API key (paid tier): " GEMINI_KEY_INPUT && echo && export GEMINI_KEY_INPUT
python3 - .env.production <<'PY'
import os, re, sys
from pathlib import Path
env = Path(sys.argv[1]); text = env.read_text()
key = os.environ["GEMINI_KEY_INPUT"].strip()
# Same rule as the API (photo_check/gemini.py): printable ASCII only. Pasted curly quotes,
# zero-width spaces or "…" would break the HTTP header. The key itself is never printed.
if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{20,256}", key):
    odd = sorted({f"U+{ord(c):04X}" for c in key if ord(c) > 127 or c.isspace() or c in "\"'`"})
    sys.exit(f"Key rejected: length {len(key)}, unexpected characters {odd or 'none'}. Copy it again from AI Studio.")
values = {"FREE_HOOK_ENABLED": "true", "FREE_HOOK_PAID_TIER_CONFIRMED": "true", "GEMINI_API_KEY": key}
for name, value in values.items():
    line = f"{name}={value}"
    text, n = re.subn(rf"(?m)^{name}=.*$", lambda _: line, text)
    if n == 0:
        text = text.rstrip("\n") + "\n" + line + "\n"
env.write_text(text)
print("photo check settings updated")
PY
unset GEMINI_KEY_INPUT
chmod 600 .env.production

# 4. Build, migrate, check, start.
dc config --quiet && dc build --pull
dc stop proxy web api worker
dc run --rm --no-deps api alembic -c services/api/alembic.ini upgrade head
dc run --rm --no-deps api alembic -c services/api/alembic.ini current   # expect the latest revision (head)
dc run --rm --no-deps api alembic -c services/api/alembic.ini check
dc up -d --wait
curl -fsS https://auvylen.duckdns.org/ready && echo

# 5. Outbound reachability from the API container (no key sent; expect 403 or 400).
dc exec -T api python -c "import urllib.request,urllib.error
try: urllib.request.urlopen('https://generativelanguage.googleapis.com/v1beta/models', timeout=10)
except urllib.error.HTTPError as e: print('reachable, HTTP', e.code)"
```

Then sign in at `https://auvylen.duckdns.org/photo-check`, accept the terms and check
one photo of yourself. Watch the spend:

```bash
dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT day, spent_micro_usd/1e6 AS usd, reserved_micro_usd, paused_at FROM photo_check_budget_days ORDER BY day DESC LIMIT 7"'
dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT status, failure_reason, count(*) FROM photo_check_analyses GROUP BY 1, 2"'
dc logs --since 1h api | grep -E "photo_check_(provider_failed|paused|internal_error)"
```

If the page says the check is not available and the API log shows
`photo_check_api_key_invalid`, the stored key is malformed. Its `error_type` says how:
`non_ascii_character` (curly quotes, zero-width space or "…" pasted with the key),
`quote_character`, `whitespace` or `unexpected_length`. Check the configured key without
printing it, then enter it again with step 3:

```bash
dc exec -T api python -c "import os; k=os.environ.get('GEMINI_API_KEY',''); print('length', len(k), '| starts AQ.:', k.startswith('AQ.'), '| starts AIza:', k.startswith('AIza'), '| unusual characters:', sorted({f'U+{ord(c):04X} at {i}' for i,c in enumerate(k) if ord(c)>127 or c.isspace() or c in chr(34)+chr(39)}) or 'none')"
```

After fixing `.env.production`, run `dc up -d api` so the container picks it up.

If the first real check fails with `photo_check_provider_failed`, look at the logged
`status_code`. A 400 usually means the model ID or `thinkingConfig` is not accepted:
check the model ID in AI Studio, or set `FREE_HOOK_THINKING_LEVEL=` (empty) and run
`dc up -d api`.

**Turn it off immediately:** set `FREE_HOOK_ENABLED=false` in `.env.production`, then
run `dc up -d api`.

## Not verified here

- No call was made to the real Gemini API: no key was available in the development
  environment, and every test uses a fake transport.
- These details follow Google's documentation and should be confirmed by the first real
  check after deployment: the request format (`responseSchema`, `mediaResolution`,
  `thinkingConfig`, `seed`) and the reported token fields.
- How stable the band is for one real photo. Temperature 0 and a fixed seed make repeat
  runs as close as the provider allows, but Google doesn't promise identical output. Run
  the consistency check to measure it.
- How often the model writes a line the safety filter drops. Dropped lines are never shown
  or logged. If roasts often come back empty, the prompt needs tuning.
