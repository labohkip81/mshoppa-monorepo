# MSHOPPA

An Angular + Django ecommerce-platform foundation. SQLite is the initial development database: no PostgreSQL, Redis, or Docker service is needed to run this phase.

This is a working **local alpha**, not yet a production commerce platform. Signup, verification, staff MFA, approvals, provisioning, products/variants/images/offers, store settings, public storefronts, carts, guest checkout, orders/payments, rich text editing, Stripe test Checkout and a Venty M-Pesa adapter are implemented. Provider credentials are required; M-Pesa stays disabled until configured. Production deployment is not enabled.

See the [current architecture](docs/architecture/CURRENT.md) for service boundaries, data ownership, request flows, permissions, and operational limits, and [implementation status](docs/IMPLEMENTATION_STATUS.md) for verification results.

For hosting, use the [Nginx deployment guide](docs/DEPLOYMENT.md): VPS setup, Gunicorn/systemd templates, automatic wildcard and merchant-domain SSL with Certbot, static caching, performance targets, backups, and rollback. It identifies the production code changes required before public commerce can run; the current payment service still requires local debug mode.

## Quick start

Requires Node 24, Python 3.13, and [uv](https://docs.astral.sh/uv/).

From the repository root:

```sh
npm ci
cd services/core
uv sync --frozen
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py configure_local_domains
cd ../payments
../core/.venv/bin/python manage.py migrate
cd ../..
npm run dev:all
```

`dev:all` starts the core Django API (8000), payment API (8001), one SQLite-compatible background worker, and all five Angular applications. The payment service uses the core virtual environment and its own `.local/payments.sqlite3` database. Ctrl+C stops them together. Do not also run the individual services on the same ports.

Local defaults work without copying `.env.example`. Django does **not** automatically load `.env` files. The `dev:all` launcher explicitly reads `services/payments/.env` for the payment API only; exported environment variables take precedence. Core and standalone management commands require exported overrides. Never use the placeholder production secrets in the example file. Development secrets are generated into ignored `.local/` files; preserve those files to keep local sessions, MFA enrollment, and encrypted payment credentials valid.

## Local addresses

| Application | Address |
| --- | --- |
| Marketing/signup | http://localhost:4200 |
| Business workspace | http://admin.localhost:4201 |
| MSHOPPA reviewer portal | http://platform.localhost:4202 |
| Example storefront | http://everyday-studio.localhost:4203 |
| Second example storefront | http://field-and-form.localhost:4203 |
| Payments | http://payments.localhost:4204 |
| Core API health | http://127.0.0.1:8000/api/health/ |
| Payment API health | http://127.0.0.1:8001/api/health/ |

A business approved with slug `abc` gets `abc.localhost:4203` and goes online automatically when provisioning completes. Existing approved, ready, non-suspended businesses are enabled by a one-time migration. Owners/managers can switch **Website online** off or on from Store settings; subsequent provisioning retries preserve that choice. Storefront addresses resolve from verified domain records, not a query-string business ID. Unknown, offline, or suspended stores return an unavailable page. “Online” here means available on the local development address, not deployed to the internet.

Use **Store settings → Private preview** in the business workspace to see the cover-and-profile storefront. The link is valid for five minutes, bound to its exact store hostname, and rechecks the issuer's membership. It grants read-only preview access, not admin access. The token is removed from the browser URL immediately; refreshing needs a new link. Treat preview links as private.

Modern browsers generally resolve `*.localhost` to loopback. If your browser or system resolver does not, manually add the exact names you use to `/etc/hosts`, pointing them to `127.0.0.1`; `/etc/hosts` does not support wildcard entries. No hosts file or system DNS was modified by this implementation.

Example entries if necessary:

```text
127.0.0.1 admin.localhost platform.localhost payments.localhost
127.0.0.1 everyday-studio.localhost field-and-form.localhost abc.localhost
```

The ports are intentional. Bare `http://abc.localhost` uses port 80 and will not reach the current development setup; a reverse proxy can remove the ports later. Angular binds to loopback, allows `.localhost` hosts, and proxies `/api/**` to Django while preserving the original Host header. Authentication cookies remain host-only; storefronts do not receive the admin cookie. CSRF trusts specific admin/marketing origins, not every store subdomain.

The separate storage service remains reserved. Product images currently upload through the core Django API and are stored locally under `.local/media/`.

## Editing products and photos

Open **Products → Edit** (or click a product name) to change its name, category, description, regular price, offer price, quantity, and visibility. Leave offer price blank to remove an offer; a specified offer must be lower than the regular price. The storefront shows the offer alongside the crossed-out regular price.

Enable **Has variants** to add up to 50 named options, each with its own price, optional offer price, and quantity. Variant names must be unique within the product. Existing IDs/SKUs survive edits; removed options are marked inactive rather than deleted. Unchecking the flag uses the first option's values as the single-product defaults; review those values before saving. Public lists/detail pages expose only active options and let shoppers choose one before adding to cart.

The business admin header has **View shop**, opening the selected online store in a new tab. Published products on an online store have **View on website**, opening `/products/<product-slug>` with the product gallery, price, and description. Draft products have no public preview action; product URLs reject drafts, products from another shop, and offline/suspended stores. The product list's **Select shop** dropdown and **Add product** button are aligned with matching control heights.

The image widget supports multiple selection, drag-and-drop, thumbnail previews, and an enlarged gallery. Up to eight JPEG/PNG/WebP images are allowed per product, at most 5 MB and 20 megapixels each. The first image is the cover. Click a thumbnail to preview it, or remove a selection before saving. Existing-image removals take effect on Save and can be undone before then. Images are validated from decoded content, metadata is stripped, and optimized WebP files are stored at a maximum of 2000px on the longest edge.

Product details and each image save independently. If an upload fails after product details were saved, the editor retains the remaining changes for retry without creating another product. Image URLs are one-hour, image-specific read grants; private product photos do not have unrestricted media-directory URLs. Removed images stop being served immediately; underlying local files are retained for recovery until a future cleanup workflow.

New products default to **Draft**. Select **Published** to show one on an online storefront; drafts are included only in private previews. Website visibility and product visibility are separate. Public stores support checkout with configured providers; private preview does not allow shopping. See payment setup below.

Choose **Store settings → Featured product** to pin the first product in the storefront’s Featured sort. Automatic uses the newest published product; unavailable selections fall back automatically. Shoppers can also sort by newest, name, or price and filter by category.

The storefront's **Our Products** section has live search by name, category, or description, with a matching product count and load-more pagination. Search covers the entire store catalog, not just the first 24 items. Public search excludes drafts; no matches show a subtle 404 illustration, “No products found,” and “Check later.”

## Storefront footer

In **Store settings**, upload a store logo, edit contact details, add social profile links, and enter your return/refund policy, privacy policy, and terms and conditions. The footer shows the logo and introduction on the left, followed by populated contact/social/policy sections. Blank fields are hidden; no placeholder story or policy text is added. Policies open in accessible native dialogs and are rendered as plain text.

Set **WhatsApp number** with its country code to show the floating WhatsApp button. Leave it blank to hide the floating button. The top-bar WhatsApp icon uses this number, or falls back to the public store phone when it has a valid international format. Store phone overrides the approved application's phone when provided. Social links accept HTTP/HTTPS only.

Use the **Social media** and **Terms & policies** shortcuts in Store settings to jump directly to those editors. Social media supports Instagram, Facebook, TikTok, X, and LinkedIn with matching icons in the admin and storefront. **Save social links** and **Save policies** save only their respective fields, preserving other unsaved settings. Clear a profile link or policy and save its section to hide it from the footer.

Logo and cover uploads accept JPEG, PNG, or WebP (5 MB / 20 megapixels maximum), use the same image normalization as products, and save immediately without discarding unsaved settings edits. Removing or replacing an image invalidates its previous URL; the old local file is retained for recovery.

## Merchant management and storefront branding

The business sidebar includes **Orders**, **Businesses**, **Payments**, **Customers**, **Promotions**, and **Staff**. Use the store selector to change which business you manage.

- **Orders:** search incoming orders, inspect items and delivery details, add internal notes and tracking references, and advance paid orders through processing, shipped, and delivered. These updates never change the payment state or contact a courier.
- **Businesses:** view all your stores, rename a business, open its settings, and manage local domain aliases. Owners/managers can add available `shop-name.localhost` addresses, choose a verified primary domain, and remove non-primary domains. Custom internet domains are not connected. New businesses use the existing application/approval flow.
- **Payments:** owners/managers can browse checkout transactions, filter by status or method, see provider readiness and identify late payments needing review. Refunds require provider-side handling.
- **Customers:** view customers grouped by checkout email, paid totals, order counts, and paginated order history for the selected store. These are guest-checkout records, not shopper accounts.
- **Promotions:** owners/managers can set or clear offer prices for each active product variant without overwriting inventory or regular prices. Offers apply immediately to published products and checkout. Coupon codes and scheduled campaigns are not implemented.
- **Staff:** owners can add existing verified merchant accounts, change roles, or remove store access. Owners manage staff; managers manage catalog/orders/payments/domains; fulfillment staff can update orders; support staff can view store and order data. Users cannot remove or downgrade their own access. Adding staff sends no invitation email.

In **Store settings → Logo & cover image**, upload a square logo and a wide cover (recommended 1800 × 500 px). The storefront displays the cover above an overlapping logo, store name, introduction, and social links. With no cover, it uses a gradient based on the material tone. With no logo, it shows the shop initial. Uploads save immediately without discarding other unsaved settings. Existing signed-image validation and access expiry also apply to covers.

## Local cart, checkout, and payments

1. Publish a product with available quantity. Use **Has variants** if needed.
2. In **Store settings → Checkout & payments**, set a test tax rate and enable Stripe and/or M-Pesa. Tax defaults to **0%**; prices are tax-exclusive. Tax is calculated on the discounted subtotal and rounded once to the currency's precision. This is a simple test configuration, not jurisdiction-aware tax handling.
3. Add products from listings or a product page. The header Cart opens a right-side drawer with quantities, removal, subtotal, tax, and total. Carts persist per store in the browser.
4. Click **Checkout** in the cart. It opens `localhost:4204`, where customers enter contact/delivery details, review totals, and select Card or M-Pesa. Existing `/checkout` links hand off to the same page. The signed cart link lasts one hour; opening it does not create an order or reserve stock.
5. Complete Stripe hosted test Checkout or the configured Venty phone prompt, then check payment status and return to the shop. For offline testing, select simulator backends before starting the services; those sessions offer **Simulate success** and **Simulate failure** controls. The confirmation reflects the verified core order state.

The server validates published products, active variants, tenant ownership, current prices, stock, tax, and the chosen method. A signed ten-minute quote protects displayed totals. Checkout idempotency prevents duplicate reservations for the same request. Pending orders reserve stock for 35 minutes; failed/expired orders release it once. The local background worker expires abandoned orders. Successful orders consume reserved stock. No delivery fee is added in this slice.

The simulator has signed dummy webhook routes at `http://127.0.0.1:8001/api/webhooks/dummy/stripe/` and `/api/webhooks/dummy/mpesa/`. These use MSHOPPA's local HMAC protocol—not real Stripe/Daraja webhook formats. The service forwards signed normalized events to core; duplicate events do not apply stock/payment changes twice. See [payment service documentation](services/payments/README.md).

Card details are entered only on Stripe hosted Checkout. M-Pesa PINs are entered only on the phone prompt. The Venty adapter can collect real payments when explicitly enabled; it is disabled by default. Credentials are service-wide for this local alpha. Automated refunds and courier actions are not implemented. Keep these development servers on loopback. Dummy checkout endpoints are disabled when `DJANGO_DEBUG=0` or `LOCAL_DUMMY_PAYMENTS=0`; the simulator refuses to start outside local mode.

## Local demo accounts

All demo accounts use password **`Local-Mshoppa-2026!`**. These accounts are created only with `seed_demo` while `DJANGO_DEBUG=1`. Seeding never resets an existing password.

| Account | Purpose |
| --- | --- |
| `owner@example.test` | Owns Everyday Studio; also has a pending Linen House application |
| `second@example.test` | Owns Field & Form, for business-isolation testing |
| `reviewer@example.test` | Platform reviewer; authenticator enrollment required at first login |

For the reviewer, sign in at `platform.localhost:4202`, add the displayed setup key to an authenticator as a time-based account, then enter its six-digit code. There is no MFA bypass or hardcoded shared MFA secret. Recovery codes/reset flows are not implemented yet.

For a new signup, the local worker writes verification emails to `.local/mail/`; open the newest generated mail file for your test account and follow its verification link. No real email or SMS is sent by default. The worker also provisions approved stores. Run only **one worker** with this SQLite pilot.

## Useful commands

```sh
npm run dev                 # business Angular app only
npm run dev:marketing
npm run dev:platform
npm run dev:storefront
npm run dev:payments
npm run check               # TypeScript
npm run build               # all five production frontend builds
npm run test:smoke          # real local subdomain/proxy API checks; needs dev:all + seed

cd services/core
uv run pytest -q
uv run ruff check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py process_jobs --once
uv run python manage.py smoke_checkout  # requires dev:all; isolated test store, four simulated orders
uv run python manage.py spectacular --file ../../docs/architecture/openapi.yaml --fail-on-warn
cd ../..
npm run api:generate

cd services/payments
../core/.venv/bin/python manage.py test simulator
```

Optional browser tests live in `tests/e2e/`. Start `dev:all`, install the Playwright Chromium browser, then run `npm run test:e2e`. They are **not yet run in this session** because no connected browser was available for visual/interactive QA.

## Monorepo

```text
apps/
  marketing/       Angular public landing and signup
  merchant-admin/  Angular business workspace
  platform-admin/  Angular staff review portal
  storefront/      Angular natural-01 storefront / private preview
  payments/        Angular payment checkout
services/
  core/            Django accounts, businesses, catalog, checkout/orders, SQLite
  payments/        Separate Django provider adapters, verified webhooks, own SQLite
  storage/         Reserved service boundary, not implemented
packages/
  api-client/      Generated OpenAPI types + Angular API transport
  ui/              Shared Angular primitives, admin pages and separate styles
assets/            Supplied logo and storefront references
docs/              Product specification, design system and implementation status
```

The storefront uses a wide cover, overlapping logo, shop profile, social links, category filters, and a product grid. Business/platform admin and marketing use MSHOPPA's logo with minimal neutral surfaces and restrained orange accents. No proprietary fonts or stock product photographs are bundled.

## Limitations and next milestones

- Catalog supports named variants, prices/offers, photos, and available quantities. A full inventory movement/audit workflow remains to implement.
- Cart, guest checkout, order status, Stripe test Checkout, Venty M-Pesa and optional local simulations work. Provider credentials and account configuration are required. COD, automated refunds, courier integrations, and shopper accounts remain unimplemented.
- No staff invitations, password recovery, MFA recovery, custom-domain verification, SMS, in-app notifications, analytics or SaaS billing yet.
- Email outbox is single-worker, at-least-once, with bounded retries. Do not interpret it as an exactly-once or production delivery guarantee.
- APIs are deliberately uncached. SSR/prerendering, public-store cache invalidation/CDN, accessibility audit, and browser performance testing are future work. Build transfer estimates are not real-world load-time measurements.
- SQLite uses application-level tenant scoping and immediate write transactions. Production deployment requires a separate security/concurrency review and a deliberate database decision. Tests are not a production-readiness guarantee.

See [implementation status](docs/IMPLEMENTATION_STATUS.md), [current architecture](docs/architecture/CURRENT.md), [foundation decisions](docs/architecture/FOUNDATION.md), [full implementation prompt](docs/CODEX_IMPLEMENTATION_PROMPT.md), and [storefront design](docs/design/STOREFRONT_DESIGN.md).

### Payment provider setup

See [payments setup](services/payments/README.md) for Stripe test keys/cards and Venty tenant/callback settings. Copy `services/payments/.env.example` to `services/payments/.env`; the development launcher reads it for the payment API only. To use offline simulations, explicitly select both simulator backends.

Descriptions and store policies now support headings, bold/italic/underline, lists, quotes and links. HTML is sanitized on the server and rendered through Angular sanitization. Sidebar navigation and the cart drawer use staggered entrance motion and honor reduced-motion preferences. Product cards include clearer price spacing, discount/availability badges and responsive image framing.

Customers can use **View order & tracking** from payment confirmation to see payment state, order progress, and the tracking reference maintained in admin Orders. Pending payments refresh every 3 seconds; paid orders refresh fulfillment every 15 seconds until delivered. The order link is private to its bearer and scoped to the store; internal staff notes are never exposed.
