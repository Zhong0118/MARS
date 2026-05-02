from __future__ import annotations

"""Load local sample chat files and normalize them into RawEvent objects.

This module is the MVP adapter boundary. It knows the sample JSON format, while
the rest of the system only consumes internal models such as RawEvent.
外部 JSON 转内部 RawEvent
"""

import json
from pathlib import Path
from typing import Any

from app.storage.models import RawEvent


def load_sample_messages(path: str | Path) -> list[dict[str, Any]]:
    """Read a sample chat JSON file and return the raw message list."""
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, list):
        raise ValueError("Sample chat input must be a JSON array of messages.")

    return payload


def message_to_raw_event(message: dict[str, Any]) -> RawEvent:
    """Convert one external sample message into the internal RawEvent schema."""
    message_id = str(message["message_id"])
    message_time = str(message["time"])

    return RawEvent(
        event_id=f"evt_{message_id}",
        event_type="message.created",
        source_type="sample_chat",
        source_id=message_id,
        tenant_id=message.get("tenant_id", "tenant_demo"),
        project_id=message.get("project_id"),
        chat_id=message.get("chat_id"),
        thread_id=message.get("thread_id"),
        actor_id=message.get("user_id"),
        actor_name=message.get("user_name"),
        content=message.get("content", ""),
        content_type=message.get("content_type", "text"),
        mentions=message.get("mentions", []),
        reply_to=message.get("reply_to"),
        raw_payload=message,
        transaction_time=message_time,
        valid_time_start=message_time,
        valid_time_end=message.get("valid_time_end"),
        source_url=message.get("source_url"),
    )


def load_raw_events(path: str | Path) -> list[RawEvent]:
    """Load a sample file and normalize every message into a RawEvent."""
    return [message_to_raw_event(message) for message in load_sample_messages(path)]
