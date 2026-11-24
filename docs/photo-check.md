# Free photo check

A signed-in user uploads 1–5 photos at `/photo-check` and gets them ranked on **photo
technique**: lighting, sharpness, framing, expression, eye contact and background. Each
criterion is scored 1–10, with up to two short tips per photo. It never rates
attractiveness and has no face-shape, jawline, skin or symmetry scores. It makes no
percentile or population claims; the ranking only compares the user's own photos. No
SCUT-FBP5500 or other restricted dataset is involved anywhere (see AGENTS.md).

## How it works

| Step | Where |
| --- | --- |
| Consent (once per version `gemini-paid-v1`): user confirms they are 18+ and agrees to processing | `POST /api/v1/photo-check/consent` |
| The browser shrinks photos to 1024 px JPEG; the server re-decodes them under the normal upload limits, strips metadata and re-encodes | `apps/web/src/lib/photo-check-api.ts`, `photo_check/service.py` |
| Per-user limit (default 30 per UTC day) and global spend cap (default $3 per UTC day) | `photo_check/service.py` |
| One Gemini 3.5 Flash-Lite call (Standard paid tier): strict JSON schema, temperature 0, minimal thinking, medium image resolution | `photo_check/gemini.py` |
| The server validates the JSON, computes each photo's score as the mean of the six criteria, and ranks | `photo_check/service.py` |
| Photos are discarded in memory as soon as the result is ready and are never written to disk | — |

**Data kept** (PostgreSQL, migration `0012_photo_check`):

| Table | Contents |
| --- | --- |
| `photo_check_consents` | Who agreed, to which consent version, and when |
| `photo_check_analyses` | One row per call (the spend ledger): model, prompt version, tokens, cost in integer micro-USD, status. The result (scores and tips) is cleared after 30 days |
| `photo_check_budget_days` | Spent and reserved micro-USD per UTC day |

**Spend cap.** Before each call the API reserves a worst-case cost while holding a row
lock on the day's budget row:
- the reservation for a 5-photo request is 4,400 input plus 1,300 output tokens, about $0.0046;
- after the call, the real cost from Gemini's reported token counts replaces the reservation;
- once the remaining budget cannot cover a full 5-photo reservation, the check pauses
  until the next UTC day: the page says so and the API returns `photo_check_paused`;
- a call that failed at Google costs the user nothing towards their daily limit;
- a reservation left behind by a crash is charged in full after 10 minutes.

A PostgreSQL test runs 24 concurrent requests and confirms the cap holds.

**Expected cost** (Standard paid tier: $0.30 per 1M input tokens, $2.50 per 1M output
tokens including thinking; verified 2026-11-24): about $0.001 for one photo and about
$0.003 for five. $3 a day covers roughly 1,000 five-photo checks.

**Policy gate.** Every call passes `EngineRegistry.check_policy` with provider metadata.
It is refused unless `FREE_HOOK_PAID_TIER_CONFIRMED=true`. That flag is the operator's
statement that billing is linked and the Standard paid tier is in use; the API cannot
check it. Never use a free-tier or Contributor-tier key.

## Settings (`.env.production`)

| Variable | Default | Notes |
| --- | --- | --- |
| `FREE_HOOK_ENABLED` | `false` | Master switch |
| `GEMINI_API_KEY` | empty | Secret. Never commit or paste it into chat |
| `FREE_HOOK_PAID_TIER_CONFIRMED` | `false` | Set `true` only after checking AI Studio billing |
| `FREE_HOOK_MODEL` | `gemini-3.5-flash-lite` | |
| `FREE_HOOK_USER_DAILY_LIMIT` | `30` | Anti-abuse limit per user per UTC day |
| `FREE_HOOK_DAILY_BUDGET_USD` | `3.00` | Global cap; the check pauses when it is reached |
| `FREE_HOOK_PRICE_INPUT_PER_M` / `FREE_HOOK_PRICE_OUTPUT_PER_M` | `0.30` / `2.50` | Update these if Google changes prices |
| `FREE_HOOK_THINKING_LEVEL` | `minimal` | Set it to empty if the model rejects `thinkingConfig` |

## Deploy on `/opt/auvylen-b`

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
read -rs -p "Gemini API key (paid tier): " GEMINI_KEY_INPUT && echo && export GEMINI_KEY_INPUT
python3 - .env.production <<'PY'
import os, re, sys
from pathlib import Path
env = Path(sys.argv[1]); text = env.read_text()
values = {"FREE_HOOK_ENABLED": "true", "FREE_HOOK_PAID_TIER_CONFIRMED": "true",
          "GEMINI_API_KEY": os.environ["GEMINI_KEY_INPUT"].strip()}
assert re.fullmatch(r"[A-Za-z0-9_-]{20,200}", values["GEMINI_API_KEY"]), "unexpected key format"
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
dc run --rm --no-deps api alembic -c services/api/alembic.ini current   # expect 0012_photo_check (head)
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
  `thinkingConfig`) and the reported token fields.
