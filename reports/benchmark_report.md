# Báo Cáo Benchmark

## Tóm Tắt

Benchmark so sánh hai cách chạy trên cùng 3 câu hỏi:

- **Baseline**: một LLM call xử lý toàn bộ yêu cầu.
- **Multi-agent**: Supervisor điều phối Researcher, Analyst, Writer và Critic.

Kết quả chính:

- Run có quality cao nhất: **multi-agent-2**.
- Run nhanh nhất: **baseline-3**.
- Multi-agent đạt quality proxy cao hơn baseline ở cả 3 query.
- Multi-agent có citation coverage tốt hơn rõ rệt sau khi thêm CriticAgent.
- Không có run nào fail.

## Failure Rate

0/6 runs failed (0%).

## Bảng Metrics

| Run | Latency (s) | Cost (USD) | Quality | Quality Source | Citation Coverage | Claims | Errors | Failed | Notes |
|---|---:|---:|---:|---|---:|---:|---:|---|---|
| baseline-1 | 11.70 | 0.0004 | 4.0 | automated_proxy | 0% | 0/26 | 0 | no | providers=openai; routes=none |
| multi-agent-1 | 26.83 | 0.0014 | 9.7 | automated_proxy | 86% | 18/21 | 0 | no | providers=openai; routes=researcher>analyst>writer>critic>done |
| baseline-2 | 5.32 | 0.0003 | 4.0 | automated_proxy | 0% | 0/17 | 0 | no | providers=openai; routes=none |
| multi-agent-2 | 23.68 | 0.0014 | 10.0 | automated_proxy | 100% | 19/19 | 0 | no | providers=openai; routes=researcher>analyst>writer>critic>done |
| baseline-3 | 4.41 | 0.0002 | 4.0 | automated_proxy | 0% | 0/13 | 0 | no | providers=openai; routes=none |
| multi-agent-3 | 22.71 | 0.0012 | 9.5 | automated_proxy | 76% | 13/17 | 0 | no | providers=openai; routes=researcher>analyst>writer>critic>done |

## Đánh Giá Theo Từng Cặp

### Query 1

Multi-agent đạt quality proxy **9.7**, cao hơn baseline **4.0**. Latency tăng từ **11.70s** lên **26.83s**, và cost tăng từ **0.0004 USD** lên **0.0014 USD**.

Citation coverage của multi-agent đạt **86%**, tương ứng **18/21 claims** có citation. Đây là cải thiện lớn so với baseline, vốn không có search/source nên coverage là **0%**.

### Query 2

Multi-agent đạt quality proxy cao nhất: **10.0**, trong khi baseline là **4.0**. Latency tăng từ **5.32s** lên **23.68s**, cost tăng từ **0.0003 USD** lên **0.0014 USD**.

Citation coverage đạt **100%**, tương ứng **19/19 claims** có citation. Đây là run tốt nhất của benchmark vì vừa có quality proxy cao nhất vừa đạt citation coverage tuyệt đối.

### Query 3

Multi-agent đạt quality proxy **9.5**, cao hơn baseline **4.0**. Latency tăng từ **4.41s** lên **22.71s**, cost tăng từ **0.0002 USD** lên **0.0012 USD**.

Citation coverage đạt **76%**, tương ứng **13/17 claims** có citation. Coverage thấp hơn query 1 và query 2 nhưng vẫn vượt ngưỡng kiểm tra **70%** của CriticAgent.

## Nhận Xét

Baseline nhanh và rẻ hơn vì chỉ dùng một LLM call, không có bước search, phân tích, viết lại và kiểm tra citation. Tuy nhiên baseline không dùng nguồn đầu vào nên citation coverage là **0%** ở cả 3 query.

Multi-agent chậm và tốn chi phí hơn vì thực hiện nhiều bước:

1. Supervisor chọn route.
2. Researcher tìm nguồn và tạo research notes.
3. Analyst phân tích claim, tradeoff và điểm yếu.
4. Writer tổng hợp final answer với citation.
5. Critic kiểm tra citation coverage trước khi kết thúc.

Đổi lại, multi-agent cho chất lượng cao hơn và trace rõ ràng:

```text
researcher > analyst > writer > critic > done
```

Kết quả mới cho thấy việc thêm CriticAgent và siết citation prompt đã cải thiện citation coverage đáng kể:

- Query 1: **86%**
- Query 2: **100%**
- Query 3: **76%**

## Failure Mode Và Cách Giảm Thiểu

Failure mode ban đầu: **final answer có nhiều claim chưa được gắn citation**.

Trong phiên benchmark trước, multi-agent từng có citation coverage thấp, đặc biệt query 2 chỉ đạt **8%**. Sau cải tiến, coverage của query 2 tăng lên **100%**.

Các mitigation đã triển khai:

1. Siết prompt của Analyst để giữ source id từ research notes.
2. Siết prompt của Writer để mọi factual claim có citation dạng `[n]`.
3. Thêm CriticAgent vào workflow chính.
4. CriticAgent đo citation coverage theo `cited main claims / total main claims`.
5. Nếu coverage dưới **70%**, Supervisor route quay lại Writer để sửa trong revision budget.
6. Writer có post-process bảo thủ để gắn citation vào factual sentence còn thiếu citation và ghi metadata `auto_cited_claims`.

Failure mode còn lại:

- Multi-agent vẫn chậm và tốn chi phí hơn baseline.
- `Quality` hiện vẫn là `automated_proxy`, chưa phải điểm peer review thật.
- Citation coverage phụ thuộc vào bộ tách claim tự động, nên vẫn cần reviewer kiểm tra thủ công ở bài nộp cuối.

## Kết Luận

Project đã đáp ứng mục tiêu lab: có baseline, multi-agent workflow, tracing, benchmark report, guardrails và failure-mode analysis.

Multi-agent phù hợp hơn cho các câu hỏi nghiên cứu cần nguồn, phân tích và trace. Trong benchmark này, multi-agent cải thiện rõ về quality proxy và citation coverage, nhưng đánh đổi bằng latency và cost cao hơn.

Ưu tiên tiếp theo nếu tiếp tục cải thiện production quality:

1. Thêm peer review score thật vào `configs/lab_default.yaml`.
2. Commit hoặc nộp kèm trace JSON / screenshot LangSmith.
3. Tối ưu latency bằng cách giảm prompt length hoặc cache search results.
4. Làm citation validator chính xác hơn bằng structured claim extraction.

## Ghi Chú Review

- `Quality` hiện là `automated_proxy`, chưa phải điểm peer review thật.
- `Citation Coverage` được tính bằng số main claims có citation chia cho tổng main claims được phát hiện.
- Trace chi tiết nằm trong `reports/traces/`.
