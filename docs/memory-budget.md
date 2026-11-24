# Production memory budget (Phase A slimming)

Target host: 2 vCPU / 4 GB VPS (`free -h` reports 3.6 GiB), running
`docker-compose.prod.yml` with `--profile research`.

## Limits

| Service | `mem_limit` | Notes |
| --- | --- | --- |
| web | 384m | Next.js standalone server, `NODE_OPTIONS=--max-old-space-size=256` |
| api | 512m | Never imports numpy/ONNX at startup; Argon2 limited to 2 concurrent hashes |
| worker | 512m | ONNX/MobileNet created per job, freed and `malloc_trim`med afterwards |
| postgres | 512m | `shared_buffers=128MB`, `effective_cache_size=1GB`, `max_connections=50` |
| redis | 256m | `--maxmemory 128mb` (disposable cache) |
| proxy | 128m | Caddy |
| **total** | **~2.3 GB** | leaves ~1.3 GiB for the OS, Docker and image builds (keep swap on) |

`max_connections=50`: the API and the worker each use SQLAlchemy's default pool (5 + 10
overflow); the operator, owner, export and migration CLIs open a few more.

## Measurements

Production VPS before this change (`docker stats --no-stream`, supplied by the operator):
web 97.8, api 133.8, worker 107.2, proxy 11.9, postgres 41.5, redis 12.7 MiB, about
405 MiB in total. Host: 1.1 GiB used, 2.5 GiB available.

Local runs of the same `docker-compose.prod.yml` (`APP_ENV=production`, `RESEARCH_MODE=true`,
local TLS overlay) on a 4-CPU cloud container. Images: `main` at `eedac25` ("before") and
this branch ("after"). Idle is the median of five samples about a minute after
`up --wait`; peak is the per-container maximum of `docker stats`, sampled continuously while
load ran:

- 800 server-rendered page requests, 16 at a time, across eight public pages;
- 24 concurrent account registrations (Argon2id, 64 MiB each), each followed by 40
  authenticated API reads;
- a simulated MobileNet training batch run inside the worker container: the worker's
  imports, eight 16 MP JPEGs through both extractors' preprocessing, and the onnxruntime
  import. The reviewed ONNX weights are not installed in this environment, so the
  inference session was replaced by a stub that returns a 1024-value embedding per image.

| Service | Idle before | Idle after | Peak before | Peak after |
| --- | ---: | ---: | ---: | ---: |
| api | 104.1 | 92.2 | **1421.3** | **226.1** |
| worker | 78.3 | 79.1 | 369.6 | 375.6 |
| web | 128.1 ¹ | 56.8 | 265.9 | 112.5 |
| postgres | 39.6 | 44.9 | 42.2 | 63.5 |
| redis | 5.9 | 5.8 | 7.6 | 7.7 |
| proxy | 20.6 | 14.8 | 24.7 | 22.4 |
| **total (MiB)** | **376.6** | **293.6** | **2131.3** | **807.9** |

¹ The "before" idle sample was taken after an earlier load run; a fresh start measured
51.9 MiB, so the web idle figures are roughly the same before and after.

Worker job process (from inside the simulation): 91 MiB after the worker's imports, a
336 MiB peak during the batch, and 118 MiB once the job finished. Before this change the
process stayed at **210 MiB** after the job, because freed pages were never returned to the
OS. The remaining ~27 MiB above idle is the onnxruntime module, which Python cannot
unload.

### Findings

- The largest risk was the API: concurrent logins/registrations each allocated 64 MiB of
  Argon2 memory without any limit, and a 24-request burst reached 1.4 GiB. The rate limits
  still allow bursts of that size. Hashing now waits for one of two slots; the parameters
  are unchanged.
- The API imported numpy and Pillow through inference modules at startup. They now load
  on the first request that needs them (aesthetic status, native preview, study exports,
  dataset readiness), and onnxruntime is never imported by the API.
- The worker already created a new extractor for each job; it now also frees that memory
  when the job ends. The simulated batch peak (~370 MiB container) fits the new 512m limit
  with headroom. Reviewed-weight inference was **not** measured here: verify one real
  MobileNet training run on the VPS (`docker stats` during the job) after deploying.
- PostgreSQL's defaults already used `shared_buffers=128MB`; the tuning lowers
  `effective_cache_size` (planner hint, 4 GB default) and `max_connections` (100 → 50).

Re-run on the VPS after deploying (see `docs/vps-restore.md`, Update procedure).
