import asyncio
import json

import pytest
from fastapi import HTTPException

import server


def test_tenant_config_returns_clear_error_when_access_token_missing(monkeypatch):
    monkeypatch.delenv("X_ACCESS_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            server._update_tenant_telegram_config_internal(
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
            server._update_tenant_telegram_config_internal(
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
    monkeypatch.setenv("X_ACCESS_TOKEN", "expected-token")

    saved_config = {
        "tenant_id": "test-tenant",
        "telegram_enabled": True,
        "telegram_bot_token": "123:test-token",
        "telegram_chat_id": "456",
        "telegram_message_template": None,
    }
    monkeypatch.setattr(server, "get_or_create_tenant_webhook_secret", lambda tenant_id: "webhook-secret")
    monkeypatch.setattr(server, "save_tenant_telegram_config", lambda **kwargs: saved_config)

    response = asyncio.run(
        server._update_tenant_telegram_config_internal(
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
    body = json.loads(response.body)
    assert body["ok"] is True
    assert body["tenant_id"] == "test-tenant"
    assert body["telegram_config"]["tenant_id"] == "test-tenant"
    assert body["telegram_config"]["telegram_enabled"] == True
    assert body["telegram_config"]["telegram_chat_id"] == "456"
    assert "webhook_url" in body
    assert "webhook_secret" in body


def test_tenant_config_rejects_invalid_telegram_bot_token(monkeypatch):
    monkeypatch.setenv("X_ACCESS_TOKEN", "expected-token")
    def fail_save(**kwargs):
        raise AssertionError("invalid Telegram config should not be saved")

    monkeypatch.setattr(server, "save_tenant_telegram_config", fail_save)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            server._update_tenant_telegram_config_internal(
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
    assert exc_info.value.detail == "Invalid Telegram bot token format"


def test_telegram_webhook_returns_immediately_and_schedules_background_processing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "shared-secret")
    monkeypatch.setattr(
        server,
        "_get_bot_token",
        lambda: (_ for _ in ()).throw(AssertionError("inline processing should not run")),
    )

    scheduled = []

    class DummyBackgroundTasks:
        def add_task(self, func, *args, **kwargs):
            scheduled.append((func, args, kwargs))

    response = asyncio.run(
        server.telegram_webhook(
            secret="shared-secret",
            background_tasks=DummyBackgroundTasks(),
            update={"message": {"chat": {"id": 1}, "text": "hello"}},
        )
    )

    assert response.status_code == 200
    assert len(scheduled) == 1
    assert scheduled[0][0] is server._process_webhook_update
