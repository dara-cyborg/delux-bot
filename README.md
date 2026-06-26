# Telegram Bot Package

This package contains Telegram integration support for Delux Crawler.

## Purpose

- Send live order notifications to Telegram via bot chat.
- Persist Telegram runtime configuration in the app state.
- Provide a reusable client for Telegram Bot API requests.
- Format order and session messages for Telegram.
- Support future command/callback workflows via polling.

## Contents

- `telegram_bot/__init__.py` — Package exports.
- `telegram_bot/config.py` — Telegram API constants, default templates, and button labels.
- `telegram_bot/models.py` — Pydantic models for configuration, payloads, responses, and callback state.
- `telegram_bot/client.py` — HTTP wrapper for Telegram Bot API using built-in `urllib`.
- `telegram_bot/message_builder.py` — HTML-safe message formatting, template processing, and menu text builders.
- `telegram_bot/bot.py` — Optional polling-based bot lifecycle for incoming Telegram updates.
- `server.py` — FastAPI webhook server and tenant API entrypoint for Heroku.
- `telegram_bot/commands.py` — Command handler scaffolding for Telegram bot text commands.
- `telegram_bot/callback_handler.py` — Callback query handler scaffolding for inline button navigation.
- `telegram_bot/session_manager.py` — Session and order lookup helpers for the future menu flow.
- `telegram_bot/tests/` — Unit tests for client, message builder, commands, callback handling, and session manager.

## Running tests

From the repository root, run:

```powershell
python -m pytest telegram_bot/tests -q
```

## API documentation

- [Heroku Telegram Bot API Integration](docs/API_INTEGRATION.md) explains how another app or AI agent can call the tenant config and order ingestion APIs.
- [Multi-Tenant Access Availability](docs/MULTI_TENANT_ACCESS.md) explains the current tenant isolation model, availability, and production limits.

## Notes

- The package currently uses built-in `urllib` instead of external Telegram SDKs.
- Order sending is triggered through `backend/routers/telegram.py` via `POST /stupidego/telegram/send-order`.
- Telegram polling in `telegram_bot/bot.py` is optional and only started when the app is configured to use Telegram.
- `server.py` provides a lightweight FastAPI webhook server and tenant API for Heroku or other HTTPS hosting.

## Webhook deployment

- Use `server.py` instead of `telegram_bot/bot.py` for Heroku.
- Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `HOSTNAME`, and `X_ACCESS_TOKEN` in the Heroku environment.
- Use `requirements.txt` for minimal Heroku dependency installation.
- Deploy the bot package and root `server.py`, then expose `web: uvicorn server:app --host 0.0.0.0 --port $PORT` via Procfile.

## Tenant API access

The tenant API endpoints require the caller to send the configured access token
as an `X-Access-Token` header:

```powershell
heroku config:set X_ACCESS_TOKEN="shared-secret-token"
```

Configure Delux Crawler Playwright with the same value when it calls:

- `POST /api/tenants/{tenant_id}/telegram/config`
- `POST /api/tenants/{tenant_id}/orders`
