"""
Audit logging for tenant configuration changes.

Logs all tenant configuration modifications for security and compliance.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def log_tenant_config_change(
    tenant_id: str,
    action: str,
    enabled: bool,
    chat_id: Optional[str] = None,
    remote_addr: Optional[str] = None,
    status: str = "success",
) -> None:
    """
    Log a tenant configuration change.
    
    Args:
        tenant_id: The tenant ID
        action: The action performed (e.g., "enable_webhook", "disable_webhook", "update_config")
        enabled: Whether the configuration is enabled
        chat_id: The Telegram chat ID (if applicable)
        remote_addr: The remote IP address making the request
        status: The status of the operation (success, failure, etc.)
    """
    timestamp = datetime.utcnow().isoformat()
    
    # Log at INFO level for successful changes, WARNING for failures
    level = logging.WARNING if status != "success" else logging.INFO
    
    log_message = (
        f"[AUDIT] Tenant configuration change | "
        f"tenant_id={tenant_id} | "
        f"action={action} | "
        f"enabled={enabled} | "
        f"status={status}"
    )
    
    if chat_id:
        log_message += f" | chat_id={chat_id}"
    
    if remote_addr:
        log_message += f" | remote_addr={remote_addr}"
    
    logger.log(level, log_message)


def log_order_ingestion(
    tenant_id: str,
    session_id: str,
    order_id: str,
    remote_addr: Optional[str] = None,
    status: str = "success",
) -> None:
    """
    Log order ingestion for audit trail.
    
    Args:
        tenant_id: The tenant ID
        session_id: The session ID
        order_id: The order ID
        remote_addr: The remote IP address making the request
        status: The status of the operation
    """
    timestamp = datetime.utcnow().isoformat()
    
    level = logging.WARNING if status != "success" else logging.INFO
    
    log_message = (
        f"[AUDIT] Order ingestion | "
        f"tenant_id={tenant_id} | "
        f"session_id={session_id} | "
        f"order_id={order_id} | "
        f"status={status}"
    )
    
    if remote_addr:
        log_message += f" | remote_addr={remote_addr}"
    
    logger.log(level, log_message)


def log_webhook_event(
    tenant_id: str,
    event_type: str,
    chat_id: Optional[str] = None,
    status: str = "success",
    error: Optional[str] = None,
) -> None:
    """
    Log webhook events for audit trail.
    
    Args:
        tenant_id: The tenant ID
        event_type: Type of event (message, callback_query, etc.)
        chat_id: The Telegram chat ID
        status: The status of the operation
        error: Error message if applicable
    """
    level = logging.WARNING if status != "success" else logging.DEBUG
    
    log_message = (
        f"[AUDIT] Webhook event | "
        f"tenant_id={tenant_id} | "
        f"event_type={event_type} | "
        f"status={status}"
    )
    
    if chat_id:
        log_message += f" | chat_id={chat_id}"
    
    if error:
        log_message += f" | error={error}"
    
    logger.log(level, log_message)
