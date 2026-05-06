# Lab 20: Hệ Thống Nghiên Cứu Multi-Agent
## Kết quả và báo cáo sẽ ở thư mục report/traces
Repo này triển khai một research assistant theo hướng production-lite với workflow:

```text
Supervisor + Researcher + Analyst + Writer + Critic
```

Hệ thống có baseline single-agent để benchmark và so sánh với multi-agent.

Repo có thể chạy ở hai chế độ:

- **Provider thật**: dùng OpenAI cho LLM, Tavily cho web search, LangGraph cho workflow, LangSmith cho tracing.
- **Fallback local/offline**: vẫn chạy được khi thiếu API key hoặc thiếu optional dependency, phù hợp để test và phát triển.

## Kiến Trúc

```text
User Query
   |
   v
Supervisor / Router
   |------> Researcher Agent  -> sources + research_notes
   |------> Analyst Agent     -> analysis_notes
   |------> Writer Agent      -> final_answer
   |------> Critic Agent      -> citation validation
   |
   v
Trace + Benchmark Report
```

Route multi-agent hiện tại:

```text
researcher > analyst > writer > critic > done
```

Nếu Critic phát hiện citation coverage dưới ngưỡng **70%**, Supervisor có thể route quay lại Writer để sửa trong revision budget.

## Cấu Trúc Repo

```text
.
|-- src/multi_agent_research_lab/
|   |-- agents/              # Supervisor, Researcher, Analyst, Writer, Critic
|   |-- core/                # Config, state, schemas, errors
|   |-- graph/               # LangGraph workflow + local fallback executor
|   |-- services/            # LLM, search, storage clients
|   |-- evaluation/          # Benchmark metrics và report rendering
|   |-- observability/       # Logging và tracing hooks
|   `-- cli.py               # CLI entrypoint
|-- configs/                 # YAML config cho benchmark
|-- docs/                    # Lab guide, rubric, design notes
|-- reports/                 # Benchmark report và trace exports
|-- tests/                   # Unit tests
|-- .env.example             # Template biến môi trường
|-- pyproject.toml           # Python project config
|-- Dockerfile
`-- Makefile
```

## Quickstart

### 1. Tạo Môi Trường

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Unix/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "[dev]"
cp .env.example .env
```

Cài thêm provider integrations nếu muốn dùng OpenAI, LangGraph và LangSmith thật:

```bash
pip install -e "[dev,llm]"
```

### 2. Cấu Hình API Keys

Mở `.env` và điền các key cần dùng:

```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini

# optional
ENABLE_REMOTE_TRACING=false
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=multi-agent-research-lab
TAVILY_API_KEY=...
```

Ghi chú:

- `OPENAI_API_KEY`: dùng cho LLM calls.
- `TAVILY_API_KEY`: dùng cho web search.
- `LANGSMITH_API_KEY`: dùng để export tracing lên LangSmith.
- `ENABLE_REMOTE_TRACING=true`: chỉ bật khi thật sự muốn gửi span lên LangSmith.

Nếu thiếu key, CLI vẫn chạy bằng fallback local/offline và metadata sẽ ghi rõ provider đang dùng.

### 3. Smoke Test

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m multi_agent_research_lab.cli --help
```

Unix/macOS:

```bash
make test
python -m multi_agent_research_lab.cli --help
```

## Cách Chạy

### Chạy Baseline

Baseline là single-agent: một LLM call xử lý toàn bộ câu hỏi.

```bash
python -m multi_agent_research_lab.cli baseline \
  --query "Research GraphRAG state-of-the-art and write a 500-word summary"
```

### Chạy Multi-Agent Workflow

```bash
python -m multi_agent_research_lab.cli multi-agent \
  --query "Research GraphRAG state-of-the-art and write a 500-word summary"
```

Output gồm:

- `sources`
- `research_notes`
- `analysis_notes`
- `final_answer`
- `citation_coverage`
- `route_history`
- `trace`
- `errors`

### Chạy Benchmark

```bash
python -m multi_agent_research_lab.cli benchmark
```

Lệnh này chạy mỗi query trong `configs/lab_default.yaml` theo 2 mode:

```text
baseline-n
multi-agent-n
```

Kết quả được ghi vào:

```text
reports/benchmark_report.md
reports/traces/query_1_baseline.json
reports/traces/query_1_multi_agent.json
...
```

## Kết Quả Benchmark Hiện Tại

Benchmark mới nhất cho thấy multi-agent cải thiện rõ citation coverage sau khi thêm CriticAgent:

