# Heroku Telegram Bot API Integration

This document describes the HTTP API exposed by the Heroku-hosted Telegram bot service so another app or AI agent can configure tenant Telegram delivery and publish live order events.

## Base URL

Use the deployed Heroku app URL as the base URL:

```text
https://<your-heroku-app>.herokuapp.com
```

For local development:

```text
http://localhost:8000
```

The Heroku `Procfile` runs:

```text
uvicorn server:app --host 0.0.0.0 --port $PORT
```

## Database

Current implementation uses local SQLite at `data/tenant_data.db`. That is not durable on Heroku.

The selected durable database target is Neon Postgres. After the migration is implemented, set Heroku `DATABASE_URL` to the Neon pooled connection string:

```powershell
heroku config:set DATABASE_URL="<neon-pooled-postgres-connection-string>"
```

When `DATABASE_URL` is present, the app should use Neon Postgres. When it is absent, the app should keep using SQLite for local development.

## Authentication

Tenant API endpoints require a shared access token in the `X-Access-Token` header.

Server environment variable:

```powershell
heroku config:set X_ACCESS_TOKEN="shared-secret-token"
```

Client header:

```http
X-Access-Token: shared-secret-token
```

If the server has no `X_ACCESS_TOKEN`, tenant endpoints return `500`.
If the header is missing or wrong, tenant endpoints return `403`.

## Health Check

### `GET /health`

Returns service health.

Response:

```json
{
  "status": "ok"
}
```

## Configure Tenant Telegram Delivery

### `POST /api/tenants/{tenant_id}/telegram/config`

Creates or updates Telegram delivery settings for one tenant.

Use this endpoint before sending orders if the tenant should receive Telegram notifications.

Path parameters:

| Name | Required | Description |
| --- | --- | --- |
| `tenant_id` | Yes | Stable tenant identifier from your app. It is used for storage isolation. |

Headers:

| Name | Required | Description |
| --- | --- | --- |
| `X-Access-Token` | Yes | Shared API access token matching Heroku `X_ACCESS_TOKEN`. |
| `Content-Type` | Yes | `application/json` |

Request body:

```json
{
  "enabled": true,
  "telegram_bot_token": "123456:tenant-bot-token",
  "telegram_chat_id": "987654321",
  "telegram_message_template": "New order from {{commenter}}\n{{comment}}"
}
```

Fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `enabled` | boolean | No | Defaults to `true`. When `false`, Telegram delivery is disabled and stored credentials are cleared. |
| `telegram_bot_token` | string | Required when enabled | Tenant bot token. The API validates it through Telegram `getMe` before saving. |
| `telegram_chat_id` | string | Required when enabled | Telegram chat, group, or channel ID to receive tenant alerts. |
| `telegram_message_template` | string | No | Optional alert template. Supports both `{{field}}` and Python `{field}` placeholders. |

Supported template fields:

```text
commenter
comment
profile_url
collected_at
comment_id
```

Success response:

```json
{
  "ok": true,
  "tenant_id": "tenant-a",
  "telegram_config": {
    "tenant_id": "tenant-a",
    "telegram_enabled": 1,
    "telegram_bot_token": "123456:tenant-bot-token",
    "telegram_chat_id": "987654321",
    "telegram_message_template": "New order from {{commenter}}\n{{comment}}",
    "created_at": "2026-06-26T10:15:00",
    "updated_at": "2026-06-26T10:15:00"
  }
}
```

Common errors:

| Status | Detail | Meaning |
| --- | --- | --- |
| `400` | `Enabled Telegram configuration requires telegram_bot_token and telegram_chat_id` | `enabled` is true but credentials are missing. |
| `400` | `Invalid Telegram bot token` | Telegram rejected the bot token. |
| `403` | `Forbidden` | `X-Access-Token` is missing or wrong. |
| `500` | `API access token is not configured` | Heroku `X_ACCESS_TOKEN` is missing. |

### cURL

```bash
curl -X POST "https://<your-heroku-app>.herokuapp.com/api/tenants/tenant-a/telegram/config" \
  -H "Content-Type: application/json" \
  -H "X-Access-Token: shared-secret-token" \
  -d '{
    "enabled": true,
    "telegram_bot_token": "123456:tenant-bot-token",
    "telegram_chat_id": "987654321",
    "telegram_message_template": "New order from {{commenter}}\n{{comment}}"
  }'
```

## Create Tenant Order

### `POST /api/tenants/{tenant_id}/orders`

Stores an order under the tenant and session. If Telegram is enabled for the tenant, the bot immediately sends an alert using that tenant's saved Telegram credentials.

Path parameters:

| Name | Required | Description |
| --- | --- | --- |
| `tenant_id` | Yes | Stable tenant identifier. Orders are isolated by this value. |

Headers:

| Name | Required | Description |
| --- | --- | --- |
| `X-Access-Token` | Yes | Shared API access token matching Heroku `X_ACCESS_TOKEN`. |
| `Content-Type` | Yes | `application/json` |

Request body:

```json
{
  "session_id": "live-2026-06-26-1",
  "commenter": "Dara",
  "comment": "2 red shirts",
  "comment_id": "fb-comment-1",
  "collected_at": "2026-06-26 10:15:00",
  "profile_url": "https://facebook.example/dara",
  "order_date": "2026-06-26"
}
```

Fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `session_id` | string | Yes | Live session ID from the calling app. The service creates the session if needed. |
| `commenter` | string | Yes | Customer or commenter name. |
| `comment` | string | Yes | Raw order comment text. |
| `comment_id` | string | No | Source comment ID for traceability. |
| `collected_at` | string | No | Source timestamp. If omitted, the server time is used. |
| `profile_url` | string | No | Customer profile URL. |
| `order_date` | string | No | Date used by `/today` summaries, usually `YYYY-MM-DD`. If omitted, the server date is used. |

