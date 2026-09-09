# Payments service

Django API at `127.0.0.1:8001`, Angular checkout at `http://localhost:4204`. It shares the core virtual environment and internal signing key, and stores sessions in `.local/payments.sqlite3`. Provider credentials stay on the server. The service remains a local alpha: `DJANGO_DEBUG=1` and `LOCAL_DUMMY_PAYMENTS=1` are required even when a provider adapter is selected.

## Configure

Stores use MSHOPPA’s shared payment accounts by default. Configure these server-side in `services/payments/.env` (copy `.env.example`); `npm run dev:all` reads it only for the payment API, with environment variables taking precedence. Restart the development group after changes. Standalone management commands require exported environment variables.

In merchant admin → **Payments → Payment configuration**, owners can uncheck **Use MSHOPPA payment account** and save their own Stripe test key or Venty account. Recheck it to restore the shared account. Existing store configurations remain overrides. Disabling a provider applies to new checkouts. Blank secret fields preserve only that store’s previously saved override; they never copy shared credentials. Shared credentials, tenant IDs and callback settings are never returned to merchants; only source and readiness are shown.

Store credentials and each new session’s effective credentials are encrypted with `MSHOPPA_ENCRYPTION_KEY`. Sessions retain their original account even after switching providers’ accounts or rotating shared keys. Keep the encryption key when backing up or moving the database. Existing sessions retain their original backend. Missing credentials never fall back to fake success. Automated refunds are not implemented.

### Stripe test cards

1. Set `STRIPE_SECRET_KEY=sk_test_…` in the payment service’s `.env` for the shared account, or save a store override in **Payments → Payment configuration → Stripe**. Live keys are rejected. No publishable key is needed for hosted Checkout.
2. Optionally run `stripe listen --forward-to localhost:8001/api/webhooks/stripe/`. Save the printed signing secret in that store’s Stripe webhook secret field before creating checkout sessions. Without forwarding, **Check payment status** verifies the session directly with Stripe and updates the order.
3. Enable Stripe in store settings. Start checkout and select **Continue to Stripe test checkout**.
4. Use `4242 4242 4242 4242`, a future expiry date and any three-digit CVC. For a decline, use `4000 0000 0000 9995`. Enter these only on Stripe's hosted test page.
5. Returning from Stripe triggers a server-side status check. A redirect alone never marks an order paid.

