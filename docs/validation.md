# Kiểm thử

- Build: TypeScript strict và Vite production.
- Pytest: DB tạm riêng, business/RBAC/privacy/Google MockTransport.
- Playwright: DB/server riêng, desktop Chromium và viewport iPhone 13 bằng Chromium.
- Inference smoke: YOLO thật trên video hai giây đứng yên từ ảnh phương tiện, kiểm tra raw deletion; không đo accuracy Hà Nội.

## Dự báo XGBoost / GRU và giao diện, ngày 29/10/2026

- Backend: **94 passed, không skip** trên MongoDB 8.0.32 thật ở localhost:27019, DB tạm tự tạo/xóa theo bài. Có huấn luyện CPU XGBoost và GRU thật, lưu/nạp trọng số, phục vụ dự báo qua API và kiểm tra kích hoạt. Đây là dữ liệu tổng hợp cô lập cho kiểm thử phần mềm, không phải mô hình đã đánh giá tại Hà Nội.
- Kiểm tra cửa sổ liên tiếp, thiếu dữ liệu, mốc nhãn tương lai, khoảng cách train/validation/test, nhãn ùn tắc độc lập, preview/commit CSV và CSV nhãn, quyền operator/Admin, khóa huấn luyện, hủy tác vụ, tệp thiếu và phạm vi từng tuyến. Tìm tuyến chỉ ghép dự báo đúng thời điểm.
- TypeScript strict / Vite production build đạt. Toàn bộ **22 E2E desktop/mobile đạt**, bao gồm YOLO thật, archive, chia sẻ/phát video, camera, thống kê, tài khoản và các màn hình mới. Sáu bài của trang dự báo được chạy thêm sau khi bổ sung CSV nhãn và tự làm mới; đạt đủ.
- Kiểm thử thẻ dự báo có kết quả dùng API contract fixture riêng, không ghi dự báo giả vào database. Ảnh preview là giao diện với mạng đường demo/DB E2E; không phải kết luận giao thông thực địa.
- Tệp model/dataset không commit; source không kèm forecast model đã huấn luyện cho Hà Nội. Nâng cấp tự thêm ba collection, giữ dữ liệu và tài khoản hiện có. Chưa xác minh triển khai bản mới trong Docker local; ổ C chỉ còn khoảng 0,7 GB ở thời điểm kiểm tra. CI Linux cần xem theo commit sau push.

CI đầu của commit `87369d6` có frontend đạt, backend/E2E dừng ở Initialize containers: MongoDB 8.0 từ chối kernel >=6.19 trên runner Ubuntu 24.04.5, trước khi code dự án được chạy. Đã pin hai job MongoDB sang Ubuntu 22.04 (kernel 6.8) và image 8.0.32, cùng nhánh phiên bản đã kiểm thử local; không bỏ bài kiểm thử hoặc thay DB bằng mock. Nguồn: [MongoDB SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912), [runner Ubuntu 22.04](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2204-Readme.md). Cần cập nhật runner khi MongoDB hỗ trợ kernel mới và trước khi label 22.04 hết hỗ trợ.

## Docker và đăng nhập, ngày 28/10/2026

- Docker local đã chạy lại: MongoDB và backend healthy, frontend HTTP 200, health API báo `status=ok` và `database=mongodb`. Kiểm tra DB xác nhận 13 collection (12 nghiệp vụ và counters).
- Tái hiện lỗi: POST đăng nhập qua `127.0.0.1:8081` với Origin cùng địa chỉ trả 403, trong khi `localhost:8081` đi qua kiểm tra nguồn. Nginx dùng `$host` nên bỏ cổng, làm backend không nhận đúng nguồn của browser.
- Sửa Nginx chuyển `Host $http_host`, build/recreate riêng frontend; backend và MongoDB tiếp tục chạy. `nginx -t` thành công.
- Đã xác minh qua HTTP thật cả `localhost:8081` và `127.0.0.1:8081`: đăng nhập tài khoản demo User, đọc `/api/auth/me`, đăng xuất và xác nhận phiên hết hiệu lực đều đạt. Yêu cầu thiếu email/password cùng nguồn trả 422; Origin khác cổng hoặc domain lạ vẫn trả 403. Không đổi tài khoản/mật khẩu hoặc tắt kiểm tra nguồn; không in cookie phiên.

