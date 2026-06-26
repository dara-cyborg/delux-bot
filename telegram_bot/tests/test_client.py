import asyncio
import json

import httpx
import pytest

from telegram_bot.client import (
    send_message,
    send_message_with_buttons,
    edit_message_text,
    answer_callback_query,
    get_bot_info,
    TelegramAPIError,
    TelegramConfigError,
    _make_request_async,
)
from telegram_bot.config import TELEGRAM_API_BASE_URL


class DummyResponse:
    def __init__(self, data: bytes, code: int = 200):
        self._data = data
        self.status_code = code
        self.text = data.decode('utf-8')

    def read(self):
        return self._data

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if 400 <= self.status_code:
            raise httpx.HTTPStatusError(
                message=f"HTTP error {self.status_code}",
                request=None,
                response=self,
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyAsyncClient:
    def __init__(self, response=None, error=None, **kwargs):
        self._response = response
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, json=None):
        if self._error:
            raise self._error
        return self._response


@pytest.fixture(autouse=True)
def clear_httpx(monkeypatch):
    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', DummyAsyncClient)
    yield


def test_make_request_success(monkeypatch):
    result = {'ok': True, 'result': {'message_id': 123}}
    response_bytes = json.dumps(result).encode('utf-8')
    response = DummyResponse(response_bytes)

    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(response=response)

    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', fake_async_client)

    actual = asyncio.run(_make_request_async('POST', 'sendMessage', 'token:123', {'chat_id': '1', 'text': 'hi'}))
    assert actual == {'message_id': 123}


def test_make_request_async(monkeypatch):
    result = {'ok': True, 'result': {'message_id': 123}}
    response_bytes = json.dumps(result).encode('utf-8')

    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(response=DummyResponse(response_bytes))

    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', fake_async_client)

    response = asyncio.run(_make_request_async('POST', 'sendMessage', 'token:123', {'chat_id': '1', 'text': 'hi'}))
    assert response == {'message_id': 123}


def test_make_request_api_error(monkeypatch):
    response_bytes = json.dumps({'ok': False, 'description': 'Bad request', 'error_code': 400}).encode('utf-8')
    response = DummyResponse(response_bytes)

    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(response=response)

    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', fake_async_client)

    with pytest.raises(TelegramAPIError) as exc_info:
        asyncio.run(_make_request_async('POST', 'sendMessage', 'token:123', {'chat_id': '1', 'text': 'hi'}))

    assert 'Bad request' in str(exc_info.value)
    assert exc_info.value.error_code == 400


def test_make_request_http_error(monkeypatch):
    response_bytes = json.dumps({'ok': False, 'description': 'Server Error', 'error_code': 500}).encode('utf-8')
    response = DummyResponse(response_bytes, code=500)

    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(response=response)

    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', fake_async_client)

    with pytest.raises(TelegramAPIError) as exc_info:
        asyncio.run(_make_request_async('POST', 'sendMessage', 'token:123', {'chat_id': '1', 'text': 'hi'}))

    assert 'HTTP 500' in str(exc_info.value)


def test_make_request_network_error(monkeypatch):
    error = httpx.RequestError('timeout')

    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(error=error)

    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', fake_async_client)

    with pytest.raises(TelegramAPIError) as exc_info:
        asyncio.run(_make_request_async('POST', 'sendMessage', 'token:123', {'chat_id': '1', 'text': 'hi'}))

    assert 'Network error' in str(exc_info.value)


def test_send_message_validates_config():
    with pytest.raises(TelegramConfigError):
        asyncio.run(send_message('', '1', 'hi'))

    with pytest.raises(TelegramConfigError):
        asyncio.run(send_message('token:123', '', 'hi'))


def test_send_message_passes_payload(monkeypatch):
    response_bytes = json.dumps({'ok': True, 'result': {'message_id': 99}}).encode('utf-8')

    def fake_async_client(*args, **kwargs):
        class FakeAsyncClient(DummyAsyncClient):
            async def request(self, method, url, json=None):
                assert method == 'POST'
                assert url == f"{TELEGRAM_API_BASE_URL}/bottoken:123/sendMessage"
                assert json['chat_id'] == '1'
                assert json['text'] == 'hello'
                assert json['parse_mode'] == 'HTML'
                return DummyResponse(response_bytes)

        return FakeAsyncClient()

    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', fake_async_client)

    result = asyncio.run(send_message('token:123', '1', 'hello'))
    assert result['message_id'] == 99


def test_send_message_with_buttons(monkeypatch):
    response_bytes = json.dumps({'ok': True, 'result': {'message_id': 88}}).encode('utf-8')

    def fake_async_client(*args, **kwargs):
        class FakeAsyncClient(DummyAsyncClient):
            async def request(self, method, url, json=None):
                body = json
                assert body['reply_markup']['inline_keyboard'][0][0]['text'] == 'Click'
                return DummyResponse(response_bytes)

        return FakeAsyncClient()

    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', fake_async_client)

    result = asyncio.run(send_message_with_buttons(
        'token:123',
        '1',
        'hello',
        [[{'text': 'Click', 'callback_data': 'click'}]],
    ))

    assert result['message_id'] == 88


def test_edit_message_text(monkeypatch):
    response_bytes = json.dumps({'ok': True, 'result': {'message_id': 77}}).encode('utf-8')

    def fake_async_client(*args, **kwargs):
        class FakeAsyncClient(DummyAsyncClient):
            async def request(self, method, url, json=None):
                assert json['message_id'] == 5
                assert json['text'] == 'updated'
                return DummyResponse(response_bytes)

        return FakeAsyncClient()

    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', fake_async_client)

    result = asyncio.run(edit_message_text('token:123', '1', 5, 'updated'))
    assert result['message_id'] == 77


def test_answer_callback_query(monkeypatch):
    response_bytes = json.dumps({'ok': True, 'result': True}).encode('utf-8')

    def fake_async_client(*args, **kwargs):
        class FakeAsyncClient(DummyAsyncClient):
            async def request(self, method, url, json=None):
                assert json['callback_query_id'] == 'q1'
                return DummyResponse(response_bytes)

        return FakeAsyncClient()

    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', fake_async_client)

    result = asyncio.run(answer_callback_query('token:123', 'q1', 'Thanks'))
    assert result is True


def test_get_bot_info_validates_token(monkeypatch):
    response_bytes = json.dumps({
        'ok': True,
        'result': {'id': 123, 'is_bot': True, 'username': 'test_bot'},
    }).encode('utf-8')

    def fake_async_client(*args, **kwargs):
        class FakeAsyncClient(DummyAsyncClient):
            async def request(self, method, url, json=None):
                assert url == f"{TELEGRAM_API_BASE_URL}/bottoken:123/getMe"
                assert json == {}
                return DummyResponse(response_bytes)

        return FakeAsyncClient()

    monkeypatch.setattr('telegram_bot.client.httpx.AsyncClient', fake_async_client)

    result = asyncio.run(get_bot_info('token:123'))
    assert result['username'] == 'test_bot'
