"""Optional critic agent for answer validation."""

import re

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span


class CriticAgent(BaseAgent):
    """Lightweight citation coverage and completion check."""

    name = "critic"
    minimum_citation_coverage = 0.7

    def run(self, state: ResearchState) -> ResearchState:
        """Validate final answer and append findings."""

        with trace_span("agent.critic", {"source_count": len(state.sources)}) as span:
            findings: list[str] = []
            if not state.final_answer:
                findings.append("Final answer is missing.")

            if state.final_answer:
                cited_claims, total_claims = _claim_citation_counts(state.final_answer)
                coverage = cited_claims / total_claims if total_claims else 0.0
                state.citation_coverage = coverage
                if coverage < self.minimum_citation_coverage:
                    findings.append(
                        "Citation coverage is below threshold: "
                        f"{coverage:.0%} ({cited_claims}/{total_claims} claims)."
                    )
                    state.citation_feedback = (
                        "Add sentence-level citations to uncited factual claims. "
                        f"Current coverage is {coverage:.0%}; required coverage is "
                        f"{self.minimum_citation_coverage:.0%}."
                    )
                else:
                    state.citation_feedback = None
                span["outputs"] = {
                    "citation_coverage": coverage,
                    "cited_claims": cited_claims,
                    "total_claims": total_claims,
                    "passes_threshold": coverage >= self.minimum_citation_coverage,
                }
            else:
                state.citation_coverage = 0.0
                state.citation_feedback = "Final answer is missing."
                span["outputs"] = {
                    "citation_coverage": 0.0,
                    "cited_claims": 0,
                    "total_claims": 0,
                    "passes_threshold": False,
                }

            if not findings:
                findings.append("No blocking issues found by lightweight critic.")
            content = "\n".join(f"- {finding}" for finding in findings)
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.CRITIC,
                    content=content,
                    metadata={
                        "finding_count": len(findings),
                        "citation_coverage": state.citation_coverage,
                    },
                )
            )
        state.add_trace_event("agent.critic", span)
        return state


def _claim_citation_counts(answer: str) -> tuple[int, int]:
    claims = _extract_claims(answer)
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
