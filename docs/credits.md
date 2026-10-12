# Credit ledger

Credits are integer units. One user owns one Wallet. CreditTransaction is the authoritative,
append-only history; cached_balance accelerates reads. PostgreSQL rejects UPDATE, DELETE
and TRUNCATE of credit_transactions through migration-installed triggers. Administrators
remain a privileged trust boundary and must not disable these protections during operation.
Corrections append compensating entries; no normal operator command edits history or cache.

## Mutation invariants

Within one PostgreSQL transaction, lock the wallet row with SELECT FOR UPDATE, read SUM(amount),
and verify it equals cached_balance. Refuse mutation if reconciliation is needed. Look up
the wallet-scoped unique idempotency key; a conflicting retry fails. Append a nonzero amount
and balance_after, update the cache, and commit atomically. Never allow a negative balance;
database constraints additionally reject negative cached/balance_after values. Balances are
bounded to the JavaScript safe integer range. All business mutations use this service.
See [PostgreSQL row-lock semantics](https://www.postgresql.org/docs/current/explicit-locking.html).

Reference IDs, transaction type, metadata/reason and timestamp preserve the audit trail.
Types currently used: REDEMPTION, ANALYSIS, ANALYSIS_REFUND, PROMOTION and MANUAL_COMPENSATION.
No direct payment currently funds this ledger. A future verified payment handler can append
through the same service with a payment-event-based idempotency key; provider logic stays outside it.

## Credit-funded synthetic analysis

Product.credit_cost is backend-owned, positive, and defaults to one for the existing mock
product. The browser sends only product_slug and a UUID request key, never an authoritative
cost. Under the wallet lock, create an account-owned Analysis and append -credit_cost with
key analysis:{analysis UUID}. The deduction commits before synchronous fulfillment starts.
The unique (user_id, credit_request_key) pair handles double clicks and retries. A retry
returns the same analysis and never spends/executes again after completion.

Fulfillment locks the analysis, uses the existing registry policy gate, persists the versioned
synthetic AnalysisResult and completes the analysis. Inference failure marks FAILED and appends
the exact original debit as ANALYSIS_REFUND with key analysis-refund:{UUID}. Refund retries
lock the same rows and cannot append twice. A failed/refunded analysis is terminal; a new run
needs a new request key. Order-funded analyses retain their original payment lifecycle and inputs.

Production returns 404 before deducting for mock analysis. Development/private staging allow
execution. There are no real facial models or photo inputs.

If the process stops after deduction, the persisted CREATED analysis is recoverable. After
restoring database availability, an operator can resume it. Result-storage transaction failures
also leave the original deduction and a recoverable analysis; they never falsely complete it.
The future worker can call the same fulfillment service; no queue is implemented now.

```sh
uv run python -m aevyra_api.operator resume-analysis ANALYSIS_UUID
uv run python -m aevyra_api.operator refund-failed-analysis ANALYSIS_UUID
uv run python -m aevyra_api.operator wallet usr_PUBLIC_ID
uv run python -m aevyra_api.operator grant usr_PUBLIC_ID --amount 3 --reason "Pilot promotion" --key UUID
uv run python -m aevyra_api.operator compensate usr_PUBLIC_ID --amount 1 --reason "Reviewed correction" --key UUID
```

Operator keys must be generated once, recorded, and reused when retrying the same operation.
Compensation accepts signed amounts but cannot overdraw. All manual entries preserve their
reason; wallet inspection reports ledger/cache consistency. Account UI shows recent entries
and analyses; complete audit history remains in PostgreSQL. No public grants/admin API exists.
