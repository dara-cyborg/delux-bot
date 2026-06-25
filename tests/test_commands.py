import pytest

from telegram_bot.commands import handle_command


def test_handle_start_command():
    response = handle_command('token', 123, '/start')

    assert response['parse_mode'] == 'HTML'
    assert 'Welcome to Delux Crawler Telegram Bot' in response['text']


def test_handle_help_command():
    response = handle_command('token', 123, '/help')

    assert response['parse_mode'] == 'HTML'
    assert '/start' in response['text']
    assert '/menu' in response['text']


def test_handle_menu_command_when_no_sessions(monkeypatch):
    monkeypatch.setattr('telegram_bot.commands.get_sessions_paginated', lambda tenant_id, page: [])

    response = handle_command('token', 123, '/menu')

    assert 'No active sessions are available' in response['text']


def test_handle_unknown_command():
    response = handle_command('token', 123, '/unknown')

    assert 'Unknown command' in response['text']
