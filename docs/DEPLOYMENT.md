# Deploying MSHOPPA with Nginx, automatic SSL, and fast storefronts

Updated 2026-09-09. Recommended starting topology: one Ubuntu 24.04 LTS VPS, Nginx serving compiled Angular files, two Gunicorn services on loopback, one background worker, and Certbot managing Let's Encrypt certificates. Start with platform subdomains, then enable merchant-owned domains. No Docker is required.

**The repository is still a local alpha. Complete section 1 before exposing commerce publicly.** In particular, the payment service currently refuses `DJANGO_DEBUG=0`, and changing environment variables alone will not fix that. This guide and its configuration templates are deployment instructions, not an implemented production conversion. No server, DNS record, or certificate was changed while writing it.

## Deployment sequence

1. Complete and test the production prerequisites below.
2. Prepare the VPS, runtime, persistent storage, and environment files.
3. Build a pinned release; migrate the databases; start the three application services.
4. Point DNS at the VPS and issue the platform wildcard certificate.
5. Enable Nginx HTTPS and verify the platform using the launch checks.
6. Add verified merchant domains with individual certificates.
7. Enable renewal monitoring, backups, and performance measurements.

Replace `example.com` with your platform domain. `shop.merchant.example` represents a merchant-owned domain; it is not a usable public certificate name. Copy templates to a staging directory and replace placeholders before installing them. Commands below run **on the intended Linux server**, not on your development Mac.

## 1. Required application changes before production

These are concrete gaps found in the source, not settings already implemented by this guide.

| Area | Current behavior | Required change and acceptance check |
| --- | --- | --- |
| Payments production mode | `services/payments/payment_config/settings.py` rejects debug-off startup; `ensure_local()` is also called by real checkout/provider routes | Separate authenticated internal service transport and real-provider operation from simulation controls. Real flows must work with debug off; simulation endpoints must remain disabled and inaccessible in production. Preserve HMAC, replay, amount, currency, session, CSRF, and provider verification. Do not solve this by enabling public debug or removing all guards. |
| Service/public URLs | Core hardcodes payment URLs; payments hardcodes its core checkout URL | Read `PAYMENT_SERVICE_URL`, `PAYMENT_PUBLIC_URL`, `CORE_PAYMENT_CALLBACK_URL`, and `CORE_CHECKOUT_URL` from environment. For this VPS, internal URLs stay on loopback; browser/payment-return URLs use HTTPS without development ports. |
| Return URL validation | `SessionInput.validate_return_url()` accepts only HTTP localhost on port 4203 | Validate HTTPS return URLs against the verified domain belonging to the order's business. Reject unrelated hosts, credentials, arbitrary ports, and untrusted redirects. Do not replace this with “any HTTPS URL.” |
| HTTPS behind Nginx | No trusted proxy HTTPS setting; debug-off enables Django's redirect on every request | Set `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`. Bind Gunicorn to loopback and let Nginx overwrite that header. For the loopback HTTP service calls in this guide, set `SECURE_SSL_REDIRECT=False` in production settings and enforce public redirects at Nginx. Otherwise internal POSTs can redirect to nonexistent loopback HTTPS. Secure session/CSRF cookies must remain enabled. |
| Hosts and CSRF | Local defaults; payments overrides CSRF origins with localhost | Configure exact public administration/payment origins. For the initial manual workflow, allow `.example.com`, loopback/internal hosts, and each verified customer hostname explicitly in Django. Never add all merchant origins to admin CSRF trust. Same-origin storefront mutations do not need a global wildcard CSRF exemption. |
| Frontend URLs | Marketing/auth links and several merchant labels contain localhost; storefront footer names a fixed platform domain | Introduce build/runtime public URL configuration; replace local links and store-domain labels. Test signup, verification links, sign-in, private previews, checkout, and returns using real HTTPS hostnames. |
| Custom-domain onboarding | Merchant domain API accepts `.localhost` only; `Domain` has no DNS/certificate lifecycle | Initially use the operator workflow in section 6. Self-service needs ownership verification, domain uniqueness, issuance jobs, failure/retry state, revocation/removal, and audited assignment. |
| WSGI runtime | Gunicorn is absent from the locked dependencies | Add a reviewed Gunicorn version to `services/core/pyproject.toml` and update `uv.lock` in a tested code change. Payments uses that same environment and needs the core directory on `PYTHONPATH`. |
| Email | File backend by default; SMTP credentials/TLS settings are not read from environment | Configure real SMTP delivery, credentials, TLS, sender DNS, and expiry/recovery behavior. Add the missing environment mappings; test receipt and verification on a real mailbox. |
| Throttling and database contention | Per-process default cache; SQLite writes serialize; provider initiation includes network work inside payment DB transactions | Add shared throttling for multiple workers and configure trusted proxy counting/client IP handling. Move slow provider network calls outside write transactions using durable initiation state. Test concurrent checkout, stock, idempotency, and wallet balances. |
| Real payment operations | Stripe test only; Venty can collect real funds; reconciliation/refunds are incomplete | Launch only the payment capabilities actually supported. Stripe live/Connect needs a separate implementation. Provide reconciliation and customer-support procedures before taking real money. Never count mocked tests as provider acceptance. |

