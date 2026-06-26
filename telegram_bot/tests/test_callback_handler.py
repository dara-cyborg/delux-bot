import pytest

from telegram_bot.callback_handler import handle_callback_query


def test_handle_session_summary(monkeypatch):
    monkeypatch.setattr(
        'telegram_bot.callback_handler.get_session_summary',
        lambda tenant_id, session_id: {
            'session_name': 'Live Session',
            'order_count': 4,
            'customer_count': 2,
            'start_time': '2026-06-25 14:00',
        },
    )

    response = handle_callback_query('token', 'btn_session_summary', 123, 1)

    assert 'Live Session' in response['text']
    assert response['buttons']
    assert 'Session summary' in response['notification']


def test_handle_customer_list(monkeypatch):
    monkeypatch.setattr(
        'telegram_bot.callback_handler.get_customers_for_session',
        lambda tenant_id, session_id: [
            {'name': 'Jane', 'order_count': 2},
        ],
    )

    response = handle_callback_query('token', 'btn_customer_list', 123, 1)

    assert 'Customers Today' in response['text']
    assert response['buttons']
    assert 'Customer list updated' in response['notification']


def test_handle_customer_orders(monkeypatch):
    monkeypatch.setattr(
        'telegram_bot.callback_handler.get_customers_for_session',
        lambda tenant_id, session_id: [
            {'name': 'Jane', 'order_count': 1},
        ],
    )
    monkeypatch.setattr(
        'telegram_bot.callback_handler.get_orders_for_customer',
        lambda tenant_id, session_id, customer_name: [
            {'comment': '2 pcs', 'collected_at': '2026-06-25 15:00'},
        ],
    )

    response = handle_callback_query('token', 'btn_customer_orders', 123, 1)

    assert 'Top customer orders' in response['text']
    assert response['buttons']
    assert 'Order details shown' in response['notification']


def test_handle_close_menu():
    response = handle_callback_query('token', 'btn_close_menu', 123, 1)

    assert 'Menu closed' in response['text']
    assert response['buttons'] == []
    assert 'Menu closed' in response['notification']


def test_handle_customer_list_paginates_results(monkeypatch):
    customers = [{'name': f'Customer {i}', 'order_count': i} for i in range(25)]
    monkeypatch.setattr(
        'telegram_bot.callback_handler.get_customers_for_session',
        lambda tenant_id, session_id: customers,
    )

    response = handle_callback_query('token', 'btn_custlist|session-1|1', 123, 1)

    assert 'Showing 11-20 of 25' in response['text']
    assert 'Customer 11' in response['text']
    assert 'Customer 19' in response['text']
    assert 'Customer 9' not in response['text']
    assert 'Customer 20' not in response['text']
    assert any(
        button['callback_data'] == 'btn_custlist|session-1|0'
        for row in response['buttons']
        for button in row
    )
    assert any(
        button['callback_data'] == 'btn_custlist|session-1|2'
        for row in response['buttons']
        for button in row
    )


def test_handle_order_list_paginates_results_and_uses_large_limit(monkeypatch):
    calls = {}

    def fake_get_session_orders(tenant_id, session_id, limit=None):
        calls['limit'] = limit
        return [
            {'commenter': f'User {i}', 'comment': f'Comment {i}', 'collected_at': '2026-06-25 15:00'}
            for i in range(25)
        ]

    monkeypatch.setattr('telegram_bot.storage.get_session_orders', fake_get_session_orders)
    monkeypatch.setattr('telegram_bot.storage.get_tenant_orders_by_date', lambda *args, **kwargs: [])

    response = handle_callback_query('token', 'btn_ordlist|session-1|1', 123, 1)

    assert calls['limit'] == 200
    assert 'Showing 11-20 of 25' in response['text']
    assert 'User 11' in response['text']
    assert 'User 19' in response['text']
    assert 'User 9' not in response['text']
    assert 'User 20' not in response['text']
