# Lab Guide: Multi-Agent Research System

## Scenario

Build and evaluate a research assistant that can receive a long question, collect
sources, analyze evidence, and write a final answer.

The repo compares two approaches:

1. **Single-agent baseline**: one LLM call handles the full task.
2. **Multi-agent workflow**: Supervisor routes to Researcher, Analyst, and Writer.

## Operating Rules

- Do not add an agent unless it owns a clear responsibility.
- Keep shared state explicit enough to debug handoffs.
- Trace each step so a reviewer can explain who did what.
- Benchmark the behavior; do not rely only on subjective output quality.
- Keep API keys in `.env` and never hard-code them.

## Milestone 1: Baseline

Relevant files:

- `src/multi_agent_research_lab/cli.py`
- `src/multi_agent_research_lab/services/llm_client.py`

Current behavior: `baseline` calls `LLMClient`. With OpenAI configured, it uses the
provider. Without provider dependencies or keys, it marks the result as offline mode.

## Milestone 2: Supervisor

Relevant files:

- `src/multi_agent_research_lab/agents/supervisor.py`
- `src/multi_agent_research_lab/graph/workflow.py`

Current routing policy:

- Missing sources or research notes -> `researcher`
- Missing analysis notes -> `analyst`
- Missing final answer -> `writer`
- Complete state -> `done`
- Too many iterations or repeated errors -> best-effort writer fallback or `done`

## Milestone 3: Worker Agents

Relevant files:

- `agents/researcher.py`
- `agents/analyst.py`
- `agents/writer.py`

The Researcher gathers sources and notes, the Analyst extracts claims/tradeoffs,
and the Writer produces the final answer with source references.

## Milestone 4: Trace And Benchmark

Relevant files:

- `observability/tracing.py`
- `evaluation/benchmark.py`
- `evaluation/report.py`

Implemented metrics:

| Metric | Measurement |
|---|---|
| Latency | wall-clock runtime |
| Cost | provider usage metadata when available |
| Quality | automated proxy score plus peer-review rubric |
| Citation coverage | cited source IDs / collected sources |
| Failure rate | errors per run |

Run:

```bash
python -m multi_agent_research_lab.cli benchmark
```

## Exit Ticket

Answer these two questions:

1. When should a multi-agent workflow be used? Why?
2. When is a single-agent workflow better? Why?