Reference: [Stripe testing](https://docs.stripe.com/testing), [Checkout](https://docs.stripe.com/checkout/quickstart?lang=python), [signed webhooks](https://docs.stripe.com/webhooks/signature), [currency units](https://docs.stripe.com/currencies). RWF uses zero-decimal amounts; UGX is whole-unit but encoded in hundredths as Stripe requires. Session creation uses a stable idempotency key. Checkout reservations last 35 minutes to accommodate Stripe's minimum 30-minute expiry; start the Stripe session within the first five minutes.

### M-Pesa via Venty

The wrapper follows `/Users/admin/Dev/Venty/mpesa-api/stkpush`, using `https://mpesa.venti.africa/mpesa/api/v1`:

- `POST stkpush/initiate/`: Kenyan phone, integer KES amount, tenant ID, `transaction_id` set to the MSHOPPA payment-session UUID, payment type, configuration flag and optional callback URL.
- `GET stkpush/payment-detail/{payment_id}/`: the **payment_id returned by initiation**, not transaction_id. The response must match the stored reference, phone, tenant and amount before it can update the order.

For MSHOPPA’s default Venty account set `VENTY_MPESA_ENABLED=1`, `VENTY_MPESA_TENANT_ID=default` and `VENTY_MPESA_USE_DEFAULT_CONFIG=1` in the payment service’s `.env`. Venty resolves its default collection credentials on its server; no Safaricom passkey is copied into MSHOPPA. For a store override, save its tenant ID and enable M-Pesa in that store’s payment configuration. Leave **Use Venty’s default collection configuration** unchecked to use the tenant configuration. The inspected Venty implementation targets live Safaricom, including custom tenants; changing the tenant flag does not make it a sandbox. The UI identifies Venty payments as real payments. No live STK request was made during implementation verification.

Optional callbacks: expose only `/api/webhooks/venty/mpesa/` through a suitable HTTPS forwarding URL, save the public callback URL and callback secret in the store’s M-Pesa configuration to match Venty's deployment `PAYMENT_CALLBACK_SECRET`. The wrapper verifies `X-Payment-Callback-Secret`, order/session ID, amount and receipt; saved provider records are also checked when available. Without callbacks, use **Check payment status** after approval on the phone.

Venty initiation is not idempotent. Once an STK request starts, the wrapper prevents a second request. A timeout or uncertain response leaves the session `unknown` and requires reconciliation with Venty before creating another checkout. An authenticated callback can resolve a request even if its initiation response was lost. Amounts with fractional shillings are rejected, never silently rounded. Venty's current status endpoint has no receipt field; receipt numbers are saved when delivered by callback.

## Checkout handoff

The cart opens `http://localhost:4204/?checkout=<signed-cart>`. The payments page collects name, email, phone and delivery address, displays server-calculated totals and enabled methods, then submits the order through core. `GET/POST /api/checkout/` forwards internally signed requests to core; the signed cart fixes the store, items and idempotency key. Handoffs expire after one hour and never contain customer details. No order or stock reservation is created until form submission. Once created, the customer gets a payment session and a **View order & tracking** link.

## API and verification

- `POST /api/configuration/`: internally signed request with business ID; read safe configuration or save a new encrypted provider version.
- `POST /api/providers/`: internally signed request with business ID; safe provider readiness/mode only.
- `POST /api/sessions/`: internally signed core request; unique session per order.
- `GET /api/sessions/<opaque-token>/`: status and checkout information.
- `POST /api/sessions/<opaque-token>/start/`: CSRF required; phone for M-Pesa, hosted URL for Stripe.
- `POST /api/sessions/<opaque-token>/refresh/`: CSRF required; fetch provider status and deliver verified result to core.
- `POST /api/webhooks/stripe/`: verifies the actual Stripe signature and test mode.
- `POST /api/webhooks/venty/mpesa/`: verifies Venty's shared callback secret.
- `POST /api/sessions/<opaque-token>/simulate/` and `/api/webhooks/dummy/<provider>/`: work only for sessions created with the simulator backend. Real provider sessions cannot be settled through these routes.

The internal core callback uses MSHOPPA HMAC-SHA256 signatures with a five-minute timestamp window. Core validates amount, currency, provider, order and session. Event replay does not deduct stock twice. A success arriving after stock was released is flagged **Payment needs review** in admin; it never silently reclaims stock. Delivery retries and uncertain M-Pesa requests require manual reconciliation in this local version.

```sh
cd services/payments
../core/.venv/bin/python manage.py migrate
../core/.venv/bin/python manage.py test simulator
```

Tests exercise real Stripe signature verification and SDK response objects, with mocked provider HTTP calls. They cover mismatched payments, replay, CSRF, Venty amount/phone/reference handling and timeout retry prevention. To run the existing full local simulator smoke test, set both payment backends to `simulator`, restart, then run `cd services/core && .venv/bin/python manage.py smoke_checkout`.

## Wallet and withdrawals

Merchant admin **Payments** has wallet, configuration and withdrawal sections. Wallet access and withdrawal requests are owner-only. Managers can read configuration flags and payment transactions. Requests enforce tenant scope, CSRF, positive amounts, recipient validation and available balance. A business-row lock serializes changes; an idempotency key prevents repeat requests from reserving funds twice.

The wallet is an internal settlement ledger, not a provider account-balance lookup. Verified, paid Venty orders are shown as collected/awaiting settlement. Stripe test and simulator money is excluded. In platform admin **Wallet operations**, an MFA-authenticated platform operator confirms the net amount actually received into the account funding withdrawals, with a settlement reference. Each order can be settled once, at no more than its collected total. Settled funds become available; pending requests reserve them. Cancellation or rejection releases the reservation. Completed requests permanently reduce available funds.

Withdrawals are requests for manual review. No automatic transfer is sent. The inspected Venty B2C code uses a shared account and placeholder completion callbacks, and offers no reliable final payout-status contract; it is not used for transfers. An operator executes a transfer through the authorised provider separately, then records completion and its reference in Wallet operations, or rejects the request with a reason. Each settlement, withdrawal request and review is audited without credentials. This implementation does not simulate payouts or display order totals as settled cash.

Core endpoints:
- `GET/PATCH /api/businesses/{id}/payments/configuration/`
- `GET/POST /api/businesses/{id}/payments/wallet/` (summary / withdrawal request)
- `POST /api/businesses/{id}/payments/withdrawals/{withdrawal_id}/cancel/`
- `GET/POST /api/platform/wallet/` (review queues / record a settlement)
- `POST /api/platform/withdrawals/{id}/review/` (record a completed transfer or reject)

Withdrawal history returns the most recent 50 requests; platform queues return the first 100 outstanding records. Reviewing records removes them from the queue. Real Stripe balances/payouts require a future live/Connect integration; this project accepts Stripe test keys only.
