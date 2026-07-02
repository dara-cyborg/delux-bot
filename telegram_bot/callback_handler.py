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
from telegram_bot.tenant_store import get_order, delete_order
from telegram_bot.commands import set_pending_note_request, clear_pending_note_request
from telegram_bot.utils import build_callback_data, format_local_time, format_session_label
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
            
        # 2. btn_session|{session_id}|{session_date?}
        elif action == 'btn_session':
            session_id = parts[1]
            session_date = parts[2] if len(parts) > 2 and parts[2] else session_id
            summary = get_session_summary(tenant_id, session_id)
            
            name = format_session_label(summary.get('session_name') or session_id, session_date)
            text = (
                f"📅 <b>Session Details</b>\n\n"
                f"<b>Name:</b> {name}\n"
                f"<b>Orders:</b> {summary['order_count']}\n"
                f"<b>Customers:</b> {summary['customer_count']}\n"
            )
            
            buttons = [
                [
                    {"text": "👥 View Customers", "callback_data": build_callback_data('btn_custlist', session_id)},
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
            
        # 3. btn_custlist|{session_id}|{page}
        elif action == 'btn_custlist':
            session_id = parts[1]
            page = int(parts[2]) if len(parts) > 2 and parts[2] else 0
            customers = get_customers_for_session(tenant_id, session_id)
            page_size = 10
            start = page * page_size
            end = (page + 1) * page_size
            page_customers = customers[start:end]
            
            if not page_customers:
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
            
            for i, c in enumerate(page_customers, start + 1):
                name = c['name']
                count = c['order_count']
                text_lines.append(f"{i}. 👤 <b>{name}</b> — {count} order(s)")
                
                callback_data = build_callback_data('btn_cust', session_id, name)
                buttons.append([{
                    "text": f"👤 {name[:20]} ({count})",
                    "callback_data": callback_data
                }])
                
            if len(customers) > page_size:
                range_end = min(end, len(customers))
                text_lines.append(f"\n<i>Showing {start + 1}-{range_end} of {len(customers)} customer(s).</i>")
            
            nav_buttons = []
            if page > 0:
                nav_buttons.append({
                    "text": "◀️ Prev",
                    "callback_data": build_callback_data('btn_custlist', session_id, str(page - 1))
                })
            if len(customers) > (page + 1) * page_size:
                nav_buttons.append({
                    "text": "Next ▶️",
                    "callback_data": build_callback_data('btn_custlist', session_id, str(page + 1))
                })
            if nav_buttons:
                buttons.append(nav_buttons)
                
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
                time_str = format_local_time(o.get('collected_at', ''))
                text_lines.append(
                    f"{i}. <b>Order:</b> {comment}\n"
                    f"   <b>Time:</b> {time_str}"
                )
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
            
        # 5. btn_customer_note|{order_id}
        elif action == 'btn_customer_note':
            order_id = parts[1] if len(parts) > 1 else ''
            order = get_order(tenant_id, order_id)
            if not order:
                return {
                    'text': '<b>Order not found.</b>',
                    'buttons': _close_button(),
                    'notification': 'Order not found.',
                    'parse_mode': 'HTML'
                }

            set_pending_note_request(chat_id, order_id)
            text = (
                f"<b>Enter a note for {format_session_label(order['commenter'], order['commenter'])}.</b>\n"
                "Send your note as plain text (max 50 characters)."
            )
            buttons = [[
                {"text": "Cancel", "callback_data": build_callback_data('btn_customer_note_cancel', order_id)}
            ]]
            return {
                'text': text,
                'buttons': buttons,
                'notification': 'Enter a note.',
                'parse_mode': 'HTML'
            }

        elif action == 'btn_customer_note_cancel':
            clear_pending_note_request(chat_id)
            return {
                'text': '<b>Note entry canceled.</b>',
                'buttons': _close_button(),
                'notification': 'Note canceled.',
                'parse_mode': 'HTML'
            }

        elif action == 'btn_delete_order_request':
            order_id = parts[1] if len(parts) > 1 else ''
            order = get_order(tenant_id, order_id)
            if not order:
                return {
                    'text': '<b>Order not found.</b>',
                    'buttons': _close_button(),
                    'notification': 'Order not found.',
                    'parse_mode': 'HTML'
                }

            text = (
                f"<b>Delete order for {order['commenter']}?</b>\n"
                "Confirm to remove this order permanently."
            )
            buttons = [
                [
                    {"text": "Confirm", "callback_data": build_callback_data('btn_delete_order_confirm', order_id)},
                    {"text": "Cancel", "callback_data": build_callback_data('btn_delete_order_cancel', order_id)},
                ]
            ]
            return {
                'text': text,
                'buttons': buttons,
                'notification': 'Confirm delete.',
                'parse_mode': 'HTML'
            }

        elif action == 'btn_delete_order_confirm':
            order_id = parts[1] if len(parts) > 1 else ''
            order = get_order(tenant_id, order_id)
            if not order:
                return {
                    'text': '<b>Order not found.</b>',
                    'buttons': _close_button(),
                    'notification': 'Order not found.',
                    'parse_mode': 'HTML'
                }

            delete_order(tenant_id, order_id)
            return {
                'text': '<b>Order deleted successfully.</b>',
                'buttons': _close_button(),
                'notification': 'Order deleted.',
                'parse_mode': 'HTML'
            }

        elif action == 'btn_delete_order_cancel':
            return {
                'text': '<b>Delete canceled.</b>',
                'buttons': _close_button(),
                'notification': 'Delete canceled.',
                'parse_mode': 'HTML'
            }

        # 5. btn_ordlist|{session_id}|{page}
        elif action == 'btn_ordlist':
            session_id = parts[1]
            page = int(parts[2]) if len(parts) > 2 and parts[2] else 0
            
            from telegram_bot.storage import get_session_orders, get_tenant_orders_by_date
            page_size = 10
            if session_id == "today":
                from datetime import datetime
                today_str = datetime.now().strftime("%Y-%m-%d")
                try:
                    orders = get_tenant_orders_by_date(tenant_id, today_str, limit=200)
                except Exception:
                    orders = []
                session_name = f"Today's Orders ({today_str})"
                back_callback = build_callback_data('btn_sessions_page', '0')
            else:
                try:
                    orders = get_session_orders(tenant_id, session_id, limit=200)
                except Exception:
                    orders = []
                session_name = format_session_label('', session_id)
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
            
            start = page * page_size
            end = (page + 1) * page_size
            page_orders = orders[start:end]
            
            text_lines = [f"📦 <b>Orders in Session {session_name[:20]}:</b>\n"]
            for i, o in enumerate(page_orders, start + 1):
                commenter = o['commenter']
                comment = o['comment']
                time_str = format_local_time(o.get('collected_at', ''))
                text_lines.append(f"{i}. 👤 <b>{commenter}</b>: {comment} (at {time_str})")
                
            if len(orders) > page_size:
                range_end = min(end, len(orders))
                text_lines.append(f"\n<i>Showing {start + 1}-{range_end} of {len(orders)} order(s).</i>")
                
            buttons = []
            nav_buttons = []
            if page > 0:
                nav_buttons.append({
                    "text": "◀️ Prev",
                    "callback_data": build_callback_data('btn_ordlist', session_id, str(page - 1))
                })
            if len(orders) > (page + 1) * page_size:
                nav_buttons.append({
                    "text": "Next ▶️",
                    "callback_data": build_callback_data('btn_ordlist', session_id, str(page + 1))
                })
            if nav_buttons:
                buttons.append(nav_buttons)
            buttons.append([
                {"text": "🔙 Back", "callback_data": back_callback},
                {"text": "❌ Close", "callback_data": "btn_close_menu"}
            ])
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

