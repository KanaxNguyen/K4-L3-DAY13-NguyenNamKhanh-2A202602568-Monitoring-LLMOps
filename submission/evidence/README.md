# Evidence cá nhân K4-L3A

Evidence chạy lệnh được lưu dưới dạng text và JSON để có thể mở trực tiếp trên GitHub:

- `01-pytest.txt`: kết quả pytest cuối, 26 tests passed.
- `02-log-validator.txt`: validator 100/100, không thiếu field/context và không có PII leak.
- `03-dashboard-validator.txt`: contract dashboard hợp lệ 6/6.
- `05-pii-redaction.txt`: ví dụ log đã scrub cùng kết quả kiểm tra.
- `06-traces-and-prompts.txt`: số trace trong project cá nhân, prompt v1/v2, rollback và trace v1 sau rollback.
- `12-incident-metric.json` và `13-incident-log.jsonl`: incident metrics và 10 log records dùng chung 5 correlation IDs.

Dashboard và Langfuse đã được chụp bằng Computer Use trong phiên làm việc. Không có PNG được lưu tại đây, do giao diện Computer Use chỉ trả ảnh vào phiên làm việc; không đánh dấu ảnh GitHub là hoàn tất. Trang API Keys không được mở.

Challenge ID là `day13-k4-l3a-monitoring-llmops-v1`; file challenge cá nhân bị ignore và không nằm trong evidence.
