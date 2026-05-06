"""Command-line entrypoint for the lab."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml  # type: ignore[import-untyped]
from rich.console import Console
from rich.panel import Panel

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.schemas import AgentName, AgentResult, ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.benchmark import run_benchmark
from multi_agent_research_lab.evaluation.report import render_markdown_report
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow
from multi_agent_research_lab.observability.logging import configure_logging
from multi_agent_research_lab.services.llm_client import LLMClient
from multi_agent_research_lab.services.storage import LocalArtifactStore

app = typer.Typer(help="Multi-Agent Research Lab CLI")
console = Console()


def _init() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)


@app.command()
def baseline(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
) -> None:
    """Run a single-agent baseline."""

    _init()
    state = run_baseline(query)
    console.print(Panel.fit(state.final_answer or "", title="Single-Agent Baseline"))


@app.command("multi-agent")
def multi_agent(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
) -> None:
    """Run the multi-agent workflow."""

    _init()
    state = ResearchState(request=ResearchQuery(query=query))
    workflow = MultiAgentWorkflow()
    result = workflow.run(state)
    console.print(result.model_dump_json(indent=2))


@app.command()
def benchmark(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="YAML config with benchmark queries"),
    ] = Path("configs/lab_default.yaml"),
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Markdown report output path"),
    ] = Path("reports/benchmark_report.md"),
) -> None:
    """Benchmark baseline and multi-agent runs and write a report."""

    _init()
    benchmark_config = _load_benchmark_config(config)
    metrics = []
    store = LocalArtifactStore(output.parent)
    for index, query in enumerate(benchmark_config.queries, start=1):
        baseline_name = f"baseline-{index}"
        multi_agent_name = f"multi-agent-{index}"
        baseline_state, baseline_metrics = run_benchmark(
            baseline_name,
            query,
            run_baseline,
            peer_quality_score=benchmark_config.peer_review_scores.get(baseline_name),
        )
        multi_state, multi_metrics = run_benchmark(
            multi_agent_name,
            query,
            lambda item: MultiAgentWorkflow().run(ResearchState(request=ResearchQuery(query=item))),
            peer_quality_score=benchmark_config.peer_review_scores.get(multi_agent_name),
        )
        metrics.extend([baseline_metrics, multi_metrics])
        store.write_text(
            f"traces/query_{index}_baseline.json",
            baseline_state.model_dump_json(indent=2),
        )
        store.write_text(
            f"traces/query_{index}_multi_agent.json",
            multi_state.model_dump_json(indent=2),
        )
    report = render_markdown_report(metrics)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    console.print(Panel.fit(str(output), title="Benchmark Report Written"))


def run_baseline(query: str) -> ResearchState:
    request = ResearchQuery(query=query)
    state = ResearchState(request=request)
    client = LLMClient()
    response = client.complete(
        system_prompt=(
            "You are a single-agent research assistant. Answer the user's question directly, "
            "and mention limitations when you do not have live search context."
        ),
        user_prompt=(
            f"Question: {query}\n\n"
            "Produce a concise, useful answer. Include assumptions and note whether external "
            "research was available."
        ),
        temperature=0.2,
        max_tokens=1_000,
    )
    state.final_answer = response.content
    state.agent_results.append(
        AgentResult(
            agent=AgentName.WRITER,
            content=response.content,
            metadata={
                "mode": "single-agent",
                "llm_provider": response.provider,
                "cost_usd": response.cost_usd,
            },
        )
    )
    state.add_trace_event(
        "baseline.single_agent",
        {"llm_provider": response.provider, "model": response.model},
    )
    return state


@dataclass(frozen=True)
class BenchmarkConfig:
    queries: list[str]
    peer_review_scores: dict[str, float]


def _load_benchmark_config(config: Path) -> BenchmarkConfig:
    if not config.exists():
        raise typer.BadParameter(f"Config file not found: {config}")
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise typer.BadParameter("Benchmark config must be a YAML mapping")
    benchmark_config: Any = data.get("benchmark", {})
    queries: Any = benchmark_config.get("queries", [])
    if not isinstance(queries, list) or not all(isinstance(item, str) for item in queries):
        raise typer.BadParameter("benchmark.queries must be a list of strings")
    peer_review_scores = _parse_peer_review_scores(benchmark_config.get("peer_review_scores", {}))
    return BenchmarkConfig(queries=queries, peer_review_scores=peer_review_scores)


def _parse_peer_review_scores(raw_scores: Any) -> dict[str, float]:
    if raw_scores is None:
        return {}
    if not isinstance(raw_scores, dict):
        raise typer.BadParameter("benchmark.peer_review_scores must be a mapping")
    scores: dict[str, float] = {}
    for run_name, score in raw_scores.items():
        if not isinstance(run_name, str):
            raise typer.BadParameter("peer review score keys must be run names")
        if not isinstance(score, (int, float)) or not 0 <= float(score) <= 10:
            raise typer.BadParameter("peer review scores must be numbers from 0 to 10")
        scores[run_name] = float(score)
    return scores


if __name__ == "__main__":
    app()
