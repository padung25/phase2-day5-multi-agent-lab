"""Analyst agent implementation."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span
from multi_agent_research_lab.services.llm_client import LLMClient


class AnalystAgent(BaseAgent):
    """Turns research notes into structured insights."""

    name = "analyst"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.analysis_notes`."""

        with trace_span("agent.analyst", {"source_count": len(state.sources)}) as span:
            if not state.research_notes:
                message = "Cannot analyze because research_notes are missing."
                state.errors.append(message)
                state.analysis_notes = message
            else:
                response = self.llm_client.complete(
                    system_prompt=(
                        "You are an analytical agent. Separate evidence-backed claims from "
                        "assumptions. Preserve source ids like [1] from the research notes "
                        "on every evidence-backed claim. Highlight tradeoffs and weak evidence."
                    ),
                    user_prompt=(
                        f"Question: {state.request.query}\n\n"
                        f"Research notes:\n{state.research_notes}\n\n"
                        "Produce structured analysis with sections: Key claims, Tradeoffs, "
                        "Risks or weak evidence, and Recommendation. Every factual claim in "
                        "Key claims and Recommendation must include one or more source ids "
                        "from the research notes, for example [1] or [2][4]. If a point is "
                        "an assumption, label it explicitly instead of citing it."
                    ),
                    temperature=0.1,
                    max_tokens=800,
                )
                state.analysis_notes = response.content
                state.agent_results.append(
                    AgentResult(
                        agent=AgentName.ANALYST,
                        content=response.content,
                        metadata={
                            "llm_provider": response.provider,
                            "cost_usd": response.cost_usd,
                        },
                    )
                )
                span["outputs"] = {"llm_provider": response.provider}
        state.add_trace_event("agent.analyst", span)
        return state
