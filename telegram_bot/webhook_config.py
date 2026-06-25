"""
Telegram webhook secret management with encryption.
Stores webhook secret in encrypted format using the same secure_store pattern as license.json.
"""

import secrets
import json
import sys
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _get_webhook_config_path() -> Path:
    """Get path to encrypted webhook config file"""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32" or sys.platform == "cygwin":
        import os
        local_app_data = os.getenv("LOCALAPPDATA", "").strip()
        if local_app_data:
            base = Path(local_app_data)
        else:
            base = Path.home() / "AppData" / "Local"
    else:
        # Linux/other: use home directory
        base = Path.home() / ".local" / "share"

    config_dir = base / "DeluxCrawler"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "telegram-webhook.json"


def generate_webhook_secret(length: int = 32) -> str:
    """
    Generate a cryptographically secure random webhook secret.
    Uses secrets.token_urlsafe for URL-safe encoding.
    """
    return secrets.token_urlsafe(length)


def save_webhook_secret(secret: str) -> bool:
    """
    Save webhook secret in encrypted format.
    Uses the same secure storage pattern as license.json.
    
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        from licensing.secure_store import encrypt_json_payload

        config_path = _get_webhook_config_path()
        data = {"webhook_secret": secret}
        
        # Encrypt using secure_store pattern
        encrypted = encrypt_json_payload(data)
        
        # Write to file
        config_path.write_text(json.dumps(encrypted, indent=2), encoding="utf-8")
        logger.info(f"Webhook secret saved to {config_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save webhook secret: {e}")
        return False


def load_webhook_secret() -> Optional[str]:
    """
    Load and decrypt webhook secret from storage.
    
    Returns:
        The webhook secret, or None if not found/invalid
    """
    try:
        from licensing.secure_store import decrypt_json_payload

        config_path = _get_webhook_config_path()
        if not config_path.exists():
            logger.warning("Webhook config file not found - no secret set")
            return None

        # Read encrypted file
        encrypted_data = json.loads(config_path.read_text(encoding="utf-8"))
        
        # Decrypt
        decrypted = decrypt_json_payload(encrypted_data)
        secret = decrypted.get("webhook_secret")
        
        if not secret:
            logger.warning("Webhook secret not found in config")
            return None

        return secret
    except Exception as e:
        logger.error(f"Failed to load webhook secret: {e}")
        return None


def has_webhook_secret() -> bool:
    """Check if webhook secret is configured"""
    return load_webhook_secret() is not None


def delete_webhook_secret() -> bool:
    """Delete the webhook secret from storage"""
    try:
        config_path = _get_webhook_config_path()
        if config_path.exists():
            config_path.unlink()
            logger.info("Webhook secret deleted")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to delete webhook secret: {e}")
        return False


def rotate_webhook_secret() -> Optional[str]:
    """
    Generate and save a new webhook secret, replacing the old one.
    
    Returns:
        The new secret, or None if rotation failed
    """
    try:
        new_secret = generate_webhook_secret()
        if save_webhook_secret(new_secret):
            logger.info("Webhook secret rotated successfully")
            return new_secret
        return None
    except Exception as e:
        logger.error(f"Failed to rotate webhook secret: {e}")
        return None
