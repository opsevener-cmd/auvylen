# Order and fulfillment lifecycle — Phase 1

## Order states

```text
CREATED → PENDING_PAYMENT → PAID → FULFILLING → COMPLETED
   └→ CANCELLED      └→ CANCELLED       └→ FAILED → FULFILLING (explicit retry)
```

The state machine in `commercial/state.py` validates every transition. Routes delegate
to services and cannot arbitrarily assign states. PAID is entered only by payment-event
processing. Product price/currency are copied when creating an order and remain authoritative
even if the product price changes later. Public references and analysis/payment UUIDs are
random rather than sequential.

CREATED and PENDING_PAYMENT have validated cancellation transitions in the domain, but no
cancellation API is implemented. REFUNDED is reserved and terminal; no transition or refund
workflow is exposed in this phase. CANCELLED/COMPLETED are terminal in the implemented flow.

## Payment attempts and receipts

One order can hold multiple PaymentAttempts, with unique provider transaction identifiers.
The current API reuses an existing PENDING attempt, including checkout refresh/submission.
Only successful notification processing changes an attempt to SUCCEEDED. PaymentEvent has
a unique `(provider, provider_event_id)` key, normalized payload, received/processed timestamps
and RECEIVED/PROCESSED/REJECTED processing status. See [payment rules](payments.md).

## Fulfillment

Payment commits first. `SynchronousFulfillment` then locks the order and validates payment
evidence. It creates exactly one Analysis via the order unique constraint, moves through
CREATED/PROCESSING, and executes the registry with explicit production context. The mock
input is a server-generated fixture derived from the public order reference; no image exists.

Success stores one AnalysisResult, including raw/display scores, engine/version, optional
calibration version, execution timestamp and `synthetic=true`. Analysis becomes COMPLETED
and Order becomes COMPLETED within the same transaction. Existing completed orders return
without another engine invocation. Different event IDs for a prior successful attempt also
reuse fulfillment rather than rescore.

The intermediate PAID/FULFILLING states may not be visible to the synchronous caller;
paid_at persists payment confirmation and completed_at persists successful completion.

## Failure and explicit recovery

An engine exception records a safe FAILED analysis and FAILED order, without a result or
completed_at. Failure messages do not expose exception text. The successful payment and
processed event remain recorded in their earlier transaction. Duplicate events do not
retry the engine. An explicit development operator retry uses the same Analysis record:

```sh
uv run python -m aevyra_api.retry_fulfillment av_REPLACE_WITH_PUBLIC_ORDER_ID
```

A database/process failure during fulfillment rolls back that fulfillment transaction,
leaving durable PAID state available for recovery. Completed results remain unique. The
CLI is local only and disabled in production; there is no admin/retry endpoint.

## Before a future worker

Keep the Fulfillment interface; replace synchronous implementation deliberately. Design
durable work claiming, an outbox or reconciliation process, retry limits, timeouts and
audit evidence before removing the short mock execution's database lock. Do not hold
financial transactions open across long real inference or external payment calls.
