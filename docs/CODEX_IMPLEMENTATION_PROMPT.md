# MSHOPPA — Codex implementation prompt and delivery plan

Status: implementation is in progress. See `docs/IMPLEMENTATION_STATUS.md` for verified capabilities and remaining phases.

Prepared: 2026-09-05.

Latest user overrides, 2026-09-05: approved businesses go online automatically after successful provisioning, with an owner/manager online/offline control in Store settings. This supersedes the manual store-publication gate below. Draft/published product visibility remains separate; no payment capability is implied by an online store. Remove decorative overline headings from interface pages. The business product editor must support regular/offer prices and intuitive multiple-image uploads with thumbnails and enlarged previews. Local stores use `<slug>.localhost:4203`.

Initial implementation override, 2026-09-05: the user requested SQLite for easier testing. Use SQLite with explicit business foreign keys, membership authorization, and tenant-scoped queries in the initial phase. PostgreSQL, `django-tenants`, schema provisioning, and schema-specific acceptance criteria below describe a later migration, not the current implementation. Adapt the initial acceptance gates to prove row-level business isolation; do not claim database schema isolation on SQLite. Local testing must not require PostgreSQL or Docker.

## How to use this brief

Give Codex this instruction from the repository root when ready to implement:

> Implement MSHOPPA according to `docs/CODEX_IMPLEMENTATION_PROMPT.md`. Read the complete brief and applicable repository instructions first. Treat this document as the product specification and phased implementation plan. Inspect the existing workspace and reference assets, preserve existing projects, and implement the phases in order. Make reasonable reversible implementation decisions within the specified architecture. Verify each phase with the acceptance criteria and maintain an honest progress record in `docs/IMPLEMENTATION_STATUS.md`. Do not substitute a static demo for functioning backend workflows. Report external dependencies separately from completed functionality.

This document authorizes no action by itself. The current request is to prepare the plan and preserve references. A later instruction to implement activates the implementation workflow above. Do not deploy, register domains, create live payment accounts, charge money, or contact customers merely because those actions appear in the plan.

## 1. Product objective

Build an ecommerce SaaS where independent businesses apply to MSHOPPA, receive approval from platform staff, configure their own branded stores, and sell to customers. Each business manages its products, variants, inventory, orders, payments, customers, delivery, communication, staff, domains, and policies.

The platform must be straightforward for nontechnical merchants, fast on mobile connections, and secure across tenant boundaries. A business is a tenant. Initially each business has one storefront, one base currency, and one inventory location. A merchant identity may belong to multiple businesses through explicit memberships.

The defining first milestone is: two independent businesses apply, are approved, publish differently branded stores, accept orders, and manage fulfillment without accessing each other's private data.

## 2. Required stack and architecture decisions

- Use Angular and TypeScript for all user interfaces, including marketing, business administration, platform administration, storefront, and payment pages.
- Use Django and Django REST Framework for all business backends. Use REST APIs with an OpenAPI contract and generated TypeScript clients.
- Use custom commerce code. Do not introduce Saleor, Oscar, Medusa, or another commerce engine without a new product decision.
- Use PostgreSQL. Evaluate and prove `django-tenants` schema-per-business integration during the foundation phase before building the commerce modules.
- Use background workers for provisioning, notifications, media processing, and payment reconciliation. Select supported queue/cache packages and document their versions and licenses.
- Use S3-compatible object storage and a CDN for assets. Django authorizes operations; it should not proxy ordinary product-image downloads.
- Keep commerce business logic modular within the core Django service. Separate payments and storage into their own service directories with explicit APIs and ownership. Do not create another microservice for every product feature.
- Keep dependency versions supported and mutually compatible. Validate the Angular UI library, Django, DRF, tenant package, and worker stack before pinning versions and lockfiles.
- Angular SSR may use a Node rendering process. Node performs frontend rendering only; authentication decisions, commerce rules, APIs, and payment orchestration remain in Django. Document this infrastructure requirement.

## 3. Monorepo and directory ownership

