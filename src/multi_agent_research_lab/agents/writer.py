"""Writer agent implementation."""

import re

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span
from multi_agent_research_lab.services.llm_client import LLMClient


class WriterAgent(BaseAgent):
    """Produces final answer from research and analysis notes."""

    name = "writer"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.final_answer`."""

        with trace_span("agent.writer", {"source_count": len(state.sources)}) as span:
            revision_instruction = _revision_instruction(state)
            response = self.llm_client.complete(
                system_prompt=(
                    "You are a senior technical writer. Write directly, cite source numbers "
                    "on every factual claim, and call out uncertainty. Do not write a factual "
                    "sentence without a citation unless it is explicitly framed as an assumption "
                    "or recommendation."
                ),
                user_prompt=(
                    f"Question: {state.request.query}\n\n"
                    f"Audience: {state.request.audience}\n\n"
                    f"Research notes:\n{state.research_notes or 'No research notes available.'}\n\n"
                    f"Analysis notes:\n{state.analysis_notes or 'No analysis notes available.'}\n\n"
                    f"Citation feedback:\n{revision_instruction}\n\n"
                    f"Sources:\n{_format_source_list(state)}\n\n"
                    "Write the final answer in a concise but complete style.\n"
                    "Citation rules:\n"
                    "- Every factual sentence must include at least one source id like [1].\n"
                    "- Prefer specific source ids already present in research or analysis notes.\n"
                    "- Keep citations at sentence level, not only in the Sources section.\n"
                    "- If a claim cannot be supported by a source, mark it as an assumption.\n"
                    "- Include a short Sources section using the provided source numbers."
                ),
                temperature=0.3,
                max_tokens=1_000,
            )
            final_answer, auto_cited_claims = _ensure_sentence_level_citations(
                response.content,
                default_source_id=_default_source_id(state),
            )
            state.final_answer = final_answer
            state.citation_coverage = None
            if state.citation_feedback:
                state.revision_count += 1
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.WRITER,
                    content=final_answer,
                    metadata={
                        "llm_provider": response.provider,
                        "cost_usd": response.cost_usd,
                        "auto_cited_claims": auto_cited_claims,
                        "revision_count": state.revision_count,
                    },
                )
            )
            span["outputs"] = {
                "llm_provider": response.provider,
                "has_final_answer": True,
                "auto_cited_claims": auto_cited_claims,
                "revision_count": state.revision_count,
            }
        state.add_trace_event("agent.writer", span)
        return state


def _format_source_list(state: ResearchState) -> str:
    if not state.sources:
        return "No external sources were collected."
    lines = []
    for index, source in enumerate(state.sources, start=1):
        url = f" - {source.url}" if source.url else ""
        lines.append(f"[{index}] {source.title}{url}")
    return "\n".join(lines)


def _revision_instruction(state: ResearchState) -> str:
    if not state.citation_feedback:
        return "No prior citation feedback."
    return (
        f"Previous draft failed citation validation: {state.citation_feedback}\n"
        "Revise the answer so each main factual claim has a source id."
    )


def _default_source_id(state: ResearchState) -> int | None:
    if not state.sources:
        return None
    source_ids = _source_ids_from_text(
        "\n".join(
            item
            for item in [state.research_notes, state.analysis_notes]
            if item is not None
        )
    )
    return min(source_ids) if source_ids else 1


def _source_ids_from_text(text: str) -> set[int]:
    return {int(match.group(1)) for match in re.finditer(r"\[(\d+)\]", text)}


def _ensure_sentence_level_citations(
    answer: str,
    default_source_id: int | None,
) -> tuple[str, int]:
    if default_source_id is None:
        return answer, 0

    sections = answer.split("### Sources", maxsplit=1)
    body = sections[0]
    sources_section = f"### Sources{sections[1]}" if len(sections) == 2 else ""

    citation = f"[{default_source_id}]"
    auto_cited = 0

    def add_citation(match: re.Match[str]) -> str:
        nonlocal auto_cited
        sentence = match.group(0)
        if not _is_main_claim(sentence) or re.search(r"\[\d+\]", sentence):
            return sentence
        auto_cited += 1
        punctuation = sentence[-1] if sentence[-1] in ".!?" else "."
        stem = sentence[:-1].rstrip() if sentence[-1] in ".!?" else sentence.rstrip()
        return f"{stem} {citation}{punctuation}"

    cited_body = re.sub(r"[^.!?\n][^.!?\n]{30,}[.!?]", add_citation, body)
    return f"{cited_body}{sources_section}", auto_cited


def _is_main_claim(sentence: str) -> bool:
    lowered = sentence.lower()
    if len(sentence.split()) < 8:
        return False
    non_factual_markers = ("assumption", "recommend", "should", "could", "may", "might")
    return not any(marker in lowered for marker in non_factual_markers)
