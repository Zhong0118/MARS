from __future__ import annotations

from app.storage.models import PolicyAction


class PolicyEngine:
    """Phase 0/1 placeholder for later policy orchestration."""

    def record_noop(self, project_id: str | None = None) -> PolicyAction:
        return PolicyAction(
            action_type="NOOP",
            project_id=project_id,
            decision="NONE",
            reason="Policy engine placeholder for phase 0/1.",
            confidence=1.0,
        )