The current `/Users/admin/Dev/MSHOPPA` directory is the monorepo root. Do not create a second nested `mshoppa/` repository. The existing `saleor/`, `saleor-dashboard/`, `storefront/`, and `run.sh` are legacy/reference material until explicitly migrated. Inspect nested Git repositories, user changes, and local instructions before acting. Do not delete, move, rewrite, or absorb their Git histories automatically.

Create new implementation work under the following structure. This is a planned tree, not a claim that these applications already exist:

```text
MSHOPPA/
  apps/
    marketing/                 # Angular: mshoppa.com
    merchant-admin/            # Angular: admin.mshoppa.com
    platform-admin/            # Angular: platform.mshoppa.com
    storefront/                # Angular SSR: tenant and custom domains
    payments/                  # Angular: payments.mshoppa.app
  services/
    core/                      # Django: platform and tenant commerce APIs
      config/
      apps/
        accounts/
        businesses/
        provisioning/
        domains/
        catalog/
        inventory/
        checkout/
        orders/
        customers/
        delivery/
        themes/
        policies/
        notifications/
        billing/
        audit/
    payments/                  # Django: provider credentials, payment ledger, callbacks
    storage/                   # Django: upload authorization and asset records
  packages/
    ui/                        # Shared Angular primitives and platform design tokens
    api-client/                # Generated clients; do not hand-edit generated files
    storefront-themes/         # Versioned Angular storefront themes and section types
    frontend-utils/            # Small shared utilities; no secret/backend logic
  assets/
    brand/
    references/
      storefront/
  docs/
    CODEX_IMPLEMENTATION_PROMPT.md
    IMPLEMENTATION_STATUS.md   # Create when implementation begins
    design/
      STOREFRONT_DESIGN.md     # Required client-storefront visual specification
    architecture/
    runbooks/
  infra/
    local/                     # Local containers, domain routing, seed commands
    deployment/                # Reviewable deployment configuration
  tests/
    e2e/
    integration/
```

Use one Angular workspace with separately buildable applications and shared libraries. Each Django service owns its own dependency configuration, migrations, tests, and environment example. Common tooling may live at the root. Avoid duplicating Django models between services.

### Domains and routes

| Domain | Directory | Responsibility |
| --- | --- | --- |
| `mshoppa.com` | `apps/marketing` | Product information, signup, application submission |
| `admin.mshoppa.com` | `apps/merchant-admin` | Applicant status and business administration |
| `platform.mshoppa.com` | `apps/platform-admin` | MSHOPPA staff approvals and platform operations |
| `<business>.mshoppa.com` and verified custom domains | `apps/storefront` | Shopping, checkout, confirmation, order history, tracking |
| `payments.mshoppa.app` | `apps/payments` + `services/payments` | Payment session UI, payment APIs, provider callbacks |
| `storage.mshoppa.com` | `services/storage` + object storage/CDN routing | Asset service and file delivery; no standalone admin UI initially |

`platform.mshoppa.com` is the proposed platform staff address. Reserve `admin`, `platform`, `payments`, `storage`, `www`, `api`, and other infrastructure names so merchants cannot claim them.

Use same-origin `/api/` routing where practical; the edge routes requests to the owning Django service. Storefront origin routing must preserve a trusted original hostname for tenant resolution. Custom domains use the same storefront deployment, not generated code or separate deployments.

## 4. Branding and visual references

Use `assets/brand/mshoppa-logo-reference.png` as the supplied M-SHOPPA logo. It is a raster reference with a white background. Preserve its proportions. Do not redraw, crop, recolor, or claim a transparent/vector version exists without an explicit asset task.

Brand direction:

- Orange accent, black wordmark/text, and white surfaces, as shown in the supplied logo.
- Provisional orange token: `#F58220`. This is a working approximation, not a sampled or user-confirmed exact color. Replace it if an original brand specification becomes available.
- Core black: `#000000`; core white: `#FFFFFF`. Use neutral grays for borders, muted text, and surfaces.
- Use orange for accents and selected elements. Check contrast rather than assuming white text works on the orange token. Dark primary buttons are acceptable.
- MSHOPPA branding applies to platform interfaces. Storefront branding belongs to the merchant; the default client-storefront language is defined in `docs/design/STOREFRONT_DESIGN.md`, with merchant logos/content and validated tenant-scoped theme settings.

