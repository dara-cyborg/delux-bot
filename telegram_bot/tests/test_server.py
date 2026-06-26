import asyncio
import json

import pytest
from fastapi import HTTPException

import server


def test_tenant_config_returns_clear_error_when_access_token_missing(monkeypatch):
    monkeypatch.delenv("X_ACCESS_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            server.update_tenant_telegram_config(
                tenant_id="test-tenant",
                config=server.TelegramConfigRequest(
                    enabled=True,
                    telegram_bot_token="123:test-token",
                    telegram_chat_id="456",
                ),
                x_access_token="crawler-token",
            )
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "API access token is not configured"


def test_tenant_config_rejects_wrong_access_token(monkeypatch):
    monkeypatch.setenv("X_ACCESS_TOKEN", "expected-token")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            server.update_tenant_telegram_config(
                tenant_id="test-tenant",
                config=server.TelegramConfigRequest(
                    enabled=True,
                    telegram_bot_token="123:test-token",
                    telegram_chat_id="456",
                ),
                x_access_token="wrong-token",
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Forbidden"


def test_tenant_config_saves_with_matching_access_token(monkeypatch):
    monkeypatch.setenv("X_ACCESS_TOKEN", "expected-token")

    saved_config = {
        "tenant_id": "test-tenant",
        "telegram_enabled": True,
        "telegram_bot_token": "123:test-token",
        "telegram_chat_id": "456",
        "telegram_message_template": None,
    }
    monkeypatch.setattr(server, "get_bot_info", lambda bot_token: {"username": "test_bot"})
    monkeypatch.setattr(server, "save_tenant_telegram_config", lambda **kwargs: saved_config)

    response = asyncio.run(
        server.update_tenant_telegram_config(
            tenant_id="test-tenant",
            config=server.TelegramConfigRequest(
                enabled=True,
                telegram_bot_token="123:test-token",
                telegram_chat_id="456",
            ),
            x_access_token="expected-token",
        )
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "ok": True,
        "tenant_id": "test-tenant",
        "telegram_config": saved_config,
    }


def test_tenant_config_rejects_invalid_telegram_bot_token(monkeypatch):
    monkeypatch.setenv("X_ACCESS_TOKEN", "expected-token")
    monkeypatch.setattr(
        server,
        "get_bot_info",
        lambda bot_token: (_ for _ in ()).throw(server.TelegramAPIError("Unauthorized", 401)),
    )

    def fail_save(**kwargs):
        raise AssertionError("invalid Telegram config should not be saved")

    monkeypatch.setattr(server, "save_tenant_telegram_config", fail_save)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            server.update_tenant_telegram_config(
                tenant_id="test-tenant",
                config=server.TelegramConfigRequest(
                    enabled=True,
                    telegram_bot_token="bad-token",
                    telegram_chat_id="456",
                ),
                x_access_token="expected-token",
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid Telegram bot token"
