# Recovery and cloud transition — 2026-10-12

## Current execution and Git state

This session is local Windows/PowerShell in the existing project directory, not a
remote cloud environment. It performs safe recovery and source preparation only.
No VPS/domain/GPU service exists, and no remote development executor is available
to this session. A callable GitHub connector is not a cloud shell or training host.

Initial branch: `codex/phase4a-cloud-ready`, unborn with **no commits**, **no remote**,
and **177 untracked source/config/documentation files** eligible under the original
ignore rules (975,285 bytes). No existing versioned source was overwritten. Recovery
creates a reviewed baseline on that branch, then `codex/phase4b-custom-preferences`.
Use `git log --oneline` for the resulting commit IDs. Nothing has been pushed.

## Confirmed source baseline

| Component | Evidence in repository | Scope/status |
| --- | --- | --- |
| Next.js / TypeScript | `apps/web/package.json`, routes and components | Existing accounts, Credits, redemption, results and research UI |
| FastAPI | `services/api/src/aevyra_api/main.py`, `routes/` | Existing modular HTTP app; no replacement |
| PostgreSQL / Alembic | Compose, SQLAlchemy models, four migration files | Latest revision `0004_research`; no new migration in recovery |
| Redis | Compose, account rate limiter | Existing private cache/rate limits; cloud AOF enabled |
| Caddy / HTTPS | `infra/caddy`, production/cloud Compose | Existing provider-neutral single-host deployment |
| Accounts | `accounts.py`, `credits/models.py`, account routes | Argon2id, opaque hashed sessions, CSRF/Origin and ownership |
| Credit ledger | `credits/ledger.py`, migration 0003 | Locked wallets, immutable history and compensating entries |
| Redemption | `credits/codes.py`, operator CLI | HMAC digests; plaintext restricted to protected exports |
| Analysis/payment | `commercial/`, `payments/`, `credits/analysis.py` | Synthetic mock only; legacy order path preserved |
| Async research | `research/jobs.py`, `worker.py`, migration 0004 | PostgreSQL durable jobs, grants, quotas, fenced leases and bounded attempts |
| Private artifacts | `research/storage.py`, cloud volumes | Bounded owner-scoped storage primitive; not an image upload API |
| Custom contracts | `services/inference/src/aevyra_inference/custom.py` | Dataset/rating/pairwise/checkpoint protocols only |
| External models | `services/inference/src/aevyra_inference/providers.py` | Independent plugin slots; no installed real-model implementation |
| Tests / CI | Backend/inference tests, web unit/browser tests, `.github/workflows/ci.yml` | Existing remote Linux workflow; not run by this recovery session |

Source inspection confirms implementation presence, **not a fresh functional pass**.
The historical Phase 4A report records 117 backend/infrastructure, 27 frontend,
two legacy browser and one cloud browser tests passing. They were not rerun here.

Missing Phase 4B features: persisted projects/datasets/annotations, private decoded
image ingestion and authorized image delivery, consent/retention/deletion controls,
real feature extraction/training/inference, embeddings, checkpoint version lifecycle,
validation metrics, long-job lease renewal/progress/cancellation and model comparison.
No trained model exists. Custom/ComboLoss/FPEM/FACLIP/SwinGFVQA-ca remain unavailable
for real predictions. Existing mock results remain explicitly synthetic.

## Local service shutdown and data preservation

Docker inspection found 13 running containers across these confirmed project labels:

| Project | Running containers before stop | Approximate container RAM |
| --- | --- | --- |
| `auvylen-phase4a-test` | web, api, worker, proxy, postgres, redis | 346 MiB |
| `aevyra-phase2` | web, api, proxy, postgres, redis | 186 MiB |
| `aevyra` | postgres, redis | 40 MiB |

Their individual sampled CPU readings were 0–0.17%; these are momentary measurements,
not sustained load estimates. Total sampled container RAM was about **572 MiB**.
Docker/WSL host overhead is separate and was not measured.

All 13 were gracefully stopped using Docker's Compose-project label filter and a
30-second timeout. No unrelated project was stopped. No container, image or volume
was removed. All **15 volumes** remain, including PostgreSQL, Redis, private uploads,
private models, Caddy state and disposable restore-drill volumes. Matching local env
files remain in place. Source preservation was checked by hashes of the existing
application/package/infrastructure files. No database migration or schema change ran.

Before shutdown, Docker-wide disk accounting reported images 1.579 GB, persistent
volumes 236.7 MB and build cache 5.337 GB. This is aggregate logical Docker accounting,
not a measured Windows virtual-disk size or per-project allocation. Stopping releases
running container resources; persistent storage remains intentionally retained.
Docker Desktop, WSL and shared tools were not uninstalled or reconfigured. Docker
Desktop may retain host overhead even after containers stop; the user may quit it
from the tray when other workloads do not need it.

## Preparation changes

- Stronger `.gitignore`/`.dockerignore` rules for local agent state, photos, data,
  checkpoints, archives, logs, database files, credential files and CSV exports.
- `.gitattributes` ensures Linux LF checkouts, especially shell scripts.
- Next.js's generated `next-env.d.ts` is excluded from source/Docker inputs without
  deleting the local file. Remote setup and frontend CI explicitly run `next typegen`
  before type checking, as the installed Next.js documentation requires for a fresh
  checkout. This avoids depending on the existing local `.next` cache.
- `scripts/cloud-dev-setup.sh` requires explicit remote opt-in, rejects Windows/WSL,
  installs only locked dependencies, and reports container support without starting
  services. It is preparation; it has not installed anything locally.
- `docs/cloud-development.md` provides private Git transfer, current Codex Cloud setup,
  remote test commands, data boundaries and the exact Phase 4B resume prompt.
- `docs/phase4b-master-instruction.md` preserves the user-authorized scope for the next
  environment. README/AGENTS identify the cloud-first boundary.

Application code, contracts, all four migrations, Docker service architecture and
business behavior are preserved. No new billing, model, API route or frontend page
is implemented during local preparation.

## Security review and verification scope

All candidate source files were inventoried and read by a lightweight scanner for
binary payloads, oversized artifacts, private keys, common access-token patterns,
secret assignments and credential-bearing URLs. Flagged locations were reviewed:
only labelled local fixtures, replacement placeholders and environment-generated
connection strings belong in the baseline. Real `.env*` files are excluded. No image,
dataset, model checkpoint or exported code file is included. This targeted review is
not a guarantee against every possible secret format.

Recovery checks cover source/secret exclusion, unchanged application hashes, migration
chain structure, shell syntax and commit contents. Regression suites, production
builds and remote integration checks are **deferred**, not marked passing. See the
final recovery verification entry in [verification.md](verification.md).
Initial Git whitespace review also found a pre-existing extra blank line at EOF in
`apps/web/src/lib/api-schemas.ts`; it is retained to preserve the application source.
This is not a compiler or runtime failure. Preparation files pass whitespace checks.

## Blocker and next action

No private remote or remote compute environment is configured. Follow
[cloud-development.md](cloud-development.md): create an empty private repository,
review and push the committed branches with authorized Git access, then choose
**Work in > Cloud** and publish a private environment. Verify remote resources and
Docker support before continuing. No paid service or public deployment is required
to develop Phase 4B. Essential data must have approved off-environment backups;
a temporary development workspace is not production storage.
