"""Telegram polling loop and update routing."""

import asyncio
import logging
import threading
import time
from typing import Optional

from telegram_bot.client import (
    send_message,
    send_message_with_buttons,
    edit_message_text,
    answer_callback_query,
    _make_request_async,
    TelegramAPIError,
)
from telegram_bot.commands import handle_command
from telegram_bot.callback_handler import handle_callback_query

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


class TelegramBot:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._offset = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Telegram polling thread started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
            logger.info("Telegram polling thread stopped")

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._process_updates()
            except Exception as exc:
                logger.exception(f"Telegram polling error: {exc}")
            time.sleep(POLL_INTERVAL_SECONDS)

    def _process_updates(self) -> None:
        result = asyncio.run(
            _make_request_async(
                'GET',
                'getUpdates',
                self.bot_token,
                {'offset': self._offset + 1, 'timeout': 1},
            )
        )

        for update in result if isinstance(result, list) else []:
            self._offset = max(self._offset, update.get('update_id', 0))
            if 'message' in update and 'text' in update['message']:
                self._handle_message(update['message'])
            elif 'callback_query' in update:
                self._handle_callback(update['callback_query'])

    def _handle_message(self, message: dict) -> None:
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()

        try:
            response = handle_command(self.bot_token, chat_id, text)
            if response:
                if response.get('buttons'):
                    asyncio.run(send_message_with_buttons(
                        bot_token=self.bot_token,
                        chat_id=str(chat_id),
                        text=response['text'],
                        buttons=response['buttons'],
                        parse_mode=response.get('parse_mode', 'HTML'),
                    ))
                else:
                    asyncio.run(send_message(
                        bot_token=self.bot_token,
                        chat_id=str(chat_id),
                        text=response['text'],
                        parse_mode=response.get('parse_mode', 'HTML'),
                    ))
        except TelegramAPIError as exc:
            logger.error(f"Telegram command handler failed: {exc}")

    def _handle_callback(self, callback_query: dict) -> None:
        callback_query_id = callback_query['id']
        data = callback_query.get('data', '')
        chat_id = callback_query['message']['chat']['id']
        message_id = callback_query['message']['message_id']

        try:
            response = handle_callback_query(self.bot_token, data, chat_id, message_id)
            if response and 'text' in response:
                asyncio.run(edit_message_text(
                    bot_token=self.bot_token,
                    chat_id=str(chat_id),
                    message_id=message_id,
                    text=response['text'],
                    buttons=response.get('buttons'),
                ))
            asyncio.run(answer_callback_query(
                bot_token=self.bot_token,
                callback_query_id=callback_query_id,
                text=response.get('notification'),
                show_alert=False,
            ))
        except TelegramAPIError as exc:
            logger.error(f"Telegram callback handler failed: {exc}")