The requested Shadcn Admin reference is `https://www.shadcn.io/template/satnaing-shadcn-admin`. It is a React template. Reproduce the visual conventions in Angular using Tailwind and Angular-native Spartan UI primitives after verifying compatibility. Do not introduce React to reuse the template. Preserve applicable attribution/licenses when reusing assets or design source.

### Client storefront design decision — 2026-09-05

Read `docs/design/STOREFRONT_DESIGN.md` completely before implementing client storefront UI. The user selected the supplied Allbirds design language for `<business>.mshoppa.com` and verified merchant custom domains: warm canvas `#ece9e2`, graphite ink/CTAs `#212121`, full-pill actions, 16px cards, muted material-tone image backgrounds, restrained serif displays, and flat surfaces. Implement this as the default Angular theme `natural-01` in `packages/storefront-themes`.

This decision applies to storefront browsing, shopper accounts, cart, store-hosted checkout/confirmation, and delivery tracking. It does not restyle merchant/platform admins, the MSHOPPA marketing website, or the separate `payments.mshoppa.app` application. Admins retain their Shadcn-inspired Angular design; scope theme tokens and previews so styles do not leak between applications. The reference's React metadata does not change the Angular stack.

Use merchant branding and products, not Allbirds assets/copy. Font names in the reference do not supply font licenses or files. Follow the design document's explicit font fallbacks, accessible focus/touch-target adaptations, and mobile/checkout extensions. Reference extraction counts and contradictory source commentary are not implementation requirements.

Use `assets/references/storefront/` as the shopping workflow and component-structure reference, with the new design document taking precedence for visual styling:

1. `01-product-detail.png`: image gallery, variants, price, purchase action.
2. `02-product-list.png`: product grid, filter controls, sorting, category context.
3. `03-cart-empty.png`: cart drawer empty state.
4. `04-cart-filled.png`: line items, quantities, totals, delivery threshold, checkout action.
5. `05-checkout.png`: contact/address form, progress, order summary.

Use the hierarchy and interactions as references and apply the `natural-01` theme; replace Saleor branding, demo images, hardcoded currencies, and default policies. Do not copy reference defects such as duplicate “optional” labels, misleading free-shipping claims, or an unexplained disabled purchase button. The screenshot branding is not MSHOPPA production artwork.

The user intends to add a folder containing planned frontend UI. During implementation, inspect it if present and inventory its screens. Record its path in the status document. If absent, proceed with these references and document the assumption; do not claim it was inspected.

## 5. Required user journeys

### A. Marketing and business application

Keep marketing minimal: value proposition, product preview, feature overview, contact/support, signup, and login. Do not invent subscription prices or publish placeholder pricing as real pricing.

Application flow:

1. User registers, verifies email, and creates a merchant identity.
2. User enters business name, contact details, business category, launch country, and preferred subdomain.
3. Save drafts and validate subdomain availability and reserved names.
4. User submits; the application becomes pending review.
5. MSHOPPA reviewer approves, requests changes, or rejects with a reason.
6. Approval starts an idempotent background provisioning job.
7. Once provisioning succeeds, the owner enters the store setup checklist.

Model application review, provisioning, and storefront publication separately. A request for changes is resubmittable. An approved application may have provisioning in progress or failed. An approved store can remain unpublished.

The launch checklist requires business profile, branding, at least one sellable product, an available payment method, delivery/pickup setup, and contact/policy pages. Payment on delivery may satisfy the payment requirement if enabled and applicable. Preview is private; public selling requires approval and publication.

### B. Platform staff portal

Implement application queue, business detail, approval actions, provisioning status/retry, business status, domain overview, provider readiness summaries, and operational errors.

