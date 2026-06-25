"""
Message formatting for Telegram order notifications.

Converts order data into formatted HTML messages for Telegram Bot API.
"""

from telegram_bot.config import (
    DEFAULT_ORDER_TEMPLATE,
    DEFAULT_SESSION_SUMMARY_TEMPLATE,
    EMOJI_ORDER,
    EMOJI_MENU,
    EMOJI_CUSTOMERS,
    EMOJI_EDIT,
)
from typing import Optional, List, Dict


def escape_html(text: Optional[str]) -> str:
    """
    Escape HTML special characters for safe use in Telegram messages.
    
    Telegram's HTML parse mode requires escaping: < > &
    """
    if not text:
        return ""
    
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def build_order_message(
    commenter: str,
    comment: str,
    profile_url: Optional[str] = None,
    collected_at: Optional[str] = None,
    comment_id: Optional[str] = None,
    template: Optional[str] = None,
) -> str:
    """
    Build a formatted order message for Telegram.
    
    Args:
        commenter: Customer/commenter name
        comment: Order comment text
        profile_url: Facebook profile URL (optional)
        collected_at: Timestamp when collected (optional)
        comment_id: Unique comment ID (optional)
        template: Custom message template (optional)
    
    Returns:
        HTML-formatted message string for Telegram
    
    Example output:
        🧾 <b>New Live Order</b>
        <b>Name:</b> John Doe
        <b>Comment:</b> 2 pcs red shirt
        <b>Profile:</b> https://facebook.com/john.doe
        <b>Time:</b> 2026-06-25 14:32
    """
    # Escape values
    safe_commenter = escape_html(commenter)
    safe_comment = escape_html(comment)
    safe_profile = escape_html(profile_url) if profile_url else "N/A"
    safe_time = escape_html(collected_at) if collected_at else "N/A"
    
    # Use provided template or default
    msg = template if template else DEFAULT_ORDER_TEMPLATE

    # Support both mustache-style templates ({{commenter}}) and Python format templates
    if any(tag in msg for tag in ["{{commenter}}", "{{comment}}", "{{profile_url}}", "{{collected_at}}", "{{comment_id}}"]):
        formatted = msg.replace("{{commenter}}", safe_commenter)
        formatted = formatted.replace("{{comment}}", safe_comment)
        formatted = formatted.replace("{{profile_url}}", safe_profile)
        formatted = formatted.replace("{{collected_at}}", safe_time)
        formatted = formatted.replace("{{comment_id}}", comment_id or "")
    else:
        formatted = msg.format(
            commenter=safe_commenter,
            comment=safe_comment,
            profile_url=safe_profile,
            collected_at=safe_time,
            comment_id=comment_id or "",
        )

    return formatted


def build_session_summary(
    session_name: str,
    order_count: int,
    customer_count: int,
    start_time: Optional[str] = None,
    template: Optional[str] = None,
) -> str:
    """
    Build a session summary message for the menu.
    
    Args:
        session_name: Name/label of the session
        order_count: Total orders in session
        customer_count: Total unique customers
        start_time: Session start time (optional)
        template: Custom template (optional)
    
    Returns:
        HTML-formatted session summary
    
    Example output:
        📋 <b>Live Session</b>
        <b>Session:</b> 19 Jun 2026 14:00
        <b>Orders:</b> 24
        <b>Customers:</b> 18
    """
    safe_session = escape_html(session_name)
    safe_time = escape_html(start_time) if start_time else "N/A"
    
    if template:
        msg = template
    else:
        msg = DEFAULT_SESSION_SUMMARY_TEMPLATE
    
    formatted = msg.format(
        session_name=safe_session,
        order_count=order_count,
        customer_count=customer_count,
        start_time=safe_time,
    )
    
    return formatted


def build_customer_list(customers: List[Dict[str, any]]) -> str:
    """
    Build a list of customers with order counts.
    
    Args:
        customers: List of customer dicts with 'name' and 'order_count' keys
    
    Returns:
        HTML-formatted customer list
    
    Example:
        customers = [
            {"name": "John Doe", "order_count": 3},
            {"name": "Mary Ann", "order_count": 2},
        ]
        
        Output:
        👥 <b>Customers Today</b>
        1. John Doe — 3 orders
        2. Mary Ann — 2 orders
    """
    if not customers:
        return f"{EMOJI_CUSTOMERS} <b>Customers Today</b>\n<i>No customers yet.</i>"
    
    sorted_customers = sorted(
        customers,
        key=lambda item: (-int(item.get('order_count', 0)), str(item.get('name', '')).lower())
    )
    
    lines = [f"{EMOJI_CUSTOMERS} <b>Customers Today</b>"]
    
    for i, customer in enumerate(sorted_customers, 1):
        name = escape_html(customer.get('name', 'Unknown'))
        count = customer.get('order_count', 0)
        lines.append(f"{i}. {name} — {count} order{'s' if count != 1 else ''}")
    
    return "\n".join(lines)


def build_menu_text() -> str:
    """
    Build the main menu text for /menu command.
    
    Returns:
        HTML-formatted menu instructions
    """
    return f"""{EMOJI_MENU} <b>Live Session Menu</b>

Select an action below:

<b>ឡាយថ្ងៃនេះ</b> — Show today's session summary
<b>មើលចំនួនភ្ញៀវថ្ងៃនេះ</b> — View customer count
<b>មើលអូដឺរបស់ភ្ញៀវ</b> — View customer orders
<b>{EMOJI_EDIT} កែប្រែអូដឺ</b> — Edit an order
<b>Last / Next</b> — Navigate through saved sessions"""


def build_order_details(
    commenter: str,
    comment: str,
    collected_at: Optional[str] = None,
    profile_url: Optional[str] = None,
) -> str:
    """
    Build a detailed order view for menu display.
    
    Args:
        commenter: Customer name
        comment: Order comment
        collected_at: Collection time
        profile_url: Customer profile URL
    
    Returns:
        HTML-formatted order details
    """
    safe_commenter = escape_html(commenter)
    safe_comment = escape_html(comment)
    safe_profile = escape_html(profile_url) if profile_url else "N/A"
    safe_time = escape_html(collected_at) if collected_at else "N/A"
    
    return f"""{EMOJI_ORDER} <b>Order Details</b>

<b>Customer:</b> {safe_commenter}
<b>Order:</b> {safe_comment}
<b>Time:</b> {safe_time}
<b>Profile:</b> {safe_profile}"""


def build_pagination_info(page: int, total_pages: int) -> str:
    """
    Build pagination info text.
    
    Args:
        page: Current page number (0-indexed)
        total_pages: Total number of pages
    
    Returns:
        Pagination text
    """
    if total_pages <= 1:
        return ""
    
    return f"Page {page + 1} of {total_pages}"
