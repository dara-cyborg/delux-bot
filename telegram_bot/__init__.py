"""
Telegram Bot integration for order delivery.

This package handles:
- Configuration management for Telegram bot credentials
- HTTP API communication with Telegram Bot API
- Message formatting and delivery
- Future: Command handling, session management, and menu-driven UI
"""

from telegram_bot.client import (
    send_message,
    send_message_with_buttons,
    set_webhook,
    delete_webhook,
    TelegramAPIError,
    TelegramConfigError,
)
from telegram_bot.message_builder import build_order_message, build_session_summary
from telegram_bot.bot import TelegramBot
from telegram_bot.commands import handle_command
from telegram_bot.callback_handler import handle_callback_query
from telegram_bot.session_manager import (
    get_sessions_paginated,
    get_session_summary,
    get_customers_for_session,
    get_orders_for_customer,
)
from telegram_bot.storage import register_storage_provider, reset_storage_provider

__all__ = [
    "send_message",
    "send_message_with_buttons",
    "set_webhook",
    "delete_webhook",
    "build_order_message",
    "build_session_summary",
    "TelegramBot",
    "handle_command",
    "handle_callback_query",
    "get_sessions_paginated",
    "get_session_summary",
    "get_customers_for_session",
    "get_orders_for_customer",
    "register_storage_provider",
    "reset_storage_provider",
    "TelegramAPIError",
    "TelegramConfigError",
]
