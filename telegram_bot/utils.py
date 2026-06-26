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
    if not session_name or session_name == session_id or session_name.startswith('live-'):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", session_id)
        if match:
            try:
                return datetime.fromisoformat(match.group(1)).strftime('%d-%b-%Y')
            except ValueError:
                pass
    return session_name