Use separate platform permissions and MFA. A merchant must never become platform staff by setting a request field or ordinary business role. Audit approvals, suspensions, privileged access, provider configuration changes, and refunds.

Suspension blocks new selling and relevant merchant writes while preserving records and appropriate customer access to existing orders. Document exact behavior. Do not implement tenant deletion as a suspension mechanism. Broad support impersonation is deferred; initial support access must be explicit, scoped, and audited.

### C. Merchant administration

Provide a store switcher only for businesses where the current user has membership. Always display the selected store and a “View store” action. Before launch, emphasize the checklist. After launch, emphasize actionable orders, sales, low stock, and payment issues.

| Section | Required first-release scope |
| --- | --- |
| Dashboard | Date-filtered sales/orders, low stock, pending fulfillment, payment problems; define metric meanings |
| Products | Draft/published products, categories, descriptions, images, simple variants, prices, visibility |
| Inventory | On-hand/reserved/available stock, adjustments with reasons, stock movement history, low-stock threshold |
| Orders | Search/filter, details, customer contact, status history, cancellation, refund requests, fulfillment |
| Payments | Attempts, pending/successful/failed payments, refunds, COD collection, reconciliation issues |
| Customers | Store-scoped profiles, addresses, order history, communication preferences |
| Communication | Transactional template settings, delivery history, failed-message retries, in-app inbox |
| Website | Theme, sections, navigation, domains, preview/publish, policy pages |
| Staff | Invitations, owner/manager/fulfillment/support roles, permissions, membership removal |
| Settings | Business identity, currency/timezone, payment providers, delivery, notifications, platform subscription status |

Product creation must work without understanding SKUs, channels, warehouses, or product types. Start with name, image, price, and stock. Offer optional size/color/etc. attributes, generate combinations, and provide an editable price/stock/SKU table. Allow disabling combinations. Generate SKUs when omitted. Validate uniqueness within the business.

Use server pagination/filtering and bulk actions where appropriate. Every section needs meaningful empty, loading, error, permission, and success states. Changes shown in the UI must persist through the Django API.

### D. Customer shopping

Implement homepage, category/collection pages, searchable/filterable product list, product details, gallery, variant selection, cart drawer, checkout, confirmation, order history, and delivery tracking.

Variant selection must resolve a valid sellable variant, show its price/availability, and explain unavailable combinations. Cart edits must refresh authoritative server totals. Shipping thresholds and promotional badges must reflect actual configured rules.

Checkout supports guests and optional customer accounts. Collect country-appropriate fields and pickup/delivery information. Keep marketing consent optional and separate from accepting necessary transaction terms.

Order confirmation must distinguish payment successful, payment pending, payment failed, and payment due on delivery. An order confirmation is not automatically a payment receipt.

Guest order access and tracking require an opaque, scoped token or verification flow. Never expose order/customer data by predictable order number alone.

### E. Themes, domains, and policies

Start with the polished responsive `natural-01` theme specified in `docs/design/STOREFRONT_DESIGN.md` and typed sections: hero, featured products, collections, image/text, announcement, and footer. Merchants configure validated theme settings, logo, navigation, section content/order, and contact links. Keep the warm canvas and graphite CTA as defaults. The theme editor retains the admin design, with an isolated storefront preview.

Store a draft and a published version. Preview must be private and excluded from search indexing. Publishing updates the active version and invalidates tenant-specific caches. Include rollback to a previous published configuration. Theme configuration is data, not arbitrary executable merchant code.

Support a platform subdomain first, then custom domains with ownership verification, DNS instructions, TLS status, primary-domain selection, and safe redirects. Enforce unique ownership and reject unknown hosts; do not fall back to another store. Domain removal/reassignment must prevent stale mappings and takeover.

Provide editable privacy, terms, returns/refunds, and delivery policies. Any starter wording is a draft for merchant review, not a guarantee of legal compliance. Show the published policies on the storefront and record required checkout acceptances with a policy version.

### F. Delivery

Support pickup and simple delivery zones/rates, including a configurable free-shipping threshold. A nonmatching address should not silently receive free delivery.

