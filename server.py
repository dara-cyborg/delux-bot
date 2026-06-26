from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, Body, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from telegram_bot.client import (
    send_alert_with_tenant_credentials,
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
    get_or_create_tenant_webhook_secret,
    validate_webhook_secret,
)
from telegram_bot.audit import log_tenant_config_change, log_order_ingestion, log_webhook_event
from telegram_bot.middleware import RateLimitMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    register_storage_provider(
        get_sessions_paginated=_tenant_sessions_paginated,
        get_session_orders=_tenant_session_orders,
        get_tenant_orders_by_date=_tenant_orders_by_date,
        get_tenant_by_chat_id=_tenant_lookup_callback,
    )
    yield


app = FastAPI(title="Delux Crawler Telegram Bot Webhook", lifespan=lifespan)
app.add_middleware(RateLimitMiddleware, requests_per_minute=100)

WEBHOOK_SECRET_ENV = "TELEGRAM_WEBHOOK_SECRET"
BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
API_ACCESS_TOKEN_ENV = "X_ACCESS_TOKEN"
WEBHOOK_ROUTE_PREFIX = "/telegram/webhook"
TENANT_WEBHOOK_ROUTE_PREFIX = "/telegram/tenant-webhook"


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


def _normalize_app_domain(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    if parsed.scheme and parsed.path:
        return f"{parsed.scheme}://{parsed.path}"
    return f"https://{value.lstrip('https://').lstrip('http://').rstrip('/') }"


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


def _is_valid_telegram_bot_token(token: str) -> bool:
    return bool(re.match(r"^\d+:[A-Za-z0-9_-]{10,}$", token))


def _tenant_lookup_callback(chat_id: int | str) -> Optional[str]:
    tenant_config = tenant_store_get_tenant_by_chat_id(str(chat_id))
    if not tenant_config:
        return None
    return tenant_config.get("tenant_id")


def _is_message_not_modified_error(exc: TelegramAPIError) -> bool:
    message = str(exc.message or "").lower()
    return "message is not modified" in message


def _tenant_sessions_paginated(tenant_id: str, page: int, page_size: int = 10):
    sessions = get_tenant_sessions(tenant_id, limit=(page + 1) * page_size)
    start = page * page_size
    return sessions[start:start + page_size]


def _tenant_session_orders(tenant_id: str, session_id: str, limit: int = 500):
    return tenant_store_get_session_orders(tenant_id, session_id, limit)


def _tenant_orders_by_date(tenant_id: str, order_date: str, limit: int = 500):
    return tenant_store_get_tenant_orders_by_date(tenant_id, order_date, limit)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/tenants/{tenant_id}/telegram/config", response_model=None)
async def update_tenant_telegram_config(
    request: Request,
    tenant_id: str,
    config: TelegramConfigRequest,
    background_tasks: BackgroundTasks,
    x_access_token: Optional[str] = Header(None, alias="X-Access-Token"),
) -> JSONResponse:
    return await _update_tenant_telegram_config_internal(
        tenant_id=tenant_id,
        config=config,
        request=request,
        x_access_token=x_access_token,
        background_tasks=background_tasks,
    )


async def _update_tenant_telegram_config_internal(
    tenant_id: str,
    config: TelegramConfigRequest,
    request: Optional[Request] = None,
    x_access_token: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None,
) -> JSONResponse:
    _validate_access_token(x_access_token)

    if config.enabled and (not config.telegram_bot_token or not config.telegram_chat_id):
        raise HTTPException(
            status_code=400,
            detail="Enabled Telegram configuration requires telegram_bot_token and telegram_chat_id",
        )

    if config.enabled and config.telegram_bot_token:
        if not _is_valid_telegram_bot_token(config.telegram_bot_token):
            logger.error(f"Invalid Telegram bot token format for tenant {tenant_id}")
            raise HTTPException(status_code=400, detail="Invalid Telegram bot token format")

    saved_config = await asyncio.to_thread(
        save_tenant_telegram_config,
        tenant_id=tenant_id,
        enabled=config.enabled,
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        message_template=config.telegram_message_template,
    )
    
    # Generate or retrieve webhook secret for tenant
    webhook_secret = None
    webhook_url = None
    if config.enabled:
        webhook_secret = await asyncio.to_thread(get_or_create_tenant_webhook_secret, tenant_id)
        # Build webhook URL (requires app to know its own domain)
        app_domain = os.environ.get("APP_DOMAIN")
        if not app_domain:
            host = os.environ.get("HOSTNAME")
            if host:
                app_domain = host
            elif request is not None:
                forwarded_proto = request.headers.get("x-forwarded-proto", "https")
                host_header = request.headers.get("host")
                if not host_header:
                    raise HTTPException(
                        status_code=500,
                        detail="HOSTNAME or APP_DOMAIN environment variable is required to set webhook URL",
                    )
                app_domain = f"{forwarded_proto}://{host_header}"
            else:
                logger.info(
                    f"Skipping webhook registration for tenant {tenant_id} because request context is unavailable"
                )
                app_domain = ""
        app_domain = _normalize_app_domain(app_domain)
        webhook_url = f"{app_domain.rstrip('/')}{TENANT_WEBHOOK_ROUTE_PREFIX}/{tenant_id}/{webhook_secret}"
        logger.info(f"Tenant {tenant_id} webhook URL: {webhook_url}")

        if background_tasks is not None:
            background_tasks.add_task(
                _configure_tenant_webhook,
                tenant_id,
                config.telegram_bot_token,
                webhook_url,
                webhook_secret,
            )
            logger.info(
                f"Scheduled Telegram webhook configuration for tenant {tenant_id}: {webhook_url}"
            )
        else:
            logger.info(
                f"BackgroundTasks unavailable for tenant {tenant_id}; webhook registration deferred"
            )

    # Log the configuration change
    log_tenant_config_change(
        tenant_id=tenant_id,
        action="update_config" if config.enabled else "disable_config",
        enabled=config.enabled,
        chat_id=config.telegram_chat_id,
        remote_addr=x_access_token,  # We don't have direct access to client IP here
        status="success"
    )

    # Return safe config without raw bot token
    safe_config = {
        "tenant_id": saved_config.get("tenant_id"),
        "telegram_enabled": saved_config.get("telegram_enabled"),
        "telegram_chat_id": saved_config.get("telegram_chat_id"),
        "telegram_message_template": saved_config.get("telegram_message_template"),
        "created_at": saved_config.get("created_at"),
        "updated_at": saved_config.get("updated_at"),
    }

    response_data = {
        "ok": True,
        "tenant_id": tenant_id,
        "telegram_config": safe_config,
    }

    if webhook_url:
        response_data["webhook_url"] = webhook_url
        response_data["webhook_secret"] = webhook_secret

    return JSONResponse(response_data)


async def _configure_tenant_webhook(
    tenant_id: str,
    bot_token: str,
    webhook_url: str,
    webhook_secret: str,
) -> None:
    try:
        await delete_webhook(
            bot_token=bot_token,
            drop_pending_updates=True,
        )
    except TelegramAPIError as exc:
        logger.warning(
            f"Failed to clear pending Telegram updates for tenant {tenant_id}: {exc}"
        )

    try:
        await set_webhook(
            bot_token=bot_token,
            webhook_url=webhook_url,
            secret_token=webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
    except TelegramAPIError as exc:
        logger.error(
            f"Failed to set Telegram webhook for tenant {tenant_id}: {exc}"
            f"; webhook_url={webhook_url}"
        )


@app.post("/api/tenants/{tenant_id}/orders")
async def create_tenant_order(
    tenant_id: str,
    order: OrderCreateRequest,
    x_access_token: str | None = Header(None, alias="X-Access-Token"),
) -> JSONResponse:
    _validate_access_token(x_access_token)

    saved_order = await asyncio.to_thread(
        save_order,
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
    
    # Log order ingestion
    log_order_ingestion(
        tenant_id=tenant_id,
        session_id=order.session_id,
        order_id=saved_order.get("order_id"),
        status="success"
    )

    telegram_config = await asyncio.to_thread(get_tenant_telegram_config, tenant_id)
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
            await send_alert_with_tenant_credentials(
                tenant_id=tenant_id,
                tenant_bot_token=telegram_config.get("telegram_bot_token", ""),
                tenant_chat_id=telegram_config.get("telegram_chat_id", ""),
                message=message_text,
            )
        except TelegramAPIError as exc:
            logger.error(f"Failed to deliver tenant alert for {tenant_id}: {exc}")
            raise HTTPException(status_code=502, detail=str(exc))

    return JSONResponse({"ok": True, "tenant_id": tenant_id, "order": saved_order})


@app.post("/telegram/tenant-webhook/{tenant_id}/{secret}")
async def tenant_telegram_webhook(
    tenant_id: str,
    secret: str,
    update: dict[str, Any] = Body(...),
    x_telegram_secret: str | None = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> JSONResponse:
    """
    Tenant-specific Telegram webhook for processing updates.
    
    Validates secret against tenant's stored webhook secret and ensures
    incoming chat_id matches the tenant's configured Telegram chat.
    Silently drops requests from unregistered users/tenants.
    """
    try:
        # Validate webhook secret - catch all errors gracefully
        try:
            if not await asyncio.to_thread(validate_webhook_secret, tenant_id, secret):
                if x_telegram_secret != secret:
                    logger.warning(f"Invalid webhook secret for tenant {tenant_id}")
                    return JSONResponse({"ok": False}, status_code=401)
        except Exception as exc:
            logger.warning(f"Webhook validation error for tenant {tenant_id}: {exc}")
            return JSONResponse({"ok": False}, status_code=401)
        
        # Get tenant config - catch errors gracefully
        try:
            tenant_config = await asyncio.to_thread(get_tenant_telegram_config, tenant_id)
        except Exception as exc:
            logger.warning(f"Failed to get config for tenant {tenant_id}: {exc}")
            return JSONResponse({"ok": False}, status_code=401)
        
        if not tenant_config or not tenant_config.get("telegram_enabled"):
            logger.warning(f"Webhook received for disabled tenant {tenant_id}")
            return JSONResponse({"ok": False}, status_code=401)
        
        bot_token = tenant_config.get("telegram_bot_token")
        configured_chat_id = tenant_config.get("telegram_chat_id")
        
        if not bot_token or not configured_chat_id:
            logger.warning(f"Incomplete tenant config for {tenant_id}")
            return JSONResponse({"ok": False}, status_code=401)
        
        if "message" in update and isinstance(update["message"], dict):
            message = update["message"]
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            text = message.get("text", "").strip()
            
            if chat_id is None or not text:
                return JSONResponse({"ok": True})
            
            # Validate that message came from tenant's configured chat
            if str(chat_id) != str(configured_chat_id):
                logger.warning(
                    f"Message from unauthorized chat {chat_id} for tenant {tenant_id} "
                    f"(expected {configured_chat_id})"
                )
                raise HTTPException(status_code=403, detail="Chat ID mismatch")
            
            logger.debug(f"Tenant webhook message from {tenant_id} in chat {chat_id}")
            log_webhook_event(tenant_id, "message", chat_id, "success")
            
            response = handle_command(bot_token, chat_id, text, tenant_id=tenant_id)
            if response.get("buttons"):
                await send_message_with_buttons(
                    bot_token=bot_token,
                    chat_id=str(chat_id),
                    text=response["text"],
                    buttons=response["buttons"],
                    parse_mode=response.get("parse_mode", "HTML"),
                )
            else:
                await send_message(
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
            
            # Validate that callback came from tenant's configured chat
            if str(chat_id) != str(configured_chat_id):
                logger.warning(
                    f"Callback from unauthorized chat {chat_id} for tenant {tenant_id} "
                    f"(expected {configured_chat_id})"
                )
                raise HTTPException(status_code=403, detail="Chat ID mismatch")
            
            logger.debug(f"Tenant webhook callback from {tenant_id} in chat {chat_id}")
            log_webhook_event(tenant_id, "callback_query", chat_id, "success")
            
            response = handle_callback_query(bot_token, data, chat_id, message_id, tenant_id=tenant_id)
            if response.get("text") is not None:
                try:
                    await edit_message_text(
                        bot_token=bot_token,
                        chat_id=str(chat_id),
                        message_id=int(message_id),
                        text=response["text"],
                        buttons=response.get("buttons"),
                        parse_mode=response.get("parse_mode", "HTML"),
                    )
                except TelegramAPIError as exc:
                    if _is_message_not_modified_error(exc):
                        logger.warning(
                            "Telegram callback edit returned message not modified; ignoring harmless error."
                        )
                    else:
                        raise
            await answer_callback_query(
                bot_token=bot_token,
                callback_query_id=str(callback_query_id),
                text=response.get("notification", ""),
                show_alert=False,
            )
    
    except TelegramConfigError as exc:
        logger.error(f"Telegram config error in tenant webhook: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    except TelegramAPIError as exc:
        logger.error(f"Telegram API error in tenant webhook: {exc}")
        raise HTTPException(status_code=502, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Unexpected error in tenant webhook {tenant_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
    return JSONResponse({"ok": True})


async def _process_webhook_update(update: dict[str, Any]) -> None:
    bot_token = _get_bot_token()

    try:
        if "message" in update and isinstance(update["message"], dict):
            message = update["message"]
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            text = message.get("text", "").strip()

            if chat_id is None or not text:
                return

            tenant_id = await asyncio.to_thread(get_tenant_by_chat_id, chat_id) or ""
            logger.debug(f"Webhook message from chat {chat_id}, resolved tenant: {tenant_id or '(none)'}")

            response = handle_command(bot_token, chat_id, text, tenant_id=tenant_id)
            if response.get("buttons"):
                await send_message_with_buttons(
                    bot_token=bot_token,
                    chat_id=str(chat_id),
                    text=response["text"],
                    buttons=response["buttons"],
                    parse_mode=response.get("parse_mode", "HTML"),
                )
            else:
                await send_message(
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
                return

            tenant_id = await asyncio.to_thread(get_tenant_by_chat_id, chat_id) or ""
            logger.debug(f"Webhook callback from chat {chat_id}, resolved tenant: {tenant_id or '(none)'}")

            response = handle_callback_query(bot_token, data, chat_id, message_id, tenant_id=tenant_id)
            if response.get("text") is not None:
                try:
                    await edit_message_text(
                        bot_token=bot_token,
                        chat_id=str(chat_id),
                        message_id=int(message_id),
                        text=response["text"],
                        buttons=response.get("buttons"),
                        parse_mode=response.get("parse_mode", "HTML"),
                    )
                except TelegramAPIError as exc:
                    if _is_message_not_modified_error(exc):
                        logger.warning(
                            "Telegram callback edit returned message not modified; ignoring harmless error."
                        )
                    else:
                        raise
            await answer_callback_query(
                bot_token=bot_token,
                callback_query_id=str(callback_query_id),
                text=response.get("notification", ""),
                show_alert=False,
            )

    except TelegramConfigError as exc:
        logger.error(f"Telegram config error in webhook: {exc}")
    except TelegramAPIError as exc:
        logger.error(f"Telegram API error in webhook: {exc}")
    except Exception as exc:
        logger.exception(f"Unexpected error processing Telegram webhook: {exc}")


@app.post(f"{WEBHOOK_ROUTE_PREFIX}/{{secret}}")
async def telegram_webhook(
    secret: str,
    background_tasks: BackgroundTasks,
    update: dict[str, Any] = Body(...),
    x_telegram_secret: str | None = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> JSONResponse:
    _validate_webhook_secret(secret, x_telegram_secret)
    background_tasks.add_task(_process_webhook_update, update)
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
        result = await set_webhook(
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
        result = await delete_webhook(bot_token=bot_token)
        return JSONResponse({"ok": True, "result": result})
    except TelegramAPIError as exc:
        logger.error(f"Failed to delete webhook: {exc}")
        raise HTTPException(status_code=502, detail=str(exc))
