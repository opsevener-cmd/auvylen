# Redemption engine and operator exports

RedemptionBatch records name, arbitrary validated lowercase channel, SKU, credits, quantity,
expiration, active flag and metadata. Channel is descriptive, never payment-provider logic.
Codes are one-time, cryptographically generated with secrets.choice: 24 independent symbols
from an alphabet excluding visually ambiguous characters (~118 bits of entropy). Format:
AUV-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX. Input permits this grouping or its compact equivalent,
case-insensitive with surrounding whitespace; other characters/groupings fail. Maximum input
length is forty. Codes are not sequential and are never generated with predictable RNG.

## Storage and pepper

The database stores HMAC-SHA256(REDEMPTION_CODE_PEPPER, normalized_code), a four-character
masked suffix, UUID/batch association, AVAILABLE/REDEEMED status, expiry and metadata.
It does not store plaintext unused codes. Plaintext exists transiently during generation,
in the explicit CSV export, and transiently when a customer submits it. It is not logged,
placed in URLs, copied to other application files, or recoverable from the database.

REDEMPTION_CODE_PEPPER is mandatory outside tests, at least 32 characters, and must be
generated securely (recommended secrets.token_hex(48)). Examples contain placeholders only.
Protect and back up the exact secret separately from PostgreSQL backups. Losing/changing
it makes existing unused codes unredeemable. There is no automatic rotation or old-key fallback;
coordinate any future rotation with issuance/delivery and audit requirements. Store exports
and this secret in controlled encrypted storage with restricted operator access.

## Generate a ten-Credit pilot batch

Run from the repository root after migration:

```sh
uv run python -m aevyra_api.operator generate-batch --name "Pilot 10 Credits" --channel manual --sku pilot-10 --credits 10 --quantity 10 --output ./exports/pilot-10.csv
```

The CSV has one header and exactly ten rows, with code, credits, batch, channel, expires_at.
The channel can instead be any validated identifier; there is no platform-specific delivery
integration. Optional --expires-at uses an ISO8601 timestamp; use an explicit UTC offset.
SKU/name have length limits and spreadsheet formula prefixes are rejected. Exports must be
.csv files inside ./exports, which Git and Docker ignore. The CLI creates files exclusively
(no overwrite), requests mode 0600 on Unix, and prints only batch ID, export path and quantity.
On Windows, restrict the export directory ACL to authorized operators; POSIX modes do not
replace Windows ACLs. Never share the CSV in logs, Git, screenshots or support tickets.

Database commit and a file cannot be one atomic resource. The operator writes/fsyncs the CSV
before committing an active batch. Normal rollback removes the partial export. A process/host
crash can leave a partial/uncommitted file; uncertain commit outcomes need batch-summary review.
**Before delivery**, inspect the exported batch ID and verify summary quantity/active status.
If a batch committed but its export was lost, codes cannot be reconstructed: disable it and
issue a replacement batch. Do not assume an exported file alone proves successful issuance.

```sh
uv run python -m aevyra_api.operator batch-summary batch_PUBLIC_ID
uv run python -m aevyra_api.operator disable-batch batch_PUBLIC_ID
uv run python -m aevyra_api.operator expire-batch batch_PUBLIC_ID
```

Disable/expire block future redemptions; they do not erase ledger entries or reverse previous
redemptions. There is no public generation endpoint or unused-code listing. Summary exposes
only counts/metadata. Generic CSV delivery can support future third-party channels.

## Redemption transaction

Authenticated POST /api/v1/redeem accepts code only. Normalize and calculate the digest,
locate the code, acquire a shared batch lock, an exclusive code lock, then a wallet lock.
Recheck batch/status/expiry after locking. Append REDEMPTION, update cache, mark REDEEMED,
and insert the unique Redemption audit record in the same transaction. Shared batch locks
serialize with operator disable/expire while allowing different codes to redeem concurrently.
Unique code lookup, redemption-code and ledger idempotency constraints are durable safeguards.

Two simultaneous requests for one code yield exactly one success. Unknown, expired, disabled,
used and malformed codes receive the same generic error. Rate limiting precedes code lookup.
Client-provided user/wallet IDs are rejected, and validation responses omit submitted codes.
The UI says only Redeem Code / Enter the code you received after purchase; no sales channel
is assumed. Batch/channel/SKU are preserved in the internal redemption audit record.
