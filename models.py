"""
Pydantic models for Telegram integration.

Defines data structures for:
- Configuration management
- Request/response payloads
- Callback state management
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TelegramConfig(BaseModel):
    """Telegram configuration settings."""
    enabled: bool = False
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    message_template: Optional[str] = None

    class Config:
        """Pydantic config."""
        use_enum_values = True


class TelegramOrderPayload(BaseModel):
    """Request payload for sending an order to Telegram."""
    commenter: str = Field(..., description="Name of the commenter/customer")
    comment: str = Field(..., description="Order comment text")
    comment_id: str = Field(..., description="Unique comment ID")
    collected_at: str = Field(..., description="Timestamp when comment was collected")
    profile_url: Optional[str] = Field(None, description="Facebook profile URL")

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "commenter": "John Doe",
                "comment": "2 pcs red shirt",
                "comment_id": "123456",
                "collected_at": "2026-06-25 14:32",
                "profile_url": "https://facebook.com/john.doe",
            }
        }


class TelegramSendResponse(BaseModel):
    """Response from sending a message to Telegram."""
    success: bool
    message: Optional[str] = None
    telegram_message_id: Optional[int] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example_success": {
                "success": True,
                "message": "Order sent to Telegram",
                "telegram_message_id": 12345,
            },
            "example_error": {
                "success": False,
                "error": "Telegram not configured",
                "error_code": "TELEGRAM_NOT_CONFIGURED",
            },
        }


class TelegramCallbackState(BaseModel):
    """State for menu navigation and pagination."""
    callback_id: str
    action: str  # "session_summary", "customer_list", "next_page", "prev_page", etc.
    page: int = 0
    selected_customer: Optional[str] = None
    selected_session_id: Optional[str] = None

    class Config:
        """Pydantic config."""
        use_enum_values = True


class TelegramAPIError(Exception):
    """Exception for Telegram API errors."""
    def __init__(self, message: str, error_code: Optional[str] = None):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class TelegramConfigError(Exception):
    """Exception for configuration errors."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
