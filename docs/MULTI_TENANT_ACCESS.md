# Multi-Tenant Access Availability

This document explains the current availability and limits of multi-tenant access in the Heroku Telegram bot service.

## Status

Multi-tenant access is available for tenant Telegram configuration, tenant order ingestion, tenant-isolated storage, Telegram alert delivery, and Telegram menu lookup.

The implementation uses `tenant_id` as the primary isolation key and stores tenant data in SQLite through `telegram_bot/tenant_store.py`.

## Available Capabilities

### Tenant-Specific Telegram Configuration

Each tenant can have its own:

- Telegram bot token.
- Telegram chat ID.
- Message template.
- Enabled or disabled Telegram delivery state.

Endpoint:

```text
POST /api/tenants/{tenant_id}/telegram/config
```

When `enabled` is true, the API validates the tenant bot token with Telegram before saving it.

### Tenant-Specific Order Storage

Each order is stored with:

- `tenant_id`
- `session_id`
- `commenter`
- `comment`
- source metadata such as `comment_id`, `profile_url`, `collected_at`, and `order_date`

Endpoint:

```text
POST /api/tenants/{tenant_id}/orders
```

The service automatically creates the tenant and session rows if they do not already exist.

### Tenant-Specific Telegram Alert Delivery

If a tenant has Telegram delivery enabled, each created order sends a Telegram message using that tenant's saved bot token and chat ID.

This means `tenant-a` and `tenant-b` can use different Telegram bots, chats, and templates while sharing the same Heroku API service.

### Tenant-Isolated Bot Menus

Telegram commands and inline menu callbacks resolve the tenant by Telegram chat ID.

Supported commands include:

```text
/start
/help
/menu
/sessions
/today
```

After the webhook resolves the tenant, menu data is filtered by that tenant ID. Sessions, orders, today summaries, customer lists, and customer order views are tenant-scoped.

## Isolation Model

Tenant data is isolated in the database by composite keys and tenant filters.

Important storage rules:

| Data | Isolation Method |
| --- | --- |
| Tenants | `tenant_id` primary key |
| Telegram config | `tenant_id` primary key |
| Sessions | composite primary key: `(tenant_id, session_id)` |
| Orders | `tenant_id` foreign key plus session foreign key |
| Chat lookup | enabled Telegram config matched by `telegram_chat_id` |

Two tenants can use the same `session_id` without sharing orders because session identity is scoped by `(tenant_id, session_id)`.

## API Access Model

Current tenant API access uses one shared service token:

```http
X-Access-Token: <shared secret>
```

This is service-to-service authentication. It is suitable when a trusted backend or crawler calls the Heroku bot API on behalf of all tenants.

Current access control does not include:

- Per-tenant API keys.
- Tenant-scoped bearer tokens.
- Role-based access control.
- Public read endpoints for tenant sessions or orders.
- Admin endpoints to list tenants.

Because the token is shared, the calling application is responsible for only sending data to the correct `tenant_id`.

## Data Persistence Availability On Heroku

The current implementation stores data in:

```text
data/tenant_data.db
```

That is local SQLite storage inside the dyno filesystem.

On Heroku, dyno filesystems are ephemeral. Data can be lost after dyno restart, redeploy, crash recovery, or dyno replacement unless the app is changed to use durable storage.

For production multi-tenant availability, use a durable database. The selected migration target for this project is Neon Postgres, connected from Heroku through the `DATABASE_URL` config var. SQLite is acceptable for local development, demos, and short-lived testing, but it is not a durable Heroku production storage layer.

## Operational Availability

The app supports many tenants through one Heroku deployment, but availability depends on these shared resources:

| Resource | Shared Or Tenant-Specific | Availability Impact |
| --- | --- | --- |
| Heroku dyno | Shared | If the dyno is down, all tenants are unavailable. |
| `X_ACCESS_TOKEN` | Shared | If missing, all tenant API endpoints fail with `500`. |
| SQLite database file | Shared | Local file availability affects all tenants. |
| Tenant Telegram bot token | Tenant-specific | Bad token affects only that tenant's delivery. |
| Tenant Telegram chat ID | Tenant-specific | Bad chat ID affects only that tenant's delivery and chat lookup. |
| Shared webhook bot token | Shared | Webhook commands depend on the global `TELEGRAM_BOT_TOKEN`. |

## Known Limits

- No per-tenant REST read API exists yet. Tenant data is readable through Telegram menus only.
- `POST /api/tenants/{tenant_id}/orders` can return `502` if Telegram delivery fails after the order is saved.
- The webhook command path uses the global `TELEGRAM_BOT_TOKEN` for replies, even though order alerts use tenant-specific bot tokens.
- Telegram chat ID lookup assumes an enabled tenant config with a unique chat ID. If two enabled tenants share the same chat ID, lookup can be ambiguous.
- SQLite has limited write concurrency compared with a production database.
- Local server time is used when `collected_at` or `order_date` is omitted.

## Recommended Production Upgrade Path

For stronger multi-tenant availability:

1. Move tenant storage from SQLite to Neon Postgres.
2. Add per-tenant API keys or signed requests.
3. Add read endpoints for sessions, orders, and tenant config if external apps need API reads.
4. Enforce unique enabled Telegram chat IDs.
5. Decide whether webhook replies should use tenant-specific bot tokens or a single shared bot.
6. Add idempotency for order ingestion using `comment_id` or a caller-provided idempotency key.

## Practical Answer

Multi-tenant access is currently available for trusted backend integrations that can hold the shared `X-Access-Token`. It is ready for local development and controlled Heroku testing.

For production use with real tenant data, durable database storage and stronger tenant-scoped authentication should be added before relying on it as the system of record.
