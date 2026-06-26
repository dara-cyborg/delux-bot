import re
from datetime import datetime


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text

    truncated = encoded[:max_bytes]
    while truncated and truncated[-1] >> 6 == 0b10:
        truncated = truncated[:-1]
    return truncated.decode('utf-8', 'ignore')


def build_callback_data(action: str, *parts: str) -> str:
    """Build Telegram callback_data safely within 64 bytes."""
    data_parts = (action, *parts)
    callback_data = '|'.join(data_parts)
    encoded = callback_data.encode('utf-8')
    if len(encoded) <= 64:
        return callback_data

    prefix = '|'.join(data_parts[:-1]) + '|' if len(data_parts) > 1 else f"{action}|"
    max_last = 64 - len(prefix.encode('utf-8'))
    if max_last <= 0:
        raise ValueError('Callback data prefix is too long')
    return prefix + _truncate_utf8(parts[-1], max_last)


def format_session_label(session_name: str, session_id: str) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", session_id)
    if match:
        try:
            return datetime.fromisoformat(match.group(1)).strftime('%d-%b-%Y')
        except ValueError:
            pass
    return session_name


def format_local_time(timestamp: str) -> str:
    """Format a timestamp string to local HH:MM AM/PM."""
    if not timestamp:
        return timestamp
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%H:%M:%S", "%H:%M"):
        try:
            dt = datetime.strptime(timestamp, fmt)
            return dt.strftime('%I:%M %p').lstrip('0')
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime('%I:%M %p').lstrip('0')
    except ValueError:
        return timestamp
