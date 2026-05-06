"""Search client abstraction for ResearcherAgent."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib import request
from urllib.error import URLError

from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.schemas import SourceDocument

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResponse:
    sources: list[SourceDocument]
    provider: str


class SearchClient:
    """Provider-agnostic search client.

    Uses Tavily when `TAVILY_API_KEY` is configured. Without a key it searches a small
    curated local corpus that keeps development deterministic and makes missing web
    credentials explicit in metadata.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
        """Search for documents relevant to a query."""

        return self.search_with_metadata(query, max_results).sources

    def search_with_metadata(self, query: str, max_results: int = 5) -> SearchResponse:
        if self.settings.tavily_api_key:
            try:
                return SearchResponse(
                    sources=self._search_tavily(query, max_results),
                    provider="tavily",
                )
            except (TimeoutError, URLError, OSError, ValueError) as exc:
                LOGGER.warning("Tavily search failed (%s); falling back to local corpus", exc)
        return SearchResponse(sources=_search_local_corpus(query, max_results), provider="local")

    def _search_tavily(self, query: str, max_results: int) -> list[SourceDocument]:
        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": self.settings.tavily_search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        encoded = json.dumps(payload).encode("utf-8")
        tavily_request = request.Request(
            "https://api.tavily.com/search",
            data=encoded,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(tavily_request, timeout=self.settings.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))

        results = data.get("results", [])
        sources: list[SourceDocument] = []
        for index, item in enumerate(results[:max_results], start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or f"Search result {index}")
            url = item.get("url")
            content = str(item.get("content") or item.get("snippet") or "")
            if not content:
                continue
            sources.append(
                SourceDocument(
                    title=title,
                    url=str(url) if url else None,
                    snippet=content,
                    metadata={"provider": "tavily", "rank": index, "score": item.get("score")},
                )
            )
        return sources


LOCAL_CORPUS = [
    SourceDocument(
        title="Anthropic: Building effective agents",
        url="https://www.anthropic.com/engineering/building-effective-agents",
        snippet=(
            "Effective agentic systems often start with simple workflows. Add autonomy only "
            "when clear task decomposition, tool use, and evaluation justify the extra control "
            "flow and latency."
        ),
        metadata={"provider": "local", "topic": "agent design"},
    ),
    SourceDocument(
        title="OpenAI Agents orchestration patterns",
        url="https://developers.openai.com/api/docs/guides/agents/orchestration",
        snippet=(
            "Agent orchestration relies on explicit handoffs, tool boundaries, instructions, "
            "and state passed between specialized agents."
        ),
        metadata={"provider": "local", "topic": "orchestration"},
    ),
    SourceDocument(
        title="LangGraph workflow concepts",
        url="https://langchain-ai.github.io/langgraph/concepts/",
        snippet=(
            "LangGraph models workflows as stateful graphs with nodes, edges, conditional "
            "routing, persistence, and controllable execution."
        ),
        metadata={"provider": "local", "topic": "workflow"},
    ),
    SourceDocument(
        title="LangSmith tracing",
        url="https://docs.smith.langchain.com/",
        snippet=(
            "Tracing captures inputs, outputs, errors, timing, and metadata so teams can debug "
            "agent decisions and evaluate quality over time."
        ),
        metadata={"provider": "local", "topic": "observability"},
    ),
    SourceDocument(
        title="Benchmarking LLM systems",
        url=None,
        snippet=(
            "A useful benchmark includes latency, cost, quality rubric scores, citation "
            "coverage, and failure rate across representative queries."
        ),
        metadata={"provider": "local", "topic": "evaluation"},
    ),
]


def _search_local_corpus(query: str, max_results: int) -> list[SourceDocument]:
    query_terms = {term.lower().strip(".,:;!?()[]") for term in query.split()}
    scored: list[tuple[int, SourceDocument]] = []
    for source in LOCAL_CORPUS:
        haystack = f"{source.title} {source.snippet} {source.metadata}".lower()
        score = sum(1 for term in query_terms if term and term in haystack)
        scored.append((score, source))
    ranked = sorted(scored, key=lambda item: item[0], reverse=True)
    return [
        source.model_copy(update={"metadata": {**source.metadata, "rank": index + 1}})
        for index, (_, source) in enumerate(ranked[:max_results])
    ]
