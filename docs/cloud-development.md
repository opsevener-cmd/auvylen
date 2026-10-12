# Cloud-first development handoff

Updated 2026-10-12. This is development preparation, not a public deployment.
The user's Windows computer is only for editing/review, Codex access and browser access.
Do not run containers, databases, model downloads, builds or training there. WSL and
Docker Desktop on that computer are still local execution, not a remote environment.

## 1. Transfer source through a private repository

Recovery creates a reviewed Phase 4A baseline on `codex/phase4a-cloud-ready` and a
Phase 4B branch `codex/phase4b-custom-preferences`. There was no existing commit or
remote at the start of recovery. The baseline uses a neutral local commit author
`Auvylen Engineering <engineering@auvylen.invalid>` if no author is configured;
this is not a claim about a GitHub identity. Configure your real Git author before
future personal commits if desired.

Create an **empty private** GitHub repository named `auvylen` in your chosen account.
Do not initialize a README, license or .gitignore remotely. Restrict collaborator
access. Check included Actions usage and spending limits before enabling CI; if you
have not approved CI usage, disable Actions for the initial push. No paid runner,
cloud server, GPU or extra usage is authorized by these instructions.

After reviewing the source commit, replace `YOUR_ACCOUNT` below with the owner of
that private repository. Use an already authorized SSH connection, or the repository's
HTTPS URL with your Git credential manager. Never put a token in the URL.
These are lightweight source-transfer commands, permitted on Windows:

```powershell
Set-Location 'C:\Users\ChenC\Documents\ChatGPT\aevyra'
git status --short
git log -2 --oneline
git remote add origin git@github.com:YOUR_ACCOUNT/auvylen.git
git push -u origin codex/phase4a-cloud-ready
git push -u origin codex/phase4b-custom-preferences
```

If `origin` already exists, inspect it and confirm the destination instead of adding
or replacing it blindly. This session does not create a repository, authenticate,
add a remote, or push. User authorization and a confirmed private destination are
required before an agent performs external writes.

Only versioned source transfers. `.env.cloud.local`, other real env files, exports,
backups, database files, logs, facial images, datasets and checkpoints are excluded.
Never upload the whole working directory as an archive: it contains ignored secrets
and generated artifacts. Existing local volumes and their matching env files stay
untouched. Moving real data later requires an approved encrypted backup/restore
procedure; see [cloud-backups.md](cloud-backups.md).

## 2. Create a remote Codex environment

Current official workflow:

1. Open ChatGPT/Codex on the web or desktop. In a **new task**, choose **Work in >
   Cloud**, then **Select environment > Create environment**. Alternatively use
   **Settings > Codex Cloud > Environments > Create environment**.
2. Connect GitHub if prompted, allowing access only to the private Auvylen repository.
3. Select that repository, then **Get started**. Ask setup to use Node.js 24, Python
   from `.python-version` (currently 3.14), uv and the existing lockfiles.
4. Ask setup to run `AUVYLEN_REMOTE_DEV=1 bash scripts/cloud-dev-setup.sh` in the
   checked-out repository. It installs locked Python/npm dependencies, generates
   Next.js route types without a full build, starts no
   services, downloads no models/datasets, and reports whether Docker is available.
   The opt-in is an operator assertion, not proof of remote hosting; verify the
   selected host before running it. Do not execute it in a Linux container on Windows.
5. Keep environment access **Only me**. Allow required package registries for setup;
   enable additional network destinations only after reviewing them. Do not supply
   production credentials or the existing redemption pepper. A value needed by the
   local application process belongs in an environment variable/personal vault;
   HTTPS network secrets are not a substitute for an application HMAC key.
6. Review setup results and resource limits. Confirm that PostgreSQL, Redis, Compose
   and browser testing are supported before claiming integration readiness. Docker
   support, GPU access and account entitlement are **not assumed** here.
7. Save and **Publish**. Wait for **Environment published**, then **Start a new task**.
   Select/check out `codex/phase4b-custom-preferences`. Give it the handoff below.

