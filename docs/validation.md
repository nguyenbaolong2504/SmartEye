# Kiểm thử

- Build: TypeScript strict và Vite production.
- Pytest: DB tạm riêng, business/RBAC/privacy/Google MockTransport.
- Playwright: DB/server riêng, desktop Chromium và viewport iPhone 13 bằng Chromium.
- Inference smoke: YOLO thật trên video hai giây đứng yên từ ảnh phương tiện, kiểm tra raw deletion; không đo accuracy Hà Nội.

## Chuyển MongoDB, ngày 18/10/2026

Đây là kết quả của runtime MongoDB hiện tại; các mục SQLite/PostgreSQL phía dưới là lịch sử phiên bản cũ.

| Kiểm tra | Kết quả |
|---|---|
| Pytest với MongoDB 8.0.32 thật (portable Windows, localhost:27019) | **49 passed** |
| Playwright với MongoDB thật, desktop + mobile Chromium | **10 passed**, có YOLO inference thật |
| TypeScript strict + Vite production build | Passed |
| pip check | No broken requirements found |
| Compose đầy đủ và override DB local: config --quiet | Passed |
| MongoDB CLI check/init/demo | Passed; lần đầu tạo 3 user, lần sau giữ cả 3; từ chối demo ở production |
| MongoDB portable download | Tải riêng mongod.exe từ ZIP chính thức; ZIP CRC đúng; executable xác nhận v8.0.32 |

Kiểm tra mới gồm JSONSchema trên server thật, unique email/công bố video/alert, TTL index token, counters sau import Compass, restore JSON và đăng ký ID kế tiếp, login/RBAC ba tài khoản mẫu, session auth_version, reset token một lần, và cập nhật video không ghi đè trạng thái cancelled. Setup env giữ API key, sao lưu file cũ và giữ password Docker khi chuyển local rồi quay lại.

Lượt E2E đầu timeout ở page.goto đợi load trên desktop; trace cho thấy Vite tải lạnh và Google Fonts chưa trả lời. Lượt đầy đủ sau khởi động lại server qua 10/10, không tăng timeout hoặc bỏ bài kiểm thử. Cold start phụ thuộc mạng/ổ đĩa; đây không phải phép đo hiệu năng.

Docker Desktop lỗi quyền truy cập Windows socket dockerInference rồi docker-secrets-engine/engine.sock; Engine chưa hoạt động nên **chưa build/run ba container**. Không suy kết quả Compose runtime từ config validation hoặc MongoDB portable. Google/SMTP thật và Atlas chưa cấu hình nên chưa kiểm tra live; đường tích hợp Google dùng mock. CI đã chuyển sang MongoDB 8.0 service; kết quả CI cần xem trên GitHub sau push.

**Cập nhật khi Docker Engine đã hoạt động, cùng ngày 18/10:** image đã được build trên máy. Kiểm tra thực tế thấy MongoDB/backend healthy, frontend còn Created do cổng 8080 bị process khác sử dụng. Chuyển FRONTEND_PORT sang 8081, ghép APP_BASE_URL backend theo cổng frontend rồi chạy `docker compose up -d --wait` thành công; không đổi MongoDB volume/credentials. Cả ba container Running, MongoDB/backend healthy. Xác minh frontend HTML HTTP 200, `/api/health` qua Nginx HTTP 200/database mongodb, video_available true và đăng nhập/logout đủ ba tài khoản demo với Origin `http://localhost:8081`. Đã mở giao diện thật trong browser và thấy 13 đường/4 camera. Kết quả này thay thế giới hạn chưa chạy Docker ở đoạn trên; chưa xác minh Google/SMTP/Atlas live.

MongoDB kiểm thử có DB riêng; không dùng tài khoản/token/video cá nhân làm fixture. `database/mongodb/` chỉ chứa dữ liệu demo công khai; dữ liệu SQL cũ giữ ở `database/legacy-sql/`, không có migration tự động sang MongoDB.

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
