# 2026-08-14 Reliability Hotfix

## Why this exists

The Java portal can fail while releasing locked SKU inventory during delayed
order cancellation. The original listener allowed the failure to become a
repeated RabbitMQ delivery, while the Docker Compose stack had no stdout log
rotation limit. A single inconsistent order could therefore produce unbounded
logs and exhaust the host disk.

The message means that the locked-inventory ledger is smaller than the order
quantity at release time. It does not by itself mean that physical inventory
is unavailable.

## Changes

- Compose applies a 10 MB / 3-file cap to every container's `json-file` log.
- Spring Boot file logging is capped at 10 MB per file, 7 files, and 100 MB
  total for the Docker profile.
- Cancellation failures are published to the durable
  `mall.order.cancel.failure` queue with a bounded size and seven-day TTL.
- The original cancellation message is acknowledged after the failure is
  preserved, so it cannot hot-loop in the source queue.
- If the failure queue itself is unavailable, the listener rejects without
  requeue instead of retrying forever.
- Three unit tests cover success, failure preservation, and failure-queue
  unavailability.

## Deliberate boundary

This hotfix contains the failure and protects the host. It does not pretend to
repair an inconsistent stock ledger automatically, and it does not implement
the transactional Outbox + RabbitMQ after-sales event path planned for Build
18. A failure-queue consumer and a business reconciliation workflow remain
future work.

## Verification

- YAML parsing: passed.
- Java module compilation: passed.
- `CancelOrderReceiverTest`: 3/3 passed.
- Docker live revalidation: pending until the local Docker CLI/daemon is
  available after the Desktop data relocation.
