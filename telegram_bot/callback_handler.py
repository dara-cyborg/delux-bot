"""Telegram callback query handling."""

import re
from datetime import datetime

from telegram_bot.message_builder import (
    build_customer_list,
    build_order_details,
    build_session_summary,
)
from telegram_bot.session_manager import (
    get_session_summary,
    get_customers_for_session,
    get_orders_for_customer,
)
from telegram_bot.utils import build_callback_data, format_session_label
from telegram_bot.config import BUTTON_CLOSE_MENU


def _close_button():
    return [[{"text": BUTTON_CLOSE_MENU, "callback_data": "btn_close_menu"}]]


def handle_callback_query(bot_token: str, data: str, chat_id: int, message_id: int, tenant_id: str = "") -> dict:
    """Handle callback queries and button actions."""
    if data == 'btn_close_menu':
        return {
            'text': '<b>Menu closed.</b>',
            'buttons': [],
            'notification': 'Menu closed.',
        }
    if '|' in data:
        parts = data.split('|')
        action = parts[0]
        
        # 1. btn_sessions_page|{page}
        if action == 'btn_sessions_page':
            page = int(parts[1])
            from telegram_bot.commands import get_sessions_menu
            res = get_sessions_menu(tenant_id, page)
            res['notification'] = f"Loaded page {page + 1}"
            return res
            
        # 2. btn_session|{session_id}
        elif action == 'btn_session':
            session_id = parts[1]
            summary = get_session_summary(tenant_id, session_id)
            
            name = format_session_label(summary.get('session_name') or session_id, session_id)
            text = (
                f"📅 <b>Session Details</b>\n\n"
                f"<b>Name:</b> {name}\n"
                f"<b>Orders:</b> {summary['order_count']}\n"
                f"<b>Customers:</b> {summary['customer_count']}\n"
            )
            
            buttons = [
                [
                    {"text": "👥 View Customers", "callback_data": build_callback_data('btn_custlist', session_id)},
                    {"text": "📦 View Orders", "callback_data": build_callback_data('btn_ordlist', session_id)}
                ],
                [
                    {"text": "🔙 Back to Sessions", "callback_data": build_callback_data('btn_sessions_page', '0')},
                    {"text": "❌ Close", "callback_data": "btn_close_menu"}
                ]
            ]
            return {
                'text': text,
                'buttons': buttons,
                'notification': f"Session {name[:15]} loaded",
                'parse_mode': 'HTML'
            }
            
        # 3. btn_custlist|{session_id}
        elif action == 'btn_custlist':
            session_id = parts[1]
            customers = get_customers_for_session(tenant_id, session_id)
            
            if not customers:
                text = "👥 <b>Customers:</b>\n\n<i>No customers or orders yet in this session.</i>"
                buttons = [
                    [{"text": "🔙 Back to Session", "callback_data": build_callback_data('btn_session', session_id)}],
                    [{"text": "❌ Close", "callback_data": "btn_close_menu"}]
                ]
                return {
                    'text': text,
                    'buttons': buttons,
                    'notification': 'No customers found',
                    'parse_mode': 'HTML'
                }
                
            text_lines = ["👥 <b>Customers in Session:</b>\n"]
            buttons = []
            
            for i, c in enumerate(customers[:15], 1):
                name = c['name']
                count = c['order_count']
                text_lines.append(f"{i}. 👤 <b>{name}</b> — {count} order(s)")
                
                callback_data = build_callback_data('btn_cust', session_id, name)
                buttons.append([{
                    "text": f"👤 {name[:20]} ({count})",
                    "callback_data": callback_data
                }])
                
            if len(customers) > 15:
                text_lines.append(f"\n<i>...and {len(customers) - 15} more customer(s).</i>")
                
            buttons.append([
                    {"text": "🔙 Back", "callback_data": build_callback_data('btn_session', session_id)},
            ])
            
            return {
                'text': "\n".join(text_lines),
                'buttons': buttons,
                'notification': 'Loaded customer list',
                'parse_mode': 'HTML'
            }
            
        # 4. btn_cust|{session_id}|{customer_name}
        elif action == 'btn_cust':
            session_id = parts[1]
            customer_name_part = parts[2]
            
            # Prefix search in database/customers to get full name
            customers = get_customers_for_session(tenant_id, session_id)
            full_name = customer_name_part
            for c in customers:
                if c['name'].lower().startswith(customer_name_part.lower()):
                    full_name = c['name']
                    break
                    
            orders = get_orders_for_customer(tenant_id, session_id, full_name)
            
            text_lines = [f"👤 <b>Orders for {full_name}:</b>\n"]
            for i, o in enumerate(orders, 1):
                comment = o['comment']
                time_str = o['collected_at']
                text_lines.append(
                    f"{i}. <b>Order:</b> {comment}\n"
                    f"   <b>Time:</b> {time_str}"
                )
                if o.get('profile_url'):
                    text_lines.append(f"   <b>Profile:</b> {o['profile_url']}")
                text_lines.append("")
                
            buttons = [
                [
                    {"text": "🔙 Back to Customers", "callback_data": build_callback_data('btn_custlist', session_id)},
                    {"text": "❌ Close", "callback_data": "btn_close_menu"}
                ]
            ]
            return {
                'text': "\n".join(text_lines),
                'buttons': buttons,
                'notification': f"Orders for {full_name[:15]}",
                'parse_mode': 'HTML'
            }
            
        # 5. btn_ordlist|{session_id}
        elif action == 'btn_ordlist':
            session_id = parts[1]
            
            from telegram_bot.storage import get_session_orders, get_tenant_orders_by_date
            if session_id == "today":
                from datetime import datetime
                today_str = datetime.now().strftime("%Y-%m-%d")
                try:
                    orders = get_tenant_orders_by_date(tenant_id, today_str, limit=50)
                except Exception:
                    orders = []
                session_name = f"Today's Orders ({today_str})"
                back_callback = build_callback_data('btn_sessions_page', '0')
            else:
                try:
                    orders = get_session_orders(tenant_id, session_id, limit=100)
                except Exception:
                    orders = []
                session_name = session_id
                back_callback = build_callback_data('btn_session', session_id)
                
            if not orders:
                text = f"📦 <b>Orders in Session {session_name}:</b>\n\n<i>No orders found.</i>"
                buttons = [
                    [{"text": "🔙 Back", "callback_data": back_callback}],
                    [{"text": "❌ Close", "callback_data": "btn_close_menu"}]
                ]
                return {
                    'text': text,
                    'buttons': buttons,
                    'notification': 'No orders found',
                    'parse_mode': 'HTML'
                }
                
            text_lines = [f"📦 <b>Orders in Session {session_name[:20]}:</b>\n"]
            for i, o in enumerate(orders[:15], 1):
                commenter = o['commenter']
                comment = o['comment']
                time_str = o['collected_at'].split(" ")[-1] if " " in o['collected_at'] else o['collected_at']
                text_lines.append(f"{i}. 👤 <b>{commenter}</b>: {comment} (at {time_str})")
                
            if len(orders) > 15:
                text_lines.append(f"\n<i>...and {len(orders) - 15} more order(s).</i>")
                
            buttons = [
                [
                    {"text": "🔙 Back", "callback_data": back_callback},
                    {"text": "❌ Close", "callback_data": "btn_close_menu"}
                ]
            ]
            return {
                'text': "\n".join(text_lines),
                'buttons': buttons,
                'notification': f"Orders loaded for {session_name[:15]}",
                'parse_mode': 'HTML'
            }

    if data == 'btn_session_summary':
        session = get_session_summary(tenant_id, 'current')
        return {
            'text': build_session_summary(
                session_name=session['session_name'],
                order_count=session['order_count'],
                customer_count=session['customer_count'],
                start_time=session.get('start_time'),
                template=None,
            ),
            'buttons': _close_button(),
            'notification': 'Session summary',
        }

    if data == 'btn_customer_list':
        customers = get_customers_for_session(tenant_id, 'current')
        text = build_customer_list(customers)
        return {
            'text': text,
            'buttons': _close_button(),
            'notification': 'Customer list updated.',
        }

    if data == 'btn_customer_orders':
        customers = get_customers_for_session(tenant_id, 'current')
        if not customers:
            return {
                'text': '<b>No orders are available yet.</b>',
                'buttons': _close_button(),
                'notification': 'No orders available.',
            }

        sections = ['<b>Top customer orders</b>']
        for customer in customers[:3]:
            sections.append(f"\n<b>{customer['name']}</b> — {customer['order_count']} order{'s' if customer['order_count'] != 1 else ''}")
            order_rows = get_orders_for_customer(tenant_id, 'current', customer['name'])
            for order in order_rows[:3]:
                sections.append(build_order_details(
                    commenter=customer['name'],
                    comment=order['comment'],
                    collected_at=order['collected_at'],
                    profile_url=None,
                ))

        return {
            'text': '\n\n'.join(sections),
            'buttons': _close_button(),
            'notification': 'Order details shown.',
        }

    return {
        'text': '<b>Unknown action.</b>',
        'buttons': _close_button(),
        'notification': 'Action not implemented.',
    }