Track confirmed, preparing, dispatched, out-for-delivery, delivered, failed-delivery, and returned events with timestamps and actors. Validate allowed transitions and record corrections. Staff update statuses initially; live courier integrations and GPS tracking are deferred.

Keep order, payment, and delivery state separate. A delivered COD order may still need collection verification. Inventory release/restocking must follow documented cancellation/return rules rather than every status change.

## 6. Tenant data and authentication design

Proposed database layout:

- Core public schema: merchant identities, business memberships, business/application registry, domain mappings, provisioning status, platform subscriptions, platform audit events.
- Core tenant schema: catalog, inventory, shopper profiles/addresses, carts, orders, delivery events, theme settings, policies, and tenant communication records.
- Payments-owned database: provider configurations, payment sessions/attempts, refunds, webhook records, reconciliation, and payment event outbox. Every merchant-owned row carries an immutable tenant identifier.
- Storage-owned metadata: asset ownership, public/private classification, upload status, and object keys. Every merchant-owned row carries an immutable tenant identifier.

The deployment can use one PostgreSQL server initially with distinct service databases/roles. Only the owning service writes its database; core stores a projection of payment status, not a second editable payment ledger.

For storefronts, verified hostnames select tenants. For the central merchant portal, authenticate first, validate business membership, and then enter the selected schema. Never treat a client-supplied tenant ID/header as authorization. Restore database context after every operation, including failures and reused worker connections.

Explicitly separate merchant/platform identities from shopper identities. Define how shared merchant identities authenticate against tenant-scoped operations before implementing Oscar-like or Django auth assumptions. A shopper in business A must not gain business B's account or order access because an email matches.

Use secure HttpOnly cookies for browser sessions where appropriate, CSRF protection for cookie-authenticated writes, exact origin policies, rate limits, and MFA for privileged roles. Do not use a broad `.mshoppa.com` session cookie across merchant storefronts and administration. Treat custom-domain sessions and the `.app` payment origin as separate contexts.

Payment/storage service requests require authenticated service identity and server-validated tenant scope. Public storefront catalog access does not imply access to a tenant's private APIs.

Schema isolation is logical separation within shared infrastructure, not a complete security boundary. Test queries, joins, exports, search indexes, files, sessions, logs, caches, background jobs, and webhooks for tenant leakage. Use tenant IDs in cache keys and object namespaces. Never log credentials or unnecessary customer data.

## 7. Payment architecture and correctness

Initial methods: Stripe card payments, Safaricom M-Pesa, and payment on delivery.

Working assumption: customer funds settle to each business's provider account. MSHOPPA's subscription billing is a separate flow. Do not silently implement pooled collection or merchant payouts. Confirm settlement ownership and provider eligibility before live onboarding; continue safe sandbox and core work meanwhile.

### Provider setup

- Merchant settings show disconnected, configuring, test-ready, live-ready, disabled, and action-required states as appropriate.
- Stripe: evaluate Connect onboarding and direct charges against the launch country and account requirements. Use Stripe-hosted payment fields/Elements so Django never receives raw card data. Do not assume all merchants can use Stripe in all countries.
- M-Pesa: use Daraja and verify which merchant shortcode/business account configuration supports the desired prompt and reconciliation flows. Support sandbox first. Do not invent production credentials, business identifiers, or callback-signature mechanisms.
- COD: configure eligibility by delivery zone and optional order limit. Restrict recording collection and adjustments to authorized staff; audit amount, actor, time, and collection reference.
- Store secrets encrypted and masked; never return secret values to Angular. Separate test and live configuration. Handle credential rotation and disabled providers.

### Payment handoff

