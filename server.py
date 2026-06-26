from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import FastAPI, Body, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from telegram_bot.client import (
    send_alert_with_tenant_credentials,
    send_message,
    send_message_with_buttons,
    edit_message_text,
    answer_callback_query,
    get_bot_info,
    set_webhook,
    delete_webhook,
    TelegramAPIError,
    TelegramConfigError,
)
from telegram_bot.commands import handle_command
from telegram_bot.callback_handler import handle_callback_query
from telegram_bot.message_builder import build_order_message
from telegram_bot.storage import (
    get_tenant_by_chat_id,
    register_storage_provider,
)
from telegram_bot.tenant_store import (
    init_db,
    get_tenant_by_chat_id as tenant_store_get_tenant_by_chat_id,
    get_tenant_telegram_config,
    get_tenant_sessions,
    get_session_orders as tenant_store_get_session_orders,
    get_tenant_orders_by_date as tenant_store_get_tenant_orders_by_date,
    save_order,
    save_tenant_telegram_config,
)

logger = logging.getLogger(__name__)
app = FastAPI(title="Delux Crawler Telegram Bot Webhook")

WEBHOOK_SECRET_ENV = "TELEGRAM_WEBHOOK_SECRET"
BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
API_ACCESS_TOKEN_ENV = "X_ACCESS_TOKEN"
WEBHOOK_ROUTE_PREFIX = "/telegram/webhook"


class TelegramConfigRequest(BaseModel):
    enabled: bool = True
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_message_template: Optional[str] = None


class OrderCreateRequest(BaseModel):
    session_id: str
    commenter: str
    comment: str
    comment_id: Optional[str] = None
    collected_at: Optional[str] = None
    profile_url: Optional[str] = None
    order_date: Optional[str] = None


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


def _get_access_token() -> str:
    token = _get_env(API_ACCESS_TOKEN_ENV, required=True)
    return token


def _validate_access_token(header_token: str | None = None) -> None:
    try:
        expected = _get_access_token()
    except RuntimeError as exc:
        logger.error(str(exc))
        raise HTTPException(status_code=500, detail="API access token is not configured") from exc

    if header_token != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


def _tenant_lookup_callback(chat_id: int | str) -> Optional[str]:
    tenant_config = tenant_store_get_tenant_by_chat_id(str(chat_id))
    if not tenant_config:
        return None
    return tenant_config.get("tenant_id")


def _tenant_sessions_paginated(tenant_id: str, page: int, page_size: int = 10):
    sessions = get_tenant_sessions(tenant_id, limit=(page + 1) * page_size)
    start = page * page_size
    return sessions[start:start + page_size]


def _tenant_session_orders(tenant_id: str, session_id: str, limit: int = 500):
    return tenant_store_get_session_orders(tenant_id, session_id, limit)


def _tenant_orders_by_date(tenant_id: str, order_date: str, limit: int = 500):
    return tenant_store_get_tenant_orders_by_date(tenant_id, order_date, limit)


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    register_storage_provider(
        get_sessions_paginated=_tenant_sessions_paginated,
        get_session_orders=_tenant_session_orders,
        get_tenant_orders_by_date=_tenant_orders_by_date,
        get_tenant_by_chat_id=_tenant_lookup_callback,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/tenants/{tenant_id}/telegram/config")
async def update_tenant_telegram_config(
    tenant_id: str,
    config: TelegramConfigRequest,
    x_access_token: str | None = Header(None, alias="X-Access-Token"),
) -> JSONResponse:
    _validate_access_token(x_access_token)

    if config.enabled and (not config.telegram_bot_token or not config.telegram_chat_id):
        raise HTTPException(
            status_code=400,
            detail="Enabled Telegram configuration requires telegram_bot_token and telegram_chat_id",
        )

    if config.enabled and config.telegram_bot_token:
        try:
            get_bot_info(config.telegram_bot_token)
        except TelegramAPIError as exc:
            logger.error(f"Invalid Telegram bot token for tenant {tenant_id}: {exc}")
            raise HTTPException(status_code=400, detail="Invalid Telegram bot token") from exc

    saved_config = save_tenant_telegram_config(
        tenant_id=tenant_id,
        enabled=config.enabled,
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        message_template=config.telegram_message_template,
    )

    return JSONResponse({"ok": True, "tenant_id": tenant_id, "telegram_config": saved_config})


@app.post("/api/tenants/{tenant_id}/orders")
async def create_tenant_order(
    tenant_id: str,
    order: OrderCreateRequest,
    x_access_token: str | None = Header(None, alias="X-Access-Token"),
) -> JSONResponse:
    _validate_access_token(x_access_token)

    saved_order = save_order(
        tenant_id=tenant_id,
        session_id=order.session_id,
        commenter=order.commenter,
        comment=order.comment,
        comment_id=order.comment_id,
        collected_at=order.collected_at,
        profile_url=order.profile_url,
        order_date=order.order_date,
        source_host="api",
    )

    telegram_config = get_tenant_telegram_config(tenant_id)
    if telegram_config and telegram_config.get("telegram_enabled"):
        message_text = build_order_message(
            commenter=order.commenter,
            comment=order.comment,
            profile_url=order.profile_url,
            collected_at=order.collected_at,
            comment_id=order.comment_id,
            template=telegram_config.get("telegram_message_template"),
        )
        try:
            send_alert_with_tenant_credentials(
                tenant_id=tenant_id,
                tenant_bot_token=telegram_config.get("telegram_bot_token", ""),
                tenant_chat_id=telegram_config.get("telegram_chat_id", ""),
                message=message_text,
            )
        except TelegramAPIError as exc:
            logger.error(f"Failed to deliver tenant alert for {tenant_id}: {exc}")
            raise HTTPException(status_code=502, detail=str(exc))

    return JSONResponse({"ok": True, "tenant_id": tenant_id, "order": saved_order})


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

            # Resolve tenant from chat_id
            tenant_id = get_tenant_by_chat_id(chat_id) or ""
            logger.debug(f"Webhook message from chat {chat_id}, resolved tenant: {tenant_id or '(none)'}")

            response = handle_command(bot_token, chat_id, text, tenant_id=tenant_id)
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

            # Resolve tenant from chat_id
            tenant_id = get_tenant_by_chat_id(chat_id) or ""
            logger.debug(f"Webhook callback from chat {chat_id}, resolved tenant: {tenant_id or '(none)'}")

            response = handle_callback_query(bot_token, data, chat_id, message_id, tenant_id=tenant_id)
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
