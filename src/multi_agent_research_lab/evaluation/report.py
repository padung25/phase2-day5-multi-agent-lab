"""Benchmark report rendering."""

from multi_agent_research_lab.core.schemas import BenchmarkMetrics


def render_markdown_report(metrics: list[BenchmarkMetrics]) -> str:
    """Render benchmark metrics to markdown."""

    lines = [
        "# Benchmark Report",
        "",
        "## Summary",
        "",
        _summary(metrics),
        "",
        "## Failure Rate",
        "",
        _failure_rate_summary(metrics),
        "",
        "## Metrics",
        "",
        "| Run | Latency (s) | Cost (USD) | Quality | Quality Source | "
        "Citation Coverage | Claims | Errors | Failed | Notes |",
        "|---|---:|---:|---:|---|---:|---:|---:|---|---|",
    ]
    for item in metrics:
        cost = "" if item.estimated_cost_usd is None else f"{item.estimated_cost_usd:.4f}"
        quality = "" if item.quality_score is None else f"{item.quality_score:.1f}"
        coverage = "" if item.citation_coverage is None else f"{item.citation_coverage:.0%}"
        claims = f"{item.cited_claims}/{item.total_claims}" if item.total_claims else ""
        failed = "yes" if item.failed else "no"
        notes = item.notes.replace("|", "\\|")
        lines.append(
            f"| {item.run_name} | {item.latency_seconds:.2f} | {cost} | {quality} | "
            f"{item.quality_source} | {coverage} | {claims} | {item.error_count} | "
            f"{failed} | {notes} |"
        )
    lines.extend(
        [
            "",
            "## Review Notes",
            "",
            "- Quality uses peer review when provided; otherwise it is marked automated_proxy.",
            "- Citation coverage counts cited main claims / total detected main claims.",
            "- Inspect trace output for route order, provider fallback, latency, and errors.",
            "",
            "## Failure Mode Checklist",
            "",
            "- Missing or low-quality sources",
            "- Router loop or premature stop",
            "- Uncited claims in final answer",
            "- Provider timeout or fallback mode",
        ]
    )
    return "\n".join(lines) + "\n"


def _summary(metrics: list[BenchmarkMetrics]) -> str:
    if not metrics:
        return "No benchmark runs were recorded."
    best_quality = max(metrics, key=lambda item: item.quality_score or 0)
    fastest = min(metrics, key=lambda item: item.latency_seconds)
    return (
        f"Best quality: **{best_quality.run_name}**. "
        f"Fastest run: **{fastest.run_name}**."
    )


def _failure_rate_summary(metrics: list[BenchmarkMetrics]) -> str:
    if not metrics:
        return "No benchmark runs were recorded."
    failed_count = sum(1 for item in metrics if item.failed)
    return f"{failed_count}/{len(metrics)} runs failed ({failed_count / len(metrics):.0%})."