1. Core revalidates variant availability, currency, server prices, discounts, delivery, and final totals.
2. Core creates a pending order snapshot and a bounded inventory reservation in a database transaction. Use integer minor units or exact decimals, never binary floating-point money.
3. Core creates a payment session through an authenticated payment-service request with an idempotency key and immutable order/tenant references.
4. Customer navigates to `payments.mshoppa.app` using a short-lived opaque reference. Do not put secrets or customer details in the URL. The reference cannot authorize arbitrary amounts or tenants.
5. The Angular payment app shows merchant identity and authoritative totals, then initiates the selected method. It exposes only scoped session operations.
6. Payment service verifies provider events, records durable state, and emits a retryable event to core. Core applies it idempotently and updates the order.
7. Customer returns to an allowlisted storefront URL; the confirmation page loads server status. Browser redirects and client assertions never establish payment success.

Do not hold database transactions open while calling providers. Handle retries through durable records and reconciliation. Payment and order services must recover if the provider succeeds but an internal request times out.

Persist webhook events before acknowledgement and process them asynchronously. Verify signatures where the provider supports them; otherwise apply the documented provider verification mechanism and server-side transaction reconciliation. Check provider account, transaction reference, amount, currency, and tenant mapping. Handle duplicate, delayed, and out-of-order events without duplicate charges, orders, fulfillment, or notifications.

Model multiple payment attempts per order. A timeout is not proof of failure. Before creating another attempt, reconcile uncertain state. Define a late-success policy when an inventory reservation has expired: do not silently oversell; reconcile availability and flag/refund according to an explicit policy.

Support pending, succeeded, failed, expired, cancelled, and refunded/partially-refunded outcomes where applicable. Record refund attempts separately, cap refunds against the refundable balance, and make provider refunds idempotent. Surface unknown/manual-review states honestly.

Track COD collection separately from online payment attempts and fulfillment. Inventory updates and notification creation must be transactionally consistent with the relevant business event. Use an outbox or equivalent durable event pattern across service boundaries.

## 8. Notifications and communication

Support email, SMS, and persisted in-app notifications through provider adapters. Select actual email/SMS providers before production; local development uses a mail catcher and explicit test adapters.

Required events: email verification/password recovery, application status, staff invitation, order placed, payment result, dispatch, delivery/failed delivery, and low stock.

Persist notification intent, channel, tenant, recipient reference, delivery attempts, provider reference, and final status. Retry transient failures with backoff, deduplicate by business event/recipient/channel, and prevent a notification retry from replaying the original business operation.

Communication settings support approved transactional templates and channel preferences. Marketing subscriptions are separate and opt-in. Bulk campaigns, two-way SMS conversations, and automation builders are deferred. Never label an SMS/email “delivered” based only on queue submission.

## 9. Storage service

Implement upload authorization, object key generation, file type/size limits, completion verification, and asset metadata. Use short-lived signed operations and scope them to a tenant, object, and purpose.

Use public CDN delivery for published product images and restricted downloads for approval documents, private exports, and other sensitive files. Avoid public bucket defaults. Serve uploaded active content safely; isolate untrusted files from trusted application origins.

Validate uploaded content and process product images into responsive formats/sizes in background jobs. Do not process large uploads inside the main request. Clean abandoned uploads according to a documented retention policy.

Do not let a caller choose another business's object key. Test access to both metadata and the underlying object URL. Explicitly define cache invalidation and deletion behavior.

## 10. Performance and usability requirements

- Prerender stable marketing pages. SSR storefront catalog/product pages with hydration. Lazy-load private administration and payment routes.
- SSR output must resolve the correct tenant, theme, metadata, canonical URL, and product content before sending the page. Tenant identity must be part of every HTML/data cache key.
- Exclude private, cart, payment, and account data from shared caches. Revalidate authoritative price/stock/totals during checkout regardless of catalog cache state.
- Optimize images, reserve image dimensions, paginate queries, prevent N+1 queries, and add indexes justified by actual access patterns.
- Keep charts, rich editors, and management dependencies out of shopper bundles. Define per-application build budgets after the first measured build.
- Target mobile p75 LCP below 2.5 seconds, INP below 200 ms, and CLS below 0.1. These are targets, not claims of achieved performance. Use lab checks before launch and field monitoring after launch.
- Test keyboard navigation, focus management, form errors, cart drawer behavior, responsive layouts, and contrast. Validate on a small mobile viewport and a desktop viewport.
- Merchant-visible totals and counts must be real or explicitly empty. No production demo metrics, fake sales, placeholder payment success, or invented delivery events.

