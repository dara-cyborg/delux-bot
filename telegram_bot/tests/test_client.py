import asyncio
import json
import urllib.error
import urllib.request

import pytest

from telegram_bot.client import (
    send_message,
    send_message_with_buttons,
    edit_message_text,
    answer_callback_query,
    get_bot_info,
    TelegramAPIError,
    TelegramConfigError,
    _make_request,
    _make_request_async,
)
from telegram_bot.config import TELEGRAM_API_BASE_URL


class DummyResponse:
    def __init__(self, data: bytes, code: int = 200):
        self._data = data
        self.code = code

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyHTTPError(urllib.error.HTTPError):
    def __init__(self, url, code, msg, hdrs, fp):
        super().__init__(url, code, msg, hdrs, fp)


@pytest.fixture(autouse=True)
def clear_logging(monkeypatch):
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *args, **kwargs: None)
    yield


def test_make_request_success(monkeypatch):
    result = {'ok': True, 'result': {'message_id': 123}}
    response_bytes = json.dumps(result).encode('utf-8')

    def fake_urlopen(request, timeout=None):
        return DummyResponse(response_bytes)

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)

    response = _make_request('POST', 'sendMessage', 'token:123', {'chat_id': '1', 'text': 'hi'})
    assert response == {'message_id': 123}


def test_make_request_async(monkeypatch):
    result = {'ok': True, 'result': {'message_id': 123}}
    response_bytes = json.dumps(result).encode('utf-8')

    def fake_urlopen(request, timeout=None):
        return DummyResponse(response_bytes)

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)

    response = asyncio.run(_make_request_async('POST', 'sendMessage', 'token:123', {'chat_id': '1', 'text': 'hi'}))
    assert response == {'message_id': 123}


def test_make_request_api_error(monkeypatch):
    response_bytes = json.dumps({'ok': False, 'description': 'Bad request', 'error_code': 400}).encode('utf-8')

    def fake_urlopen(request, timeout=None):
        return DummyResponse(response_bytes)

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)

    with pytest.raises(TelegramAPIError) as exc_info:
        _make_request('POST', 'sendMessage', 'token:123', {'chat_id': '1', 'text': 'hi'})

    assert 'Bad request' in str(exc_info.value)
    assert exc_info.value.error_code == 400


def test_make_request_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise DummyHTTPError(request.full_url, 500, 'Server Error', None, None)

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)

    with pytest.raises(TelegramAPIError) as exc_info:
        _make_request('POST', 'sendMessage', 'token:123', {'chat_id': '1', 'text': 'hi'})

    assert 'HTTP 500' in str(exc_info.value)


def test_make_request_network_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError('timeout')

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)

    with pytest.raises(TelegramAPIError) as exc_info:
        _make_request('POST', 'sendMessage', 'token:123', {'chat_id': '1', 'text': 'hi'})

    assert 'Network error' in str(exc_info.value)


def test_send_message_validates_config():
    with pytest.raises(TelegramConfigError):
        asyncio.run(send_message('', '1', 'hi'))

    with pytest.raises(TelegramConfigError):
        asyncio.run(send_message('token:123', '', 'hi'))


def test_send_message_passes_payload(monkeypatch):
    response_bytes = json.dumps({'ok': True, 'result': {'message_id': 99}}).encode('utf-8')

    def fake_urlopen(request, timeout=None):
        assert request.full_url == f"{TELEGRAM_API_BASE_URL}/bottoken:123/sendMessage"
        body = json.loads(request.data.decode('utf-8'))
        assert body['chat_id'] == '1'
        assert body['text'] == 'hello'
        assert body['parse_mode'] == 'HTML'
        return DummyResponse(response_bytes)

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)

    result = asyncio.run(send_message('token:123', '1', 'hello'))
    assert result['message_id'] == 99


def test_send_message_with_buttons(monkeypatch):
    response_bytes = json.dumps({'ok': True, 'result': {'message_id': 88}}).encode('utf-8')

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data.decode('utf-8'))
        assert body['reply_markup']['inline_keyboard'][0][0]['text'] == 'Click'
        return DummyResponse(response_bytes)

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)

    result = asyncio.run(send_message_with_buttons(
        'token:123',
        '1',
        'hello',
        [[{'text': 'Click', 'callback_data': 'click'}]],
    ))

    assert result['message_id'] == 88


def test_edit_message_text(monkeypatch):
    response_bytes = json.dumps({'ok': True, 'result': {'message_id': 77}}).encode('utf-8')

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data.decode('utf-8'))
        assert body['message_id'] == 5
        assert body['text'] == 'updated'
        return DummyResponse(response_bytes)

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)

    result = asyncio.run(edit_message_text('token:123', '1', 5, 'updated'))
    assert result['message_id'] == 77


def test_answer_callback_query(monkeypatch):
    response_bytes = json.dumps({'ok': True, 'result': True}).encode('utf-8')

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data.decode('utf-8'))
        assert body['callback_query_id'] == 'q1'
        return DummyResponse(response_bytes)

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)

    result = asyncio.run(answer_callback_query('token:123', 'q1', 'Thanks'))
    assert result is True


def test_get_bot_info_validates_token(monkeypatch):
    response_bytes = json.dumps({
        'ok': True,
        'result': {'id': 123, 'is_bot': True, 'username': 'test_bot'},
    }).encode('utf-8')

    def fake_urlopen(request, timeout=None):
        assert request.full_url == f"{TELEGRAM_API_BASE_URL}/bottoken:123/getMe"
        body = json.loads(request.data.decode('utf-8'))
        assert body == {}
        return DummyResponse(response_bytes)

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)

    result = asyncio.run(get_bot_info('token:123'))
    assert result['username'] == 'test_bot'
