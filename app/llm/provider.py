from __future__ import annotations

"""LLM provider layer for local MVP and future real-model integration.

The provider boundary supports:
- mock: deterministic outputs for repeatable local pipeline testing
- glm: real GLM API calls through the OpenAI-compatible endpoint
- minimax: real MiniMax API calls through the OpenAI-compatible endpoint
"""

import json
import os
import re
from typing import Any, Protocol

from app.config import load_local_env


load_local_env()


class LLMProvider(Protocol):
    """Minimal interface shared by mock and real providers."""

    def extract_memories(self, events: list[dict[str, Any]], extraction_hints: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ...

    def judge_relation(self, new_memory: dict[str, Any], existing_memories: list[dict[str, Any]]) -> dict[str, Any]:
        ...

    def generate_answer(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        query_type: str,
    ) -> dict[str, Any]:
        ...

    def classify_topic(
        self,
        window: dict[str, Any],
        candidate_topics: list[str],
        previous_topics: list[str],
    ) -> dict[str, Any]:
        ...

    def plan_query(self, query: str, candidate_topics: list[str]) -> dict[str, Any]:
        ...

    def judge_consolidation(self, primary: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        ...


class MockLLM:
    """Deterministic placeholder provider for local MVP phases."""

    def extract_memories(self, events: list[dict[str, Any]], extraction_hints: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return structured memory candidates for known sample scenarios."""
        if not events:
            return []

        project_id = events[0].get("project_id")
        tenant_id = events[0].get("tenant_id")
        event_ids = [str(event["event_id"]) for event in events]
        combined_text = " ".join(str(event.get("content", "")) for event in events).lower()
        first_time = str(events[0].get("valid_time_start") or events[0].get("transaction_time"))
        last_time = str(events[-1].get("transaction_time") or events[-1].get("valid_time_start"))

        if "streamlit" in combined_text and "vue plus fastapi" in combined_text and "correction:" not in combined_text:
            return [
                {
                    "memory_id": f"mem_{project_id}_tech_route_v1",
                    "version_group_id": f"vg_{project_id}_tech_route",
                    "memory_type": "decision",
                    "scope": "project",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "topic": "tech_route",
                    "title": "Phase One Demo Uses Streamlit",
                    "content": "Use Streamlit for phase one so the demo ships quickly, and revisit Vue + FastAPI later.",
                    "rationale": [
                        "The timeline is tight.",
                        "The current data processing stack is already Python-heavy.",
                        "Streamlit is faster for a first demo.",
                    ],
                    "objections": [
                        "Vue + FastAPI may be better for a more engineered long-term frontend.",
                    ],
                    "tags": ["demo", "frontend", "tech_route"],
                    "status": "active",
                    "version": 1,
                    "confidence": 0.92,
                    "importance": 4,
                    "valid_time_start": first_time,
                    "valid_time_end": None,
                    "transaction_time": last_time,
                    "source_event_ids": event_ids,
                }
            ]

        if "correction:" in combined_text and "vue plus fastapi" in combined_text:
            return [
                {
                    "memory_id": f"mem_{project_id}_tech_route_v2",
                    "version_group_id": f"vg_{project_id}_tech_route",
                    "memory_type": "decision",
                    "scope": "project",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "topic": "tech_route",
                    "title": "Phase One Moves to Vue + FastAPI",
                    "content": "The formal phase-one demo should use Vue + FastAPI instead of Streamlit.",
                    "rationale": [
                        "The formal demo needs a more engineered frontend.",
                    ],
                    "objections": [
                        "This is slower than the earlier Streamlit-first plan.",
                    ],
                    "tags": ["demo", "frontend", "tech_route", "correction"],
                    "status": "active",
                    "version": 2,
                    "confidence": 0.95,
                    "importance": 5,
                    "valid_time_start": first_time,
                    "valid_time_end": None,
                    "transaction_time": last_time,
                    "source_event_ids": event_ids,
                }
            ]

        return []

    def judge_relation(self, new_memory: dict[str, Any], existing_memories: list[dict[str, Any]]) -> dict[str, Any]:
        """Return a simple deterministic relation judgment for MVP samples."""
        new_title = str(new_memory.get("title", "")).lower()
        existing_titles = " ".join(str(memory.get("title", "")).lower() for memory in existing_memories)

        if "vue + fastapi" in new_title and "streamlit" in existing_titles:
            return {
                "relation": "supersedes",
                "reason": "The new statement explicitly replaces the earlier Streamlit-first plan.",
                "confidence": 0.95,
            }

        if new_title and new_title in existing_titles:
            return {
                "relation": "duplicate",
                "reason": "The candidate repeats an existing memory title.",
                "confidence": 0.9,
            }

        return {"relation": "unrelated", "reason": "MockLLM placeholder.", "confidence": 1.0}

    def generate_answer(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        query_type: str,
    ) -> dict[str, Any]:
        """Return a deterministic structured answer for local non-network testing."""
        if not evidence:
            return {
                "current_conclusion": "No strong active memory was found.",
                "basis": [],
                "risks": [],
                "uncertainties": ["The memory store does not yet contain a strong matching active memory."],
                "final_answer": "I could not find a strong active memory for that query yet.",
            }

        primary = evidence[0]
        basis = [item.get("title", "") for item in evidence[:3] if item.get("title")]
        risks = [item.get("title", "") for item in evidence if item.get("topic") == "risk"]
        return {
            "current_conclusion": primary.get("content", ""),
            "basis": basis,
            "risks": risks,
            "uncertainties": [],
            "final_answer": primary.get("content", ""),
        }

    def classify_topic(
        self,
        window: dict[str, Any],
        candidate_topics: list[str],
        previous_topics: list[str],
    ) -> dict[str, Any]:
        """Return a lightweight semantic-ish topic guess for local fallback use."""
        summary = str(window.get("raw_summary", "")).lower()
        if any(token in summary for token in ["streamlit", "vue", "fastapi", "frontend", "backend", "api"]):
            return {"canonical_topic": "tech_route", "suggested_label": "tech_route", "confidence": 0.75, "reason": "mock_semantic_topic"}
        if any(token in summary for token in ["risk", "fail", "unstable", "blocker", "deploy"]):
            return {"canonical_topic": "risk", "suggested_label": "risk", "confidence": 0.7, "reason": "mock_semantic_topic"}
        if any(token in summary for token in ["deadline", "review", "next friday", "timeline", "schedule"]):
            return {"canonical_topic": "timeline", "suggested_label": "timeline", "confidence": 0.7, "reason": "mock_semantic_topic"}
        if any(token in summary for token in ["onboarding", "handoff", "new teammate", "background"]):
            return {"canonical_topic": "onboarding", "suggested_label": "onboarding", "confidence": 0.7, "reason": "mock_semantic_topic"}
        return {"canonical_topic": "general", "suggested_label": "general", "confidence": 0.4, "reason": "mock_semantic_topic"}

    def plan_query(self, query: str, candidate_topics: list[str]) -> dict[str, Any]:
        """Return a deterministic retrieval plan for local testing."""
        lowered = query.lower()
        if any(token in lowered for token in ["risk", "blocker", "problem"]):
            return {
                "query_type": "risk_lookup",
                "normalized_topic": "risk",
                "preferred_types": ["risk", "procedure", "fact"],
                "primary_types": ["risk", "procedure"],
                "strict_topic": True,
            }
        if any(token in lowered for token in ["new teammate", "onboarding", "handoff", "context"]):
            return {
                "query_type": "onboarding_lookup",
                "normalized_topic": "onboarding",
                "preferred_types": ["decision", "procedure", "fact"],
                "primary_types": ["decision", "procedure"],
                "strict_topic": True,
            }
        if any(token in lowered for token in ["current", "latest", "route", "stack", "frontend", "backend", "tech"]):
            return {
                "query_type": "current_state",
                "normalized_topic": "tech_route",
                "preferred_types": ["decision", "fact", "procedure"],
                "primary_types": ["decision"],
                "strict_topic": True,
            }
        return {
            "query_type": "general",
            "normalized_topic": None,
            "preferred_types": ["decision", "fact"],
            "primary_types": ["decision"],
            "strict_topic": False,
        }

    def judge_consolidation(self, primary: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        """Deterministic consolidation judgment for mock testing."""
        from app.core.window_builder import tokenize_text

        primary_type = str(primary.get("memory_type", ""))
        candidate_type = str(candidate.get("memory_type", ""))
        primary_topic = str(primary.get("topic", ""))
        candidate_topic = str(candidate.get("topic", ""))

        high_types = {"decision", "risk", "procedure"}
        support_types = {"fact", "preference", "episode"}

        if primary_topic != candidate_topic:
            return self._cons_result(False, "unrelated", 0.9, "Different topics.", "Topics do not match.")

        p_tokens = tokenize_text(str(primary.get("content", "")))
        c_tokens = tokenize_text(str(candidate.get("content", "")))
        content_overlap = (len(p_tokens & c_tokens) / min(len(p_tokens), len(c_tokens))) if p_tokens and c_tokens else 0.0

        if primary_type in high_types and candidate_type in high_types:
            if content_overlap >= 0.6:
                return self._cons_result(True, "duplicate", 0.85,
                    f"Near-duplicate high-priority pair ({content_overlap:.2f} overlap).")
            return self._cons_result(False, "independent", 0.8,
                "Both are high-priority types; merging could lose distinct semantics.",
                "Two high-priority memories on the same topic should stay separate.")

        if primary_type in high_types and candidate_type in support_types:
            return self._cons_result(True, "support", 0.85,
                f"{candidate_type} naturally supports {primary_type}.")

        if primary_type in support_types and candidate_type in high_types:
            return self._cons_result(True, "support", 0.85,
                f"{primary_type} naturally supports {candidate_type}.")

        if primary_type in support_types and candidate_type in support_types:
            if content_overlap >= 0.3:
                relation = "duplicate" if primary_type == candidate_type else "support"
                return self._cons_result(True, relation, 0.8,
                    f"Support-type pair with high content overlap ({content_overlap:.2f}).")
            return self._cons_result(False, "unrelated", 0.5,
                "Low content overlap between support types.", "No clear merge signal.")

        return self._cons_result(False, "unrelated", 0.5,
            "MockLLM default: keep separate.", "No clear merge signal.")

    def _cons_result(
        self, merge: bool, relation: str, confidence: float, reason: str,
        keep_separate: str | None = None,
    ) -> dict[str, Any]:
        return {
            "merge_decision": merge,
            "relation": relation,
            "merge_role": "support" if merge and relation == "support" else None,
            "reason": reason,
            "confidence": confidence,
            "keep_separate_reason": keep_separate,
        }


class OpenAICompatibleProvider:
    """Shared implementation for OpenAI-compatible chat completion providers."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        provider_label: str,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") + "/"
        self.model = model
        self.provider_label = provider_label
        if not self.api_key:
            raise ValueError(f"{provider_label} API key is not configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for real providers. "
                "Install it with `pip install openai` or keep using mock mode."
            ) from exc
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def extract_memories(self, events: list[dict[str, Any]], extraction_hints: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Call the provider to extract structured memories from normalized events."""
        if not events:
            return []

        payload: dict[str, Any] = {
            "events": [
                {
                    "event_id": event.get("event_id"),
                    "project_id": event.get("project_id"),
                    "chat_id": event.get("chat_id"),
                    "actor_name": event.get("actor_name"),
                    "content": event.get("content"),
                    "time": event.get("transaction_time"),
                }
                for event in events
            ],
            "output_schema": {
                "memories": [
                    {
                        "memory_id": "string",
                        "version_group_id": "string|null",
                        "memory_type": "decision|fact|procedure|risk|preference|episode|skill",
                        "scope": "user|team|project|org",
                        "tenant_id": "string|null",
                        "project_id": "string|null",
                        "topic": "string|null",
                        "title": "string",
                        "content": "string",
                        "rationale": ["string"],
                        "objections": ["string"],
                        "tags": ["string"],
                        "status": "pending|active|superseded|expired|archived|conflicted|rejected",
                        "version": "integer >= 1",
                        "confidence": "0.0-1.0",
                        "importance": "1-5",
                        "valid_time_start": "ISO-8601 string",
                        "valid_time_end": "ISO-8601 string|null",
                        "transaction_time": "ISO-8601 string",
                        "source_event_ids": ["event_id"],
                    }
                ]
            },
        }

        if extraction_hints:
            payload["context"] = extraction_hints

        context_clause = ""
        if extraction_hints:
            if extraction_hints.get("existing_memory_titles"):
                titles = ", ".join(extraction_hints["existing_memory_titles"])
                context_clause += f" The following memories already exist for this topic: [{titles}]. Do NOT re-extract information already covered by these memories."
            if extraction_hints.get("bridge_context"):
                context_clause += " Some messages from the preceding conversation are included as bridge_context for continuity."
            if extraction_hints.get("recent_topics"):
                topics = ", ".join(extraction_hints["recent_topics"])
                context_clause += f" Recent discussion topics: [{topics}]."

        prompt = (
            "You are the memory extraction component of MARS. "
            "Read the normalized collaboration events and return strict JSON only. "
            "Extract only durable project memory candidates such as decisions, facts, procedures, risks, or preferences. "
            "Do not include explanations outside JSON. "
            "Use the provided event IDs in source_event_ids. "
            "Prefer one concise memory per coherent topic unless there are clearly multiple durable memories."
            + context_clause
        )

        content = self._chat_json(system_prompt=prompt, user_payload=payload)
        parsed = self._parse_json(content)
        memories = parsed.get("memories", [])
        if not isinstance(memories, list):
            raise ValueError(f"{self.provider_label} extraction response did not contain a valid memories list.")
        return memories

    def judge_relation(self, new_memory: dict[str, Any], existing_memories: list[dict[str, Any]]) -> dict[str, Any]:
        """Call the provider to judge semantic relation between memories."""
        if not existing_memories:
            return {"relation": "unrelated", "reason": "No existing candidate memories were provided.", "confidence": 1.0}

        payload = {
            "new_memory": new_memory,
            "existing_memories": existing_memories,
            "allowed_relations": ["duplicate", "support", "update", "conflict", "supersedes", "unrelated"],
            "output_schema": {
                "relation": "duplicate|support|update|conflict|supersedes|unrelated",
                "reason": "string",
                "confidence": "0.0-1.0",
            },
        }
        prompt = (
            "You are the reconciliation component of MARS. "
            "Compare one new memory candidate against existing project memories. "
            "Return strict JSON only. "
            "Choose 'supersedes' only when the new memory clearly replaces the old active memory. "
            "Choose 'conflict' when there is contradiction without a clear replacement. "
            "Choose 'duplicate' when they mean the same thing."
        )
        content = self._chat_json(system_prompt=prompt, user_payload=payload)
        parsed = self._parse_json(content)
        return {
            "relation": parsed.get("relation", "unrelated"),
            "reason": parsed.get("reason", "No reason provided."),
            "confidence": float(parsed.get("confidence", 0.0)),
        }

    def generate_answer(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        query_type: str,
    ) -> dict[str, Any]:
        """Generate a structured user-facing answer from retrieved memories."""
        payload = {
            "query": query,
            "query_type": query_type,
            "evidence": evidence,
            "output_schema": {
                "current_conclusion": "string",
                "basis": ["string"],
                "risks": ["string"],
                "uncertainties": ["string"],
                "final_answer": "string",
            },
        }
        prompt = (
            "You are the answer composition component of MARS. "
            "Read the retrieved memory evidence and answer the user query. "
            "Return strict JSON only. "
            "Synthesize the current conclusion, supporting basis, active risks, and any remaining uncertainties. "
            "Do not invent facts outside the supplied evidence."
        )
        content = self._chat_json(system_prompt=prompt, user_payload=payload)
        parsed = self._parse_json(content)
        return {
            "current_conclusion": parsed.get("current_conclusion", ""),
            "basis": parsed.get("basis", []),
            "risks": parsed.get("risks", []),
            "uncertainties": parsed.get("uncertainties", []),
            "final_answer": parsed.get("final_answer", ""),
        }

    def classify_topic(
        self,
        window: dict[str, Any],
        candidate_topics: list[str],
        previous_topics: list[str],
    ) -> dict[str, Any]:
        """Classify one discussion window into a canonical or concise semantic topic."""
        payload = {
            "window": window,
            "candidate_topics": candidate_topics,
            "previous_topics": previous_topics,
            "output_schema": {
                "canonical_topic": "string",
                "suggested_label": "string",
                "confidence": "0.0-1.0",
                "reason": "string",
            },
        }
        prompt = (
            "You are the topic classification component of MARS. "
            "Read one discussion window and decide its best topic. "
            "Prefer one canonical topic from candidate_topics when possible. "
            "If none fit well, use canonical_topic='general' and provide a short suggested_label. "
            "Return strict JSON only."
        )
        content = self._chat_json(system_prompt=prompt, user_payload=payload)
        parsed = self._parse_json(content)
        return {
            "canonical_topic": str(parsed.get("canonical_topic", "general")).strip() or "general",
            "suggested_label": str(parsed.get("suggested_label", "general")).strip() or "general",
            "confidence": float(parsed.get("confidence", 0.0)),
            "reason": str(parsed.get("reason", "llm_topic_classification")),
        }

    def plan_query(self, query: str, candidate_topics: list[str]) -> dict[str, Any]:
        """Build a retrieval plan from a free-form user query."""
        payload = {
            "query": query,
            "candidate_topics": candidate_topics,
            "allowed_query_types": [
                "current_state",
                "risk_lookup",
                "reporting_lookup",
                "onboarding_lookup",
                "timeline_lookup",
                "explanation",
                "general",
            ],
            "allowed_memory_types": ["decision", "fact", "procedure", "risk", "preference", "episode", "skill"],
            "output_schema": {
                "query_type": "string",
                "normalized_topic": "string|null",
                "preferred_types": ["string"],
                "primary_types": ["string"],
                "strict_topic": "boolean",
                "reason": "string",
            },
        }
        prompt = (
            "You are the query planning component of MARS. "
            "Classify the user query into one retrieval intent and choose the best normalized topic if any. "
            "Use candidate_topics when relevant, but return normalized_topic=null if the query is broad. "
            "Return strict JSON only."
        )
        content = self._chat_json(system_prompt=prompt, user_payload=payload)
        parsed = self._parse_json(content)
        return {
            "query_type": str(parsed.get("query_type", "general")).strip() or "general",
            "normalized_topic": parsed.get("normalized_topic"),
            "preferred_types": parsed.get("preferred_types", []),
            "primary_types": parsed.get("primary_types", []),
            "strict_topic": bool(parsed.get("strict_topic", False)),
            "reason": str(parsed.get("reason", "llm_query_planning")),
        }

    def judge_consolidation(self, primary: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        """Judge whether two same-batch memories should be merged during consolidation."""
        payload = {
            "primary_memory": {
                "memory_type": primary.get("memory_type"),
                "topic": primary.get("topic"),
                "title": primary.get("title"),
                "content": primary.get("content"),
                "source_event_ids": primary.get("source_event_ids", []),
                "confidence": primary.get("confidence"),
                "importance": primary.get("importance"),
            },
            "candidate_memory": {
                "memory_type": candidate.get("memory_type"),
                "topic": candidate.get("topic"),
                "title": candidate.get("title"),
                "content": candidate.get("content"),
                "source_event_ids": candidate.get("source_event_ids", []),
                "confidence": candidate.get("confidence"),
                "importance": candidate.get("importance"),
            },
            "output_schema": {
                "merge_decision": "boolean",
                "relation": "support|duplicate|independent|unrelated",
                "merge_role": "support|null",
                "reason": "string",
                "confidence": "0.0-1.0",
                "keep_separate_reason": "string|null",
            },
        }
        prompt = (
            "You are the consolidation component of MARS. "
            "Two memory candidates were extracted from the same batch of conversation events. "
            "Decide whether the candidate should be merged into the primary, or kept separate.\n\n"

            "RELATION TYPES (choose exactly one):\n"
            "- support: candidate adds background, rationale, or context to the primary. "
            "Typical: fact supporting a decision, preference explaining a choice. merge_decision=true.\n"
            "- duplicate: candidate says the same thing as primary in different words. merge_decision=true.\n"
            "- independent: candidate is a separate durable memory worth preserving on its own. merge_decision=false.\n"
            "- unrelated: candidate has no meaningful connection to primary. merge_decision=false.\n\n"

            "RULES:\n"
            "1. merge_decision=true ONLY when relation is support or duplicate.\n"
            "2. merge_decision=false ALWAYS when relation is independent or unrelated.\n"
            "3. Same topic does NOT mean same memory. Two facts about the same project that describe "
            "different things must stay separate.\n"
            "4. Different stakeholder preferences must stay separate even on the same topic.\n\n"

            "TYPE COMBINATION GUIDELINES:\n"
            "- decision + fact/preference -> likely support (fact provides basis, preference provides rationale)\n"
            "- risk + fact -> likely support (fact provides evidence for the risk)\n"
            "- decision + risk -> default independent (risk is a separate governance concern)\n"
            "- decision + procedure -> default independent (procedure is actionable, not just context)\n"
            "- risk + procedure -> default independent\n"
            "- Two high-priority types (decision+decision, risk+risk, procedure+procedure, etc.) -> "
            "default independent unless one is clearly just restating the other word-for-word.\n\n"

            "Return strict JSON matching the output_schema."
        )
        content = self._chat_json(system_prompt=prompt, user_payload=payload)
        parsed = self._parse_json(content)
        return {
            "merge_decision": bool(parsed.get("merge_decision", False)),
            "relation": str(parsed.get("relation", "unrelated")),
            "merge_role": parsed.get("merge_role"),
            "reason": str(parsed.get("reason", "No reason provided.")),
            "confidence": float(parsed.get("confidence", 0.0)),
            "keep_separate_reason": parsed.get("keep_separate_reason"),
        }

    def _chat_json(self, *, system_prompt: str, user_payload: dict[str, Any]) -> str:
        """Send one OpenAI-compatible chat request and return the text content."""
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        system_prompt
                        + " Return JSON only. Do not output markdown fences. "
                        + "Do not output <think> tags or any reasoning text."
                    ),
                },
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.1,
            top_p=0.8,
            response_format={"type": "json_object"},
        )
        message = response.choices[0].message
        return message.content or "{}"

    def _parse_json(self, content: str) -> dict[str, Any]:
        """Parse strict JSON and surface a clearer provider error if parsing fails."""
        normalized = extract_json_payload(content)
        try:
            return json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{self.provider_label} response was not valid JSON: {content}") from exc


class GLMProvider(OpenAICompatibleProvider):
    """Real GLM API provider using the OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        super().__init__(
            api_key=os.getenv("GLM_API_KEY") or os.getenv("MARS_GLM_API_KEY"),
            base_url=os.getenv("GLM_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4/",
            model=os.getenv("GLM_MODEL") or "glm-4.7",
            provider_label="GLM",
        )


class MiniMaxProvider(OpenAICompatibleProvider):
    """Real MiniMax API provider using the official OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        super().__init__(
            api_key=os.getenv("MINIMAX_API_KEY") or os.getenv("MARS_MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("MINIMAX_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.minimaxi.com/v1",
            model=os.getenv("MINIMAX_MODEL") or "MiniMax-M2.7",
            provider_label="MiniMax",
        )


def extract_json_payload(content: str) -> str:
    """Extract the JSON body from provider text that may include reasoning wrappers."""
    text = content.strip()
    if not text:
        return text

    fenced_match = re.search(r"```json\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced_match:
        return fenced_match.group(1).strip()

    think_closed_index = text.rfind("</think>")
    if think_closed_index != -1:
        candidate = text[think_closed_index + len("</think>") :].strip()
        if candidate:
            text = candidate

    obj_start = text.find("{")
    obj_end = text.rfind("}")
    arr_start = text.find("[")
    arr_end = text.rfind("]")

    obj_valid = obj_start != -1 and obj_end != -1 and obj_end > obj_start
    arr_valid = arr_start != -1 and arr_end != -1 and arr_end > arr_start

    if obj_valid and arr_valid:
        start = min(obj_start, arr_start)
        end = max(obj_end, arr_end)
        return text[start : end + 1].strip()
    if obj_valid:
        return text[obj_start : obj_end + 1].strip()
    if arr_valid:
        return text[arr_start : arr_end + 1].strip()

    return text


def get_llm_provider() -> LLMProvider:
    """Return the configured provider, defaulting to the deterministic mock."""
    provider_name = (os.getenv("MARS_LLM_PROVIDER") or "mock").strip().lower()
    if provider_name == "mock":
        return MockLLM()
    if provider_name == "glm":
        return GLMProvider()
    if provider_name == "minimax":
        return MiniMaxProvider()
    raise ValueError(f"Unsupported MARS_LLM_PROVIDER value: {provider_name}")
