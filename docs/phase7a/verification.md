# Phase 7A verification report

Test environment: managed Linux cloud workspace; local test PostgreSQL/Redis, isolated
randomized PostgreSQL schemas and fresh in-memory SQLite. No live Codespace, persistent
Owner, customer photograph, dataset or checkpoint was modified. Development base:
`3df2ff1ecdd2ccf59650f53e431f1c2d85cd4d7c` (confirmed against GitHub before delivery).

## Checks

| Check | Result |
| --- | --- |
| Full backend + integration suite, excluding separately run login proxy | 265 passed, 6 reviewed-weight opt-in skips (before final deletion-idempotency test) |
| Final collection suite, including PostgreSQL concurrency/migration checks | 11 passed |
| Built Next.js Codespaces login/Origin/CSRF proxy regressions | 4 passed |
| Frontend unit tests | 150 passed |
| Ruff lint / formatting | Passed |
| mypy | Passed, 96 source files |
| ESLint / TypeScript | Passed |
| Production build | Passed with `next build --webpack`; default Turbopack failed opening a compiler socket in this sandbox; CI runs the default build |
| Production-browser collection workflow through real proxy | Passed, final run 19 seconds (24.6 seconds including servers) |
| Git diff whitespace / deletion review | Passed; no existing tracked files deleted |
| GitHub Actions | See the draft PR checks for the final commit; never infer CI success from local results |

The six full-suite skips require explicitly installed, reviewed pretrained weights.
No model, image encoder or score calculation changed in Phase 7A. They are not counted
as executed real-weight inference tests or as new accuracy evidence.

The 11 collection tests cover default-off/access/CSRF, complete consent→verification→
upload→independent rating→native export→withdrawal, immutable consent/receipts/identity,
new-version reconsent, Owner denial of holdout data/audit/export, custody and sealing,
post-seal withdrawal and irreversible seal invalidation, filesystem failure/retry,
duplicate-person proof checks and self-rating exclusion, hidden quality repeats,
1–7 validation, integrity/expiry/disabled-mode removal, proof reassignment prevention,
PostgreSQL concurrent assignment idempotency, database append-only triggers and
idempotent portrait deletion. Every fixture image is generated colour/noise data;
entered fixture ratings are **not human aesthetic evidence or model predictions**.

The dedicated browser config is added to the existing `commercial-browser` CI job.
Its API receives a fresh SQLite engine directly and never initializes the configured
PostgreSQL database. Other existing browser suites stay independent. Trace/video and
automatic screenshots are disabled. Optional reviewed screenshots are taken only after
the generated image and labels have been removed and the invitation cleared.

The browser verifies English administration, Chinese consent/upload, independent
rating by three distinct approved fixture accounts, private export download, withdrawal,
mobile overflow, error recovery, double-submit fencing and no premature success during
a delayed response. It deliberately injects one failed response before transmission,
then retries the same file/request against the actual API. The noise PNG is 1,772,763
bytes, verifying that the real proxy no longer rejects a valid study upload at 1 MiB.
All pages use the existing bilingual provider; literal and dynamic study error/consent
translations, safe error-body handling and proxy path boundaries have unit coverage.

## Measurements and performance bounds

- No new runtime/frontend dependency or external image/tracking request.
- Generated fixture binary transfer: **1,772,763 bytes**; base64 would require 2,363,684
  bytes before JSON overhead (33.3% more). Existing binary transport is reused.
- Successful complete browser flow: **19 seconds**, including three deliberate minimum
  viewing delays, independent logins, consent, upload, review, archive and withdrawal.
  This is a test-runtime observation, not a service-latency benchmark.
- Final local webpack production manifest: study page references 264,319 bytes of unique
  JS (87,363 gzip); existing research page references 218,273 (72,148 gzip). Difference:
  **46,046 raw / 15,215 gzip bytes**, including route-specific contracts, forms and Zod.
  This is a same-build route comparison, not an assertion that shared scripts download
  twice or that bundles improved against a measured old build.
- 200 active images globally by default, 4 MiB inbound cap, two concurrent decodes,
  at most 30 primary slots/image, private 64 MiB archive cap and twelve initially
  displayed review images. No polling, training or model initialization for rating.
- Browser progress measures browser-to-proxy transport bytes. Proxy-to-API transfer,
  processing and durable save wait are represented by a separate waiting state, never
  a fabricated percentage. Filesystem failure reports cleanup pending and retains a
  durable retry record after access is revoked.

## Visual evidence

These reviewed screenshots contain only a withdrawn disposable fixture account,
zero portraits/ratings and no invitation. They are safe source evidence, not live data.

- [English desktop](study-withdrawal-en-desktop.webp)
- [English mobile](study-withdrawal-en-mobile.webp)
- [Simplified Chinese mobile](study-withdrawal-zh-mobile.webp)

Native form controls, labelled fields, keyboard-operable details/radios, focusable
error alerts, status announcements, minimum touch targets and reduced-motion styles
reuse the existing design system. Consent remains expandable after withdrawal and
receipts remain downloadable without re-enrolling or changing an account's Credits.

## Release decision

**GO: draft review and isolated authorized fixture testing.**
**NO-GO: real participant collection and consumer scoring.**

Repository visibility is currently public. Manual identity/adulthood/independence checks,
external holdout custody and preregistration, final rights/processor review, backup
retention/deletion-on-restore procedures and explicit collection approval remain required.
The application cannot revoke an already downloaded archive, prove human independence
from account IDs, perform machine unlearning or isolate data from its root operator.
See [the implementation report](README.md) for operational safeguards and safe rollout.