Use [Django's deployment checks](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) with the actual production environment. Nginx must sanitize the trusted header as described in [Django's proxy setting documentation](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header). With HTTPS enforced at the edge, assess the resulting `security.W008` redirect warning explicitly; do not silence unrelated warnings.

Keep SQLite only for a deliberately limited, single-server pilot after concurrency tests. For a busy multi-merchant launch, plan PostgreSQL with separate core/payment databases, a tested data migration, appropriate transaction/locking behavior, and shared Redis throttling/cache. The existing project does not implement a PostgreSQL `DATABASE_URL` switch. More Gunicorn workers do not remove SQLite's write bottleneck.

## 2. Server and filesystem

Use a starting budget of **4 vCPU, 8 GB RAM, and SSD/NVMe storage**, then size from measurements rather than a promised store count. Pick a region with measured low latency to your shoppers and payment providers. Keep both APIs and their databases together initially; the shared checkout makes internal round trips. Build on CI or a separate builder once available so builds do not compete with shoppers.

On a fresh Ubuntu server:

```sh
sudo apt update
sudo apt install nginx certbot python3-certbot-dns-cloudflare git rsync sqlite3 dnsutils
sudo adduser --system --group --home /srv/mshoppa mshoppa
sudo install -d -o mshoppa -g mshoppa /srv/mshoppa/releases /srv/mshoppa/shared /srv/mshoppa/python
sudo install -d -m 755 /srv/mshoppa/www /var/www/letsencrypt /etc/nginx/mshoppa/custom-domains
sudo install -d -m 700 /etc/mshoppa
sudo install -d -m 700 /etc/letsencrypt
sudo install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
sudo touch /etc/nginx/mshoppa/store-hosts.map
```

Cloudflare is only the example DNS provider for automated wildcard validation. Use your DNS provider's Certbot plugin if different; merchant DNS does not have to use Cloudflare. Use one Certbot installation method consistently. See [Certbot installation options](https://certbot.eff.org/instructions) and [Nginx packages](https://nginx.org/en/linux_packages.html).

Install Node 24 and uv from their supported distribution channels. Install Python 3.13 outside a home directory so systemd's `ProtectHome=true` does not hide the interpreter:

```sh
sudo -u mshoppa env UV_PYTHON_INSTALL_DIR=/srv/mshoppa/python uv python install 3.13
```

The command assumes `uv` is installed on the server PATH accessible to `mshoppa`; use its absolute path otherwise. Allow inbound TCP 80/443 and restrict SSH to your administration network. Keep ports 8000/8001, database/cache ports, and all development ports private. Do not run `ng serve`, `npm run dev:all`, or Django `runserver` as public services.

| Path | Purpose |
| --- | --- |
| `/srv/mshoppa/releases/<commit>/` | Source, built assets, release-specific Python environment |
| `/srv/mshoppa/current` | Symlink to the selected release |
| `/srv/mshoppa/shared` | Persistent `.local` contents: databases, media, encryption-dependent data |
| `/srv/mshoppa/www/<app>/` | Published Angular browser files only; readable by Nginx |
| `/etc/mshoppa/core.env`, `payments.env` | Root-owned environment files, mode 600 |
| `/etc/letsencrypt` | Certificate lineages, renewal configuration, DNS credentials |

Create `releases/<commit>/.local` as a symlink to `/srv/mshoppa/shared`; this supports both services' current path assumptions across releases. Never serve the repository root or `shared` as a webroot. Nginx should not have write access to application state.