[Official Codex Cloud instructions](https://learn.chatgpt.com/docs/cloud) and
[environment configuration](https://learn.chatgpt.com/docs/environments/cloud-environments)
describe setup, sharing and saved state. Published development state is not production
hosting or the sole backup for essential private data. Commit source changes and
retain approved off-environment backups of any important artifacts.

## 3. Remote verification commands

Only run this section in the verified remote Linux environment. No paid infrastructure
or local-Windows fallback is authorized. These commands are prepared, not executed
by the local recovery session.

```sh
git switch codex/phase4b-custom-preferences
AUVYLEN_REMOTE_DEV=1 bash scripts/cloud-dev-setup.sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m mypy
npm test
npm run lint
npm run typecheck
npm run build
```

For a disposable remote host with Docker Engine and Compose, use fresh test credentials
and isolated volumes. No purchased domain is needed for this loopback TLS simulation:

```sh
python3 scripts/create-cloud-test-env.py
docker compose --env-file .env.cloud.local -p auvylen-phase4a-test -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud.local.yml --profile research build
docker compose --env-file .env.cloud.local -p auvylen-phase4a-test -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud.local.yml --profile research up -d --wait
npm exec --workspace @auvylen/web -- playwright install --with-deps chromium
npm exec --workspace @auvylen/web -- playwright test --config playwright.cloud.config.ts
docker compose --env-file .env.cloud.local -p auvylen-phase4a-test -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud.local.yml --profile research down
```

The generator refuses to overwrite an existing env file; preserve credentials matching
existing volumes. `down` here has **no `-v`**. Do not publish this simulation through a
tunnel. Loopback URLs refer to the remote test runner, not the user's Windows browser.
Use remote Playwright for that test. Public previews require a separate access/security
review and are not required to implement Phase 4B.

The existing CI's backend job runs migrations, `pytest --integration` and `alembic check`
against disposable PostgreSQL/Redis. Its browser jobs cover legacy checkout, Credits
and the cloud research path. Review quota before running CI. If the cloud sandbox
cannot host containers, report that limitation and request an approved remote runner.
Do not replace PostgreSQL/Redis or report skipped tests as successful checks.

## 4. Resume prompt

> Continue Auvylen on codex/phase4b-custom-preferences. First read AGENTS.md,
> docs/phase4b-master-instruction.md, docs/recovery-cloud-transition.md and
> docs/phase4a-report.md. Verify that execution is remote Linux and establish the
> current resource limits, Docker availability and Git baseline. Preserve accounts,
> Credits, redemption, payment architecture and migrations 0001–0004. Implement
> Phase 4B in the existing website: private authorized adult-image datasets,
> ratings and pairwise annotations, real asynchronous custom preference training,
> checkpoint versions and unseen-image inference. Add lease renewal/cancellation
> before long jobs. Verify code and weight licenses before selecting an extractor.
> Third-party model plugins remain independently removable and unavailable until
> their reviewed dependencies/weights exist. Research never deducts Credits. Use
> synthetic test images, run previous regressions and new tests, and report actual
> results. No paid infrastructure, public deployment, local Windows execution,
> large dataset downloads or new billing work.

## 5. Data and server portability

Code is in Git. Users, annotations, ledger and jobs belong in PostgreSQL. Private
images and trained checkpoints belong in distinct private persistent stores. Redis
is internal and recoverable; PostgreSQL owns durable jobs. Do not expose private
volumes through web/proxy containers. Keep storage access behind an interface so an
S3-compatible adapter can be added without replacing domain services.

The existing cloud stack's engineering starting estimate is 2 vCPU / 4 GiB RAM /
60 GiB SSD for the foundation; 4 vCPU / 8 GiB provides build headroom. This is not a
measured Phase 4B training requirement or a purchase recommendation. Measure the
chosen CPU extractor/trainer remotely before sizing a server. GPU is optional and
no GPU account is authorized. Image storage scales with compressed originals plus
thumbnails; 1,000 images averaging 3 MiB use about 3 GiB before derivatives/backups.
Embedding storage depends on dimension, dtype and image count. Dataset/checkpoint
quotas and retention must be explicit before real ingestion.

## 6. Verified cloud continuation (2026-10-12)

See [the Phase 4B progress report](phase4b-progress.md) for the fresh cloud verification
and first dataset/annotation implementation. The baseline dependency setup, application
health, regression suites and production builds were executed on managed Linux. The
repository now includes additive migration `0005_preferences`; always upgrade/check
before running the updated API or worker.

For environments with an installed Chromium and a blocked Playwright CDN, use
`PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/chromium`. The new browser test uses
`E2E_RESEARCH=true` and isolated test images in ignored `private-data/e2e-uploads`.
This does not enable a public preview.

Managed proxy builds can mount the existing trusted combined CA as a BuildKit secret:

```sh
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f services/api/Dockerfile -t auvylen-api:phase4b .
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f apps/web/Dockerfile -t auvylen-web:phase4b .
```

Use the matching `IMAGE_TAG=phase4b` in the isolated cloud test environment file. The CA
mount is optional outside a managed proxy. It is not copied into runtime layers. Keep
the private upload volume writable in the worker for retryable retention/deletion.

Compose explicitly excludes only container-local and internal service names from outbound
proxying. Managed proxy variables remain intact for external traffic. BusyBox health
checks disable proxying only for their fixed `127.0.0.1` target. This prevents false 403
responses from sending Caddy/Next.js internal requests to the cloud egress proxy.
