from __future__ import annotations

"""Compose user-facing answers from retrieved memories."""

from dataclasses import dataclass

from app.llm.provider import LLMProvider, get_llm_provider
from app.core.query_planner import QueryPlan
from app.storage.models import EvidencePack


@dataclass(slots=True)
class AnswerBundle:
    """Final answer plus retrieved evidence."""

    answer: str
    evidence: list[EvidencePack]


class MemoryAnswerer:
    """Turn retrieved evidence packs into one concise answer."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm or get_llm_provider()

    def compose(self, plan: QueryPlan, evidence: list[EvidencePack]) -> AnswerBundle:
        """Build a user-facing answer with lightweight structure."""
        if not evidence:
            return AnswerBundle(
                answer="I could not find a strong active memory for that query yet.",
                evidence=[],
            )

        primary = self.select_primary(plan, evidence)
        supporting = [item for item in evidence if item.memory_id != primary.memory_id]
        answer_parts = self.build_answer_parts(plan, primary, supporting, evidence)
        return AnswerBundle(answer=" ".join(answer_parts), evidence=evidence)

    def select_primary(self, plan: QueryPlan, evidence: list[EvidencePack]) -> EvidencePack:
        """Pick the most suitable main memory for final answer composition."""
        def priority(item: EvidencePack) -> tuple[int, float]:
            primary_type_score = 1 if memory_type_from_title(item.title, item.content) in plan.primary_types else 0
            topic_score = 1 if item.topic == plan.normalized_topic else 0
            return (primary_type_score + topic_score, item.score)

        return max(evidence, key=priority)

    def build_answer_parts(
        self,
        plan: QueryPlan,
        primary: EvidencePack,
        supporting: list[EvidencePack],
        evidence: list[EvidencePack],
    ) -> list[str]:
        """Render query-specific answer templates."""
        llm_answer = self._try_llm_answer(plan, evidence)
        if llm_answer is not None:
            return llm_answer
        if plan.query_type == "risk_lookup":
            return self._risk_answer(primary, supporting)
        if plan.query_type == "onboarding_lookup":
            return self._onboarding_answer(primary, supporting)
        if plan.query_type == "timeline_lookup":
            return self._timeline_answer(primary, supporting)
        return self._current_state_answer(primary, supporting)

    def _try_llm_answer(self, plan: QueryPlan, evidence: list[EvidencePack]) -> list[str] | None:
        """Use the configured LLM to synthesize a richer final answer when available."""
        try:
            payload = self.llm.generate_answer(
                plan.query,
                [item.model_dump() for item in evidence],
                plan.query_type,
            )
        except Exception:
            return None

        final_answer = str(payload.get("final_answer", "")).strip()
        if not final_answer:
            return None

        parts = [final_answer]
        basis = [item for item in payload.get("basis", []) if item]
        risks = [item for item in payload.get("risks", []) if item]
        uncertainties = [item for item in payload.get("uncertainties", []) if item]

        if basis:
            parts.append(f"Basis: {'; '.join(basis[:3])}.")
        if risks:
            parts.append(f"Risks: {'; '.join(risks[:3])}.")
        if uncertainties:
            parts.append(f"Uncertainties: {'; '.join(uncertainties[:3])}.")
        return parts

    def _current_state_answer(self, primary: EvidencePack, supporting: list[EvidencePack]) -> list[str]:
        parts = [primary.content]
        if primary.rationale:
            parts.append(f"Reasoning: {'; '.join(primary.rationale[:3])}.")
        if supporting:
            support_titles = [item.title for item in supporting[:3]]
            parts.append(f"Supporting memories: {', '.join(support_titles)}.")
        parts.append(f"Primary memory topic: {primary.topic}.")
        return parts

    def _risk_answer(self, primary: EvidencePack, supporting: list[EvidencePack]) -> list[str]:
        parts = [f"Current primary risk memory: {primary.content}"]
        if primary.rationale:
            parts.append(f"Why this matters: {'; '.join(primary.rationale[:3])}.")
        if supporting:
            support_titles = [item.title for item in supporting[:2]]
            parts.append(f"Related supporting memories: {', '.join(support_titles)}.")
        return parts

    def _onboarding_answer(self, primary: EvidencePack, supporting: list[EvidencePack]) -> list[str]:
        parts = [f"New teammate context: {primary.content}"]
        if primary.rationale:
            parts.append(f"Key rationale: {'; '.join(primary.rationale[:3])}.")
        if supporting:
            support_titles = [item.title for item in supporting[:3]]
            parts.append(f"Additional context memories: {', '.join(support_titles)}.")
        return parts

    def _timeline_answer(self, primary: EvidencePack, supporting: list[EvidencePack]) -> list[str]:
        parts = [f"Timeline memory: {primary.content}"]
        if supporting:
            support_titles = [item.title for item in supporting[:2]]
            parts.append(f"Related timeline support: {', '.join(support_titles)}.")
        return parts


def memory_type_from_title(title: str, content: str) -> str:
    """Infer a coarse type hint from evidence text when type is not directly exposed."""
    combined = f"{title} {content}".lower()
    if any(keyword in combined for keyword in ["decide", "decision", "selected", "will use", "instead of"]):
        return "decision"
    if any(keyword in combined for keyword in ["risk", "failure", "blocker", "unstable"]):
        return "risk"
    if any(keyword in combined for keyword in ["required", "procedure", "fallback", "need to"]):
        return "procedure"
    return "fact"
