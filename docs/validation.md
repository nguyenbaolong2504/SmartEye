# Kiểm thử

- Build: TypeScript strict và Vite production.
- Pytest: DB tạm riêng, business/RBAC/privacy/Google MockTransport.
- Playwright: DB/server riêng, desktop Chromium và viewport iPhone 13 bằng Chromium.
- Inference smoke: YOLO thật trên video hai giây đứng yên từ ảnh phương tiện, kiểm tra raw deletion; không đo accuracy Hà Nội.

## Kết quả ngày 15/10/2026 (giờ Việt Nam)

| Kiểm tra | Kết quả |
|---|---|
| Pytest | 31 passed |
| Playwright | 10 passed, 5 luồng × desktop/mobile |
| TypeScript + production build | Passed |
| `docker compose config --quiet` | Passed |
| YOLO smoke: clip đứng yên 2 giây | 2 samples, mỗi sample đếm 1 phương tiện, density NORMAL; raw video bị xóa |
| Upload/inference qua UI | Passed trên desktop/mobile, cảnh trống LOW, không publish khi thiếu recording time |

Windows: Node 24.18.0, Python 3.11.6, FastAPI 0.140.0, Ultralytics 8.4.89; model yolo11n.pt pretrained COCO. Inference smoke dùng ảnh bus mẫu từ repository Ultralytics, không commit fixture/model/database. Một ảnh mẫu không chứng minh accuracy thực địa.

Docker Engine trên máy không chạy, nên chưa build/run Compose hay kiểm thử PostgreSQL thực. Google chưa có API key nên chỉ kiểm thử tích hợp bằng mock; SMTP thật chưa cấu hình. GitHub Actions được thêm vào repo, kết quả CI trên GitHub cần xem sau push.

## Bổ sung database ngày 16/10/2026

- Backend: **44 passed, 1 skipped**. Bài skipped cần PostgreSQL server riêng qua `SMARTEYE_POSTGRES_TEST_URL`; chưa có kết quả PostgreSQL thật trên máy local.
- Database mẫu 90.112 bytes: đủ 11 bảng, 3 user đúng vai trò, 13 đoạn minh họa, 4 camera; integrity/foreign key đều hợp lệ, các bảng session/token/job/quan sát riêng tư trống.
- Login ba tài khoản mẫu qua API thật trong TestClient; kiểm tra Admin/Analyst/User có quyền tương ứng. Password trong DB là scrypt hash; kết quả API không trả password.
- Restore SQL SQLite thành công; bootstrap chạy lại không trùng dữ liệu, không đổi mật khẩu/role/status user cũ và từ chối demo ở production.
- Bootstrap DB không import FastAPI/Torch/OpenCV. Builder chỉ xuất fixture sạch, không lấy Admin từ env vào DB chia sẻ.
- Kiểm thử cấu hình PostgreSQL với password có ký tự đặc biệt; `docker compose config` hợp lệ cho cả bản đầy đủ và override DB local.
- CI backend bổ sung PostgreSQL 16 để restore SQL PostgreSQL, kiểm tra sequence, JSON và foreign key. Kết quả CI phải xem sau push; sinh SQL không đồng nghĩa đã kiểm thử PostgreSQL live.

Frontend không thay đổi trong lần bổ sung DB; kết quả 10 E2E ở mục trước thuộc lần kiểm thử 15/10, không được tính thành lượt chạy mới.

## Giới hạn xác minh

Google thật cần key/billing; chưa xác minh coverage/ETA Hà Nội. Density threshold và pretrained detector cần nhãn thực/ROI/capacity; chưa có precision/recall/Macro-F1 cho giao thông Hà Nội. Docker/PostgreSQL run cần ghi riêng, không suy từ SQLite tests. Chưa có forecast/training/GPS/RTSP; không dùng số minh họa làm đánh giá khoa học.
