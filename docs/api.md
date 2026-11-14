# API

Swagger `/docs` trên backend. Cookie cùng origin, không lưu token trong localStorage.

| Nhóm | Endpoint | Quyền |
|---|---|---|
| Public | `GET /api/health`, `/config`, `/places`, `/segments` | Công khai theo quyền của trang giao thông |
| Auth | `POST /api/auth/register`, `/login`, `/logout` | Public/cookie |
| Profile | `GET /api/auth/me`, `PATCH /api/auth/profile`, `POST /api/auth/password` | Own |
| Reset | `POST /api/auth/forgot-password`, `/reset-password` | Public/token |
| Route | `POST /api/routes/search` | Public, 20/min/IP |
| Upload | `POST /api/videos` multipart file/camera_id/observed_at? | User |
| Jobs/frames | `GET /api/videos`, `/{id}`, `/{id}/frames/{second}` | Chủ sở hữu, tài khoản Người dùng hoặc Quản lý |
| Cancel/delete | `POST /api/videos/{id}/cancel`, `DELETE /api/videos/{id}` | Chủ sở hữu, tài khoản Người dùng hoặc Quản lý |
| Publish | `POST /api/videos/{id}/publish` | Quản lý có quyền `sources.manage`, sở hữu tác vụ và phụ trách tuyến |
| Observation | `POST /api/observations` | Admin hoặc Quản lý có `sources.manage`, theo phạm vi tuyến của Quản lý |
| Favorites | `GET/POST /api/favorites`, `DELETE /api/favorites/{id}` | Own |
| Alerts | `GET/POST /api/alerts`, `DELETE /api/alerts/{id}` | Own |
| Notices | `POST /api/notifications/{id}/read` | Own |
| Reports | `GET /api/reports`, `/api/reports/export`, `/api/management/traffic-report`, `/api/management/traffic-report/export` | Quản lý có `analytics.view` hoặc `analytics.export`, theo tuyến được giao |
| Cameras | `GET/POST /api/cameras`, `PUT/DELETE /api/cameras/{id}` | Admin hoặc Quản lý có `network.manage`, theo tuyến được giao |
| Segments | `POST /api/segments`, `PUT/DELETE /api/segments/{id}` | Admin hoặc Quản lý có `network.manage`, tạo mới dành cho Admin hoặc Quản lý toàn bộ tuyến |
| Users | `GET /api/admin/users?q=`, `PATCH /api/admin/users/{id}`, `POST /api/admin/users/{id}/revoke` | Admin |
| Operations | `GET /api/management/operations`, `/api/management/events`, `/api/management/events/{id}` | Admin xem toàn bộ nhật ký, Quản lý toàn bộ tuyến có `diagnostics.view` xem nhật ký vận hành giao thông |
| Sources | `GET/POST /api/management/sources`, `/{id}`, `/{id}/mapping`, `/{id}/test`, `/{id}/toggle`, `/{id}/receive` | Admin hoặc Quản lý có `sources.manage`, theo tuyến được giao |
| Forecast evaluation | `GET /api/management/hourly-backtest` | Quản lý có `analytics.view`, theo tuyến được giao |
| Camera board | `GET /api/monitor/cameras` | Public, không trả user ID hay thông tin tệp riêng tư |
| Shared camera media | `GET /api/monitor/cameras/{id}/frame`, `/{id}/video` | Public chỉ khi đã cho phép chia sẻ, camera/đường còn hoạt động |
| Retained original | `GET /api/videos/{id}/source` | Chủ sở hữu, tài khoản Người dùng hoặc Quản lý, HTTP Range |
| Historical archive | `POST /api/videos/{id}/archive` body `{share_preview:false}` | Quản lý có `sources.manage`, sở hữu tác vụ và phụ trách tuyến, video hoàn tất có thời điểm quay |
| Change sharing | `POST /api/videos/{id}/share-preview` body `{share_preview:true/false}` | Quản lý có `sources.manage`, sở hữu tác vụ và phụ trách tuyến, đã công bố/lưu lịch sử |
| Day/month analytics | `GET /api/traffic/history?segment_id=1&period=day&value=2026-10-01` hoặc `period=month&value=2026-10` | Public, thống kê UTC+7 |

