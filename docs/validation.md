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

## Giới hạn xác minh

Google thật cần key/billing; chưa xác minh coverage/ETA Hà Nội. Density threshold và pretrained detector cần nhãn thực/ROI/capacity; chưa có precision/recall/Macro-F1 cho giao thông Hà Nội. Docker/PostgreSQL run cần ghi riêng, không suy từ SQLite tests. Chưa có forecast/training/GPS/RTSP; không dùng số minh họa làm đánh giá khoa học.
