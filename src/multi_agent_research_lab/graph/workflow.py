"""LangGraph workflow implementation."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import Any, cast

from multi_agent_research_lab.agents import (
    AnalystAgent,
    CriticAgent,
    ResearcherAgent,
    SupervisorAgent,
    WriterAgent,
)
from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.config import Settings, get_settings
from multi_agent_research_lab.core.schemas import RouteName
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span

LOGGER = logging.getLogger(__name__)

StatePayload = dict[str, Any]


class MultiAgentWorkflow:
    """Builds and runs the multi-agent graph.

    Keep orchestration here; keep agent internals in `agents/`.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        supervisor: SupervisorAgent | None = None,
        researcher: ResearcherAgent | None = None,
        analyst: AnalystAgent | None = None,
        writer: WriterAgent | None = None,
        critic: CriticAgent | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.supervisor = supervisor or SupervisorAgent(self.settings)
        self.researcher = researcher or ResearcherAgent()
        self.analyst = analyst or AnalystAgent()
        self.writer = writer or WriterAgent()
        self.critic = critic or CriticAgent()
        self._compiled_graph: Any | None = None

    def build(self) -> object:
        """Create a LangGraph graph when the optional dependency is installed."""

        try:
            graph_module = importlib.import_module("langgraph.graph")
        except ModuleNotFoundError:
            LOGGER.warning("LangGraph is not installed; using local workflow executor")
            return LocalWorkflowGraph(self._run_local)

        state_graph = graph_module.StateGraph(dict)
        end = graph_module.END
        state_graph.add_node("supervisor", self._node(self.supervisor))
        state_graph.add_node("researcher", self._node(self.researcher))
        state_graph.add_node("analyst", self._node(self.analyst))
        state_graph.add_node("writer", self._node(self.writer))
        state_graph.add_node("critic", self._node(self.critic))
        state_graph.set_entry_point("supervisor")
        state_graph.add_conditional_edges(
            "supervisor",
            _route_from_payload,
            {
                RouteName.RESEARCHER.value: "researcher",
                RouteName.ANALYST.value: "analyst",
                RouteName.WRITER.value: "writer",
                RouteName.CRITIC.value: "critic",
                RouteName.DONE.value: end,
            },
        )
        state_graph.add_edge("researcher", "supervisor")
        state_graph.add_edge("analyst", "supervisor")
        state_graph.add_edge("writer", "supervisor")
        state_graph.add_edge("critic", "supervisor")
        self._compiled_graph = state_graph.compile()
        return self._compiled_graph

    def run(self, state: ResearchState) -> ResearchState:
        """Execute the graph and return final state."""

        with trace_span("workflow.multi_agent", {"query": state.request.query}) as span:
            graph = self._compiled_graph or self.build()
            if isinstance(graph, LocalWorkflowGraph):
                result = graph.invoke(state)
            else:
                compiled_graph = cast(Any, graph)
                payload = compiled_graph.invoke(state.model_dump(mode="json"))
                result = ResearchState.model_validate(payload)
            span["outputs"] = {
                "route_history": result.route_history,
                "error_count": len(result.errors),
                "has_final_answer": bool(result.final_answer),
            }
        result.add_trace_event("workflow.multi_agent", span)
        return result

    def _node(self, agent: BaseAgent) -> Callable[[StatePayload], StatePayload]:
        def invoke(payload: StatePayload) -> StatePayload:
            state = ResearchState.model_validate(payload)
            return self._run_agent(agent, state).model_dump(mode="json")

        return invoke

    def _run_local(self, state: ResearchState) -> ResearchState:
        while True:
            state = self._run_agent(self.supervisor, state)
            route = state.next_route or RouteName.DONE
            if route == RouteName.DONE:
                break
            if route == RouteName.RESEARCHER:
                state = self._run_agent(self.researcher, state)
            elif route == RouteName.ANALYST:
                state = self._run_agent(self.analyst, state)
            elif route == RouteName.WRITER:
                state = self._run_agent(self.writer, state)
            elif route == RouteName.CRITIC:
                state = self._run_agent(self.critic, state)
            if state.iteration > self.settings.max_iterations + 2:
                state.errors.append("Workflow stopped by hard iteration guard.")
                break
        return state

    def _run_agent(self, agent: BaseAgent, state: ResearchState) -> ResearchState:
        try:
            return agent.run(state)
        except Exception as exc:
            LOGGER.exception("Agent %s failed", agent.name)
            state.errors.append(f"{agent.name} failed: {exc!r}")
            state.add_trace_event("agent.error", {"agent": agent.name, "error": repr(exc)})
            return state


class LocalWorkflowGraph:
    """Small adapter with LangGraph-like `invoke` for environments without extras."""

    def __init__(self, runner: Callable[[ResearchState], ResearchState]) -> None:
        self.runner = runner

    def invoke(self, state: ResearchState) -> ResearchState:
        return self.runner(state)


def _route_from_payload(payload: StatePayload) -> str:
    route = payload.get("next_route") or RouteName.DONE.value
    return str(route)