## 3. Build, environment, and services

### Build a reviewed commit

As a deployment operator, substitute the reviewed commit for `REVIEWED_COMMIT_SHA`:

```sh
sudo -u mshoppa git clone https://github.com/labohkip81/mshoppa-monorepo.git /srv/mshoppa/releases/REVIEWED_COMMIT_SHA
cd /srv/mshoppa/releases/REVIEWED_COMMIT_SHA
sudo -u mshoppa git checkout --detach REVIEWED_COMMIT_SHA
sudo -u mshoppa ln -s /srv/mshoppa/shared .local
sudo -u mshoppa npm ci
sudo -u mshoppa npm run check
sudo -u mshoppa npm run build
cd services/core
sudo -u mshoppa env UV_PYTHON_INSTALL_DIR=/srv/mshoppa/python uv sync --frozen --no-dev
```

Gunicorn must already be included in that commit's lockfile. Do not install an unpinned server into the environment after `uv sync`. See [uv's sync behavior](https://docs.astral.sh/uv/concepts/projects/sync/).

Publish **`dist/<app>/browser/`**, not the parent `dist/<app>/` directory. Preserve old hashed chunks for open tabs and rollbacks; do not use `rsync --delete` during a release. Copy new chunks before replacing each index:

```sh
cd /srv/mshoppa/releases/REVIEWED_COMMIT_SHA
for app in marketing merchant-admin platform-admin storefront payments; do
    sudo install -d -m 755 "/srv/mshoppa/www/$app"
    sudo rsync -a --chmod=D755,F644 --exclude=index.html "dist/$app/browser/" "/srv/mshoppa/www/$app/"
    sudo install -m 644 "dist/$app/browser/index.html" "/srv/mshoppa/www/$app/index.html.next"
    sudo mv "/srv/mshoppa/www/$app/index.html.next" "/srv/mshoppa/www/$app/index.html"
done
```

For updates, perform the index publication during the cutover described in section 8, after backward-compatible backend changes are ready.

### Production environment contract

Create root-owned, mode-600 environment files using a secure editor. The following describes the **target after section 1 is implemented**; the comments distinguish today's supported fields from required mappings. Files must be compatible with systemd `EnvironmentFile` and shell sourcing. Quote values containing spaces; never commit populated files.

`/etc/mshoppa/core.env`:

```sh
# Already read by core:
DJANGO_DEBUG=0
DJANGO_SECRET_KEY='GENERATE_A_UNIQUE_RANDOM_SECRET'
MSHOPPA_ENCRYPTION_KEY='GENERATE_A_FERNET_KEY'
PAYMENT_SIGNING_SECRET='GENERATE_AN_INDEPENDENT_RANDOM_SECRET'
DJANGO_ALLOWED_HOSTS='.example.com,127.0.0.1,localhost'
BASE_DOMAIN=example.com
MERCHANT_URL=https://admin.example.com
PLATFORM_URL=https://platform.example.com
STOREFRONT_URL=https://example.com
STOREFRONT_URL_PATTERN='https://{hostname}'
CSRF_TRUSTED_ORIGINS='https://example.com,https://admin.example.com,https://platform.example.com'
SQLITE_PATH=/srv/mshoppa/shared/mshoppa.sqlite3
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST='YOUR_SMTP_HOST'
EMAIL_PORT=587
DEFAULT_FROM_EMAIL='MSHOPPA <hello@example.com>'

# REQUIRED new environment mappings; currently hardcoded/missing:
PAYMENT_SERVICE_URL=http://127.0.0.1:8001
PAYMENT_PUBLIC_URL=https://payments.example.com
CORE_PAYMENT_CALLBACK_URL=http://127.0.0.1:8000/api/payments/webhooks/dummy/
EMAIL_HOST_USER='YOUR_SMTP_USER'
EMAIL_HOST_PASSWORD='YOUR_SMTP_PASSWORD'
EMAIL_USE_TLS=1
```

`/etc/mshoppa/payments.env` inherits `core.env` through the unit and overrides/adds:

```sh
# REQUIRED new mappings / removal of the current localhost CSRF override:
CSRF_TRUSTED_ORIGINS=https://payments.example.com
CORE_CHECKOUT_URL=http://127.0.0.1:8000/api/payments/checkout/

# Existing provider settings; configure only the provider you intend to offer:
STRIPE_PAYMENT_BACKEND=stripe
STRIPE_SECRET_KEY='YOUR_STRIPE_TEST_KEY'
STRIPE_WEBHOOK_SECRET='YOUR_TEST_WEBHOOK_SECRET'
MPESA_PAYMENT_BACKEND=venty
VENTY_MPESA_ENABLED=0
VENTY_MPESA_TENANT_ID=''
VENTY_MPESA_USE_DEFAULT_CONFIG=0
VENTY_MPESA_API_TOKEN=''
VENTY_MPESA_CALLBACK_URL=https://payments.example.com/api/webhooks/venty/mpesa/
VENTY_MPESA_CALLBACK_SECRET='YOUR_CALLBACK_SECRET'
```

Do not set `LOCAL_DUMMY_PAYMENTS=1` as a public deployment workaround. Store private keys in a secret manager or protected files. Generate the Django/HMAC values independently using Python's `secrets.token_urlsafe(64)` and the encryption key using `Fernet.generate_key()`. If migrating existing data, preserve the original encryption key or the encrypted MFA/payment records will be unreadable. Do not copy development demo users into production.

### Migrate and start

First deployment: select the release with a symlink. For subsequent releases use the controlled cutover in section 8.

```sh
sudo ln -s /srv/mshoppa/releases/REVIEWED_COMMIT_SHA /srv/mshoppa/current
```

Run management commands under the same environment as services. One explicit approach is a root administrative shell that loads the private files but runs Python as the service user:

```sh
sudo -i
set -a
. /etc/mshoppa/core.env
set +a
cd /srv/mshoppa/current/services/core
runuser -u mshoppa -- .venv/bin/python manage.py check --deploy
runuser -u mshoppa -- .venv/bin/python manage.py migrate
(
    set -a
    . /etc/mshoppa/payments.env
    set +a
    cd /srv/mshoppa/current/services/payments
    runuser -u mshoppa -- ../core/.venv/bin/python manage.py check --deploy
    runuser -u mshoppa -- ../core/.venv/bin/python manage.py migrate
)
exit
```

Create the initial platform operator through an audited administrative procedure: a verified staff account with a unique password, then enroll MFA in platform admin. `createsuperuser` alone does not set this project's `email_verified` field. Do not run `seed_demo` or `configure_local_domains` in production.

Install the [three systemd templates](deployment/examples/systemd/) after completing the application prerequisites:

```sh
cd /srv/mshoppa/current
sudo cp docs/deployment/examples/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mshoppa-core mshoppa-payments mshoppa-worker
sudo systemctl status mshoppa-core mshoppa-payments mshoppa-worker
```

The templates begin with one Gunicorn worker and two threads per API, plus one job worker. This is a conservative pilot baseline, not a throughput guarantee. Payments explicitly receives core's `PYTHONPATH`; its WSGI entry point does not run the path setup in `manage.py`. Gunicorn's process model and service setup are described in its [deployment guide](https://gunicorn.org/deploy/) and [settings reference](https://gunicorn.org/reference/settings/).

## 4. Platform DNS and wildcard SSL

Example records, initially with any DNS-provider proxy disabled:

| Name | Type | Target |
| --- | --- | --- |
| `example.com` | A | VPS public IPv4 |
| `*.example.com` | A | Same VPS IPv4 |
| `edge.example.com` | A | Same VPS IPv4; merchant CNAME target |

Only publish AAAA records if IPv6 routing, firewall, and Nginx listeners work. A stale AAAA can break validation and shopper access. Wildcard DNS is routing, not permission to claim a shop. The certificate for `example.com` and `*.example.com` covers the apex and one-level subdomains, not arbitrary customer domains or deeper names such as `www.shop.example.com`.

Use DNS-01 for the platform wildcard. With the Cloudflare plugin, save a token restricted to the platform DNS zone in `/etc/letsencrypt/cloudflare.ini` with mode 600:

```ini
dns_cloudflare_api_token = YOUR_ZONE_SCOPED_API_TOKEN
```

The plugin needs DNS edit permission for that zone. Other DNS providers use their own plugins and credential formats. See [DNS challenge requirements](https://letsencrypt.org/docs/challenge-types/) and the [Cloudflare plugin](https://certbot-dns-cloudflare.readthedocs.io/en/stable/).

First install the [HTTP bootstrap](deployment/examples/nginx/bootstrap.conf) as `/etc/nginx/sites-available/mshoppa`, enable its symlink under `sites-enabled`, and disable the stock default site on this dedicated server. Review existing sites first if this is a shared server. Then:

```sh
cd /srv/mshoppa/current
sudo cp docs/deployment/examples/nginx/bootstrap.conf /etc/nginx/sites-available/mshoppa
sudo ln -s /etc/nginx/sites-available/mshoppa /etc/nginx/sites-enabled/mshoppa
sudo nginx -t
sudo systemctl reload nginx
sudo chmod 600 /etc/letsencrypt/cloudflare.ini
sudo certbot certonly --dry-run --non-interactive --agree-tos --email ops@example.com \
  --dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  --cert-name mshoppa-platform -d example.com -d '*.example.com'
```

Once the dry run succeeds, repeat without `--dry-run` to issue the trusted certificate. Do not load the TLS template until `/etc/letsencrypt/live/mshoppa-platform/fullchain.pem` and `privkey.pem` exist. Keep DNS credentials available for renewal; manual TXT entry alone does not provide unattended renewal.

## 5. Enable Nginx routing and performance settings

Copy and customize these files:

| Repository example | Server destination |
| --- | --- |
| [http.conf](deployment/examples/nginx/http.conf) | `/etc/nginx/conf.d/mshoppa.conf` — `http` context |
| [app.conf](deployment/examples/nginx/app.conf) | `/etc/nginx/snippets/mshoppa-app.conf` — shared TLS application locations |
| [platform.conf](deployment/examples/nginx/platform.conf) | `/etc/nginx/sites-available/mshoppa` — replaces bootstrap |
| [customer.conf](deployment/examples/nginx/customer.conf) | One customized file per merchant under `/etc/nginx/mshoppa/custom-domains/` |

Replace every `example.com` in the installed templates. Do not install the sample customer file until its certificate exists. The system's `nginx.conf` must include `conf.d/*.conf` and `sites-enabled/*` inside `http`; the usual Ubuntu package layout does. Keep one `worker_processes auto;` setting in the top-level configuration. The templates use `listen ... http2` for Ubuntu 24.04's older syntax; on Nginx 1.25.1+ you may use `listen ... ssl;` with `http2 on;` instead. See [HTTP/2 configuration](https://nginx.org/en/docs/http/ngx_http_v2_module.html).

Register each approved platform shop in `/etc/nginx/mshoppa/store-hosts.map`:

```nginx
# Only verified, assigned storefronts; not arbitrary wildcard traffic.
everyday-studio.example.com storefront;
field-and-form.example.com storefront;
```

These entries must match core `Domain` records. `BASE_DOMAIN` configures newly provisioned shops; changing it does not migrate existing `.localhost` rows. Provision production businesses through the approved workflow or migrate the exact verified domain records deliberately. The current job worker does not update Nginx's map; operators must do that until the domain controller in section 6 exists.

```sh
sudo nginx -t
sudo systemctl reload nginx
```

Routing preserves the tenant Host and original `/api/` path. The payments hostname proxies to port 8001; other approved hosts use core on 8000. Unknown hosts are rejected. Internal HMAC endpoints and simulator operations are blocked at the edge; real Stripe/Venty webhook routes stay reachable. Backend permission/signature checks remain mandatory. See [Nginx reverse proxy semantics](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) and [TLS configuration](https://nginx.org/en/docs/http/configuring_https_servers.html).

The examples assume Nginx is the direct internet edge. If adding a CDN/load balancer, trust only its documented source networks for real client IPs, restrict direct origin access, and revisit Django's proxy counting. Do not trust an arbitrary incoming `X-Forwarded-For` header. Never use an origin-only certificate as the browser-facing certificate for DNS-only merchant domains.

## 6. Merchant-owned domains and automatic certificates

Nginx does not issue arbitrary merchant certificates on first request in this setup. **Verify and provision the domain before activating it.** Customers never need to send you their DNS account credentials for the HTTP-01 workflow.

### Initial operator workflow

1. The owner requests an exact hostname such as `shop.merchant.example`. Normalize lowercase/IDNA, reject schemes, paths, wildcards, IP literals, reserved platform names, and conflicting ownership. Each hostname has one business; a shop name and its `www` alias are separate names.
2. Generate a random, single-use ownership challenge and require a TXT record such as `_mshoppa-verification.shop.merchant.example = <challenge>`. Record business, hostname, token hash, and expiry. Confirm the TXT using DNS before assignment; a CNAME pointing at your server alone is not proof of which merchant owns it. This challenge record/lifecycle requires implementation for self-service; an operator can maintain an audited verification record initially.
3. Ask the owner to point `shop.merchant.example CNAME edge.example.com`. For an apex domain, use A/AAAA to your edge or the DNS provider's supported ALIAS/flattening feature. Check A, AAAA, CNAME, and any restrictive CAA records. Keep port 80 accessible for HTTP-01. If the customer uses a CDN, it must forward the ACME path and provide the appropriate public TLS setup.
4. After verifying ownership and routing, reserve the exact `Domain` for that business with `verified=False` through an audited operator operation. Do not expose a generic “set verified” endpoint. Current merchant APIs cannot do this for public domains.
5. Request a separate certificate. The global HTTP challenge location works before the tenant is added to the HTTPS map:

```sh
sudo certbot certonly --dry-run --non-interactive --agree-tos --email ops@example.com \
  --webroot -w /var/www/letsencrypt \
  --cert-name shop.merchant.example -d shop.merchant.example
```

Repeat without `--dry-run` after success. Use the real verified hostname. If including `www`, verify and route that hostname too, and include it explicitly with another `-d`. Each certificate should contain only names belonging to the same merchant. Certbot's [webroot and renewal documentation](https://eff-certbot.readthedocs.io/en/stable/using.html#webroot) explains the challenge-file workflow.

6. Install the customized customer TLS server with the issued certificate's path. Add `shop.merchant.example storefront;` to the host map and add the exact hostname to `DJANGO_ALLOWED_HOSTS`; restart core/payments to load changed environment files. Never use the raw requested hostname as unvalidated shell input or a filesystem path in future automation.
7. Run `nginx -t`, reload, and validate TLS/SNI before marking the domain verified/active. Then check its storefront and checkout return behavior. Until activation, core must continue returning unavailable for that domain.
8. On removal, clear its verified/active assignment, remove edge routes and allowed-host entries, reload/restart as necessary, and release ownership only through a deliberate process. Remove Nginx references before deleting a Certbot lineage. Require fresh ownership proof before reassignment. An already-issued certificate does not grant ongoing tenant access.

### Self-service automation to implement

Add a durable domain job pipeline: `requested → ownership_verified → dns_ready → certificate_issued → active`, with retryable error states and a separate removal path. A restricted deployment worker, not the Django web process, should render exact-host Nginx configuration, invoke Certbot using argument arrays, validate with `nginx -t`, atomically install, reload, and record results. Serialize config changes and certificate operations; keep the previous valid config on failure. Restrict the worker to domain provisioning rather than granting the web user broad root/sudo access.

Mark active only after the certificate and application routing both pass. Use a globally unique normalized hostname, per-merchant quotas, issuance backoff, and audit records. Verify DNS ownership in the background; do not perform DNS or certificate issuance inside a shopper request. At larger scale, replace static Django allowlists with a tested database-backed host validator before allowing arbitrary verified customer hosts; never switch to unrestricted `ALLOWED_HOSTS=['*']` by itself.

Platform wildcard certificates avoid issuing one certificate per platform store. Customer domains still need individual certificates. Use staging/dry runs during integration and respect CA limits; repeated failures/forced renewals can exhaust issuance allowances. See [Let's Encrypt rate limits](https://letsencrypt.org/docs/rate-limits/) rather than hardcoding today's limits into jobs.

## 7. Automatic renewal and monitoring

For the apt-based installation, enable and inspect the renewal timer:

```sh
sudo systemctl enable --now certbot.timer
sudo systemctl list-timers --all certbot.timer
sudo certbot certificates
```

Create `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx` with mode 755:

```sh
#!/bin/sh
set -eu
/usr/sbin/nginx -t
/bin/systemctl reload nginx
```

Then validate both renewal and the successful-renewal hook:

```sh
sudo certbot renew --dry-run --run-deploy-hooks
sudo journalctl -u certbot.service --since today
```

Certbot must retain its renewal configuration, account keys, DNS credential files, and webroot. The deploy hook reloads Nginx after a successful renewal; without reload, workers may continue serving the old certificate. Monitor the **certificate actually served over HTTPS**, not just the files on disk. Alert on renewal failures and low remaining validity, and test from outside the VPS. Certificate lifetimes can change; rely on Certbot's renewal policy rather than assuming a fixed 90-day schedule. See [automated renewal](https://eff-certbot.readthedocs.io/en/stable/using.html#automated-renewals).

## 8. Releases, backups, and rollback

For a single-server pilot, schedule a short maintenance window for schema changes. Take a consistent backup before migrations. Build the next commit in a separate release directory, link its `.local` to shared state, and install its locked dependencies. Stop both APIs and the worker before incompatible migrations or copying SQLite state. Serve a deliberate maintenance response from Nginx instead of silently returning errors during the window.

Move `current` atomically on the same filesystem after migration checks:

```sh
sudo ln -s /srv/mshoppa/releases/NEW_COMMIT_SHA /srv/mshoppa/current.next
sudo mv -Tf /srv/mshoppa/current.next /srv/mshoppa/current
sudo systemctl restart mshoppa-core mshoppa-payments mshoppa-worker
```

Publish new frontend indexes only when matching APIs are healthy. Preserve previous release directories and their hashed assets. Prefer backward-compatible expand/migrate/contract database changes. Roll back code by switching the symlink and restoring previous frontend indexes only when the previous code supports the migrated schema. A code rollback does not undo migrations or payments.

Back up both databases, media, required encryption/signing secrets, environment configuration, domain mappings, and `/etc/letsencrypt` into encrypted off-server storage. For the simplest consistent SQLite backup, stop all three writers and archive `/srv/mshoppa/shared` together. Do not copy a live SQLite file casually or omit its journal/WAL state. Keep the application encryption key recoverable separately and restore it with the corresponding data. Reconcile provider events after any rollback/restore; never overwrite newer paid orders to fix a frontend release.

Define acceptable data loss/recovery time before launch, schedule backups accordingly, and test a full restore on an isolated server. Monitor disk usage, database lock errors, oldest pending mail/provisioning work, payment callbacks needing reconciliation, certificate expiry, Nginx upstream latency, and service restarts. Avoid logging query strings, order tokens, customer bodies, or secrets. The sample Nginx access log intentionally omits token-bearing paths; check Django/provider error logging separately.

## 9. Keeping the platform fast

The supplied Nginx settings improve static delivery; they cannot guarantee checkout throughput. Measure the whole journey from the countries and devices shoppers use.

| Content | Initial cache policy |
| --- | --- |
| Content-hashed JS/CSS/fonts | One year, immutable; retain previous-release files |
| `index.html` and SPA routes | Revalidate (`no-cache`) so new releases load correctly |
| Unversioned brand/static files | Short browser lifetime; version them before increasing it |
| All `/api/` responses | No Nginx shared cache; retain core's `private, no-store` |
| Auth, admin, checkout, order status, private preview | Never share-cache |
| Current signed image/logo/cover endpoints | Keep authorization and expiry; no unrestricted media alias or CDN override |

Nginx serves build files directly, enables HTTP/2/TLS session reuse, compresses text assets, preserves upstream connection reuse, and keeps API routes separate from SPA fallback. Missing hashed chunks return 404, not HTML. See [file routing](https://nginx.org/en/docs/http/ngx_http_core_module.html#try_files), [gzip](https://nginx.org/en/docs/http/ngx_http_gzip_module.html), and [TLS session reuse](https://nginx.org/en/docs/http/ngx_http_ssl_module.html#ssl_session_cache).

Prioritize these application changes as traffic grows:

- Generate responsive image sizes and modern formats, reserve image dimensions, lazy-load below-the-fold images, and avoid lazy-loading the main visible product/cover image. Existing WebP normalization is useful but does not create a full responsive-image pipeline.
- Measure the storefront's Quill/rich-text download path and remove unnecessary editor code from read-only views. Preserve lazy-loaded administration features and existing bundle budgets.
- Remove slow provider calls from database write transactions; measure quote queries, product search, and payment configuration lookups. Profile before adding indexes or worker counts.
- Move to tested PostgreSQL concurrency and shared throttling before horizontally scaling APIs. Keep a bounded connection pool and co-locate database/API regions.
- Add public catalog caching only with an explicit public response contract. Include tenant/host, locale/currency, filters, and version in cache keys; bypass cookies/authorization/preview headers; invalidate on publication, price, stock, domain, and suspension changes. Checkout must still recalculate authoritative totals. Never blanket-cache `/api/*` or ignore `private, no-store`.
- Add CDN caching first for versioned public assets. Preserve signed-media authorization; redesign public media delivery with explicit access rules before moving it to an object store/CDN. Cloud/CDN services for custom hostnames require their own configuration and cost review.
- Consider storefront SSR/prerendering for search discovery and first render. It is not included in the present Angular browser-only build.

Suggested acceptance budgets, to validate rather than claim as current results:

| Metric | Starting target |
| --- | --- |
| Real-user Core Web Vitals at the 75th percentile | LCP ≤ 2.5 s; INP ≤ 200 ms; CLS ≤ 0.1 |
| Same-region catalog/quote API p95 | ≤ 300 ms / ≤ 500 ms, excluding provider network time |
| Initial storefront transferred JS + CSS | ≤ 200 KB compressed, before product images |
| Under expected peak load plus agreed headroom | No overselling, duplicate charges, negative wallet balance, database-lock failures, or increasing worker backlog |

The Web Vitals thresholds come from [Google's Web Vitals guidance](https://web.dev/articles/vitals); the API/transfer budgets are proposed project targets. Record mobile field data per hostname/page type and p50/p95/p99 backend latency. Run representative browse/search/quote/checkout tests in staging with mocked/sandbox providers, then a controlled provider acceptance test. Do not load-test live payment initiation.

## 10. Launch checks and troubleshooting

Run against real staging hostnames first:

```sh
sudo nginx -t
sudo systemctl is-active nginx mshoppa-core mshoppa-payments mshoppa-worker
curl -I http://example.com/
curl -I https://example.com/
curl -fsS https://admin.example.com/api/health/
curl -fsS https://payments.example.com/api/health/
curl -I https://everyday-studio.example.com/products/KNOWN_PRODUCT_SLUG
curl -I https://everyday-studio.example.com/main-ACTUAL_BUILD_HASH.js
curl -i https://payments.example.com/api/configuration/
curl -i https://admin.example.com/api/payments/webhooks/dummy/
sudo certbot renew --dry-run --run-deploy-hooks
```

Expect HTTP→HTTPS redirects, valid hostname certificates, SPA route success, immutable cache headers only on existing hashed files, and 404 for public internal endpoints. Core health probes its DB; payment health is metadata-only today, so also test a complete sandbox checkout and database readiness. Confirm that another store's products/orders/previews cannot be accessed and that unregistered domains never resolve to a real store.

In a browser, verify signup/email, staff MFA, product/image upload, platform/store publication, private preview, cart handoff, payment status refresh/callback replay, fulfillment, and merchant custom-domain return URLs. Confirm secure host-only cookies and absence of localhost or mixed-content requests. Verify payment callbacks before enabling real collection.

| Symptom | First checks |
| --- | --- |
| 502/504 | Gunicorn status/logs, core `PYTHONPATH` for payments, environment prerequisites, loopback ports, blocked provider calls |
| Redirect loop or internal checkout error | Trusted HTTPS header and Django redirect policy for loopback service POSTs |
| 403 CSRF | Exact HTTPS origin, Host preservation, payments override, fresh token, secure cookies |
| 400/404 on a new shop | Nginx map, Django allowed hosts, exact verified Domain, provisioning/online/suspended state |
| Wrong TLS certificate | SNI, exact customer server block, certificate SANs, lineage path, reload |
| ACME validation fails | TXT/API permissions for wildcard; port 80/webroot for customer; A/AAAA/CAA; proxy interference; CA limits |
| Old UI or missing chunks | Correct `/browser` webroot, index revalidation, retained old chunks, atomic publication |
| Slow checkout or database locked | Provider calls inside transactions, SQLite contention, throttling/cache setup, upstream latency |

### Verification of this guide

The examples were reviewed against the repository's paths and official documentation. Local documentation links and shell syntax (`bash -n`) passed, and all three systemd templates passed a basic structure check. Nginx/Certbot/systemd and actual domain issuance must still be validated on the target Linux staging server; they were not executed on the development Mac. No performance benchmark or production readiness is asserted. See [current architecture](architecture/CURRENT.md) for the implemented baseline.