Các đường dẫn tương thích `/api/admin/sources...`, `/api/admin/events`, `/api/admin/events/{id}`, `/api/admin/operations` và `/api/admin/system` dành riêng cho Admin. Báo cáo theo giờ tiếp tục thuộc quyền Quản lý.

Upload nhận thêm form `retain_video=false` mặc định. Publish hiện tại nhận body tùy chọn `{share_preview:false}`; mặc định giữ ảnh/video riêng tư. Archive cho phép video cũ, không biến thời điểm tải lên thành thời điểm quay. Xem [CAMERAS.md](CAMERAS.md) về nguồn dữ liệu, quyền chia sẻ, độ phủ và điều kiện khung giờ lặp lại.

Reports: `segment_id`, `start`, `end` ISO timestamp có timezone. Server UTC, UI giờ Việt Nam. Favorite chỉ input, không polyline/ETA. Job UUID; ảnh giây 0/10/20/…

```json
{"origin":{"lat":21.0287,"lng":105.8524,"node":"hoankiem","name":"Hồ Hoàn Kiếm"},"destination":{"lat":21.0333,"lng":105.7984,"node":"caugiay","name":"Cầu Giấy"},"provider":"demo","mode":"DRIVE","departure_at":null,"weights":{"time":0.45,"distance":0.2,"density":0.35}}
```

Client xử lý 401/403/404/409/413/415/422/429/502/503/504. `detail` có thể chuỗi hoặc validation list. Lỗi file/Google không trả key/traceback. Không bật permissive CORS.

## Dự báo XGBoost / GRU

