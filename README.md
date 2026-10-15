# SmartEye

Hệ thống hỗ trợ lựa chọn tuyến đường tại Hà Nội dựa trên **Thấp / Bình thường / Cao**, nhận dạng phương tiện từ video bằng YOLO, backend FastAPI và frontend React + TypeScript.

![Giao diện SmartEye ở chế độ minh họa](docs/preview.png)

## Chức năng

- Tìm A–B, đổi chiều, ô tô/xe máy, giờ khởi hành, so sánh các tuyến theo ETA/km/rủi ro và trọng số cá nhân; giải thích đề xuất và phần thiếu dữ liệu.
- Video gắn camera/đoạn đường; hàng đợi, tiến độ, hủy, lịch sử, ảnh bounding box, biểu đồ từng giây và ba mức mật độ. YOLO đếm cả xe đứng yên.
- Hiệu chỉnh ROI, sức chứa và hai ngưỡng; snapshot cấu hình theo video. Analyst/Admin xác nhận video mới trước khi đưa vào giao thông hiện tại.
- Đăng ký/login/logout, hồ sơ, đổi mật khẩu, reset qua SMTP; cookie HttpOnly, session thu hồi được và RBAC User/Analyst/Admin.
- Hành trình yêu thích tính lại khi mở, cảnh báo trong ứng dụng, chống lặp 10 phút; báo cáo theo đường/thời gian và xuất CSV.
- Quản trị user, camera, đoạn đường khảo sát và audit; SQLite chạy nhanh, PostgreSQL qua Docker Compose; Pytest, Playwright và GitHub Actions.

## Chạy trên Windows

Yêu cầu Python 3.11+, Node.js 22+, Git. Chạy từ thư mục repo:

**Đã kèm DB mẫu và tài khoản:** xem [database/README.md](database/README.md) để mở file SQLite ngay, xem 11 bảng hoặc gắn PostgreSQL + pgAdmin. Cài riêng `backend/requirements-db.txt` và chạy `scripts/init_db.py --demo-accounts` nếu muốn chuẩn bị DB trước, chưa tải các thư viện video nặng.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
npm ci
.venv\Scripts\python.exe scripts/download_model.py
.venv\Scripts\python.exe scripts/create_admin.py
```

`create_admin.py` hỏi email và mật khẩu bằng nhập ẩn. Hoặc đặt `ADMIN_EMAIL`/`ADMIN_PASSWORD` trong `.env` trước lần chạy đầu. **Không có mật khẩu Admin mặc định.** Đăng ký qua web luôn tạo User.

Demo local có thể thay bước `create_admin.py` bằng `.venv\Scripts\python.exe scripts/init_db.py --demo-accounts` để tạo ba tài khoản công khai được liệt kê trong tài liệu DB. Chúng không được tự tạo khi server startup và không dùng để triển khai thật.

```powershell
# Terminal 1
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2
npm run dev
```

Giao diện: <http://127.0.0.1:5173> · API docs: <http://127.0.0.1:8000/docs>. Linux/macOS dùng `.venv/bin/python`. Torch/model có thể cần tải vài trăm MB; lần inference đầu chậm hơn do nạp model.

## Google Maps thật

1. Bật billing, Routes API và Maps JavaScript API trong Google Cloud.
2. `GOOGLE_ROUTES_API_KEY` trong `.env`: khóa server riêng, giới hạn API/IP triển khai.
3. `GOOGLE_MAPS_BROWSER_KEY`: khóa browser riêng, giới hạn HTTP referrer và Maps JavaScript API. Khóa browser hiển thị ở client theo cơ chế Google; không dùng chung khóa server.
4. Restart backend, chọn Google Routes; có thể nhập tọa độ `vĩ độ,kinh độ` tại Hà Nội.

Hệ thống yêu cầu traffic-aware routing và traffic-on-polyline. Không tự đổi xe máy thành ô tô. Timeout/quota/key lỗi/một tuyến/thiếu traffic có xử lý riêng. ETA Google được giữ nguyên; camera chỉ bổ sung rủi ro khi đoạn **đã khảo sát** khớp tuyến. Đoạn minh họa không ảnh hưởng Google.

Google polyline chỉ hiển thị trên Google Map; không lưu vào database, xuất báo cáo hoặc dùng huấn luyện. Favorite chỉ lưu input người dùng. Tham khảo [Routes policies](https://developers.google.com/maps/documentation/routes/policies) và [traffic-on-polyline](https://developers.google.com/maps/documentation/routes/traffic_on_polylines). Google phân loại **tốc độ**; camera phân loại **mật độ** và UI ghi riêng hai phép đo.

## Quy trình video

1. Admin tạo đoạn đường và camera, hiệu chỉnh ROI chỉ gồm mặt đường, sức chứa và ngưỡng.
2. User tải clip tối đa 150 MB / 300 giây, chọn camera và thời điểm quay nếu biết.
3. Lấy mẫu một ảnh/giây; chỉ đếm car/motorcycle/motorbike/bus/truck. `score=min(1,max(occupancy,vehicle_count/capacity))`; occupancy là **hợp** bounding box cắt theo ROI, tránh cộng trùng diện tích.
4. Score dưới ngưỡng thấp: LOW; từ ngưỡng thấp đến dưới ngưỡng cao: NORMAL; còn lại HIGH. Tổng hợp bằng trung vị score. Số xe là hiện diện mỗi ảnh, không phải tổng xe đi qua.
5. Analyst/Admin xác nhận công bố video có thời điểm quay còn trong 15 phút, camera hoạt động/không đổi đoạn; mỗi video công bố một lần. Clip cũ chỉ xem lịch sử.
6. Quan sát mới ảnh hưởng lần tìm tuyến tiếp theo và phát cảnh báo. Video gốc xóa sau xử lý/hủy; ảnh/kết quả giữ đến khi user xóa.

Mật độ là quy tắc hiệu chỉnh, **không phải classifier ùn tắc Hà Nội đã được huấn luyện**, không phải xác suất và không đo vận tốc pixel. YOLO pretrained COCO là detector độc lập. Cần nhãn thực theo từng camera để đánh giá trước sử dụng thực tế. Tham khảo [YOLO Predict](https://docs.ultralytics.com/modes/predict/) và [giấy phép Ultralytics](https://www.ultralytics.com/license).

## Minh họa

13 đoạn nối 9 địa điểm; geometry thẳng, hai chiều, km và vận tốc là mô phỏng. Không tự gán mật độ giả: đoạn thiếu/cũ hiện “Chưa có dữ liệu”, rủi ro trung tính 0,5. Vận tốc ô tô 35/22/9 km/h, xe máy 30/24/12 km/h; thiếu dữ liệu 25 km/h. Không mô hình hóa đường một chiều/cấm rẽ/cấm xe; không dùng sơ đồ này để dẫn đường.

## Docker Compose

`.env` cần `POSTGRES_PASSWORD` riêng, nên dùng chuỗi chữ/số dài; đặt `APP_BASE_URL=http://localhost:8080` khi chạy Docker local.

