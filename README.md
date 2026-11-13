# SmartEye

Hệ thống chạy thử **dự báo ùn tắc và lựa chọn tuyến đường Hà Nội**, dùng React/TypeScript, FastAPI, MongoDB và XGBoost.

## Chọn ngày, giờ và tránh giờ cao điểm

Giao diện đã bỏ thanh chọn nguồn dữ liệu phía trên và tên mô hình khỏi các màn hình người dùng. **Dự báo giao thông** mặc định xem ngày mai lúc 17:00: chọn tuyến/ngày/giờ, xem khung giờ nên tránh, số ngày phù hợp từng ùn tắc và các giờ có thể cân nhắc thay thế. **Tình trạng & thống kê** có một năm lịch sử, so sánh tháng và giờ cao điểm theo từng thứ. Khi tìm tuyến có thể bấm **So sánh giờ đi** để xem giờ đã chọn và một giờ trước/sau.

Dữ liệu minh họa mặc định tạo **365 ngày đã qua cùng ngày hiện tại** cho 14 tuyến, lưu riêng với dữ liệu thật. Phần dự báo ngày mai học từ các tuần trước; không lấy nhãn được sinh sẵn của ngày tương lai để trả kết quả. [Hướng dẫn và giới hạn](docs/PLANNING.md).

Google Maps đã được chuẩn bị: khi có cả hai khóa, trang tìm tuyến dùng Google và gửi đúng giờ khởi hành để nhận dự tính giao thông. **Hiện chưa có khóa nên bản đang chạy dùng lịch sử minh họa và OpenStreetMap.** Không lấy dữ liệu một năm bằng cách sao chép Google Maps, không lưu phản hồi Google vào lịch sử hay mô hình.

## Bản giao diện rút gọn

- Bản đồ OpenStreetMap có đường/ngõ, nhập số nhà và chọn ghim A/B.
- Tìm tuyến tự động, cân bằng thời gian và khoảng cách; không cần chọn nguồn hay thuật toán. Ô tô dùng OSRM, xe máy dùng chế độ motorcycle của Valhalla trên mạng đường đã tiền xử lý, cache ứng viên 10 phút. Không tải mạng Overpass mỗi lần tìm thông thường. A* là mặc định cho mạng đường tự quản lý; Dijkstra giữ để đối chiếu qua API.
- Tình trạng từng đường, biểu đồ 24 giờ, bản đồ nhiệt theo tháng và tải CSV mẫu.
- Dự báo ngày sắp tới và các mốc ngắn hạn bằng **XGBoost được huấn luyện thật trên dữ liệu mô phỏng**. Có thể chọn ngày mai hoặc một ngày trong 7 ngày tới.
- Đã gỡ trang nhận diện video, lựa chọn kỹ thuật và liên kết mã nguồn khỏi giao diện. Không còn các thẻ camera trống. Upload video mặc định trả HTTP 410; bản ghi cũ vẫn được bảo toàn.
- Tải từng trang khi cần, một API khởi tạo, ngừng polling khi tab bị ẩn. Gói JS ban đầu giảm khoảng 373 → 252 KB (chưa nén).

**DỮ LIỆU MÔ PHỎNG không phải giao thông thực tế.** Mặc định phát sinh 365 ngày trước và ngày hiện tại, có giờ cao điểm, cuối tuần và nhiễu. Nhãn/mô hình mẫu nằm riêng, không ghi đè quan sát hay mô hình thực. Kết quả liên quan có ghi chú nguồn lịch sử minh họa hoặc quan trắc. [Cách tạo, chạy thử và giới hạn](docs/DEMO.md).

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
docker compose exec backend python scripts/prepare_demo.py --days 365
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

Admin quản lý tài khoản, phân quyền, nguồn dữ liệu, đoạn đường, camera, mô hình và nhật ký hệ thống trong **Quản trị hệ thống**. Báo cáo theo giờ nằm trong **Giám sát & xử lý** của Quản lý. Quản lý còn có các chức năng cấu hình được cấp trong **Dữ liệu & thiết lập**, giới hạn theo tuyến phụ trách.

Thông tin công khai chỉ dành cho demo. Script giữ password/quyền của tài khoản đã tồn tại. Tài khoản database khác tài khoản website; MongoDB lưu password website dưới dạng hash.

## Mô hình và thuật toán

