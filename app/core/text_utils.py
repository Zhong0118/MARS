from __future__ import annotations

"""Shared text helpers for retrieval and planning."""

import re


def tokenize_query(query: str) -> list[str]:
    """Extract simple searchable tokens from Chinese/English mixed text."""
    lowered = query.lower()
    tokens = re.findall(r"[a-z0-9_+\-#.]+|[\u4e00-\u9fff]+", lowered)
    return [token for token in tokens if token.strip()]
