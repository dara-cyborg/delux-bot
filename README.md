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
- `telegram_bot/server.py` — FastAPI webhook server for hosting only the Telegram bot.
- `telegram_bot/commands.py` — Command handler scaffolding for Telegram bot text commands.
- `telegram_bot/callback_handler.py` — Callback query handler scaffolding for inline button navigation.
- `telegram_bot/session_manager.py` — Session and order lookup helpers for the future menu flow.
- `telegram_bot/tests/` — Unit tests for client, message builder, commands, callback handling, and session manager.

## Running tests

From the repository root, run:

```powershell
python -m pytest telegram_bot/tests -q
```

## Notes

- The package currently uses built-in `urllib` instead of external Telegram SDKs.
- Order sending is triggered through `backend/routers/telegram.py` via `POST /stupidego/telegram/send-order`.
- Telegram polling in `telegram_bot/bot.py` is optional and only started when the app is configured to use Telegram.
- `telegram_bot/server.py` provides a lightweight FastAPI webhook server for Heroku or other HTTPS hosting.

## Webhook deployment

- Use `telegram_bot/server.py` instead of `telegram_bot/bot.py` for Heroku.
- Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, and `HOSTNAME` in the Heroku environment.
- Use `telegram_bot/requirements.txt` for minimal Heroku dependency installation.
- Deploy the bot package only and expose `web: uvicorn telegram_bot.server:app --host 0.0.0.0 --port $PORT` via Procfile.
