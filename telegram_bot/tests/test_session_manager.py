from telegram_bot.local_orders import order_history_by_commenter
from telegram_bot.session_manager import (
    get_sessions_paginated,
    get_session_summary,
    get_customers_for_session,
    get_orders_for_customer,
)


def test_get_sessions_paginated_empty():
    order_history_by_commenter.clear()

    sessions = get_sessions_paginated('', 0)
    assert isinstance(sessions, list)
    assert len(sessions) == 1
    assert sessions[0]['session_id'] == 'current'


def test_get_session_summary_current():
    order_history_by_commenter.clear()
    order_history_by_commenter['jane'] = {
        'commenter': 'Jane',
        'print_count': 2,
        'comments': [
            {'comment': 'One', 'collected_at': '2026-06-25 15:00', 'comment_id': '1'},
            {'comment': 'Two', 'collected_at': '2026-06-25 15:02', 'comment_id': '2'},
        ],
    }

    summary = get_session_summary('test-tenant', 'current')
    assert summary['order_count'] == 2
    assert summary['customer_count'] == 1


def test_get_customers_for_session_sorted():
    order_history_by_commenter.clear()
    order_history_by_commenter['jane'] = {
        'commenter': 'Jane',
        'print_count': 2,
        'comments': [{'comment': 'One'}],
    }
    order_history_by_commenter['bob'] = {
        'commenter': 'Bob',
        'print_count': 3,
        'comments': [{'comment': 'Two'}],
    }

    customers = get_customers_for_session('test-tenant', 'current')
    assert customers[0]['name'] == 'Bob'
    assert customers[1]['name'] == 'Jane'


def test_get_orders_for_customer():
    order_history_by_commenter.clear()
    order_history_by_commenter['jane'] = {
        'commenter': 'Jane',
        'print_count': 1,
        'comments': [
            {'comment': 'One', 'collected_at': '2026-06-25 15:00', 'comment_id': '1', 'printed_at': '15:01'},
        ],
    }

    orders_list = get_orders_for_customer('test-tenant', 'current', 'Jane')
    assert len(orders_list) == 1
    assert orders_list[0]['comment'] == 'One'


def test_get_sessions_paginated_uses_batch_customer_counts(monkeypatch):
    sessions = [{
        'session_id': 's1',
        'session_name': 'Session 1',
        'session_date': '2026-06-26',
        'order_count': 2,
        'session_state': 'active',
    }]

    monkeypatch.setattr('telegram_bot.session_manager.storage_get_sessions_paginated', lambda tenant_id, page, page_size=10: sessions)
    monkeypatch.setattr('telegram_bot.session_manager.storage_get_session_customer_counts', lambda tenant_id, session_ids: {'s1': 2})
    monkeypatch.setattr('telegram_bot.session_manager.storage_get_session_orders', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('session orders should not be queried per session')))

    results = get_sessions_paginated('tenant-1', 0, page_size=5)

    assert results[0]['customer_count'] == 2
    assert results[0]['session_id'] == 's1'
