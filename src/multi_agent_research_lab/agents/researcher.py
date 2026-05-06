"""Researcher agent implementation."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult, SourceDocument
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.search_client import SearchClient


class ResearcherAgent(BaseAgent):
    """Collects sources and creates concise research notes."""

    name = "researcher"

    def __init__(
        self,
        search_client: SearchClient | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.search_client = search_client or SearchClient()
        self.llm_client = llm_client or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.sources` and `state.research_notes`."""

        with trace_span("agent.researcher", {"query": state.request.query}) as span:
            search_response = self.search_client.search_with_metadata(
                state.request.query,
                max_results=state.request.max_sources,
            )
            state.sources = _dedupe_sources([*state.sources, *search_response.sources])[
                : state.request.max_sources
            ]
            notes_response = self.llm_client.complete(
                system_prompt=(
                    "You are a careful research agent. Extract only evidence grounded in the "
                    "provided sources. Preserve source numbers for later citation."
                ),
                user_prompt=(
                    f"Research question: {state.request.query}\n\n"
                    f"Audience: {state.request.audience}\n\n"
                    f"Sources:\n{_format_sources(state.sources)}\n\n"
                    "Write concise research notes with 4-6 bullets. Each bullet must cite the "
                    "source number in brackets, such as [1]."
                ),
                temperature=0.1,
                max_tokens=700,
            )
            state.research_notes = notes_response.content
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.RESEARCHER,
                    content=notes_response.content,
                    metadata={
                        "source_count": len(state.sources),
                        "search_provider": search_response.provider,
                        "llm_provider": notes_response.provider,
                        "cost_usd": notes_response.cost_usd,
                    },
                )
            )
            span["outputs"] = {
                "source_count": len(state.sources),
                "search_provider": search_response.provider,
                "llm_provider": notes_response.provider,
            }
        state.add_trace_event("agent.researcher", span)
        return state


def _dedupe_sources(sources: list[SourceDocument]) -> list[SourceDocument]:
    seen: set[str] = set()
    unique: list[SourceDocument] = []
    for source in sources:
        key = source.url or f"{source.title}:{source.snippet[:60]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)
    return unique


def _format_sources(sources: list[SourceDocument]) -> str:
    lines: list[str] = []
    for index, source in enumerate(sources, start=1):
        url = f" ({source.url})" if source.url else ""
        lines.append(f"[{index}] {source.title}{url}\nSnippet: {source.snippet}")
    return "\n\n".join(lines)
