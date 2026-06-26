import asyncio
import json

import pytest
from fastapi import HTTPException

import server
from telegram_bot import storage
from telegram_bot import tenant_store
from telegram_bot.commands import get_sessions_menu, get_today_orders_summary
from telegram_bot.session_manager import get_customers_for_session, get_orders_for_customer


@pytest.fixture()
def isolated_tenant_store(tmp_path, monkeypatch):
    db_path = tmp_path / "tenant_data.db"
    monkeypatch.setattr(tenant_store, "DB_PATH", db_path)
    storage.reset_storage_provider()
    asyncio.run(server.on_startup())
    yield db_path
    storage.reset_storage_provider()


def test_local_server_can_register_config_send_order_and_read_tenant_data(
    isolated_tenant_store,
    monkeypatch,
):
    monkeypatch.setenv("X_ACCESS_TOKEN", "shared-secret-token")
    monkeypatch.setattr(server, "get_bot_info", lambda bot_token: {"username": "tenant_bot"})

    sent_alerts = []

    def fake_send_alert_with_tenant_credentials(**kwargs):
        sent_alerts.append(kwargs)
        return {"message_id": 1001}

    monkeypatch.setattr(
        server,
        "send_alert_with_tenant_credentials",
        fake_send_alert_with_tenant_credentials,
    )

    config_response = asyncio.run(
        server.update_tenant_telegram_config(
            tenant_id="tenant-a",
            config=server.TelegramConfigRequest(
                enabled=True,
                telegram_bot_token="123:test-token",
                telegram_chat_id="456",
            ),
            x_access_token="shared-secret-token",
        )
    )

    assert config_response.status_code == 200
    assert json.loads(config_response.body)["telegram_config"]["telegram_chat_id"] == "456"

    order_response = asyncio.run(
        server.create_tenant_order(
            tenant_id="tenant-a",
            order=server.OrderCreateRequest(
                session_id="live-2026-06-26-1",
                commenter="Dara",
                comment="2 red shirts",
                comment_id="fb-comment-1",
                collected_at="2026-06-26 10:15:00",
                profile_url="https://facebook.example/dara",
                order_date="2026-06-26",
            ),
            x_access_token="shared-secret-token",
        )
    )

    assert order_response.status_code == 200
    saved_order = json.loads(order_response.body)["order"]
    assert saved_order["tenant_id"] == "tenant-a"
    assert saved_order["session_id"] == "live-2026-06-26-1"
    assert sent_alerts == [
        {
            "tenant_id": "tenant-a",
            "tenant_bot_token": "123:test-token",
            "tenant_chat_id": "456",
            "message": sent_alerts[0]["message"],
        }
    ]
    assert "Dara" in sent_alerts[0]["message"]
    assert "2 red shirts" in sent_alerts[0]["message"]

    menu = get_sessions_menu("tenant-a")
    assert "live-2026-06-26-1" in menu["text"]
    assert "Orders: 1" in menu["text"]
    assert "Customers: 1" in menu["text"]

    today = get_today_orders_summary("tenant-a")
    assert "Dara" in today["text"]
    assert "2 red shirts" in today["text"]

    customers = get_customers_for_session("tenant-a", "live-2026-06-26-1")
    assert customers == [
        {
            "name": "Dara",
            "order_count": 1,
            "last_comment": "2 red shirts",
            "collected_at": "2026-06-26 10:15:00",
        }
    ]

    customer_orders = get_orders_for_customer("tenant-a", "live-2026-06-26-1", "Dara")
    assert len(customer_orders) == 1
    assert customer_orders[0]["comment"] == "2 red shirts"


def test_order_endpoint_rejects_missing_or_wrong_local_server_token(
    isolated_tenant_store,
    monkeypatch,
):
    monkeypatch.setenv("X_ACCESS_TOKEN", "shared-secret-token")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            server.create_tenant_order(
                tenant_id="tenant-a",
                order=server.OrderCreateRequest(
                    session_id="live-1",
                    commenter="Dara",
                    comment="1 item",
                ),
                x_access_token="wrong-token",
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Forbidden"


def test_orders_are_isolated_between_tenants(isolated_tenant_store, monkeypatch):
    monkeypatch.setenv("X_ACCESS_TOKEN", "shared-secret-token")
    monkeypatch.setattr(server, "send_alert_with_tenant_credentials", lambda **kwargs: {})

    for tenant_id, commenter in [("tenant-a", "Dara"), ("tenant-b", "Sokha")]:
        asyncio.run(
            server.create_tenant_order(
                tenant_id=tenant_id,
                order=server.OrderCreateRequest(
                    session_id="same-live-session-id",
                    commenter=commenter,
                    comment=f"{commenter} order",
                    order_date="2026-06-26",
                ),
                x_access_token="shared-secret-token",
            )
        )

    tenant_a_menu = get_sessions_menu("tenant-a")
    tenant_b_menu = get_sessions_menu("tenant-b")
    assert "Dara" in get_today_orders_summary("tenant-a")["text"]
    assert "Sokha" not in get_today_orders_summary("tenant-a")["text"]
    assert "Sokha" in get_today_orders_summary("tenant-b")["text"]
    assert "Orders: 1" in tenant_a_menu["text"]
    assert "Orders: 1" in tenant_b_menu["text"]