## Camera và thống kê ngày/tháng, ngày 27/10/2026

- Backend: **72 passed** với MongoDB 8.0.32 thật, chạy cô lập tại localhost:27019 với data test ở ổ D. Có kiểm tra lịch UTC+7/tháng nhuận, chuẩn hóa ô 5 phút, ngưỡng từng camera, điều kiện lặp lại nhiều ngày, lưu lịch sử, giữ/xóa/chia sẻ video, HTTP Range và nối lịch sử cùng thứ/giờ vào API tìm tuyến.
- Hai bài worker kiểm tra OpenCV đọc video thật và chính sách giữ/xóa tệp; detector được thay bằng stub riêng trong unit test. Không dùng kết quả này làm bằng chứng inference YOLO thật.
- **12 E2E passed** trên Chromium desktop và mobile: camera board/bộ lọc, ngày/tháng/bản đồ nhiệt, khung giờ lặp lại qua 3 ngày, cùng các luồng tìm tuyến/tài khoản/quản trị cũ. Dữ liệu lịch sử minh họa chỉ được tạo trong `smarteye_e2e`, không vào DB triển khai.
- Frontend: TypeScript strict và Vite production build passed. E2E dùng bản production preview để tránh phụ thuộc lượt biến đổi Vite dev lạnh trên Windows.
- Có 4 E2E liên quan inference thật/phát video sau inference (2 luồng × desktop/mobile) chưa hoàn tất trong lượt xác minh cuối. Windows báo WinError 4551 Application Control chặn torch_python.dll. Build Docker để chuyển inference sang Linux đã cài xong dependency và export frontend, nhưng thất bại giải nén backend khi ổ C đầy; Engine chuyển filesystem chỉ đọc.
- Đã sao lưu 824 MiB cache tải pip sang `D:\Temp\SmartEye-build-cache-backup`, giữ venv, source, DB và video. Docker sau restart còn lỗi socket dockerInference/docker-secrets-engine; không sửa ACL, tắt Application Control hoặc factory reset. Chưa xác nhận deploy chạy bản mới trên Docker local sau lỗi này. Kết quả CI Linux cần xem riêng sau push.

Ảnh `docs/previews/traffic-month-demo.png` là giao diện dùng dữ liệu tổng hợp trong DB E2E; không phải đánh giá mật độ thực tế của đường trong ảnh. Nguồn camera của phiên bản mới là video tải lên theo lựa chọn người dùng; chưa có URL camera trực tiếp được cung cấp.

CI đầu tiên của bản camera trên Linux có backend/frontend đạt, E2E 13 passed/2 failed/1 skipped do hai profile cùng cộng dồn giới hạn 180 request/phút của một API. Artifact xác nhận HTTP 429 ở hai bài cuối; bài video cuối bị bỏ qua sau khi config trả lỗi. Harness đã tách API/DB/proxy desktop và mobile, giữ nguyên giới hạn production; kiểm tra config phải thành công trước khi quyết định skip bài inference. Kết quả lượt CI tiếp theo cần đọc theo commit tương ứng.

**CI Linux đã xác minh thành công:** [run 40475344305](https://github.com/nguyenbaolong2504/SmartEye/actions/runs/40475344305), commit `9a91dd8`, cả backend, frontend và E2E đều success. E2E **16 passed (47.3s), không skip**, bao gồm upload/inference YOLO thật, giữ video, lưu lịch sử, chia sẻ và trình duyệt phát WebM trên desktop/mobile. Backend có 72 bài, frontend production build đạt. Kết quả CI xác nhận luồng phần mềm trên Linux; bản Docker local vẫn chờ người dùng xử lý sau theo lựa chọn trong phiên làm việc.

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
