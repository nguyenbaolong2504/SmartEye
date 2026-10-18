# SmartEye

Phân tích mật độ giao thông và hỗ trợ chọn tuyến tại Hà Nội: React + TypeScript, FastAPI, **MongoDB/PyMongo**, YOLO pretrained COCO.

![Giao diện minh họa](docs/preview.png)

## Bắt đầu

**Lệnh Windows đầy đủ, từng terminal, MongoDB portable/Atlas, backend/frontend và Docker:** [docs/RUNNING.md](docs/RUNNING.md).

**Collection, tài khoản mẫu, cách xem/import bằng Compass:** [database/README.md](database/README.md).

Compass là ứng dụng quản lý kết nối; cần MongoDB Server hoặc Atlas để lưu dữ liệu. Có script tải MongoDB portable Windows, không phải cài service. Runtime chỉ dùng MongoDB. SQL cũ được giữ trong `database/legacy-sql/`, không tự di chuyển dữ liệu.

## Tài khoản demo local

Chạy `scripts/init_db.py --demo-accounts` theo hướng dẫn trước khi đăng nhập:

| Vai trò | Email | Mật khẩu demo |
|---|---|---|
| Admin | admin@smarteye.test | SmartEyeAdmin@2026 |
| Analyst | analyst@smarteye.test | SmartEyeAnalyst@2026 |
| User | user@smarteye.test | SmartEyeUser@2026 |

Thông tin công khai chỉ dành cho demo. Startup không tự tạo các tài khoản này. Script giữ nguyên password/role/trạng thái tài khoản đã tồn tại. Bản thật dùng `scripts/create_admin.py` nhập email/mật khẩu riêng. Password trong MongoDB là scrypt hash có salt.

## Chức năng

- Tìm A–B, đổi chiều, ô tô/xe máy, giờ khởi hành, so sánh tuyến theo ETA/km/rủi ro và trọng số; giải thích đề xuất và phần thiếu dữ liệu.
- Video gắn camera/đường: hàng đợi, tiến độ, hủy, lịch sử, ảnh bounding box, biểu đồ từng giây, LOW/NORMAL/HIGH.
- Admin hiệu chỉnh ROI/sức chứa/ngưỡng; video giữ snapshot cấu hình. Analyst/Admin xác nhận trước khi công bố quan sát mới.
- Đăng ký, đăng nhập, hồ sơ, đổi/reset mật khẩu qua SMTP; cookie HttpOnly, session thu hồi được, RBAC User/Analyst/Admin.
- Hành trình yêu thích tính lại khi mở; cảnh báo trong ứng dụng, chống lặp 10 phút; báo cáo và CSV.
- Quản trị user/camera/đường/audit; unique index, TTL token, validation và cập nhật trạng thái video có điều kiện.

## Dữ liệu và phạm vi

Video tối đa 150 MB / 300 giây. Lấy mẫu một ảnh/giây, đếm car/motorcycle/motorbike/bus/truck cả khi đứng yên. Score `min(1,max(occupancy,vehicle_count/capacity))`, occupancy tính hợp bounding box trong ROI. Tổng hợp bằng trung vị score; số xe là hiện diện mỗi ảnh, không phải lưu lượng xe đi qua.

Chỉ Analyst/Admin công bố clip quay trong 15 phút và camera/đường hợp lệ; một video công bố một lần. Video gốc xóa sau xử lý/hủy; ảnh/kết quả giữ đến khi user xóa. Demo có 13 đoạn nối 9 địa điểm, 4 camera, geometry/km/vận tốc minh họa; dữ liệu thiếu/cũ có rủi ro trung tính 0,5.

Chưa có dự báo +5/+10/+15 phút, training pipeline, RTSP hoặc GPS dẫn đường. Detector pretrained COCO và quy tắc mật độ cần nhãn thực để đánh giá cho giao thông Hà Nội.

Google thật dùng hai khóa riêng `GOOGLE_ROUTES_API_KEY`/`GOOGLE_MAPS_BROWSER_KEY`, bật API/billing và giới hạn khóa phù hợp, sau đó restart backend. Không cần khóa cho demo. Giữ Google ETA; camera chỉ bổ sung rủi ro khi đường đã khảo sát khớp tuyến. Không lưu Google responses/polyline vào DB/CSV/training; xem [Routes policies](https://developers.google.com/maps/documentation/routes/policies).

## Tài liệu

[Cách chạy](docs/RUNNING.md) · [Database](database/README.md) · [Nghiệp vụ](docs/business-rules.md) · [Kiến trúc](docs/architecture.md) · [API](docs/api.md) · [Kiểm thử](docs/validation.md).

`src/`: frontend · `backend/app/`: API/PyMongo/RBAC/worker · `backend/tests/`: Pytest · `tests/e2e/`: Playwright · `scripts/`: bootstrap/download/kiểm tra · `deploy/`: Nginx/Mongo init.
