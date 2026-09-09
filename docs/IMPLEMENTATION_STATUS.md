# Implementation status

Started 2026-09-05. Updated from the source on 2026-09-09. MSHOPPA is a working local alpha. The [current architecture](architecture/CURRENT.md) describes implemented boundaries and flows; the [implementation prompt](CODEX_IMPLEMENTATION_PROMPT.md) includes future requirements.

## Implemented capabilities

| Area | Current state |
| --- | --- |
| Identity and approvals | Verified-email signup, session/CSRF auth, staff TOTP MFA, review, durable provisioning, memberships, audit trail, and mail outbox |
| Catalog and storefront | Products, named variants, regular/offer prices, stock, normalized galleries, publication, host-scoped shops, search/category/sort, product detail, cart, private previews |
| Branding and content | Cover/logo, rich text, contacts/social links, policies, theme settings, self-hosted Poppins |
| Merchant operations | Orders, forward-only paid-order fulfillment, notes/tracking, guest customer summaries, payment list, local domains, staff membership management, variant offers |
| Checkout and payments | Signed cart handoff to shared checkout, server totals/tax, stock reservations, idempotent orders, separate payment database, verified callbacks and tracking |
| Providers | Stripe test hosted Checkout, configurable Venty M-Pesa adapter, optional simulator backends, shared/per-store encrypted credentials and session snapshots |
| Wallet | Owner wallet and withdrawal requests; MFA-protected platform settlement/review; manual transfers recorded by reference |
| Infrastructure | Five Angular apps, two local Django APIs, one SQLite-compatible worker; no Redis/PostgreSQL/Docker requirement |

The payments Python app is still named `simulator`, but is no longer simulator-only. Stripe accepts test keys. Configured Venty M-Pesa can collect real funds; debug mode is not a provider sandbox. Wallet totals exclude Stripe test and simulator money, and require recorded settlement before funds become available. Withdrawals do not trigger automatic transfers. See [payment setup and behavior](../services/payments/README.md).

## Verification on 2026-09-09

- Core: **93 tests passed** using `.venv/bin/python -m pytest -q`.
- Payments: **24 tests passed** using `../core/.venv/bin/python manage.py test simulator`; provider calls are mocked.
- Both Django services passed system checks and `makemigrations --check --dry-run` with no migration drift.
- Strict TypeScript check passed with `npm run check`.
- All five Angular production builds passed with `npm run build`. Angular reported a non-fatal CommonJS optimization warning for Quill's `quill-delta` dependency in merchant admin and storefront.
- HTTP smoke checks and Playwright/browser checks were not rerun for this documentation/source publication. No claim of live provider, visual, accessibility, or production validation is made.

Useful commands and setup are in the [README](../README.md#useful-commands). Tests do not establish production concurrency or deployment readiness.

## Current constraints and remaining work

- SQLite uses explicit tenant scoping and immediate write transactions. One worker handles provisioning, expiration, and at-least-once email delivery with bounded retries.
- Local addresses are `admin.localhost:4201`, `platform.localhost:4202`, `<slug>.localhost:4203`, and payments on port 4204. Local domain management does not verify public DNS or configure TLS.
- Payments shares core's virtual environment/settings/protocol and requires debug/local-payment mode. Internal service URLs remain loopback constants. Undelivered callbacks, ambiguous initiation, and late successes require reconciliation.
- Images remain in core-managed local storage. The separate storage service is reserved, not deployed.
- Staff management adds existing verified accounts; invitations, password/MFA recovery, and shopper accounts remain unimplemented.
- Full inventory movements, automated refunds/payouts, courier/shipping rules, jurisdiction-aware taxes, coupons/campaigns, SMS, notifications, analytics, and SaaS billing remain future work.
- Production infrastructure, backup/restore automation, shared throttling, monitoring, CI, SSR/CDN/cache invalidation, browser/accessibility validation, and a deployment/security review remain outstanding.

## Source publication

The [Nginx deployment guide](DEPLOYMENT.md) now includes example Nginx/systemd configuration, wildcard and merchant-domain SSL issuance/renewal, performance targets, and backup/rollback procedures. These are deployment instructions; production application conversion, target-server validation, and measured load testing remain outstanding.

The source and architecture documentation are prepared for `labohkip81/mshoppa-monorepo`. Git excludes local secrets and `.env` files, SQLite databases, uploaded media, mail files, dependency environments, build output, and agent logs. Example environment files, source migrations, tests, and dependency lockfiles are included. Publishing the repository does not deploy the applications.
