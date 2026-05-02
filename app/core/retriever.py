from __future__ import annotations

from app.storage.models import EvidencePack


class MemoryRetriever:
    """Phase 0/1 placeholder for later retrieval logic."""

    def search(self, query: str, project_id: str | None = None) -> list[EvidencePack]:
        del query, project_id
        return []
