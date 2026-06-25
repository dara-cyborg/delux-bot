"""
Local in-memory order storage for Telegram Bot fallback mode.

Provides a lightweight order history store for Telegram command
handlers when tenant-aware data storage is not registered.
"""

from typing import Any, Dict, List, Optional

order_history_by_commenter: Dict[str, Dict[str, Any]] = {}


def _normalize_commenter_name(commenter: str) -> str:
    return (commenter or "").strip().lower()


def clear_order_history() -> None:
    """Clear the in-memory order history."""
    order_history_by_commenter.clear()


def add_order(
    commenter: str,
    comment: str,
    collected_at: str,
    comment_id: Optional[str] = None,
    printed_at: Optional[str] = None,
    profile_url: Optional[str] = None,
) -> None:
    """Add an order entry to the local in-memory store."""
    commenter_name = (commenter or "").strip()
    if not commenter_name or not comment:
        return

    key = _normalize_commenter_name(commenter_name)
    existing = order_history_by_commenter.get(key)

    if existing is None:
        existing = {
            "commenter": commenter_name,
            "print_count": 0,
            "comments": [],
        }
        order_history_by_commenter[key] = existing

    existing["commenter"] = commenter_name
    existing["print_count"] = existing.get("print_count", 0) + 1
    existing["comments"].append({
        "comment": comment,
        "collected_at": collected_at,
        "comment_id": comment_id,
        "printed_at": printed_at,
        "profile_url": profile_url,
    })


def iterate_orders() -> List[Dict[str, Any]]:
    """Return a flat list of local orders."""
    payload: List[Dict[str, Any]] = []
    for entry in order_history_by_commenter.values():
        commenter = entry.get("commenter", "Unknown")
        for comment in entry.get("comments", []):
            payload.append({
                "commenter": commenter,
                "comment": comment.get("comment", ""),
                "collected_at": comment.get("collected_at", ""),
                "comment_id": comment.get("comment_id"),
                "printed_at": comment.get("printed_at"),
                "profile_url": comment.get("profile_url"),
            })
    return payload
