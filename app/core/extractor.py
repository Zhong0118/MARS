from __future__ import annotations

from app.storage.models import MemoryObject, RawEvent


class MemoryExtractor:
    """Phase 0/1 placeholder for later extraction logic."""

    def extract(self, events: list[RawEvent]) -> list[MemoryObject]:
        return []
