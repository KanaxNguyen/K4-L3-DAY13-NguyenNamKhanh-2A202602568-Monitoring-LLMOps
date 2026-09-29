# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/01-pytest.txt`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Nam Khánh
- **MSSV:** 2A202602568
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/KanaxNguyen/K4-L3-DAY13-NguyenNamKhanh-2A202602568-Monitoring-LLMOps
- **Commit SHA cuối:** Sẽ cung cấp cùng URL repository khi nộp; SHA được xác định bằng `git rev-parse HEAD` sau commit evidence cuối.
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (K4-L3A, seed 1311)
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602568`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime (6 panels + time series) | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` (và `evidence/12-incident-metric.json`) |
| Incident log excerpt | `evidence/13-incident-log.png` (và `evidence/13-incident-log.jsonl`) |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Đã đạt toàn bộ tiêu chí (schema, correlation id, enrichment, pii) |
| `validate_dashboard.py` | Hợp lệ 6/6 | Hợp lệ 6/6 | Đạt đầy đủ 6 panels theo đúng contract |
| `pytest` | 22 passed | 26 passed | Đã bổ sung test cases kiểm thử PII và correlation ID propagation |
| Số traces hợp lệ | 0 | 20+ | Đầy đủ span tree (agent -> retrieve -> generate) trên Langfuse |
| Số PII leak | 0 | 0 | Không còn rò rỉ email, phone, cccd, credit card trong log |
| Latency P95 / TTFT P95 | 2642.9ms / 55ms | 3262.6ms / 57ms | Runtime dashboard 60 phút, 40 requests; P95 cao do các request challenge `rag_slow` còn trong cửa sổ |
| Retrieval success rate | 100% | 100% | 100% retrieval thành công ở điều kiện vận hành bình thường |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Trong `CorrelationIdMiddleware` ([`app/middleware.py`](../app/middleware.py)), mỗi request đến được dọn sạch context bằng `clear_contextvars()`. Middleware trích xuất header `x-request-id` hoặc tự động sinh mã mới dạng `req-<8-hex>` thông qua `uuid.uuid4().hex[:8]`. Sau đó bind vào structlog contextvars và gán vào `request.state.correlation_id`. Trong response headers, middleware trả về `x-request-id` và `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** Mỗi log record được làm giàu với: `ts` (ISO 8601 UTC), `level`, `service` ("api"), `event` ("request_received" / "response_sent" / "request_failed"), `correlation_id`, `user_id_hash`, `session_id`, `feature`, `model`, `env`, cùng các metrics định lượng (`latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`).
- **Cách bảo đảm PII được scrub trước khi ghi:** Processor `scrub_event` ([`app/logging_config.py`](../app/logging_config.py)) được đặt trong chuỗi xử lý structlog ngay trước renderer JSON và processor ghi file. Processor duyệt đệ quy toàn bộ chuỗi string và áp dụng regex từ [`app/pii.py`](../app/pii.py) để thay thế email, số điện thoại Việt Nam, CCCD 12 số, thẻ tín dụng 16 số và hộ chiếu thành các thẻ `[REDACTED_<TYPE>]`.
- **Cách kiểm chứng kết quả:** Chạy `python scripts/validate_logs.py` đạt 100/100, xác nhận `Potential PII leaks detected: 0` và toàn bộ unit test trong `tests/test_pii.py`, `tests/test_chat_observability.py` đều pass.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Sử dụng API keys của project `day13-k4-l3a-2A202602568` tạo trên Langfuse Cloud, thiết lập trong `.env`. Các traces mang tags `["lab", feature, model]` và metadata `correlation_id` khớp từng dòng với `data/logs.jsonl`.
- **Cấu trúc root/retrieval/generation observations:** Root observation `@observe(name="lab-agent-run", as_type="agent")` chứa 2 observations con:
  1. Child span `retrieve` (`as_type="retriever"`) ghi nhận truy vấn và danh sách docs trả về.
  2. Child generation `generate` (`as_type="generation"`) lồng trong `propagate_attributes(prompt=prompt.managed_prompt)`, ghi nhận model (`claude-sonnet-4-5`), input prompt text, output text, `usage_details` (input/output tokens) và `cost_details`.
- **Cách nối trace với log:** Sử dụng chung một `correlation_id` duy nhất từ HTTP middleware, được gán vào metadata của trace Langfuse và tất cả các dòng structured log liên quan.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** Version 1 (labels: `baseline`, `production`)
- **Version/label candidate:** Version 2 (label: `candidate`)
- **Trace ID của v1 sau rollback:** `33513940aa24674ca7db3f8995559942` (correlation ID `req-e47c64bb`; Langfuse generation hiển thị `day13-chat (v1)`).
- **Trace ID của v2:** Version 2 và nhãn `candidate` đã được xác nhận trên Langfuse Prompt Management; chưa có trace v2 được xác nhận trong lần kiểm tra cuối.
- **Cách promote và rollback `production`:** Trên Langfuse Cloud UI, chuyển label `production` sang Version 2 khi promote. Khi phát hiện vấn đề hoặc kiểm thử rollback, gán lại nhãn `production` về Version 1. App tự động load prompt theo `LANGFUSE_PROMPT_LABEL=production`.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** Dựng dashboard HTML tự động làm mới tại `http://localhost:8000/dashboard` đọc từ `data/logs.jsonl` đáp ứng hợp đồng `config/dashboard.yaml` với 6 panels: Latency (P50, P95, P99, TTFT P95, time series P95 theo bucket 5 phút), Traffic (count, rate/min), Errors (tỷ lệ lỗi, tỷ lệ retrieval thành công), Cost (USD), Tokens (tokens in/out), Quality (điểm 0-1).
- **SLO và lý do chọn:** `fast_successful_requests` với SLI: tỷ lệ requests có `event == "response_sent"` và `latency_ms <= 3000ms` trên tổng `request_received` trong 28 ngày. Ngưỡng target: 99.5%, Error budget: 0.5%. Lý do: Đảm bảo người dùng chat có trải nghiệm mượt mà không phải chờ đợi quá 3 giây.
- **Cách tính error budget:** Error budget = 100% - 99.5% = 0.5%. Với 100,000 requests trong cửa sổ 28 ngày, hệ thống chỉ cho phép tối đa 500 requests bị chậm (>3000ms) hoặc bị lỗi 500.
- **Ba alert và runbook tương ứng:**
  1. `high_tail_latency`: Warning, latency P95 > 3000ms trong 5m, thông báo qua Slack `#alerts-llmops`, runbook tại `docs/alerts.md#alert-1`.
  2. `api_error_rate_high`: Critical, error rate > 2% trong 3m, thông báo qua Slack `#alerts-llmops`, runbook tại `docs/alerts.md#alert-2`.
  3. `cost_spike_detected`: Warning, chi phí > 0.05 USD/min trong 10m, thông báo qua Slack `#alerts-cost-llmops`, runbook tại `docs/alerts.md#alert-3`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`; incident `rag_slow`, seed `1311`, feature `monitoring`, threshold `2000 ms`. Dữ liệu challenge cá nhân nằm ở [`config/challenge.json`](../config/challenge.json) (được `.gitignore` và không nộp).
- **Khoảng thời gian điều tra:** `2026-09-29 09:46:02–09:46:21 UTC` (`16:46:02–16:46:21` giờ Việt Nam). Năm request challenge đều trả HTTP 200 nhưng vượt ngưỡng: `2927, 3096, 3156, 3190, 5715 ms` (median `3156 ms`). TTFT trong khoảng `52–58 ms`, giúp khoanh vùng chậm trước khi token đầu tiên sinh ra.
- **Log line và correlation ID liên quan:** [`evidence/13-incident-log.jsonl`](evidence/13-incident-log.jsonl) giữ 10 log record cho 5 request cùng khoảng sự cố; số liệu tổng hợp ở [`evidence/12-incident-metric.json`](evidence/12-incident-metric.json). Các correlation ID: `req-8cdfbfd8`, `req-6e74899e`, `req-497b3e3b`, `req-265fd71c`, `req-3188b41b`.
- **Trace ID và span gây ảnh hưởng:** [Trace trên project Langfuse cá nhân](https://us.cloud.langfuse.com/project/cmumcy2wh0f49ad0c8ypaqd1a/traces?peek=a480f22ba9e55fe8&observation=a480f22ba9e55fe8&traceId=bc12b9eb90f196a812eab0cc63034a60&timestamp=2026-09-29T09%3A46%3A02.877Z), trace `bc12b9eb90f196a812eab0cc63034a60`, metadata correlation ID `req-8cdfbfd8`. Root `lab-agent-run` khoảng `5.71 s`; child `retrieve` `2.51 s`; child `generate` `0.16 s`.
- **Root cause:** Tín hiệu theo đúng Metrics → Logs → Traces: cả năm request có latency cao; structured log nối request bất thường bằng correlation ID; trace cho thấy retrieval chiếm phần chậm lớn nhất trong khi generation ngắn. `app/mock_rag.py` cố ý chèn `time.sleep(2.5)` khi `STATE["rag_slow"]` bật, đúng với incident được tiêm. Không có bằng chứng rằng lỗi nằm ở LLM generation.
- **Fix action:** Sau khi thu thập evidence, tắt incident injector bằng `python scripts/inject_incident.py --disable`; lệnh xác nhận `rag_slow` đã tắt. Đây là hành động khôi phục cho challenge mô phỏng, không sửa/xóa đoạn delay dùng để tái tạo incident.
- **Preventive measure:** Với retrieval thật, đặt deadline/timeout cho RAG/vector-store, theo dõi và phát alert theo retrieval p95 cùng ngưỡng latency; bảo đảm request hủy được retrieval hết hạn và ghi timeout/error kèm correlation ID. Với bài lab, chạy lại challenge sau khi tắt injector để xác nhận p95 trở về baseline trước khi đóng incident.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Đặt PII processor `scrub_event` trước JSONRenderer và file processor trong structlog. Quyết định này đảm bảo dữ liệu nhạy cảm được khử trùng ngay trong bộ nhớ trước khi ghi xuống đĩa hoặc in ra console, loại trừ triệt để nguy cơ vi phạm bảo mật dữ liệu.
- **Một lỗi/blocker đã gặp:** Port 8000 và 8001 bị chiếm dụng bởi tiến trình uvicorn chạy nền trước đó và Docker Desktop (`[Errno 48] Address already in use`), đồng thời `load_test.py` ban đầu báo thiếu correlation_id do middleware chưa hoàn thiện.
- **Cách tìm nguyên nhân và xử lý:** Sử dụng `lsof -nP -iTCP -sTCP:LISTEN` để xác định PID đang chiếm cổng và dùng `kill -9` để giải phóng; hoàn thiện logic sinh và truyền correlation ID trong middleware.
- **Cách hiểu luồng Metrics → Logs → Traces:**
  1. *Metrics*: Giúp phát hiện triệu chứng ở tầm vĩ mô và xác định khoảng thời gian xảy ra sự cố (ví dụ: P95 latency tăng đột biến hoặc error rate vượt ngưỡng).
  2. *Logs*: Dựa vào mốc thời gian, lọc file logs để tìm các request bất thường và trích xuất `correlation_id`.
  3. *Traces*: Dùng `correlation_id` tra cứu trace chi tiết trên Langfuse để xác định chính xác span/bước nào (retrieval RAG hay LLM generation) là thủ phạm gây ra lỗi hoặc chậm trễ.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Quản lý version prompt và theo dõi token/cost giúp ngăn ngừa hồi quy chất lượng và bùng nổ chi phí khi triển khai thay đổi; SLO/Error Budget tạo ranh giới an toàn để quyết định khi nào cần đóng băng tính năng để ổn định hệ thống; rollback nhanh qua nhãn label đảm bảo thời gian phục hồi dịch vụ (MTTR) tối thiểu.
- **Điều quan trọng nhất đã học:** Kỹ năng xây dựng hệ thống quan sát toàn diện (Observability) cho ứng dụng GenAI kết hợp chặt chẽ giữa Structured Logging, Metrics và Tracing phân tán.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** Cần bổ sung thêm các rules kiểm tra PII chuyên sâu hơn cho địa chỉ cụ thể của Việt Nam và cơ chế tự động hoá alert với webhook Slack thực tế.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Toàn bộ evidence hình ảnh PNG và dữ liệu bổ trợ (JSON/JSONL) mở được bằng đường dẫn tương đối trong `submission/evidence/`.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân; không mở trang API Keys.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
