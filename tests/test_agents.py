import pytest

from multi_agent_research_lab.agents import SupervisorAgent
from multi_agent_research_lab.agents.writer import _ensure_sentence_level_citations
from multi_agent_research_lab.core.schemas import ResearchQuery, RouteName, SourceDocument
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph import workflow as workflow_module
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow


def test_supervisor_routes_to_researcher_when_research_is_missing() -> None:
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    result = SupervisorAgent().run(state)
    assert result.next_route == RouteName.RESEARCHER
    assert result.route_history == ["researcher"]


def test_supervisor_routes_to_writer_when_analysis_exists() -> None:
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent systems"),
        sources=[SourceDocument(title="Source", snippet="Evidence", url=None)],
        research_notes="Research notes",
        analysis_notes="Analysis notes",
    )
    result = SupervisorAgent().run(state)
    assert result.next_route == RouteName.WRITER


def test_supervisor_routes_final_answer_to_critic() -> None:
    state = ResearchState(
        request=ResearchQuery(query="Explain multi-agent systems"),
        sources=[SourceDocument(title="Source", snippet="Evidence", url=None)],
        research_notes="Research notes [1]",
        analysis_notes="Analysis notes [1]",
        final_answer="A factual answer with a citation [1].",
    )
    result = SupervisorAgent().run(state)
    assert result.next_route == RouteName.CRITIC


def test_writer_auto_citation_attaches_before_punctuation() -> None:
    answer, auto_cited = _ensure_sentence_level_citations(
        "GraphRAG improves traceability for complex retrieval workflows in production systems.",
        default_source_id=1,
    )
    assert auto_cited == 1
    assert "systems [1]." in answer


def test_workflow_runs_offline_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import_module = workflow_module.importlib.import_module

    def raise_missing_langgraph(name: str) -> object:
        if name == "langgraph.graph":
            raise ModuleNotFoundError(name)
        return original_import_module(name)

    monkeypatch.setattr(workflow_module.importlib, "import_module", raise_missing_langgraph)
    state = ResearchState(request=ResearchQuery(query="Explain multi-agent systems"))
    result = MultiAgentWorkflow().run(state)
    assert result.research_notes
    assert result.analysis_notes
    assert result.final_answer
    assert result.next_route == RouteName.DONE
    assert "critic" in result.route_history
    assert result.citation_coverage is not None
    assert not result.errors
