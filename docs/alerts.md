# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: high_tail_latency
- Severity: warning
- Duration: 5m
- Kênh thông báo: Slack (#alerts-llmops)
- SLI/SLO liên quan: `fast_successful_requests` (SLO target: 99.5% requests <= 3000ms trong window 28d)
- Điều kiện và thời gian duy trì: Latency P95 vượt ngưỡng 3000ms kéo dài liên tục trên 5 phút
- Ảnh hưởng tới người dùng: Người dùng trải nghiệm phản hồi chậm, tăng thời gian chờ tin nhắn chat
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard kiểm tra panel Latency và TTFT xem độ trễ tăng ở bước nào (TTFT hay toàn bộ request).
  2. Lọc file `data/logs.jsonl` tìm các log `response_sent` có `latency_ms > 3000`, trích xuất `correlation_id` mẫu.
  3. Mở trace tương ứng trên Langfuse để xem span con nào chậm (`retrieve` do RAG hay `generate` do LLM).
- Mitigation tạm thời: Giảm số lượng docs retrieve (top-k) hoặc bật cache retrieval; kiểm tra trạng thái incident `rag_slow` qua `/health`.
- Owner: oncall-engineer

## Alert 2

- Tên: api_error_rate_high
- Severity: critical
- Duration: 3m
- Kênh thông báo: Slack (#alerts-llmops)
- SLI/SLO liên quan: Availability Guardrail (`error_rate_pct_max: 2%`)
- Điều kiện và thời gian duy trì: Tỷ lệ request lỗi (`request_failed` / `request_received`) > 2% kéo dài trong 3 phút
- Ảnh hưởng tới người dùng: Người dùng nhận mã lỗi HTTP 500, không nhận được câu trả lời từ AI
- Ba bước kiểm tra đầu tiên:
  1. Kiểm tra panel Errors trên dashboard để xác định `error_type` phổ biến (ví dụ: `RuntimeError`, `KeyError`, timeout).
  2. Lọc log `request_failed` trong `data/logs.jsonl` để xem error detail và `correlation_id`.
  3. Mở trace trên Langfuse để kiểm tra lỗi xảy ra ở tool retrieval hay API ngoài.
- Mitigation tạm thời: Kích hoạt fallback prompt local, ngắt incident giả lập hoặc bật circuit breaker cho downstream service.
- Owner: oncall-engineer

## Alert 3

- Tên: cost_spike_detected
- Severity: warning
- Duration: 10m
- Kênh thông báo: Slack (#alerts-cost-llmops)
- SLI/SLO liên quan: Cost Guardrail (`daily_cost_usd_max: 2.5`)
- Điều kiện và thời gian duy trì: Chi phí ước tính vượt quá 0.05 USD/phút duy trì trong 10 phút
- Ảnh hưởng tới người dùng: Không ảnh hưởng trực tiếp người dùng cuối, nhưng đe dọa làm cạn kiệt ngân sách dự án (error budget / token quota)
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Cost và Tokens trên dashboard xem đột biến đến từ `tokens_in` (prompt quá dài) hay `tokens_out` (mô hình bị lặp output).
  2. Kiểm tra `user_id_hash` và `feature` trong logs xem có session hoặc user cụ thể nào đang gửi workload bất thường.
  3. Kiểm tra prompt version hiện tại trong trace xem có thay đổi hệ thống prompt dẫn đến output dài bất thường không.
- Mitigation tạm thời: Áp dụng max_tokens chặt chẽ hơn trong LLM generation hoặc tạm thời rate-limit session gây đột biến.
- Owner: platform-team
