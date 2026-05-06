"""Benchmark helpers for single-agent vs multi-agent runs."""

from __future__ import annotations

import re
from collections.abc import Callable
from time import perf_counter

from multi_agent_research_lab.core.schemas import BenchmarkMetrics
from multi_agent_research_lab.core.state import ResearchState

Runner = Callable[[str], ResearchState]


def run_benchmark(
    run_name: str,
    query: str,
    runner: Runner,
    peer_quality_score: float | None = None,
) -> tuple[ResearchState, BenchmarkMetrics]:
    """Measure latency, cost, citation coverage, errors, and a lightweight quality score."""

    started = perf_counter()
    state = runner(query)
    latency = perf_counter() - started
    cited_claims, total_claims = _claim_citation_counts(state)
    metrics = BenchmarkMetrics(
        run_name=run_name,
        latency_seconds=latency,
        estimated_cost_usd=_sum_cost(state),
        quality_score=peer_quality_score
        if peer_quality_score is not None
        else _heuristic_quality_score(state),
        quality_source="peer_review" if peer_quality_score is not None else "automated_proxy",
        citation_coverage=_citation_coverage(cited_claims, total_claims),
        cited_claims=cited_claims,
        total_claims=total_claims,
        error_count=len(state.errors),
        failed=_is_failed(state),
        notes=_summarize_notes(state),
    )
    return state, metrics


def _sum_cost(state: ResearchState) -> float | None:
    costs: list[float] = []
    for result in state.agent_results:
        cost = result.metadata.get("cost_usd")
        if isinstance(cost, (int, float)):
            costs.append(float(cost))
    if not costs:
        return None
    return sum(costs)


def _claim_citation_counts(state: ResearchState) -> tuple[int, int]:
    if not state.final_answer:
        return 0, 0
    claims = _extract_claims(state.final_answer)
    cited = sum(1 for claim in claims if re.search(r"\[(\d+)\]", claim))
    return cited, len(claims)


def _extract_claims(answer: str) -> list[str]:
    body = answer.split("Sources:", maxsplit=1)[0]
    raw_claims = re.split(r"(?<=[.!?])\s+|\n+-\s+|\n+\d+\.\s+", body)
    claims: list[str] = []
    for raw_claim in raw_claims:
        claim = raw_claim.strip(" \n\t-*")
        if len(claim.split()) >= 8:
            claims.append(claim)
    return claims


def _citation_coverage(cited_claims: int, total_claims: int) -> float | None:
    if total_claims == 0:
        return None
    return cited_claims / total_claims


def _heuristic_quality_score(state: ResearchState) -> float:
    score = 0.0
    if state.research_notes:
        score += 2.0
    if state.analysis_notes:
        score += 2.0
    if state.final_answer and len(state.final_answer.split()) >= 80:
        score += 2.0
    elif state.final_answer:
        score += 1.0
    cited_claims, total_claims = _claim_citation_counts(state)
    coverage = _citation_coverage(cited_claims, total_claims)
    if coverage is not None:
        score += min(2.0, coverage * 2.0)
    if not state.errors:
        score += 2.0
    else:
        score -= min(2.0, len(state.errors) * 0.5)
    return max(0.0, min(10.0, score))


def _is_failed(state: ResearchState) -> bool:
    return bool(state.errors) or not bool(state.final_answer)


def _summarize_notes(state: ResearchState) -> str:
    providers = {
        str(result.metadata["llm_provider"])
        for result in state.agent_results
        if "llm_provider" in result.metadata
    }
    provider_note = f"providers={','.join(sorted(providers))}" if providers else "providers=none"
    return f"{provider_note}; routes={'>'.join(state.route_history) or 'none'}"
