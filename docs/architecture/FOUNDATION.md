# Foundation decisions

Updated 2026-09-09. The [current architecture](CURRENT.md) maps the implementation, including service/data ownership, permissions, request flows, and operational limits. This page records the governing decisions.

## Separate applications, shared implementation

Five independently buildable Angular browser applications separate marketing, merchant administration, platform administration, storefronts, and payments. Shared pages, UI primitives, styles, and API transport live under `packages/`. Backend permissions enforce access regardless of the frontend used. Lockfiles record resolved dependencies.

## SQLite and explicit tenant ownership

The initial phase uses SQLite without PostgreSQL, Redis, or Docker requirements. Business records carry explicit foreign keys; merchant queries verify membership and scope records to that business. Public shops resolve through exact verified domains. This is application-level isolation, not tenant schemas or database row security. Immediate write transactions and uniqueness constraints protect local invariants. Database migration and increased concurrency require separate validation.

## Identity boundaries

Merchant identity is separate from future shopper identity. Platform reviewers require staff permission and TOTP MFA. Membership never grants platform access, and platform staff have no implicit merchant mutation rights. Owners/managers control catalog and settings; fulfillment staff can advance paid orders; owner-only controls protect staff, provider configuration, and withdrawals. See the current architecture's permission table for the implemented matrix.

## Durable provisioning and background work

Approval persists business/provisioning intent and audit data transactionally. One database-backed worker provisions stores, expires reservations, and sends durable outbox mail. Provisioning is retryable and preserves an existing owner's online/offline setting. Mail delivery is outside write transactions, bounded to five attempts, and at-least-once. Celery configuration is present but is not the active development worker.

## Commerce and service ownership

Core owns orders, snapshot lines, inventory reservations, callback receipts, and manual settlement/withdrawal records. A separate payment process/database owns encrypted provider configurations and sessions. Signed internal HTTP, unique order/session keys, and validated callback identity coordinate the services without a distributed transaction. Payments currently shares core's environment, settings, and protocol implementation.

Stripe test, configured Venty M-Pesa, and explicitly selected simulations are implemented. Venty can collect real funds; the service remains restricted to local debug operation. Wallet withdrawals are manually reviewed records, not automatic transfers. Standalone storage remains reserved; core normalizes and serves local images through authorized endpoints.

## Host and content boundaries

Development servers bind to loopback and preserve Host through API proxies. Merchant/platform cookies are host-only; CSRF trusts explicit administration/marketing origins. Unknown, offline, unverified, or suspended public shops fail closed. Private previews use short-lived grants bound to hostname and active membership. APIs are uncached, uploads normalized, and rich text sanitized.

## Production is a separate phase

There is no production deployment, public domain/TLS provisioning, SSR/CDN strategy, autonomous payment reconciliation, automatic payout service, or production concurrency guarantee. Publishing source to GitHub does not enable these capabilities. See [operational boundaries](CURRENT.md#api-contracts-and-operational-boundaries) and [implementation status](../IMPLEMENTATION_STATUS.md).
