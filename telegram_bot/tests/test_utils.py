from telegram_bot.utils import build_callback_data, format_session_label


def test_build_callback_data_with_simple_parts():
    assert build_callback_data('btn_session', 'session-123') == 'btn_session|session-123'


def test_build_callback_data_truncates_utf8():
    long_name = 'ลูกค้า' * 20
    callback = build_callback_data('btn_cust', 'session-123', long_name)
    assert len(callback.encode('utf-8')) <= 64
    assert callback.startswith('btn_cust|session-123|')


def test_format_session_label_from_session_id():
    assert format_session_label('', '2026-06-26') == '26-Jun-2026'
    assert format_session_label('current', 'current') == 'current'
    assert format_session_label('live-abc', 'live-abc') == 'live-abc'