## 11. Implementation phases and acceptance gates

### Phase 0 — Inspect and specify

- Inspect workspace, applicable instructions, supplied UI folder if present, reference images, and local dependency tooling.
- Read `docs/design/STOREFRONT_DESIGN.md` and record the storefront/admin design boundary, available font assets/fallbacks, and the adaptations required for mobile and checkout.
- Preserve existing projects and uncommitted changes. Do not expose `.env`, private keys, or production credentials in logs.
- Create `docs/IMPLEMENTATION_STATUS.md`, a route/screen inventory, role matrix, data ownership document, state transition definitions, and architecture decision records.
- Confirm compatible package versions and record unresolved product choices. Do not install obsolete dependencies just to fit an example.

Acceptance: the scope, directory ownership, provider assumptions, and reusable/reference-only assets are explicitly recorded. Proceed with authorized reversible work while external provider decisions remain unresolved.

### Phase 1 — Monorepo, tenancy, auth, approval

- Scaffold Angular apps/shared UI and Django services with local PostgreSQL, workers, object storage emulator, and mail catcher.
- Provide local host routing, environment examples, seeds, migrations, and documented start/check commands.
- Implement merchant signup, email verification, platform login, application review, provisioning, and membership-scoped administration.
- Create two test tenants; verify tenant routing, unknown-host rejection, schema/context cleanup, permission denial, and isolated customer identities.

Acceptance: two applicants can independently be approved and provisioned; retrying approval/provisioning does not create duplicate tenants, owners, domains, or schemas. Unauthorized users cannot invoke platform actions or switch into another business.

### Phase 2 — Catalog, stock, themes, storefront

- Implement merchant products/variants/inventory, authorized uploads, tenant theme settings, private preview, and publication.
- Implement Angular storefront listing, product detail, filters, navigation, gallery, cart drawer, and basic policy/contact pages.
- Implement scoped `natural-01` tokens and components from `docs/design/STOREFRONT_DESIGN.md`; retain admin styling and use the earlier screenshots only for workflow structure. Capture catalog/PDP/cart on mobile and desktop and verify focus, contrast, and touch targets.

Acceptance: each merchant can publish a visibly different store, create a product with variants, adjust stock with history, and see only their own data. Public SSR/caches cannot mix tenant content. The cart survives navigation and has server-calculated values. The default theme meets the relevant design acceptance criteria, and tenant publishing/preview does not restyle admin interfaces.

### Phase 3 — Orders and payment methods

- Implement checkout, inventory reservations, pending order snapshots, payment sessions, Stripe sandbox, M-Pesa sandbox, and COD.
- Add webhook validation, durable events, reconciliation, refunds, failure/pending screens, and secure confirmation access.
- Extend `natural-01` to store-hosted checkout and confirmation, including pending/failed/COD-due states. Keep the separate payment application in its existing design scope and preserve clear merchant identity across handoff.

Acceptance: end-to-end test orders work for all three methods in their appropriate test modes. Cover duplicate requests, duplicate callbacks, delayed success, provider timeout, invalid amount/currency/account, concurrent purchase of the last item, expired reservations, refunds, and cross-tenant payment access. Clearly distinguish simulations from provider-verified integration tests.

### Phase 4 — Merchant operations

- Implement customer management, delivery transitions/tracking, notification delivery/history, in-app inbox, staff roles, and domain management.
- Add published policy versions, useful dashboard metrics, and platform operational views.
- Apply `natural-01` to shopper accounts, public policies, and delivery tracking while keeping merchant/platform operations in their admin design system.

Acceptance: a merchant fulfills an order, a customer sees only authorized tracking information, and notification delivery status is recorded. Staff permissions match the role matrix. A custom domain only becomes active after verified ownership and successful TLS configuration.

### Phase 5 — Pilot readiness and hardening

