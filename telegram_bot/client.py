"""
Telegram Bot API client.

Provides low-level HTTP communication with Telegram Bot API.
Uses urllib (no external dependencies).
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
from telegram_bot.config import (
    TELEGRAM_API_BASE_URL,
    TELEGRAM_API_TIMEOUT,
    PARSE_MODE_HTML,
)
from telegram_bot.models import TelegramAPIError, TelegramConfigError

logger = logging.getLogger(__name__)


class _RedactedToken(str):
    """String subclass that redacts the token in logs."""
    def __repr__(self):
        return "[REDACTED_TOKEN]"


def redact_token(token: Optional[str]) -> str:
    """Redact a bot token for safe logging."""
    if not token:
        return "[NO_TOKEN]"
    if len(token) > 10:
        return token[:5] + "..." + token[-5:]
    return "[REDACTED]"


def _validate_config(bot_token: Optional[str], chat_id: Optional[str]) -> None:
    """Validate that Telegram configuration is present."""
    if not bot_token:
        raise TelegramConfigError("Telegram bot token is not configured")
    if not chat_id:
        raise TelegramConfigError("Telegram chat ID is not configured")


def _make_request(
    method: str,
    endpoint: str,
    bot_token: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Make an HTTP POST request to Telegram Bot API.
    
    Args:
        method: HTTP method (POST, GET, etc.)
        endpoint: API endpoint (e.g., "sendMessage")
        bot_token: Telegram bot token
        data: Request payload as dict
    
    Returns:
        Parsed JSON response from Telegram API
    
    Raises:
        TelegramAPIError: If the API returns an error
    """
    url = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/{endpoint}"
    
    try:
        # Prepare request
        json_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=json_data,
            headers={'Content-Type': 'application/json'},
            method=method,
        )
        
        # Make request
        with urllib.request.urlopen(req, timeout=TELEGRAM_API_TIMEOUT) as response:
            response_data = json.loads(response.read().decode('utf-8'))
        
        # Check for API error
        if not response_data.get('ok', False):
            error_msg = response_data.get('description', 'Unknown Telegram API error')
            error_code = response_data.get('error_code')
            redacted = redact_token(bot_token)
            logger.error(
                f"Telegram API error: {error_msg} (code: {error_code}, bot: {redacted})"
            )
            raise TelegramAPIError(error_msg, error_code)
        
        return response_data.get('result', {})
    
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        redacted = redact_token(bot_token)
        logger.error(
            f"Telegram API HTTP error {e.code}: {error_body} (bot: {redacted})"
        )
        raise TelegramAPIError(f"HTTP {e.code}: {error_body}", "HTTP_ERROR")
    
    except urllib.error.URLError as e:
        redacted = redact_token(bot_token)
        logger.error(
            f"Telegram API network error: {e.reason} (bot: {redacted})"
        )
        raise TelegramAPIError(f"Network error: {e.reason}", "NETWORK_ERROR")
    
    except json.JSONDecodeError as e:
        redacted = redact_token(bot_token)
        logger.error(
            f"Telegram API response JSON decode error: {e} (bot: {redacted})"
        )
        raise TelegramAPIError(f"Invalid JSON response: {e}", "JSON_ERROR")


def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str = PARSE_MODE_HTML,
) -> Dict[str, Any]:
    """
    Send a text message to a Telegram chat.
    
    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID (can be a user ID, channel ID, etc.)
        text: Message text
        parse_mode: Parse mode for formatting (HTML or Markdown)
    
    Returns:
        Message response from Telegram API
    
    Raises:
        TelegramConfigError: If configuration is missing
        TelegramAPIError: If the API request fails
    """
    _validate_config(bot_token, chat_id)
    
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
    }
    
    result = _make_request('POST', 'sendMessage', bot_token, data)
    redacted = redact_token(bot_token)
    logger.info(f"Message sent to Telegram (chat: {chat_id}, bot: {redacted})")
    
    return result


def send_message_with_buttons(
    bot_token: str,
    chat_id: str,
    text: str,
    buttons: list[list[Dict[str, str]]],
    parse_mode: str = PARSE_MODE_HTML,
) -> Dict[str, Any]:
    """
    Send a message with inline buttons to a Telegram chat.
    
    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        text: Message text
        buttons: Inline keyboard layout as list of lists of button dicts
                Each button: {"text": "Label", "callback_data": "action_id"}
        parse_mode: Parse mode for formatting
    
    Returns:
        Message response from Telegram API
    
    Raises:
        TelegramConfigError: If configuration is missing
        TelegramAPIError: If the API request fails
    
    Example:
        buttons = [
            [{"text": "Option 1", "callback_data": "opt1"}],
            [{"text": "Last", "callback_data": "prev"}, {"text": "Next", "callback_data": "next"}],
        ]
        send_message_with_buttons(token, chat_id, "Choose:", buttons)
    """
    _validate_config(bot_token, chat_id)
    
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
        'reply_markup': {
            'inline_keyboard': buttons,
        },
    }
    
    result = _make_request('POST', 'sendMessage', bot_token, data)
    redacted = redact_token(bot_token)
    logger.info(
        f"Message with buttons sent to Telegram (chat: {chat_id}, bot: {redacted})"
    )
    
    return result


