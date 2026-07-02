from datetime import datetime
from telegram_bot.message_builder import build_session_summary, build_menu_text, escape_html
from telegram_bot.session_manager import get_sessions_paginated
from telegram_bot.utils import build_callback_data
from telegram_bot.config import (
    BUTTON_TODAY_SUMMARY,
    BUTTON_CUSTOMER_COUNT,
    BUTTON_CUSTOMER_ORDERS,
    BUTTON_CLOSE_MENU,
)


pending_note_requests: dict[str, str] = {}


def get_pending_note_request(chat_id: int | str) -> str | None:
    return pending_note_requests.get(str(chat_id))


def set_pending_note_request(chat_id: int | str, order_id: str) -> None:
    pending_note_requests[str(chat_id)] = order_id


def clear_pending_note_request(chat_id: int | str) -> None:
    pending_note_requests.pop(str(chat_id), None)


def get_sessions_menu(tenant_id: str, page: int = 0) -> dict:
    """Get the paginated sessions menu for a tenant."""
    page_size = 5
    fetched_sessions = get_sessions_paginated(tenant_id, page=page, page_size=page_size + 1)
    if not fetched_sessions:
        return {
            'text': '<b>No active sessions are available.</b>\nAdd an order by printing a comment first.',
            'parse_mode': 'HTML',
        }

    has_next = len(fetched_sessions) > page_size
    sessions = fetched_sessions[:page_size] if has_next else fetched_sessions

    text_lines = [
        f"📋 <b>ការឡាយទាំងអស់ (Page {page + 1}):</b>\n"
    ]
    buttons = []
    
    for s in sessions:
        name = s['session_name'] or s['session_id']
        text_lines.append(
            f"📅 <b>{name}</b>\n"
            f"   Orders: {s['order_count']} | Customers: {s['customer_count']}\n"
        )
        session_date = s.get('session_date')
        if session_date:
            button_data = build_callback_data('btn_session', s['session_id'], session_date)
        else:
            button_data = build_callback_data('btn_session', s['session_id'])

        buttons.append([{
            "text": f"📅 {name[:25]}",
            "callback_data": button_data
        }])
    
    # Add pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append({"text": "◀️ Prev", "callback_data": build_callback_data('btn_sessions_page', str(page - 1))})
    if has_next:
        nav_buttons.append({"text": "Next ▶️", "callback_data": build_callback_data('btn_sessions_page', str(page + 1))})
        
    if nav_buttons:
        buttons.append(nav_buttons)
        
    buttons.append([{"text": "❌ Close Menu", "callback_data": "btn_close_menu"}])
    
    return {
        'text': "\n".join(text_lines),
        'buttons': buttons,
        'parse_mode': 'HTML',
    }


def get_today_orders_summary(tenant_id: str) -> dict:
    """Return today's orders summary."""
    from telegram_bot.storage import get_tenant_orders_by_date
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        orders = get_tenant_orders_by_date(tenant_id, today_str, limit=50)
    except Exception:
        orders = []
        
    if not orders:
        return {
            'text': f"📅 <b>Today's Orders ({today_str})</b>\n\n<i>No orders collected today.</i>",
            'parse_mode': 'HTML',
        }
        
    text_lines = [
        f"📅 <b>Today's Orders ({today_str})</b>",
        f"Total: {len(orders)} order(s)\n"
    ]
    
    for i, o in enumerate(orders[:15], 1):
        commenter = o['commenter']
        comment = o['comment']
        time_str = o['collected_at'].split(" ")[-1] if " " in o['collected_at'] else o['collected_at']
        text_lines.append(f"{i}. 👤 <b>{commenter}</b>: {comment} (at {time_str})")
        
    if len(orders) > 15:
        text_lines.append(f"\n<i>...and {len(orders) - 15} more order(s).</i>")
        
    buttons = [
        [{"text": "🔄 Refresh", "callback_data": build_callback_data('btn_ordlist', 'today')}],
        [{"text": "❌ Close Menu", "callback_data": "btn_close_menu"}]
    ]
    
    return {
        'text': "\n".join(text_lines),
        'buttons': buttons,
        'parse_mode': 'HTML',
    }


def handle_command(bot_token: str, chat_id: int, text: str, tenant_id: str = "") -> dict:
    """Handle text commands from user."""
    normalized = text.strip()
    lower = normalized.lower()

    from telegram_bot.tenant_store import get_order, update_order

    if tenant_id:
        pending_order_id = get_pending_note_request(chat_id)
        if pending_order_id and not lower.startswith('/'):
            note = normalized.strip()
            if not note:
                return {
                    'text': '<b>Please send a non-empty note.</b>\nThe note must be 50 characters or less.',
                    'parse_mode': 'HTML',
                }
            if len(note) > 50:
                return {
                    'text': '<b>Note too long.</b> Please send a note with 50 characters or less.',
                    'parse_mode': 'HTML',
                }

            order = get_order(tenant_id, pending_order_id)
            clear_pending_note_request(chat_id)
            if not order:
                return {
                    'text': '<b>Could not find the order to attach the note.</b>',
                    'parse_mode': 'HTML',
                }

            update_order(
                tenant_id,
                pending_order_id,
                customer_note=note,
            )
            return {
                'text': (
                    f"<b>Note saved for {escape_html(order['commenter'])}.</b>\n"
                    f"Note: {escape_html(note)}"
                ),
                'parse_mode': 'HTML',
            }

    normalized = lower

    if normalized == '/start':
        welcome = (
            '<b>DELUX Bot - មើលទិន្នន័យលក់</b>\n\n'
            'ប្រើ /menu ដើម្បីមើល order.\n\n'
        )
        menu_res = get_sessions_menu(tenant_id, 0)
        menu_res['text'] = welcome + menu_res['text']
        return menu_res

    if normalized == '/help':
        return {
            'text': (
                '<b>ជំនួយការប្រើប្រាស់</b>\n\n'
                '/start — Welcome message and session menu\n'
                '/help — បង្ហាញតារាងជំនួយ\n'
                '/menu — មើល order នៃការឡាយ\n'
                '/sessions — មើលទិន្នន័យចាស់ៗ\n'
                '/today — មើល order ថ្ងៃនេះ'
            ),
            'parse_mode': 'HTML',
        }

    if normalized in ('/menu', '/sessions'):
        return get_sessions_menu(tenant_id, 0)

    if normalized == '/today':
        return get_today_orders_summary(tenant_id)

    return {
        'text': 'Unknown command. Use /help for available commands.',
        'parse_mode': 'HTML',
    }