- Add tenant export and backup/restore runbooks, deployment configuration, migrations strategy, health checks, monitoring, alerting, and redacted logs.
- Test payment/storage service downtime and recovery, worker retries, domain changes, suspension, database migration failure, and representative load.
- Measure performance/accessibility on representative product and checkout journeys. Fix material failures.
- Set up live providers only when credentials, business eligibility, and explicit live-operation authorization are available. Do not represent sandbox success as production readiness.

Acceptance: demonstrate application → approval → publish → purchase → payment result → fulfillment → delivery notification for two independent businesses. Restore test data from backup. Document remaining limitations and external dependencies. No required workflow is silently backed by in-memory or demo-only data.

## 12. Definition of done and implementation behavior

- Each phase includes code, migrations, generated contracts, relevant tests, runnable setup instructions, and evidence of its acceptance criteria.
- Test meaningful invariants and complete journeys; avoid tests that merely reproduce implementation details.
- Run applicable Python checks, Angular type/build checks, integration tests, and browser verification. Do not claim checks passed unless executed successfully.
- Maintain the status document with completed work, verification, assumptions, remaining work, and exact blockers. Avoid unchecked claims such as “production-ready.”
- Use deterministic local seed data for two tenants. Test credentials are local-only and must not be enabled in production.
- Keep secrets out of source control and browser bundles. Ship environment examples containing placeholders only.
- Use reversible edits and incremental commits when repository setup permits; do not publish or alter remote repositories without authorization.
- Continue within the active phase without repeated approval for routine implementation decisions. Ask only for decisions that materially change scope, credentials/eligibility that cannot be inferred, or consequential external operations.
- Do not silently simplify away required payment methods, approval, tenant authorization, or the Angular/Django stack. If blocked, complete independent work and report the actual gap.

## 13. Scope limits and choices to resolve

Initial scope excludes live GPS tracking, marketplace/shared multi-merchant checkout, split payouts, arbitrary merchant code/plugins, full drag-and-drop page building, multiple warehouses, bulk marketing automation, and international tax automation.

Resolve these product choices before dependent production work, using these stated defaults for planning:

1. Settlement: direct to each business; central collection/payouts require a different payment design.
2. Launch market: not yet confirmed. Support a configurable country and one currency per store; do not assume Stripe eligibility or hardcode USD from the reference images.
3. Merchant billing: model subscriptions/status, but do not invent plans/prices or automatic platform charges. Automated subscription collection needs pricing and billing rules.
4. Email/SMS provider and sender identity: use adapter interfaces and local/test providers until selected.
5. Approval information/documents: collect only the business information specified by the final review policy. Do not invent mandatory sensitive-document requirements.
6. Platform portal address: `platform.mshoppa.com` is the proposed default.
7. Brand orange: provisional `#F58220` until an original color specification is supplied.
8. Hosting/object storage/CDN: deployment configurations remain reviewable and provider-neutral until infrastructure is selected.

Earlier rough effort estimates assumed a smaller product. For this scope, planning estimates are 12–16 weeks for a constrained pilot with an experienced Angular developer and Django developer working together, or roughly 5–8 months for one experienced full-time developer to deliver and harden the broader first release. Re-estimate after Phase 0; provider onboarding and design decisions are external dependencies, not guaranteed engineering durations.

## 14. Technical reference links

Recheck current primary documentation and version compatibility during implementation:

- Admin design reference: https://www.shadcn.io/template/satnaing-shadcn-admin
- Angular-native UI: https://www.spartan.ng/documentation/introduction
- Angular rendering: https://angular.dev/guide/performance
- Django: https://docs.djangoproject.com/
- Django REST Framework: https://www.django-rest-framework.org/
- Schema tenancy: https://django-tenants.readthedocs.io/en/latest/
- Stripe direct charges: https://docs.stripe.com/connect/direct-charges
- Stripe webhooks: https://docs.stripe.com/webhooks
- Safaricom Daraja: https://developer.safaricom.co.ke/apis

These links establish available capabilities, not that the proposed integration has already been implemented or validated.
