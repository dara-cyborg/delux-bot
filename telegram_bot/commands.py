from datetime import datetime
from telegram_bot.message_builder import build_session_summary, build_menu_text
from telegram_bot.session_manager import get_sessions_paginated
from telegram_bot.utils import build_callback_data
from telegram_bot.config import (
    BUTTON_TODAY_SUMMARY,
    BUTTON_CUSTOMER_COUNT,
    BUTTON_CUSTOMER_ORDERS,
    BUTTON_CLOSE_MENU,
)


def get_sessions_menu(tenant_id: str, page: int = 0) -> dict:
    """Get the paginated sessions menu for a tenant."""
    page_size = 5
    sessions = get_sessions_paginated(tenant_id, page=page, page_size=page_size)
    if not sessions:
        return {
            'text': '<b>No active sessions are available.</b>\nAdd an order by printing a comment first.',
            'parse_mode': 'HTML',
        }
    
    # Check if there is a next page
    next_sessions = get_sessions_paginated(tenant_id, page=page + 1, page_size=page_size)
    has_next = len(next_sessions) > 0
    
    text_lines = [
        f"📋 <b>Your Sessions (Page {page + 1}):</b>\n"
    ]
    buttons = []
    
    for s in sessions:
        name = s['session_name'] or s['session_id']
        state = s.get('session_state', 'active')
        text_lines.append(
            f"📅 <b>{name}</b> ({state})\n"
            f"   Orders: {s['order_count']} | Customers: {s['customer_count']}\n"
        )
        buttons.append([{
            "text": f"📅 {name[:25]}",
            "callback_data": build_callback_data('btn_session', s['session_id'])
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
    normalized = text.strip().lower()

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

