from __future__ import annotations

"""Turn user questions into lightweight retrieval plans."""

from dataclasses import dataclass

from app.llm.provider import LLMProvider, get_llm_provider
from app.core.post_processor import slugify
from app.core.text_utils import tokenize_query


@dataclass(slots=True)
class QueryPlan:
    """Small retrieval plan derived from one user query."""

    query: str
    normalized_topic: str | None
    query_type: str
    top_k: int
    preferred_types: list[str]
    primary_types: list[str]
    strict_topic: bool = False
    require_active: bool = True


class QueryPlanner:
    """Heuristic planner with LLM fallback for retrieval orchestration."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm or get_llm_provider()
        self.candidate_topics = ["tech_route", "timeline", "risk", "reporting", "onboarding", "ownership", "general"]

    def plan(self, query: str, *, top_k: int = 5) -> QueryPlan:
        """Infer coarse topic and preferred memory types from the query."""
        llm_plan = self._plan_with_llm(query)
        if llm_plan is not None:
            llm_plan.top_k = top_k
            return llm_plan

        lowered = query.lower()
        tokens = tokenize_query(query)

        normalized_topic = None
        preferred_types: list[str] = ["decision", "fact"]
        primary_types: list[str] = ["decision"]
        query_type = "general"
        strict_topic = False

        if any(keyword in lowered for keyword in ["current", "latest", "route", "stack", "frontend", "backend", "tech"]):
            normalized_topic = "tech_route"
            preferred_types = ["decision", "fact", "procedure"]
            primary_types = ["decision"]
            query_type = "current_state"
            strict_topic = True
        elif any(keyword in lowered for keyword in ["risk", "issue", "blocker", "problem", "deployment"]):
            normalized_topic = "risk"
            preferred_types = ["risk", "procedure", "fact"]
            primary_types = ["risk", "procedure"]
            query_type = "risk_lookup"
            strict_topic = True
        elif any(keyword in lowered for keyword in ["summary", "report", "weekly", "slide"]):
            normalized_topic = "reporting"
            preferred_types = ["fact", "procedure"]
            primary_types = ["fact", "procedure"]
            query_type = "reporting_lookup"
        elif any(keyword in lowered for keyword in ["onboarding", "new teammate", "handoff", "context"]):
            normalized_topic = "onboarding"
            preferred_types = ["decision", "procedure", "fact"]
            primary_types = ["decision", "procedure"]
            query_type = "onboarding_lookup"
        elif any(keyword in lowered for keyword in ["deadline", "timeline", "schedule", "when"]):
            normalized_topic = "timeline"
            preferred_types = ["fact", "risk"]
            primary_types = ["fact", "risk"]
            query_type = "timeline_lookup"
        elif "why" in lowered or "reason" in lowered:
            query_type = "explanation"
            preferred_types = ["decision", "fact", "risk"]
            primary_types = ["decision", "risk"]
        else:
            strict_topic = False

        if normalized_topic is None:
            for token in tokens:
                if token in {"streamlit", "vue", "fastapi"}:
                    normalized_topic = "tech_route"
                    break

        return QueryPlan(
            query=query,
            normalized_topic=normalized_topic,
            query_type=query_type,
            top_k=top_k,
            preferred_types=preferred_types,
            primary_types=primary_types,
            strict_topic=strict_topic,
        )

    def _plan_with_llm(self, query: str) -> QueryPlan | None:
        """Let the LLM classify user intent before falling back to keyword rules."""
        try:
            payload = self.llm.plan_query(query, self.candidate_topics)
        except Exception:
            return None

        query_type = str(payload.get("query_type", "")).strip() or "general"
        normalized_topic = normalize_query_topic(payload.get("normalized_topic"))
        preferred_types = [str(item).strip() for item in payload.get("preferred_types", []) if str(item).strip()]
        primary_types = [str(item).strip() for item in payload.get("primary_types", []) if str(item).strip()]
        strict_topic = bool(payload.get("strict_topic", False))

        if not preferred_types:
            preferred_types = ["decision", "fact"]
        if not primary_types:
            primary_types = ["decision"]

        return QueryPlan(
            query=query,
            normalized_topic=normalized_topic,
            query_type=query_type,
            top_k=5,
            preferred_types=preferred_types,
            primary_types=primary_types,
            strict_topic=strict_topic,
        )


def normalize_query_topic(value: str | None) -> str | None:
    """Convert a raw topic string into an internal topic-like slug."""
    if not value:
        return None
    return slugify(value)