Success response:

```json
{
  "ok": true,
  "tenant_id": "tenant-a",
  "order": {
    "order_id": "e79a0f6f-8d6e-4b25-8b28-4f95751e8c0d",
    "tenant_id": "tenant-a",
    "session_id": "live-2026-06-26-1",
    "commenter": "Dara",
    "comment": "2 red shirts",
    "comment_id": "fb-comment-1",
    "collected_at": "2026-06-26 10:15:00",
    "printed_at": "2026-06-26T10:15:02",
    "profile_url": "https://facebook.example/dara",
    "order_date": "2026-06-26",
    "source_host": "api",
    "created_at": "2026-06-26T10:15:02",
    "updated_at": "2026-06-26T10:15:02",
    "metadata": null
  }
}
```

Common errors:

| Status | Detail | Meaning |
| --- | --- | --- |
| `403` | `Forbidden` | `X-Access-Token` is missing or wrong. |
| `500` | `API access token is not configured` | Heroku `X_ACCESS_TOKEN` is missing. |
| `502` | Telegram API error text | The order was saved, but Telegram delivery failed. |

### cURL

```bash
curl -X POST "https://<your-heroku-app>.herokuapp.com/api/tenants/tenant-a/orders" \
  -H "Content-Type: application/json" \
  -H "X-Access-Token: shared-secret-token" \
  -d '{
    "session_id": "live-2026-06-26-1",
    "commenter": "Dara",
    "comment": "2 red shirts",
    "comment_id": "fb-comment-1",
    "collected_at": "2026-06-26 10:15:00",
    "profile_url": "https://facebook.example/dara",
    "order_date": "2026-06-26"
  }'
```

## JavaScript Client Example

```js
const BOT_API_BASE_URL = "https://<your-heroku-app>.herokuapp.com";
const API_TOKEN = process.env.TELEGRAM_BOT_API_TOKEN;

async function configureTenantTelegram(tenantId, config) {
  const response = await fetch(
    `${BOT_API_BASE_URL}/api/tenants/${encodeURIComponent(tenantId)}/telegram/config`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Access-Token": API_TOKEN,
      },
      body: JSON.stringify(config),
    }
  );

  if (!response.ok) {
    throw new Error(`Telegram config failed: ${response.status} ${await response.text()}`);
  }

  return response.json();
}

async function sendTenantOrder(tenantId, order) {
  const response = await fetch(
    `${BOT_API_BASE_URL}/api/tenants/${encodeURIComponent(tenantId)}/orders`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Access-Token": API_TOKEN,
      },
      body: JSON.stringify(order),
    }
  );

  if (!response.ok) {
    throw new Error(`Order publish failed: ${response.status} ${await response.text()}`);
  }

  return response.json();
}
```

## Python Client Example

```python
import os
import requests

BOT_API_BASE_URL = "https://<your-heroku-app>.herokuapp.com"
API_TOKEN = os.environ["TELEGRAM_BOT_API_TOKEN"]


def post_json(path, payload):
    response = requests.post(
        f"{BOT_API_BASE_URL}{path}",
        json=payload,
        headers={"X-Access-Token": API_TOKEN},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


post_json(
    "/api/tenants/tenant-a/telegram/config",
    {
        "enabled": True,
        "telegram_bot_token": "123456:tenant-bot-token",
        "telegram_chat_id": "987654321",
    },
)

post_json(
    "/api/tenants/tenant-a/orders",
    {
        "session_id": "live-2026-06-26-1",
        "commenter": "Dara",
        "comment": "2 red shirts",
        "order_date": "2026-06-26",
    },
)
```

## Telegram Webhook Management

These endpoints are for operating the Telegram webhook, not for tenant apps.

### Required Heroku Config

```powershell
heroku config:set TELEGRAM_BOT_TOKEN="shared-webhook-bot-token"
heroku config:set TELEGRAM_WEBHOOK_SECRET="long-random-secret"
heroku config:set HOSTNAME="<your-heroku-app>.herokuapp.com"
```

### `POST /telegram/set-webhook`

Registers this app as the Telegram webhook for the shared webhook bot.

It sets the Telegram webhook URL to:

```text
https://<HOSTNAME>/telegram/webhook/<TELEGRAM_WEBHOOK_SECRET>
```

Allowed updates:

```json
["message", "callback_query"]
```

### `POST /telegram/delete-webhook`

Deletes the Telegram webhook for `TELEGRAM_BOT_TOKEN`.

### `POST /telegram/webhook/{secret}`

Receives Telegram updates. Telegram can authenticate with either:

- The `{secret}` path value matching `TELEGRAM_WEBHOOK_SECRET`.
- The `X-Telegram-Bot-Api-Secret-Token` header matching `TELEGRAM_WEBHOOK_SECRET`.

Incoming `/start`, `/help`, `/menu`, `/sessions`, and `/today` commands are resolved to a tenant by matching the Telegram chat ID against enabled tenant Telegram configs.

## Implementation Notes For AI Agents

- Use `tenant_id` as the isolation key in every tenant endpoint.
- Configure Telegram before sending orders when the tenant needs alerts.
- Reuse stable `session_id` values so menu views group orders correctly.
- Send `order_date` as `YYYY-MM-DD` if the caller needs `/today` to match the source app's date.
- Never log raw Telegram bot tokens or the shared `X-Access-Token`.
- Treat `502` from `/orders` as a Telegram delivery failure. The order may already be saved.
- This API currently exposes write/config endpoints only. Session and order read access is available through Telegram bot menus, not through public REST read endpoints.