```powershell
docker compose up --build -d
docker compose exec backend python scripts/download_model.py
docker compose exec backend python scripts/create_admin.py
```

Mở <http://localhost:8080>. Backend/database không mở cổng ra host, Nginx proxy `/api`. PostgreSQL trong volume; video/model ở `backend/data`. Triển khai Internet cần HTTPS, `APP_ENV=production`, `COOKIE_SECURE=true`, `APP_BASE_URL` đúng origin và secrets riêng. Giữ **một backend worker** cho hàng đợi hiện tại. HTTP local dùng `COOKIE_SECURE=false`. PostgreSQL lưu geometry JSON, chưa dùng PostGIS.

## Kiểm thử

```powershell
.venv\Scripts\python.exe -m pytest
npm run build
npx playwright install chromium
npm run test:e2e
```

E2E tự dùng database riêng `backend/data/e2e.db`, API 8011, frontend 5174 và tài khoản `example.invalid` với mật khẩu chỉ dành cho test. Không triển khai database E2E. Hai cổng cần trống.

Inference thực với ảnh phương tiện bạn có quyền dùng:

```powershell
.venv\Scripts\python.exe scripts/smoke_video.py C:\path\vehicle-image.jpg
```

Script tạo clip hai giây từ ảnh đứng yên, chạy YOLO và kiểm tra xe vẫn được đếm/video gốc bị xóa. Không thay thế đánh giá accuracy trên dataset Hà Nội.

## Cấu trúc và phạm vi

`src/`: UI · `backend/app/`: API/ORM/RBAC/routing/worker · `backend/tests/`: Pytest · `tests/e2e/`: Playwright · `scripts/`: bootstrap/model/smoke · `deploy/`: Nginx · `docs/`: tài liệu.

Xem [nghiệp vụ](docs/business-rules.md), [kiến trúc](docs/architecture.md), [API](docs/api.md), [kiểm thử](docs/validation.md). Theo yêu cầu cuối: video → ba mức mật độ → lựa chọn tuyến. Chưa có forecast +5/+10/+15 phút, training pipeline riêng, RTSP trực tiếp hoặc GPS turn-by-turn.