| Thành phần | Cách dùng hiện tại |
|---|---|
| XGBoost | Dự báo theo ngày/giờ từ lịch sử 7/14/21/28 ngày trước và đặc điểm thời gian; vẫn giữ pipeline ngắn hạn; chia train/validation/test theo thời gian |
| GRU | Pipeline nghiên cứu trên dữ liệu/nhãn thực, trong phần Dữ liệu & mô hình của Admin hoặc Quản lý được cấp quyền. Dùng để so sánh với XGBoost |
| A* | Mặc định tìm chi phí kết hợp trên đồ thị SmartEye hoặc mạng OSM tải đầy đủ |
| Dijkstra | Thuật toán tham chiếu và chuẩn hóa chi phí; có API đối chiếu, không cần lựa chọn trên giao diện |
| OSRM | Dịch vụ cung cấp nhanh các tuyến ô tô trên OSM. SmartEye xếp hạng các tuyến được trả về; không tuyên bố chạy A* trên đồ thị nội bộ của dịch vụ |
| YOLO11 | Đếm xe và đo mức chiếm vùng quan sát trong video tại trang Camera giao thông. Video mẫu có nguồn và giấy phép riêng; màn hình tải video cá nhân vẫn được gỡ |
| ByteTrack | Theo dõi mã xe qua các khung hình để đếm cộng dồn, tránh cộng lại cùng xe đang đứng chờ; có thể sai khi mất dấu hoặc camera chuyển động |

Nguồn OSRM mặc định hỗ trợ ô tô. Xe máy dùng Valhalla motorcycle, yêu cầu loại cao tốc và kiểm tra kết quả trả về; không dùng tuyến ô tô/xe đạp thay thế. Cache chỉ giữ ứng viên hình học/ETA tham chiếu; ưu tiên và tình trạng giao thông được tính lại mỗi lần. Thời gian/khoảng cách là ước tính, chưa phải dẫn đường thời gian thực. Phần đường không có dữ liệu không được coi là thông thoáng. Các dịch vụ công cộng có thể gián đoạn; dùng máy chủ riêng khi cần tải lớn. [Chi tiết định tuyến và giới hạn](docs/MAPS.md).

Đăng ký/đăng nhập, hồ sơ, hành trình yêu thích, cảnh báo theo quan sát thực, nhập CSV, phân quyền và nhật ký vận hành giao thông vẫn có sẵn. Dữ liệu mô phỏng không phát cảnh báo thật cho người dùng.

## Tài liệu kỹ thuật

[Dữ liệu demo](docs/DEMO.md) · [Bản đồ](docs/MAPS.md) · [Pipeline XGBoost/GRU trên dữ liệu thực](docs/FORECASTING.md) · [API](docs/api.md) · [Kiểm thử](docs/validation.md).

**Video camera mẫu:** chạy `docker compose exec backend python scripts/download_model.py` rồi `docker compose exec backend python scripts/setup_camera_videos.py --rush-hour --regions`. Mở **Camera giao thông** để xem bảy clip góc cao khác nhau, sức chứa theo bề rộng/chiều dài đường, ô nhận diện và số ô tô/xe máy/xe buýt/xe tải đồng bộ từng khung hình. Dự báo chạy thử 15/30/60 phút xét thêm thời tiết, sự cố đã công bố và điều kiện đường, có tỷ lệ và nút **Vì sao?**, cho thử mưa lớn/tai nạn/ngập. Mô hình học trên lịch sử/điều kiện minh họa, chưa được kiểm chứng ngoài đường. [Nguồn video, cách cài và giới hạn](docs/DEMO.md#video-camera-và-dự-báo-mật-độ).

Thêm `--rush-hour` vào lệnh chuẩn bị video để có **Ngã Tư Sở · Tình huống 17:00**. Trang tách số xe cộng dồn bằng ByteTrack và số xe đang xuất hiện; có nút xem đoạn đông xe nhất và dự báo cho 17:15/17:30. Đây là tình huống minh họa, chưa xác minh video quay tại Ngã Tư Sở hoặc lúc 17:00.

`src/`: frontend · `backend/app/`: API/PyMongo/mô hình · `backend/tests/`: Pytest · `tests/e2e/`: Playwright · `scripts/`: khởi tạo và dữ liệu mẫu · `deploy/`: Nginx/Mongo init.