API dữ liệu, nhãn thực tế, tác vụ huấn luyện, xuất báo cáo, kích hoạt và dự báo 15/30 phút: xem [FORECASTING.md](FORECASTING.md#api). Truy vấn dự báo công khai; chuẩn bị dữ liệu/huấn luyện dành cho Admin hoặc Quản lý có `models.manage` trong phạm vi được giao. Kích hoạt/ngừng mô hình dành cho Admin hoặc Quản lý phụ trách toàn bộ tuyến có cùng quyền.

## Tối ưu tuyến Dijkstra/A*

`provider=osm` nhận tọa độ/địa chỉ đã chọn, dùng dữ liệu đường OpenStreetMap qua Overpass. `GET /api/map/places?q=...` trả gợi ý địa chỉ Photon (tối thiểu 3 ký tự, khu vực Hà Nội). Config thêm `osm_available`, `osm_tile_url`, `address_search_available`. Optimization có `scope=osm_network`, vùng tải và độ lệch ghim/đường; xem [MAPS.md](MAPS.md).

`/api/routes/search` nhận thêm `algorithm` (compare/dijkstra/astar), mặc định astar cho đồ thị tự quản lý. `weights` nhận time/distance và density tùy chọn. Có `optimization` và `cost_components` trong response; scope Google chỉ là tập ứng viên. `/api/segments` hỗ trợ `one_way` mặc định false; `/api/places` gồm cả các nút của đoạn đang hoạt động. Xem [ROUTING.md](ROUTING.md).

Giao diện mặc định dùng `provider=auto`: `DRIVE` lấy các tuyến OSRM (`scope=osrm_candidates`), `TWO_WHEELER` dùng Valhalla motorcycle (`scope=valhalla_candidates`). Cả hai trả `algorithm=null`, chỉ xếp hạng trong tập ứng viên dịch vụ cung cấp. Ứng viên cache 10 phút; thời điểm khởi hành, dữ liệu giao thông và trọng số được đánh giá lại mỗi lần. Xe máy không tải Overpass trong luồng này. Khi đã cấu hình đủ hai khóa Google, auto chuyển sang Google và giữ dữ liệu quan sát thực tách khỏi mô phỏng. [Điều kiện, hạn mức và xác nhận tuyến xe máy](MAPS.md).


## Camera giao thông công khai

- `GET /api/traffic/cameras` trả danh sách camera, tỉnh/thành phố, tuyến, vị trí, trạng thái, mốc thời gian và đường dẫn media được phép chia sẻ. Yêu cầu quyền `cameras.view`, mặc định có cho khách và vai trò Người dùng/Quản lý. Nguồn riêng tư, tên biến xác thực và mã truy cập không xuất hiện trong kết quả.
- `GET /api/traffic/cameras/sources/{id}/frame` lấy ảnh nguồn đã được chia sẻ và bật. Kiểm tra quyền chia sẻ ở từng lượt, giữ bộ nhớ đệm ngắn để giảm tải nguồn. Header `X-Camera-Received-At` ghi lúc máy chủ nhận ảnh từ nguồn. Không dùng mốc này làm thời điểm camera ghi hình.
- `GET /api/traffic/cameras/recordings/{id}/frame` và `/video` đọc media đã được công bố qua luồng camera có sẵn, hỗ trợ HTTP Range cho video.
- `GET /api/traffic/cameras/recordings/{id}/analysis` đọc kết quả video mẫu đã chia sẻ, yêu cầu `cameras.view`. `frames` trả từng khung hình với timestamp, số thứ tự, kích thước, bbox/loại xe/độ tin cậy, số xe từng loại, mức che phủ và mật độ. Có `fps`, `roi`, `capacity` và `detection_version=2`; `samples` giữ một mốc/giây để vẽ biểu đồ. Trường `forecast` là null nếu thiếu `forecast.view`; nếu có sẽ trả mật độ và xác suất ùn tắc minh họa 15/30/60 phút cho từng khung hình, kèm phân bố FREE/SLOW/JAM và thống kê cùng giờ/cùng thứ 100 ngày gần nhất. `probability_kind=calibrated_synthetic`, `real_world_validated=false`. Camera tắt, tuyến tắt, thu hồi chia sẻ hoặc tác vụ khác camera trả 404; cấu hình hiệu chỉnh thay đổi trả `state=outdated`.
- `GET /api/traffic/cameras/recordings/{id}/analysis-frame` đọc khung hình nhận diện giây đầu, kiểm tra cùng quyền/chia sẻ/cấu hình như API phân tích.
- Camera có thêm `road_profile` tùy chọn: số làn, tổng bề rộng trong vùng quan sát (m), chiều dài quan sát (m), phần diện tích sử dụng được và nguồn kích thước ước lượng/đã đo. Thay profile làm phân tích cũ `outdated`. `analysis` có `road_geometry`, `capacity_version`; từng frame có `equivalent_count`, `capacity_pcu`, `load_ratio`, `motion_known`, `stopped_share`, `motion_coverage`, `queue_seconds`, `persistent_queue`. Khi dùng profile, mật độ tính theo số xe quy đổi/sức chứa diện tích, không dùng tổng ID cộng dồn. Khi chưa đủ theo dõi, tỷ lệ đứng/nhích chậm là null. Chuyển động không được công bố như km/h. [Công thức và giới hạn](ROAD-CAPACITY.md).
- Dự báo camera v4 có `evaluation` theo từng mốc: kết quả test giả lập, ECE và `accuracy_target_met`. Mục tiêu từ 80% không được thay cho kết quả test thực đo. Mô hình dùng tải đã chuẩn hóa theo sức chứa và chuyển động bên cạnh điều kiện; vẫn `real_world_validated=false`.
- `POST /api/traffic/cameras/recordings/{id}/forecast` yêu cầu cả `cameras.view` và `forecast.view`, cùng điều kiện camera/tuyến/chia sẻ/hiệu chỉnh như API phân tích. Body: `weather` = auto/dry/light/heavy/fog, `road_condition` = auto/normal/roadwork/obstruction/flood, `incident` = auto/none/accident; mặc định auto. Trả dự báo 15/30/60 phút cho các khung hình cùng `conditions`: thời tiết khu vực, thời điểm/nguồn, các cờ sự cố/đường, lựa chọn giả định. Không ghi đè kết quả dùng chung, không tạo cảnh báo hay quan sát. Không nhận URL hoặc tọa độ tùy ý. Giá trị ngoài danh sách/trường thừa trả 422; video đang xử lý hoặc cấu hình cũ trả 409. Chưa có mô hình phù hợp trả 409.
- Mô hình camera v3 thêm 10 đầu vào điều kiện: mưa, tầm nhìn, gió, cờ có thời tiết, tai nạn, công trình, vật cản, ngập, đường ướt và cờ đã tra cảnh báo. Chỉ đọc snapshot công khai đã phát hành trước mốc dự báo, đúng tuyến/chiều và `start <= issue < end`; không dùng phản ánh chưa xác minh hoặc nội dung riêng. Thời tiết Open-Meteo theo giờ không muộn hơn mốc dự báo, vị trí lấy từ tuyến; có cache/giới hạn chờ, lỗi trả không biết. Đây vẫn là mô hình học từ dữ liệu giả lập, chưa có xác nhận độ chính xác ngoài đường.
- Phân tích có thêm `counting_method=ByteTrack`, `counting_version`, `total_unique_count` và `total_unique_vehicle_counts` cho kết quả cuối clip. Mỗi `frames[]` có `cumulative_count`, `cumulative_vehicle_counts` và `tracked_count`; bbox có `track_id` (có thể null khi chưa xác nhận), `counted_as`. Số cộng dồn tính theo ID đã xác nhận, không cộng tất cả `count` của mọi frame. Client hiển thị số cộng dồn của frame đang phát, không lấy tổng cuối clip để gắn vào giây đầu. `scenario_hour`/`scenario_note` trong nguồn chỉ là giờ giả định của ví dụ, không phải `captured_at`.
- `POST /api/cameras/{id}/analyze-video` yêu cầu `network.manage` và đúng tuyến phụ trách. Chỉ phân tích lại video mẫu cục bộ đã được chuẩn bị bằng script, không nhận URL tùy ý. Trả 202 với mã tác vụ. Camera/tuyến tắt, tác vụ đang xử lý, cấu hình vừa thay đổi hoặc thiếu tệp trả 409; hàng đợi đầy trả 429. Giữ video đang chia sẻ đến khi kết quả mới hoàn tất. Các yêu cầu đồng thời cho cùng camera chỉ giữ một tác vụ. Lượt xử lý thất bại có thể thử lại từ video được chia sẻ trước đó.
- Cấu hình nguồn camera nhận thêm `public_preview` (mặc định false), `location_name` và `position` theo thứ tự vĩ độ, kinh độ. Các nguồn cũ vẫn dùng được và mặc định giữ riêng tư. Đổi cấu hình yêu cầu kiểm tra và bật lại theo luồng nguồn hiện có.
## Phần mở rộng quan trắc giao thông theo ô 5 phút

Xem [công thức, chất lượng dữ liệu và luồng huấn luyện](TRAFFIC-PIPELINE.md). Các API huấn luyện/đăng ký/kích hoạt hiện có nhận thêm `target=traffic`, `direction=forward|reverse`. Mỗi chiều có registry riêng; không tự kích hoạt.

| API | Quyền | Nội dung |
|---|---|---|
| `POST /api/forecast/traffic/windows` | `models.manage` + phạm vi đường | Nhập một ô 5 phút có đơn vị, nguồn và nhãn độc lập |
| `POST /api/forecast/traffic/import?dry_run=true` | `models.manage` + phạm vi đường | Kiểm tra CSV; `dry_run=false` xác nhận ghi/thay thế |
| `GET /api/forecast/templates/traffic.csv` | `models.manage` | Mẫu CSV phù hợp kiểu dữ liệu hiện tại |
| `GET /api/forecast/traffic/windows?segment_id=...&direction=...` | `models.manage` + phạm vi đường | 50 ô gần nhất |
| `GET /api/forecast/predict?target=traffic&segment_id=...&direction=...` | `forecast.view` | 15/30/60 phút đủ điều kiện; xác suất từng trạng thái, tốc độ và CI nếu hồi quy đạt kiểm tra |
| `GET /api/forecast/traffic/outcomes?segment_id=...&direction=...` | `models.manage` + phạm vi đường | Kết quả đối chiếu với quan trắc độc lập |

Camera demo vẫn dùng endpoint analysis/forecast hiện có. Phần giải thích trả thêm `summary.traffic_metrics`, `measurements` và dự tính tốc độ/CI riêng với xác suất. Clip ngắn không tự tạo quan trắc thật. Thiếu hiệu chuẩn trả `null` cho phép đo cần khoảng cách thực; không thay bằng 0.