| Run | Quality | Citation Coverage | Claims | Route |
|---|---:|---:|---:|---|
| baseline-1 | 4.0 | 0% | 0/26 | none |
| multi-agent-1 | 9.7 | 86% | 18/21 | researcher>analyst>writer>critic>done |
| baseline-2 | 4.0 | 0% | 0/17 | none |
| multi-agent-2 | 10.0 | 100% | 19/19 | researcher>analyst>writer>critic>done |
| baseline-3 | 4.0 | 0% | 0/13 | none |
| multi-agent-3 | 9.5 | 76% | 13/17 | researcher>analyst>writer>critic>done |

Chi tiết đầy đủ nằm trong:

```text
reports/benchmark_report.md
```

## Metrics Trong Benchmark

Benchmark report có các metric tối thiểu của lab:

| Metric | Cách đo |
|---|---|
| Latency | Wall-clock time |
| Cost | Token usage / provider usage estimate |
| Quality | Peer review nếu có, nếu chưa có thì dùng automated proxy |
| Citation coverage | Số main claims có citation / tổng main claims |
| Failure rate | Số run fail / tổng số run |

Nếu muốn nhập điểm peer review thật, sửa `configs/lab_default.yaml`:

```yaml
benchmark:
  peer_review_scores:
    baseline-1: 6
    multi-agent-1: 8
    baseline-2: 5
    multi-agent-2: 8
```

Sau đó chạy lại:

```bash
python -m multi_agent_research_lab.cli benchmark
```

## Logging Và Tracing

Logging được cấu hình qua `.env`:

```env
LOG_LEVEL=INFO
```

Các mức thường dùng:

```env
LOG_LEVEL=DEBUG
LOG_LEVEL=INFO
LOG_LEVEL=WARNING
LOG_LEVEL=ERROR
```

Trace local luôn nằm trong `state.trace` và được export ra JSON khi chạy benchmark.

Để bật LangSmith tracing:

```env
ENABLE_REMOTE_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=multi-agent-research-lab
```

## Capabilities Đã Triển Khai

1. `LLMClient` gọi OpenAI khi có key, fallback offline khi thiếu provider.
2. `SearchClient` gọi Tavily khi có key, fallback local corpus khi thiếu provider.
3. Supervisor routing policy với guard `max_iterations`.
4. Researcher, Analyst, Writer và CriticAgent.
5. LangGraph workflow, có local fallback executor khi thiếu optional dependency.
6. Local tracing và optional LangSmith export.
7. Benchmark report với latency, cost, quality, citation coverage, failure rate và trace JSON.
8. Citation validation: CriticAgent kiểm tra coverage và yêu cầu Writer sửa nếu dưới 70%.

## Quy Ước Production

- Tách rõ `agents`, `services`, `core`, `graph`, `evaluation`, `observability`.
- Không hard-code API key trong code.
- Input/output chính dùng Pydantic schema.
- Có type hints, linting, formatting và unit test tối thiểu.
- Có logging/tracing hook.
- Không để agent chạy vô hạn: dùng `max_iterations`, `timeout_seconds`, fallback và error trace.
- Có benchmark report thay vì chỉ demo output đẹp.

## Deliverables

1. GitHub repo.
2. Screenshot trace hoặc LangSmith trace link.
3. `reports/benchmark_report.md` so sánh baseline và multi-agent.
4. Failure-mode note và mitigation đã được ghi trong phần **Failure Mode Và Cách Giảm Thiểu** của benchmark report.

## Failure Mode Và Mitigation

Failure mode ban đầu:

```text
final answer có nhiều claim chưa được gắn citation
```

Mitigation đã triển khai:

1. Analyst giữ source id từ research notes.
2. Writer yêu cầu citation ở cấp từng câu factual.
3. Workflow có route `critic` sau `writer`.
4. Critic đo citation coverage theo `cited main claims / total main claims`.
5. Nếu coverage dưới 70%, Supervisor route quay lại Writer để sửa.
6. Writer ghi `auto_cited_claims` vào metadata để reviewer biết phần nào được post-process.

Kết quả sau mitigation:

- `multi-agent-1`: citation coverage **86%**.
- `multi-agent-2`: citation coverage **100%**.
- `multi-agent-3`: citation coverage **76%**.

## References

- Anthropic: Building effective agents - https://www.anthropic.com/engineering/building-effective-agents
- OpenAI Agents orchestration - https://developers.openai.com/api/docs/guides/agents/orchestration
- LangGraph concepts - https://langchain-ai.github.io/langgraph/concepts/
- LangSmith tracing - https://docs.smith.langchain.com/
