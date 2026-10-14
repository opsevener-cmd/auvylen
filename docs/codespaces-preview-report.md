# Immediate private preview verification — 2026-10-14

Prepared GitHub Codespaces configuration on `codex/phase4b-custom-preferences`, starting
from preserved `6a8d2d7fdd17c01b34d0624374d78b9042678980`. Application, model, annotation,
financial and production infrastructure code is unchanged. New files add the devcontainer,
private lifecycle commands, setup/backup documentation and preview verification only.

## Implemented preview

- One Codespaces-forwarded frontend port: **3000**. GitHub's default visibility is Private;
  the owner must keep it Private. External HTTPS terminates at GitHub; internal Next.js
  uses HTTP. Other ports are not automatically forwarded.
- Next.js, FastAPI and the existing CPU research worker run as the non-root workspace
  user under a local Unix-socket-only process supervisor. API listens on loopback 8000.
  PostgreSQL 18 and Redis run on an internal Compose network with no published host ports.
- Random database credentials and app pepper are generated once and retained. Existing
  database/app state with missing credentials fails rather than silently replacing them.
  API uses staging security, exact Codespaces HTTPS Origin, secure cookies, existing CSRF,
  ownership/research grant/quotas and disabled commercial checkout. Public pilot is off.
- First creation restores the reviewed public checkpoint through the existing pinned
  CPU-only conversion script, verifies the existing ONNX SHA-256, and installs it in
  ignored private storage with licensing notices. Export tools/cache are discarded;
  resumes reuse the model. No real facial dataset download exists.
- Website rating/training/retraining/version/prediction features are the preserved Phase 4B
  implementation. The owner explicitly grants research access to the registered login
  from the Codespace terminal; there is no automatic grant or public operator API.
- Start/stop/status/resume commands retain private data. Controller operations serialize
  on a private lock; restart handles stale supervisor sockets after container termination.
  Codespaces creation/resume hooks call setup/start without Windows services.
- Consistent encrypted backup briefly stops app writers, dumps PostgreSQL 18 and snapshots
  uploads/models/credentials. GPG/AES256 encryption uses a terminal passphrase, never a
  command-line secret. Temporary plaintext is removed. Documentation covers safe recovery
  into a fresh unused preview with the original app pepper and new database credential.

See [the exact GitHub opening and operation steps](codespaces-private-preview.md).

## Executed verification in remote Linux

The selected runtime was managed Codex Cloud Debian Linux; an explicit Unix-socket check
confirmed the Linux daemon. No Windows/WSL services, VPS, public tunnel, external
Codespace allocation, purchases or real face datasets were used.

| Verification | Actual result |
| --- | --- |
| Official Dev Containers CLI 0.89.0 `read-configuration` | Passed; workspace service, forwardPorts `[3000]` |
| Codespaces Docker image build / Compose config | Passed |
| First-time setup inside non-root preview container | Locked uv/npm install, actual checkpoint download/export/verification, migrations and Next production build passed |
| Backend, infrastructure and real-weight tests | **155 passed**, no skips, 78.34 seconds |
| Frontend unit tests | **32 passed** |
| Ruff lint / format | Passed, 129 formatted Python files |
| Mypy | Passed, 60 source files |
| ESLint / TypeScript | Passed |
| Complete one-edge HTTPS preview browser flow | **1 passed**, approximately 1.1 minutes |
| Supervisor/API/worker/web health | All three running; readiness and existing migration check passed |

The complete browser flow used an isolated Compose project and a **loopback-only** TLS
edge that forwards every route through Next.js, matching GitHub's HTTPS-to-HTTP topology.
It registered an account, checked Secure/HttpOnly/SameSite cookies, rejected unsigned and
wrong-Origin mutations, denied research before the explicit terminal grant, uploaded ten
synthetic images, saved numerical ratings, trained actual MobileNet version 1, uploaded
and predicted an unseen image, added its rating, retrained version 2 and preserved both
versions. Private model-file URLs returned 404 and Credits remained zero.

The same flow stopped/resumed application processes, restarted PostgreSQL/Redis, recreated
the workspace while running, recovered process supervision and reproduced the same raw
prediction. Authentication/session state, annotations, grants, graph and private checkpoints
survived. It made a consistent encrypted backup, decrypted it internally without emitting
credentials, compared all private file bytes and restored the SQL dump into a disposable
isolated database with both READY versions present. It then verified sign-out/sign-in.
Only generated in-memory image fixtures were used; no real photo is included in Git.

Resolved test/setup failures: the initial dev image inherited an unnecessary PGDG update
source blocked by cloud policy; PostgreSQL 18 tools were already pinned in the base and
only Debian utility repositories are now used. The local TLS simulator initially sent
internal traffic to the managed outbound proxy, producing 403; an internal-only NO_PROXY
entry corrected the test edge. Preview resume now handles a stale Unix socket after abrupt
workspace replacement. Final regression/static/browser checks passed. Source operations
never relaxed application authentication/CSRF or exposed database/model paths.

Disk usage was monitored. One dev image was built successfully after correcting the
failed apt step, and unused build/export caches were released. There was no volume prune,
`down -v`, source-data wipe or repeated blind application-image build loop. Temporary test
services are stopped after verification with their volumes and encrypted test backup retained.

## What the owner still does in GitHub

No live Codespace or personal billing/quota state was created or tested. The real GitHub
private-port gateway and URL require the owner to create a Codespace using included
personal quota and verify Private visibility in the Ports tab. This is platform setup,
not an unfinished application feature. If quota/payment restrictions prevent creation,
stop without buying infrastructure; do not fall back to a Windows server.

The preview is available only while the Codespace runs, and retains normal expiry/cleanup
and development limitations. Essential private data needs an approved encrypted backup
outside the Codespace. Pairwise training and GitHub scoring integration remain paused;
this milestone introduces no new model architecture, accuracy claim or public deployment.
