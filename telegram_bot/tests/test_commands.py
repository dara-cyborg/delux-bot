import pytest

from telegram_bot.commands import handle_command


def test_handle_start_command():
    response = handle_command('token', 123, '/start')

    assert response['parse_mode'] == 'HTML'
    assert 'DELUX Bot' in response['text']


def test_handle_help_command():
    response = handle_command('token', 123, '/help')

    assert response['parse_mode'] == 'HTML'
    assert '/start' in response['text']
    assert '/menu' in response['text']


def test_handle_menu_command_when_no_sessions(monkeypatch):
    monkeypatch.setattr('telegram_bot.commands.get_sessions_paginated', lambda tenant_id, page, page_size=10: [])

    response = handle_command('token', 123, '/menu')

    assert 'No active sessions are available' in response['text']


def test_handle_unknown_command():
    response = handle_command('token', 123, '/unknown')

    assert 'Unknown command' in response['text']


def test_handle_menu_command_uses_single_paginated_call_for_next_page(monkeypatch):
    calls = []

    def fake_get_sessions_paginated(tenant_id, page, page_size=10):
        calls.append((page, page_size))
        if page == 0:
            return [{
                'session_id': 's1',
                'session_name': 'Session 1',
                'session_date': '2026-06-26',
                'order_count': 1,
                'customer_count': 1,
                'session_state': 'active',
            }]
        return []

    monkeypatch.setattr('telegram_bot.commands.get_sessions_paginated', fake_get_sessions_paginated)

    response = handle_command('token', 123, '/menu')

    assert calls == [(0, 6)]
    assert response['parse_mode'] == 'HTML'
    assert 'Session 1' in response['text']
