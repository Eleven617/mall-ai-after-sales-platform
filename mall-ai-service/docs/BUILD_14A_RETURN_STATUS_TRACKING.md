# Build 14A: Customer Return Status Tracking

## Status

Implementation, deterministic tests, and local Docker-based Java/FastAPI/Vue live verification are complete.

Verified locally on 2026-08-10 with two disposable demo accounts:

- account A created/read application `#28` through the FastAPI customer endpoint;
- account B could not see account A's application;
- the customer response contained only the documented allow-listed fields.

This is a local deployment verification, not a production release claim.

## Product Scope

This build closes the customer-visible gap after a return application is submitted:

```text
explicit confirmation
  -> Java creates one return application
  -> FastAPI returns its safe reference and initial status
  -> Vue shows the submitted application card
  -> customer can open "售后记录" to view only their own applications
```

The build does not implement a carrier integration, customer return waybill upload, warehouse receiving workflow, payment refund, automatic notification, or an AI-controlled status transition. The existing mall-admin status flow remains the source of status changes.

## Java Contract

`POST /returnApply/ai/create`

- Still derives order, product, receiver data and ownership from the Java-authenticated user.
- Now returns a minimal `AiReturnApplySummary` rather than only an insert count.

`GET /returnApply/ai/mine`

- Uses the current JWT user.
- Finds that member's non-deleted orders first, then only return applications belonging to those orders.
- Returns only:
  `applicationId`, `orderSn`, `productName`, `productAttr`, `reason`, `description`, status fields, timestamps and a handling note.
- Never returns address, phone, price, internal order ID, member username, or staff identity.

## Status Mapping

| Java status | Customer status | Display label |
| --- | --- | --- |
| `0` | `pending_review` | 待审核 |
| `1` | `approved_return` | 已同意退货 |
| `2` | `completed` | 售后完成 |
| `3` | `rejected` | 已拒绝 |
| other/null | `unknown` | 状态待确认 |

## Boundary

The browser supplies only a Bearer Token. It never supplies `member_id`, a return application ID to authorize access, an internal order ID, or a status change request. Java remains the authorization and business-data authority.

## Verification Evidence

1. Java service test: trusted creation, current-member filtering, status mapping, safe DTO field boundary.
2. FastAPI test: parse Java summary, require Bearer Token, expose only public fields.
3. Vue build: type-check and production build.
4. Live test: create a disposable local application, confirm the submitted card, view it from account A, and ensure account B cannot view it. Passed locally on 2026-08-10.

## Known Next Boundary

This build does not solve the "Java wrote the application but its HTTP response was lost" case. Build 16 remains responsible for an idempotency key and submission-result recovery.