def edit_message_text(
    bot_token: str,
    chat_id: str,
    message_id: int,
    text: str,
    buttons: Optional[list[list[Dict[str, str]]]] = None,
    parse_mode: str = PARSE_MODE_HTML,
) -> Dict[str, Any]:
    """
    Edit an existing message in Telegram (for menu navigation without spam).
    
    Args:
        bot_token: Telegram bot token
        chat_id: Chat ID containing the message
        message_id: ID of the message to edit
        text: New message text
        buttons: Optional new inline keyboard layout
        parse_mode: Parse mode for formatting
    
    Returns:
        Updated message response from Telegram API
    
    Raises:
        TelegramConfigError: If configuration is missing
        TelegramAPIError: If the API request fails
    """
    _validate_config(bot_token, chat_id)
    
    data = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': parse_mode,
    }
    
    if buttons:
        data['reply_markup'] = {
            'inline_keyboard': buttons,
        }
    
    result = _make_request('POST', 'editMessageText', bot_token, data)
    redacted = redact_token(bot_token)
    logger.info(
        f"Message edited in Telegram (chat: {chat_id}, message: {message_id}, bot: {redacted})"
    )
    
    return result


def answer_callback_query(
    bot_token: str,
    callback_query_id: str,
    text: Optional[str] = None,
    show_alert: bool = False,
) -> bool:
    """
    Answer an inline button callback query (shows notification to user).
    
    Args:
        bot_token: Telegram bot token
        callback_query_id: Callback query ID from button press
        text: Optional notification text
        show_alert: If True, show as pop-up alert instead of toast
    
    Returns:
        True if successful
    
    Raises:
        TelegramConfigError: If configuration is missing
        TelegramAPIError: If the API request fails
    """
    if not bot_token:
        raise TelegramConfigError("Telegram bot token is not configured")
    
    data = {
        'callback_query_id': callback_query_id,
        'text': text or '',
        'show_alert': show_alert,
    }
    
    _make_request('POST', 'answerCallbackQuery', bot_token, data)
    redacted = redact_token(bot_token)
    logger.info(f"Callback answered in Telegram (bot: {redacted})")
    
    return True


def get_bot_info(bot_token: str) -> Dict[str, Any]:
    """Validate a bot token and return Telegram's bot profile."""
    if not bot_token:
        raise TelegramConfigError("Telegram bot token is not configured")

    result = _make_request('POST', 'getMe', bot_token, {})
    redacted = redact_token(bot_token)
    logger.info(f"Telegram bot token validated (bot: {redacted})")
    return result


def set_webhook(
    bot_token: str,
    webhook_url: str,
    secret_token: Optional[str] = None,
    allowed_updates: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Register a Telegram webhook for bot updates.

    Args:
        bot_token: Telegram bot token
        webhook_url: Full HTTPS URL for Telegram to send updates to
        secret_token: Optional secret token Telegram will sign in the header
        allowed_updates: Optional list of update types to receive

    Returns:
        Telegram API result for setWebhook
    """
    if not bot_token:
        raise TelegramConfigError("Telegram bot token is not configured")
    if not webhook_url:
        raise TelegramConfigError("Telegram webhook URL is not configured")

    data = {
        'url': webhook_url,
    }
    if secret_token:
        data['secret_token'] = secret_token
    if allowed_updates is not None:
        data['allowed_updates'] = allowed_updates

    result = _make_request('POST', 'setWebhook', bot_token, data)
    redacted = redact_token(bot_token)
    logger.info(
        f"Telegram webhook set to {webhook_url} (bot: {redacted})"
    )
    return result


def delete_webhook(bot_token: str, drop_pending_updates: bool = False) -> Dict[str, Any]:
    """Remove the Telegram webhook for the bot."""
    if not bot_token:
        raise TelegramConfigError("Telegram bot token is not configured")

    data = {
        'drop_pending_updates': drop_pending_updates,
    }

    result = _make_request('POST', 'deleteWebhook', bot_token, data)
    redacted = redact_token(bot_token)
    logger.info(f"Telegram webhook deleted (bot: {redacted})")
    return result


def send_alert_with_tenant_credentials(
    tenant_id: str,
    tenant_bot_token: str,
    tenant_chat_id: str,
    message: str,
    parse_mode: str = PARSE_MODE_HTML,
) -> Dict[str, Any]:
    """
    Send an alert message to a tenant using their Telegram credentials.
    
    This method is called by the backend when publishing new orders to Heroku.
    It uses the tenant's specific bot token and chat ID to send the message.
    
    Args:
        tenant_id: Tenant identifier (for logging/tracking)
        tenant_bot_token: Telegram bot token belonging to the tenant
        tenant_chat_id: Telegram chat ID for the tenant
        message: Message text to send
        parse_mode: Parse mode for formatting (HTML or Markdown)
    
    Returns:
        Message response from Telegram API
    
    Raises:
        TelegramConfigError: If configuration is missing or invalid
        TelegramAPIError: If the API request fails
    """
    if not tenant_bot_token:
        raise TelegramConfigError(f"Telegram bot token not configured for tenant {tenant_id}")
    if not tenant_chat_id:
        raise TelegramConfigError(f"Telegram chat ID not configured for tenant {tenant_id}")
    if not message:
        raise TelegramConfigError("Message text is required")
    
    data = {
        'chat_id': tenant_chat_id,
        'text': message,
        'parse_mode': parse_mode,
    }
    
    try:
        result = _make_request('POST', 'sendMessage', tenant_bot_token, data)
        redacted = redact_token(tenant_bot_token)
        logger.info(
            f"Alert sent to tenant {tenant_id} "
            f"(chat: {tenant_chat_id}, bot: {redacted})"
        )
        return result
    except TelegramAPIError as exc:
        logger.error(
            f"Failed to send alert to tenant {tenant_id}: {exc.message}"
        )
        raise
