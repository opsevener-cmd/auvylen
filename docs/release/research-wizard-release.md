# Research wizard release: review report and deployment checklist

Scope: PR #8 (`ae3f40a`, merged as `194335e`) plus the follow-up branch
`codex/research-wizard-release`. Nothing here deploys, merges or enables the aesthetic
scoring model, and nothing resets accounts, photographs, models or database volumes.

## 1. Security cleanup: `dump.rdb`

**What happened.** A local test Redis was started from the repository root during
browser testing. Its snapshot was swept into `ae3f40a` by `git add -A`. The repository is
public.

**Contents (inspected without printing values).** The 2,172-byte RDB holds:
- rate-limit counters keyed by HMAC-SHA256 digests made with the CI-only pepper, which is
  already public in `ci.yml`. The digests cover `127.0.0.1` and synthetic test accounts;
- one worker heartbeat timestamp;
- Redis metadata.

There are no sessions, CSRF tokens, passwords, redemption codes, photographs, API keys or
real users. The file was never in a Docker image: images copy only service directories.

**Actions taken.**
- `46a4d02` deletes the file.
- Redis RDB/AOF files are now ignored in Git and Docker build contexts.
- New test `test_repository_hygiene.py` fails if any datastore snapshot or dump is tracked.
- Test Redis now runs with its data directory outside the repository and with
  `--save ""`.

**History rewrite: not done; owner decision.** The file remains in history at `ae3f40a`
and `194335e`. Purging it means force-pushing rewritten history to the shared integration
branch. That invalidates every clone, including the live Codespace, and needs coordinated
re-cloning. Given the contents, I recommend **not** rewriting. If you still want it purged,
run `git filter-repo --path dump.rdb --invert-paths` on a fresh mirror, with explicit
approval and a coordinated re-clone. No credential needs rotating.

## 2. Independent code review

A high-effort automated review of `279afee..ae3f40a` produced 10 findings. I verified and
fixed nine on this branch, with tests:

| Finding | Fix |
| --- | --- |
| Readiness did not refresh after editing a score (only count changes triggered it), so `no_score_variation` could go stale | The refresh key includes a valid-score signature |
| `?step=1.5` crashed the wizard | Only integer steps are accepted |
| Seed and fraction inputs reverted while typing and requested readiness on every keystroke | Typed text is kept, and valid values are committed after a 400 ms pause. Training sends exactly the values shown |
| Wizard Previous/Next used the photo-navigation keys (zh: 上一张/下一张) | Separate "Previous step"/"Next step" keys (上一步/下一步) |
| Back/Forward did not move between steps | Step moves push history entries. `popstate` restores the step after re-validating it against server data |
| Dataset list counted prediction-only photos as images | `DatasetView.prediction_count`; lists show annotation photos plus a "N prediction-only" note |
| Thresholds and reason codes were duplicated | One `MIN_RATED_IMAGES`/`MIN_GROUPS` source and one `ReadinessReason` contract |
| Blocker copy was duplicated in two components | One shared map (`readinessMessages`) |
| Repeated summary computation | Computed once per render |

**Kept by design:** prediction-only photos still count toward the private image and
storage quota. They are stored private images, so this is the resource safeguard.

Two more defects were found and fixed during regression testing:
- After Back/Forward, browser scroll restoration could leave the lazily loaded main
  photograph off-screen and unloaded. The wizard now manages scrolling, and the main photo
  loads eagerly.
- On the completion screen the training card repeated the same blocker list. It now points
  to the summary instead.

**Access controls re-verified:**
- Readiness, uploads, ratings, comparisons and prediction keep the existing session,
  research-entitlement, ownership, CSRF and exact-Origin checks. Other users get 403/404.
- Prediction photographs are refused for rating and comparison by the server and are
  excluded from training snapshots.
- Duplicates never change purpose silently.

**Migration `0010` re-verified:**
- It upgrades, downgrades and upgrades again on a fresh database, and `alembic check` is
  clean.
- Existing rows default to `annotation`; the incremental-upgrade test asserts this.
- Downgrade refuses while prediction photos exist.

## 3. Regression and compatibility evidence

| Check | Result |
| --- | --- |
| GitHub CI on PR #8 and on merge `194335e`, all five jobs including `cloud-research` | Success |
| `uv run pytest` | 194 passed, 29 skipped (opt-in) |
| `uv run pytest --integration` (PostgreSQL + Redis) | 218 passed, 5 skipped (reviewed MobileNet weights not installed) |
| Ruff, formatting, strict mypy, `alembic check` | Clean |
| `npm test` / lint / typecheck / build | 140 passed / clean / clean / built |
| Playwright default suite | 7 passed, 1 skipped (synthetic-checkpoint test) |
| Playwright synthetic aesthetic checkpoint | Passed |

