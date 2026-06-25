"""
Telegram Bot configuration constants and API endpoints.
"""

# Telegram Bot API endpoint
TELEGRAM_API_BASE_URL = "https://api.telegram.org"

# Timeout for API requests (seconds)
TELEGRAM_API_TIMEOUT = 10

# Parse modes for message formatting
PARSE_MODE_HTML = "HTML"
PARSE_MODE_MARKDOWN = "Markdown"

# Default message templates (will be customizable later)
DEFAULT_ORDER_TEMPLATE = """🧾 <b>New Live Order</b>
<b>Name:</b> {commenter}
<b>Comment:</b> {comment}
<b>Profile:</b> {profile_url}
<b>Time:</b> {collected_at}"""

DEFAULT_SESSION_SUMMARY_TEMPLATE = """📋 <b>Live Session</b>
<b>Session:</b> {session_name}
<b>Orders:</b> {order_count}
<b>Customers:</b> {customer_count}"""

# Error codes
ERROR_TELEGRAM_NOT_CONFIGURED = "TELEGRAM_NOT_CONFIGURED"
ERROR_TELEGRAM_API_ERROR = "TELEGRAM_API_ERROR"
ERROR_TELEGRAM_NETWORK_ERROR = "TELEGRAM_NETWORK_ERROR"
ERROR_INVALID_TOKEN = "INVALID_TOKEN"
ERROR_INVALID_CHAT_ID = "INVALID_CHAT_ID"

# Menu buttons and emojis
EMOJI_ORDER = "🧾"
EMOJI_MENU = "📋"
EMOJI_CUSTOMERS = "👥"
EMOJI_SEARCH = "🔍"
EMOJI_EDIT = "✏️"
EMOJI_DELETE = "❌"
EMOJI_BACK = "⬅️"
EMOJI_NEXT = "➡️"

# Keyboard button text
BUTTON_TODAY_SUMMARY = "ឡាយថ្ងៃនេះ"  # "Today Summary"
BUTTON_CUSTOMER_COUNT = "មើលចំនួនភ្ញៀវថ្ងៃនេះ"  # "View Customer Count Today"
BUTTON_CUSTOMER_ORDERS = "មើលអូដឺរបស់ភ្ញៀវ"  # "View Customer Orders"
BUTTON_EDIT_ORDER = "កែប្រែអូដឺ"  # "Edit Order"
BUTTON_LAST_PAGE = "Last"
BUTTON_NEXT_PAGE = "Next"
BUTTON_CLOSE_MENU = "បិទមីនុយ"  # "Close Menu"
BUTTON_CANCEL = "Cancel"

# Default pagination size
DEFAULT_PAGE_SIZE = 10
