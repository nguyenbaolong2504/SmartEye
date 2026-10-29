# SmartEye

Hệ thống chạy thử **dự báo ùn tắc và lựa chọn tuyến đường Hà Nội**, dùng React/TypeScript, FastAPI, MongoDB và XGBoost.

## Bản giao diện rút gọn

- Bản đồ OpenStreetMap có đường/ngõ, nhập số nhà và chọn ghim A/B.
- Tìm tuyến tự động, cân bằng thời gian và khoảng cách; không cần chọn nguồn hay thuật toán. Ô tô dùng các tuyến OSRM đã tiền xử lý và cache 10 phút để tránh tải mạng Overpass mỗi lần. A* là mặc định cho mạng đường tự quản lý; Dijkstra giữ để đối chiếu qua API.
- Tình trạng từng đường, biểu đồ 24 giờ, bản đồ nhiệt theo tháng và tải CSV mẫu.
- Dự báo sau 15/30 phút bằng **XGBoost được huấn luyện thật trên dữ liệu mô phỏng**. Có thể thử giờ cao điểm sáng/chiều hôm qua.
- Đã gỡ trang nhận diện video, lựa chọn kỹ thuật và liên kết mã nguồn khỏi giao diện. Không còn các thẻ camera trống. Upload video mặc định trả HTTP 410; bản ghi cũ vẫn được bảo toàn.
- Tải từng trang khi cần, một API khởi tạo, ngừng polling khi tab bị ẩn. Gói JS ban đầu giảm khoảng 373 → 252 KB (chưa nén).

**DỮ LIỆU MÔ PHỎNG không phải giao thông thực tế.** Mặc định phát sinh 31 ngày trước và ngày hiện tại, có giờ cao điểm, cuối tuần và nhiễu. Nhãn/mô hình mẫu nằm riêng, không ghi đè quan sát hay mô hình thực. Chuyển sang “Quan sát thực tế” ở đầu trang để xem đúng dữ liệu đã thu thập. [Cách tạo, chạy thử và giới hạn](docs/DEMO.md).

## Chạy bằng Docker

Máy đã cài và build xong:

```powershell
cd C:\Users\Admin\Documents\GitHub\SmartEye
docker compose up -d --wait --wait-timeout 240
```

Mở [SmartEye tại localhost:8081](http://localhost:8081) trên máy hiện tại (`FRONTEND_PORT=8081`). `.env.example` mặc định cổng 8080; URL phụ thuộc `FRONTEND_PORT` của bạn. Docker chạy cả frontend, backend và MongoDB; không cần chạy npm/uvicorn riêng.

Sau khi cập nhật code:

```powershell
git pull --ff-only
docker compose up -d --build --wait --wait-timeout 240
docker compose ps
Invoke-RestMethod http://localhost:8081/api/health
```

Lần đầu khởi động bản này, backend chuẩn bị dữ liệu mẫu và huấn luyện XGBoost ở nền. Trang sẽ tự cập nhật khi sẵn sàng. Tạo lại thủ công nếu cần:

```powershell
docker compose exec backend python scripts/prepare_demo.py --days 31
```

Dừng: `docker compose stop`. Lần sau chạy lại: `docker compose up -d`. Không dùng `down -v` nếu muốn giữ database.

[Cài mới, chạy local và Docker đầy đủ](docs/RUNNING.md) · [MongoDB/Compass](database/README.md).

## Tài khoản demo local

Nếu chưa tạo: `docker compose exec backend python scripts/init_db.py --demo-accounts`.

| Vai trò | Email | Mật khẩu demo |
|---|---|---|
| Admin | admin@smarteye.test | SmartEyeAdmin@2026 |
| Quản lý | analyst@smarteye.test | SmartEyeAnalyst@2026 |
| Người dùng | user@smarteye.test | SmartEyeUser@2026 |

Thông tin công khai chỉ dành cho demo. Script giữ password/quyền của tài khoản đã tồn tại. Tài khoản database khác tài khoản website; MongoDB lưu password website dưới dạng hash.

## Mô hình và thuật toán

| Thành phần | Cách dùng hiện tại |
|---|---|
| XGBoost | Dự báo mẫu FREE / SLOW / JAM sau 15 và 30 phút; cửa sổ lịch sử 60 phút, chia train/validation/test theo thời gian |
| GRU | Pipeline nghiên cứu trên dữ liệu/nhãn thực, trong phần Dữ liệu & mô hình của Quản lý/Admin; chưa tự tuyên bố tốt hơn XGBoost |
| A* | Mặc định tìm chi phí kết hợp trên đồ thị SmartEye hoặc mạng OSM tải đầy đủ |
| Dijkstra | Thuật toán tham chiếu và chuẩn hóa chi phí; có API đối chiếu, không cần lựa chọn trên giao diện |
| OSRM | Dịch vụ cung cấp nhanh các tuyến ô tô trên OSM. SmartEye xếp hạng các tuyến được trả về; không tuyên bố chạy A* trên đồ thị nội bộ của dịch vụ |
| YOLO | Chức năng nhận diện đã tắt và gỡ khỏi giao diện; mã đọc dữ liệu cũ giữ để tương thích |

Nguồn OSRM mặc định hỗ trợ ô tô. Xe máy vẫn dùng mạng OSM và A* có kiểm tra quyền phương tiện nên lần tải đầu có thể chậm. Thời gian/khoảng cách là ước tính, chưa phải dẫn đường thời gian thực. Phần đường không có dữ liệu không được coi là thông thoáng. Các dịch vụ công cộng có thể gián đoạn; dùng máy chủ riêng khi cần tải lớn.

Đăng ký/đăng nhập, hồ sơ, hành trình yêu thích, cảnh báo theo quan sát thực, nhập CSV, phân quyền và nhật ký quản trị vẫn có sẵn. Dữ liệu mô phỏng không phát cảnh báo thật cho người dùng.

## Tài liệu kỹ thuật

[Dữ liệu demo](docs/DEMO.md) · [Bản đồ](docs/MAPS.md) · [Pipeline XGBoost/GRU trên dữ liệu thực](docs/FORECASTING.md) · [API](docs/api.md) · [Kiểm thử](docs/validation.md).

`src/`: frontend · `backend/app/`: API/PyMongo/mô hình · `backend/tests/`: Pytest · `tests/e2e/`: Playwright · `scripts/`: khởi tạo và dữ liệu mẫu · `deploy/`: Nginx/Mongo init.
