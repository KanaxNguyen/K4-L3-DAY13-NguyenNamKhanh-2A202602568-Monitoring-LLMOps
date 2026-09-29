# Evidence cá nhân K4-L3A

Toàn bộ 14 evidence của bài Lab được lưu trực tiếp dưới dạng ảnh PNG trong thư mục này:

1. `01-pytest.png`: Kết quả Pytest cuối cùng, 26/26 tests passed.
2. `02-log-validator.png`: Kết quả chạy `scripts/validate_logs.py` đạt 100/100 (đầy đủ JSON schema, Correlation ID, Log enrichment, PII scrubbing).
3. `03-dashboard-validator.png`: Kết quả chạy `scripts/validate_dashboard.py` đạt HỢP LỆ: 6/6 panels contract.
4. `04-structured-log.png`: Dòng structured log dạng JSON đầy đủ metadata và correlation ID.
5. `05-pii-redaction.png`: Kiểm thử cơ chế che dữ liệu nhạy cảm PII (`[REDACTED_*]`).
6. `06-trace-list.png`: Danh sách các traces trên project Langfuse cá nhân `day13-k4-l3a-2A202602568`.
7. `07-trace-waterfall.png`: Trace waterfall cây span (`lab-agent-run` -> `retrieve` -> `generate`).
8. `08-trace-metadata.png`: Metadata của trace trên Langfuse (khớp `correlation_id` với structured log).
9. `09-prompt-versions.png`: Quản lý prompt `day13-chat` trên Langfuse hiển thị cả Version 1 và Version 2.
10. `10-prompt-rollback.png`: Rollback prompt về Version 1 mang nhãn `production`.
11. `11-dashboard-overview.png`: Dashboard runtime 6 panels đạt chuẩn với tất cả trạng thái PASS.
12. `12-incident-metric.png`: Dashboard phát hiện sự cố RAG slow với Latency P95 vi phạm threshold báo ALERT đỏ (kèm dữ liệu bổ trợ `12-incident-metric.json`).
13. `13-incident-log.png`: Log record của request sự cố hiển thị correlation ID và latency cao (kèm dữ liệu bổ trợ `13-incident-log.jsonl`).
14. `14-incident-trace.png`: Trace Langfuse của request sự cố xác định root cause do span `retrieve` bị chậm.

- Challenge ID: `day13-k4-l3a-monitoring-llmops-v1`. File challenge cá nhân nằm trong `.gitignore` không commit theo đúng quy định.

