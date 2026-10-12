# Payments — Phase 1

## Implemented boundary

`PaymentProvider` owns create, query, verified notification handling, and provider-level
refund operations. `OrderService` uses the interface without provider-specific business
branches. Only the configured mock provider is supported. WeChat Pay and Alipay classes
implement the interface as inert scaffolds, with no SDK, credentials or network calls.

The mock ledger is the persisted PaymentAttempt. Query returns the trusted ledger snapshot;
creation returns a deterministic provider identifier from the attempt UUID. Mock refund
returns a deterministic synthetic receipt for a successful snapshot; it does not perform
an application refund or transition the order. No refund endpoint is exposed.

## Development success simulation

The development route accepts only an empty body and a random payment ID. The server loads
the attempt and its authoritative terms, creates a stable success event ID, signs the
notification with a process-local key, then verifies it through `handle_webhook` before
calling `PaymentEventProcessor`. The key is internal, ephemeral and never browser-exposed.
It is not a real-provider signature scheme. No public mock webhook exists.

This simulation is intentional unauthenticated development behavior, available only in
development/test environments. All commercial routes return 404 in production. Public
deployment requires authorization before these routes may be enabled.

## Transactions and idempotency

1. Find the persisted attempt and lock its Order using `SELECT FOR UPDATE`.
2. Refresh the attempt after obtaining the lock.
3. Check `(provider, provider_event_id)`; duplicate matching payloads reuse the receipt.
4. Insert a unique event inside a savepoint. The database handles cross-order identifier
   races; a collision with different normalized content is rejected.
5. Validate event type, provider, amount, currency and current state against both order
   and attempt. Reject mismatches without marking either successful. Persist a REJECTED
   receipt for known attempts; return an explicit domain error after committing it.
6. For a valid success, mark the attempt SUCCEEDED, transition the order PAID, and mark
   the event PROCESSED in one transaction.
7. Commit, then invoke the fulfillment interface in a separate transaction.

Only the event processor can confirm success. Price overrides and forged frontend state
fields fail request validation. Payload persistence uses normalized allowlisted event
fields; raw request bodies and provider secrets are not logged or stored here.

Order locks serialize duplicates, including different event IDs for the same successful
attempt. A second pending attempt cannot charge an already-paid order through this flow.
One analysis/order and one result/analysis unique constraints are final safeguards. No
in-memory cache or Redis lock is used for financial correctness.

## Recovery and execution guarantee

Payment evidence survives scoring failures. Duplicate events return the existing result
or FAILED state without re-executing failed scoring. Explicit operator retries are available
through the local CLI described in README. A crash after payment commit but before fulfillment
can resume a PAID order through the service, including a subsequent matching event delivery.

Successful repeated/concurrent deliveries execute the mock once and persist one result.
This is not a universal exactly-once compute guarantee across process crashes: a crash
after computation but before its transaction commits may require recomputation. The mock
is deterministic and has no external effects. Future workers need durable claiming,
timeouts, retries and an outbox/reconciliation design before real workloads are introduced.

## Future providers — not implemented

`POST /api/v1/payments/webhooks/{provider}` is reserved but absent. A future adapter must
verify authenticity before returning a normalized VerifiedPaymentEvent. Never bind that
internal model directly to an unverified HTTP body.

- WeChat Pay: request/transaction identifiers, payment query, certificate/signature
  verification, asynchronous notifications and refund support.
- Alipay: request/trade identifiers, payment query, notification verification and refunds.

Retries of external payment creation require provider-supported idempotency and durable
request reconciliation. The present database transaction encloses local mock creation;
do not assume it can atomically cover a future remote provider call. Real refund accounting
and webhook reconciliation must be designed separately. Empty future env placeholders are
not consumed; changing PAYMENT_PROVIDER to a real provider is deliberately rejected.
