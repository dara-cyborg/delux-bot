from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Body, Header, HTTPException
from fastapi.responses import JSONResponse

from telegram_bot.client import (
    send_message,
    send_message_with_buttons,
    edit_message_text,
    answer_callback_query,
    set_webhook,
    delete_webhook,
    TelegramAPIError,
    TelegramConfigError,
)
from telegram_bot.commands import handle_command
from telegram_bot.callback_handler import handle_callback_query

logger = logging.getLogger(__name__)
app = FastAPI(title="Delux Crawler Telegram Bot Webhook")

WEBHOOK_SECRET_ENV = "TELEGRAM_WEBHOOK_SECRET"
BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
WEBHOOK_ROUTE_PREFIX = "/telegram/webhook"


def _get_env(name: str, required: bool = False) -> str:
    value = os.getenv(name, "").strip()
    if required and not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def _validate_webhook_secret(secret: str, header_token: str | None = None) -> None:
    expected = _get_env(WEBHOOK_SECRET_ENV, required=True)
    if secret != expected and header_token != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


def _get_bot_token() -> str:
    token = _get_env(BOT_TOKEN_ENV, required=True)
    return token


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(f"{WEBHOOK_ROUTE_PREFIX}/{{secret}}")
async def telegram_webhook(
    secret: str,
    update: dict[str, Any] = Body(...),
    x_telegram_secret: str | None = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> JSONResponse:
    _validate_webhook_secret(secret, x_telegram_secret)
    bot_token = _get_bot_token()

    try:
        if "message" in update and isinstance(update["message"], dict):
            message = update["message"]
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            text = message.get("text", "").strip()

            if chat_id is None or not text:
                return JSONResponse({"ok": True})

            response = handle_command(bot_token, chat_id, text)
            if response.get("buttons"):
                send_message_with_buttons(
                    bot_token=bot_token,
                    chat_id=str(chat_id),
                    text=response["text"],
                    buttons=response["buttons"],
                    parse_mode=response.get("parse_mode", "HTML"),
                )
            else:
                send_message(
                    bot_token=bot_token,
                    chat_id=str(chat_id),
                    text=response["text"],
                    parse_mode=response.get("parse_mode", "HTML"),
                )

        elif "callback_query" in update and isinstance(update["callback_query"], dict):
            callback = update["callback_query"]
            callback_query_id = callback.get("id")
            data = callback.get("data", "")
            message = callback.get("message") or {}
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            message_id = message.get("message_id")

            if callback_query_id is None or chat_id is None or message_id is None:
                return JSONResponse({"ok": True})

            response = handle_callback_query(bot_token, data, chat_id, message_id)
            if response.get("text") is not None:
                edit_message_text(
                    bot_token=bot_token,
                    chat_id=str(chat_id),
                    message_id=int(message_id),
                    text=response["text"],
                    buttons=response.get("buttons"),
                    parse_mode=response.get("parse_mode", "HTML"),
                )
            answer_callback_query(
                bot_token=bot_token,
                callback_query_id=str(callback_query_id),
                text=response.get("notification", ""),
                show_alert=False,
            )

    except TelegramConfigError as exc:
        logger.error(f"Telegram config error in webhook: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    except TelegramAPIError as exc:
        logger.error(f"Telegram API error in webhook: {exc}")
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Unexpected error processing Telegram webhook: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")

    return JSONResponse({"ok": True})


@app.post("/telegram/set-webhook")
async def telegram_set_webhook() -> JSONResponse:
    bot_token = _get_bot_token()
    webhook_secret = _get_env(WEBHOOK_SECRET_ENV, required=True)
    host = _get_env("HOSTNAME", required=False)

    if not host:
        raise HTTPException(status_code=400, detail="HOSTNAME environment variable is required to set webhook")

    webhook_url = f"https://{host}{WEBHOOK_ROUTE_PREFIX}/{webhook_secret}"
    try:
        result = set_webhook(
            bot_token=bot_token,
            webhook_url=webhook_url,
            secret_token=webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
        return JSONResponse({"ok": True, "result": result})
    except TelegramAPIError as exc:
        logger.error(f"Failed to set webhook: {exc}")
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/telegram/delete-webhook")
async def telegram_delete_webhook() -> JSONResponse:
    bot_token = _get_bot_token()
    try:
        result = delete_webhook(bot_token=bot_token)
        return JSONResponse({"ok": True, "result": result})
    except TelegramAPIError as exc:
        logger.error(f"Failed to delete webhook: {exc}")
        raise HTTPException(status_code=502, detail=str(exc))
