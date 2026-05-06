"""Supervisor / router implementation."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.schemas import AgentName, AgentResult, RouteName
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span


class SupervisorAgent(BaseAgent):
    """Decides which worker should run next and when to stop."""

    name = "supervisor"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(self, state: ResearchState) -> ResearchState:
        """Update `state.route_history` with the next route."""

        with trace_span("agent.supervisor", {"iteration": state.iteration}) as span:
            route, reason = self._decide_route(state)
            state.record_route(route.value)
            content = f"Route to {route.value}: {reason}"
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.SUPERVISOR,
                    content=content,
                    metadata={"route": route.value, "reason": reason},
                )
            )
            span["outputs"] = {"route": route.value, "reason": reason}
        state.add_trace_event("agent.supervisor", span)
        return state

    def _decide_route(self, state: ResearchState) -> tuple[RouteName, str]:
        if state.iteration >= self.settings.max_iterations:
            if state.final_answer:
                return RouteName.DONE, "max iterations reached and final answer exists"
            return RouteName.WRITER, "max iterations reached; produce best-effort answer"

        if state.errors and len(state.errors) >= 3:
            if state.final_answer:
                return RouteName.DONE, "multiple errors observed after final answer"
            return RouteName.WRITER, "multiple errors observed; produce fallback answer"

        if not state.sources or not state.research_notes:
            return RouteName.RESEARCHER, "research notes and sources are missing"

        if not state.analysis_notes:
            return RouteName.ANALYST, "analysis notes are missing"

        if not state.final_answer:
            return RouteName.WRITER, "final answer is missing"

        if state.citation_coverage is None:
            return RouteName.CRITIC, "final answer needs citation validation"

        if state.citation_feedback and state.revision_count < 2:
            return RouteName.WRITER, "citation coverage is below threshold; revise answer"

        if state.citation_feedback:
            return RouteName.DONE, "citation coverage remains low after revision budget"

        return RouteName.DONE, "all required outputs are present"