**Existing-data compatibility.** Pre-PR code (`279afee`) created, at revision 0009, a
dataset with 11 photos and 10 ratings, a trained model v1 and a prediction. The new code
then migrated that database to 0010:
- every image became `annotation`;
- v1 stayed READY and reproduced the identical prediction;
- a prediction-only upload predicted correctly;
- retraining produced v2;
- readiness and counts were correct.

**Rollback check on the same data.** The downgrade was refused while a prediction photo
existed. After deleting and purging it, the downgrade succeeded and the old code's
`alembic check` was clean.

**Visual QA.** I checked the wizard (all steps, completion, prediction), home, analysis,
account and research pages at 1440, 820 and 390 px in English and Chinese. There were no
page errors and no horizontal overflow. Screenshots are in `docs/research-wizard/`.

**Not verified here:**
- MobileNet-backed training and prediction (weights not installed; the `--pretrained`
  suites cover them where weights exist);
- the Codespaces `preview-tests` (updated, but they run only inside a Codespace);
- the live Codespace itself, which was not accessed.

## 4. Deployment checklist: existing private Codespace (after your approval)

Run in the **existing** Codespace terminal only. Do not recreate the Codespace, regenerate
credentials, run Owner initialization or remove volumes. The preview controller applies
migrations automatically on `setup`/`start` (`APPLY_MIGRATIONS=true`), so the backup
**must** come first.

1. **Pre-flight.**
   - `git status` is clean and `git log -1` shows the currently deployed commit; write it
     down as the rollback target.
   - `python scripts/codespaces-preview.py status` shows the app healthy.
   - Note the Owner dashboard counts (users, datasets, images, models) for comparison
     afterwards.
2. **Encrypted backup.**
   - Run `python scripts/codespaces-preview.py backup`.
   - Enter a strong new passphrase and store it separately.
   - Record the printed ciphertext SHA-256.
   - Copy the `.tar.gz.gpg` out of the Codespace to approved private storage, and confirm
     the copy's SHA-256 matches.
   - Do not continue without a verified external copy.
3. **Update code.**
   - `python scripts/codespaces-preview.py stop`.
   - `git fetch origin && git checkout codex/phase4b-custom-preferences && git pull --ff-only`.
   - Never use `reset --hard` or `clean -fdx` over private data.
4. **Install, migrate and build.**
   - Run `python scripts/codespaces-preview.py setup`. It runs `uv sync --locked`,
     `npm ci`, the MobileNet restore/verification, the serialized migration and the build.
   - If any step fails, keep the app stopped and go to rollback.
5. **Verify the migration.**
   - Run `uv run alembic -c services/api/alembic.ini current`; it must show
     `0010_image_purpose (head)`.
   - Run `uv run alembic -c services/api/alembic.ini check`; it must show no pending
     operations.
   - Run `SELECT purpose, count(*) FROM preference_images GROUP BY purpose;` with `psql`.
     It must show only `annotation`, with the pre-flight image total.
6. **Start and smoke test.**
   - `python scripts/codespaces-preview.py start`, then `status`.
   - Port 3000 must remain **Private**.
   - Sign in normally. Owner counts and Credits must match the pre-flight values.
   - The existing dataset must open at its saved step.
   - Existing model versions must show READY.
   - Switching language must work.
   - Do not upload, rate, train or delete live research data just to test, unless you
     choose to.
7. **Leave real aesthetic scoring off.** `AESTHETIC_SCORING_ENABLED` stays unset or
   `false`, and the analysis page shows "not available".

## 5. Rollback strategy

- **Before step 5 succeeds (no schema change yet):** stop the app, `git checkout <noted
  commit>`, then run `setup` and `start`. No data changed.
- **After migration, if no prediction photos exist yet:**
  1. Stop the app.
  2. Run `uv run alembic -c services/api/alembic.ini downgrade 0009_aesthetic_analyses`.
  3. Check out the noted commit.
  4. Run `setup` and `start`. The `setup` migration is a no-op at 0009.
- **After prediction photos were uploaded:**
  1. Delete them in the app ("Delete prediction photograph"), or let them expire with their
     dataset.
  2. Let the worker purge them, then downgrade as above.
  3. If the downgrade refuses, the guard is protecting data: delete the remaining
     prediction photos first.
  - Trained models are unaffected, because prediction photos are never in training
    snapshots.
- **Data loss or corruption (any stage):** restore the verified encrypted backup into a
  **new, unused** Codespace, following the documented procedure ("Recovery into a new,
  unused Codespace" in `docs/codespaces-private-preview.md`). Keep the original Codespace
  stopped and untouched until the restore is verified.
