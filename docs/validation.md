# Kiểm thử

- Build: TypeScript strict và Vite production.
- Pytest: DB tạm riêng, business/RBAC/privacy/Google MockTransport.
- Playwright: DB/server riêng, desktop Chromium và viewport iPhone 13 bằng Chromium.
- Inference smoke: YOLO thật trên video hai giây đứng yên từ ảnh phương tiện, kiểm tra raw deletion; không đo accuracy Hà Nội.

## Tốc độ tìm tuyến xe máy, ngày 01/11/2026

- Đã bỏ việc tải toàn vùng đường qua Overpass trong nhánh `auto/TWO_WHEELER`. Valhalla nhận chế độ motorcycle riêng, yêu cầu loại cao tốc, giữ chiều đường/quyền phương tiện/hạn chế rẽ; kết quả được kiểm tra cờ cao tốc, chế độ, hình học polyline6 và ghim tối đa 200 m. Không dùng tuyến ô tô/xe đạp làm phương án dự phòng.
- Đo qua Nginx Docker ở `localhost:8081`, giữa hai vị trí công cộng gần Công viên Hòa Bình và đường Âu Cơ: lần đầu HTTP 200, 3 tuyến, **2,961 giây**; lặp cùng yêu cầu **0,015 giây**; dự báo giờ ngày mai trong chế độ minh họa **0,026 giây** và so sánh ba giờ **0,101 giây**. Đây là một mẫu đo, không phải cam kết độ trễ nguồn công cộng. Các tuyến chưa khớp đường có lịch sử giữ ETA tham chiếu, không giả định đã có thông tin ùn tắc.
- Trình duyệt chạy trực tiếp Docker: chọn hai kết quả địa chỉ Photon thật, xe máy và 17 giờ ngày hôm sau; API trả 3 tuyến trong **2,402 giây**, không tràn ngang màn hình desktop. Địa chỉ đầu là kết quả “Khu đô thị Hoàng Quốc Việt”, không khẳng định đó là số nhà cụ thể. [Ảnh giao diện thực](previews/motorcycle-fast-desktop.png).
- Đã kiểm thử bộ nhớ tạm, thay ưu tiên, tính lại giao thông tương lai, nhiều yêu cầu dùng chung lượt tải, giới hạn chờ tuyệt đối, hàng đợi/hạn mức, từ chối cao tốc và dữ liệu nguồn lỗi. Backend dùng MongoDB thật riêng để kiểm tra hồi quy; bốn ca E2E mới về tiến độ tìm xe máy và tìm lại khi lỗi đạt trên desktop/mobile, cùng 28 ca giao diện có sẵn. Nguồn HTTP trong E2E là fixture riêng, không thay nguồn triển khai.
- Build TypeScript/Vite và Docker backend/frontend đạt, triển khai giữ nguyên container/volume MongoDB. Trước/sau đều users=3, segments=14, cameras=4, observations=0. Backend/MongoDB healthy, frontend HTTP 200. Không tạo lại tài khoản hoặc chuẩn bị lại lịch sử một năm.

## Docker đã triển khai bản OSM/dự báo mới, ngày 29/10/2026

- Đã build và recreate backend/frontend trên máy thật; `mongo` và `backend` healthy, frontend HTTP 200 tại `http://localhost:8081`. MongoDB giữ nguyên container/volume trước đó; đối chiếu số bản ghi users=3, segments=13, cameras=4, các nhóm quan sát/video/favorites ban đầu trống đều không đổi. Có 16 collection sau khi tự bổ sung ba collection dự báo.
- Build mặc định gặp timeout khi tải wheel PyTorch CPU hơn 200 MB từ CDN. Đã sửa Dockerfile: tách lớp PyTorch khỏi requirements ứng dụng, bổ sung libgomp1, nâng pip và cấu hình timeout/retry; hỗ trợ base CPU cục bộ qua build arg tùy chọn. Nâng cấp lần này dùng runtime CPU đã có trong image cũ, không tải lại PyTorch; build backend/frontend hoàn tất và pip check đạt. Cách build mặc định cho máy mới vẫn dùng Python slim.
- Chỉ dọn bốn cache build SmartEye cũ đã xác minh (khoảng 2,07 GB); không dùng system prune, không xóa volume hoặc cache dự án khác. Giữ image backend cũ và bản sao file frontend trong backend/data để quay lại khi cần. Ổ C còn khoảng 3,4 GB sau build.
- Kiểm tra thực ngay trong Docker/Linux: PyTorch 2.14.1+cpu; XGBoost 3.2.0 fit/predict; GRU forward/backward và bước Adam; YOLO11n inference thật trên ảnh trống đều đạt. Mẫu mô hình tạm chỉ ở RAM, không ghi số liệu giả hoặc mô hình dự báo thực địa vào DB.
- HTTP qua Nginx: health/database mongodb; đăng nhập, đọc hồ sơ, đăng xuất và xác nhận phiên hết hiệu lực đủ ba vai trò; đăng nhập qua 127.0.0.1:8081 cũng đạt. API tìm tuyến mạng cấu hình trả đối chiếu Dijkstra/A* cùng chi phí.
- Trình duyệt xác nhận giao diện mới mặc định OSM, so sánh Dijkstra/A*, tìm/chọn hai địa danh thật qua Photon, tải nền bản đồ và mở rộng/thu gọn. Lượt tính tuyến OSM thật trả 504 từ nguồn Overpass chậm; đây vẫn là giới hạn dịch vụ ngoài cần theo dõi, không coi Docker healthy là bằng chứng nguồn đường công cộng sẵn sàng. [Ảnh giao diện Docker và thông báo nguồn đường](previews/docker-osm-live.png).

Đã chạy lại đúng lệnh khởi động thông thường `docker compose up -d --wait --wait-timeout 60`: ba container vẫn Running, MongoDB/backend healthy, không phải build lại. `docker buildx build --check --file Dockerfile.backend .` với base mặc định hoàn tất không có cảnh báo.

**CI Linux của bản sửa Docker đã đạt:** [run 40898831851](https://github.com/nguyenbaolong2504/SmartEye/actions/runs/40898831851), commit `b591ca8`; backend, frontend và E2E đều success. Đây là CI ứng dụng; bằng chứng build/runtime Docker local nằm ở các bước kiểm chứng phía trên.

## OpenStreetMap, địa chỉ và mạng đường thực, ngày 29/10/2026

- TypeScript strict và Vite production build đạt; Leaflet được tách thành bundle riêng. Toàn bộ **32/32 E2E desktop/mobile đạt**, gồm lưu/mở lại địa chỉ, tọa độ, nguồn định tuyến, đổi chiều, ghim, zoom, mở rộng và nội dung địa chỉ chưa xác nhận; các luồng dự báo/tài khoản/quản trị/video YOLO thật cũ đều đạt. E2E dùng upstream HTTP (tile, Photon, Overpass), API và DB riêng; không đưa fixture vào dữ liệu triển khai.
- Backend đã chạy trọn với MongoDB 8.0.32 thật trên 27019: **140 passed, không skip**, gồm từ chối tọa độ upstream không hợp lệ. Đã kiểm tra snap trong cạnh, chiều đường, cấm rẽ qua nút, tiếp tục đi thẳng khi cấm quay đầu, quyền xe/bề rộng, giới hạn vùng, phân biệt quan sát demo/khảo sát, tác động mật độ đến ETA, lỗi nguồn, fallback và cache. CI Linux của cùng source cũng đã đạt (liên kết bên dưới).
- Live Photon trả địa danh/số nhà thật ở Hà Nội; trình duyệt tải được nền OSM thật và chụp chi tiết đường/ngõ/công trình/số nhà. Ảnh MAPS.md không có tuyến hoặc traffic giả. Các request tile bị hủy khi chuyển vùng/zoom không được coi là bằng chứng dịch vụ nền luôn có sẵn.
- Overpass công cộng trả quá tải 502 hoặc timeout, kể cả nguồn thay thế, khi kiểm tra vùng Ngọc Hà – Văn Miếu. Vì vậy chưa xác minh thành công một lượt tìm tuyến trọn vẹn với extract Hà Nội vừa tải từ nguồn thật. Tìm tuyến được kiểm chứng trên fixture đồ thị OSM riêng; không suy thành dữ liệu nguồn công cộng đang hoạt động hay độ chính xác giao thông thực địa. Đã thêm timeout, fallback một nguồn, cache 6 giờ và lỗi rõ; không thay bằng tuyến seed khi upstream lỗi.
- Docker Engine hiện phản hồi, container ứng dụng cũ healthy nhưng chưa có module forecast/graph và chưa có thư viện XGBoost/scikit-learn. Ổ C còn khoảng 0,89 GB; chưa build lại image backend đầy đủ hoặc áp dụng source mới vào các container đang chạy. Preview kiểm tra nền thật dùng cổng 5176/8016 và DB riêng, không dùng tài khoản/video/database triển khai. Sau kiểm tra đã dừng preview, xóa đúng ba DB preview/E2E riêng và dừng MongoDB kiểm thử 27019 sau khi xác nhận dbpath ở ổ D; không dừng/xóa DB ứng dụng.

**CI Linux đã xác minh thành công:** [run 40834315698](https://github.com/nguyenbaolong2504/SmartEye/actions/runs/40834315698), commit `abd8d83`; cả backend, frontend và bộ kiểm thử E2E đều success.

## Dijkstra / A* theo thời gian + khoảng cách, ngày 29/10/2026

- Backend **117 passed, không skip** với MongoDB 8.0.32 thật, DB kiểm thử riêng trên 27019. Có oracle vét cạn độc lập đối chiếu Dijkstra/A*/Yen trên 10 đồ thị nhỏ ngẫu nhiên, đường song song, chu trình và các ca heuristic km minh họa không khớp khoảng cách địa lý.
- API kiểm tra tuyến cân bằng không phải ngắn nhất/nhanh nhất, kể cả khi không nằm trong ba tuyến nhanh nhất; đổi ưu tiên làm đổi kết quả; cạnh bị trội không làm đổi mốc chuẩn hóa; đường một chiều, địa điểm mới, favorite giữ thuật toán, trọng số lỗi và phạm vi Google.
- TypeScript strict và Vite production build đạt. Bốn E2E mới kiểm tra so sánh/trọng số và Admin cấu hình đường một chiều đều đạt trên desktop/mobile; 22 luồng cũ đã đạt trong lượt chạy đầy đủ. Nhãn textarea tọa độ được sửa rõ bằng aria-label sau khi E2E phát hiện lỗi chọn nhãn. Không nới timeout hoặc bỏ kiểm thử.
- Screenshot trong ROUTING.md là dữ liệu demo/DB E2E. Đã xác minh đúng thư mục dữ liệu và dừng MongoDB kiểm thử 27019 sau khi hoàn tất, không dừng/xóa DB ứng dụng. Chưa áp dụng vào Docker localhost vì Engine đang không phản hồi ở lượt kiểm tra trước và ổ C thiếu dung lượng cho build.

**CI Linux đã xác minh thành công:** [run 40746545330](https://github.com/nguyenbaolong2504/SmartEye/actions/runs/40746545330), commit `8191e84`; cả backend, frontend và bộ kiểm thử E2E đều success.

## Dự báo XGBoost / GRU và giao diện, ngày 29/10/2026

- Backend: **94 passed, không skip** trên MongoDB 8.0.32 thật ở localhost:27019, DB tạm tự tạo/xóa theo bài. Có huấn luyện CPU XGBoost và GRU thật, lưu/nạp trọng số, phục vụ dự báo qua API và kiểm tra kích hoạt. Đây là dữ liệu tổng hợp cô lập cho kiểm thử phần mềm, không phải mô hình đã đánh giá tại Hà Nội.
- Kiểm tra cửa sổ liên tiếp, thiếu dữ liệu, mốc nhãn tương lai, khoảng cách train/validation/test, nhãn ùn tắc độc lập, preview/commit CSV và CSV nhãn, quyền operator/Admin, khóa huấn luyện, hủy tác vụ, tệp thiếu và phạm vi từng tuyến. Tìm tuyến chỉ ghép dự báo đúng thời điểm.
- TypeScript strict / Vite production build đạt. Toàn bộ **22 E2E desktop/mobile đạt**, bao gồm YOLO thật, archive, chia sẻ/phát video, camera, thống kê, tài khoản và các màn hình mới. Sáu bài của trang dự báo được chạy thêm sau khi bổ sung CSV nhãn và tự làm mới; đạt đủ.
- Kiểm thử thẻ dự báo có kết quả dùng API contract fixture riêng, không ghi dự báo giả vào database. Ảnh preview là giao diện với mạng đường demo/DB E2E; không phải kết luận giao thông thực địa.
- Tệp model/dataset không commit; source không kèm forecast model đã huấn luyện cho Hà Nội. Nâng cấp tự thêm ba collection, giữ dữ liệu và tài khoản hiện có. Chưa xác minh triển khai bản mới trong Docker local; ổ C chỉ còn khoảng 0,7 GB ở thời điểm kiểm tra. CI Linux cần xem theo commit sau push.

CI đầu của commit `87369d6` có frontend đạt, backend/E2E dừng ở Initialize containers: MongoDB 8.0 từ chối kernel >=6.19 trên runner Ubuntu 24.04.5, trước khi code dự án được chạy. Đã pin hai job MongoDB sang Ubuntu 22.04 (kernel 6.8) và image 8.0.32, cùng nhánh phiên bản đã kiểm thử local; không bỏ bài kiểm thử hoặc thay DB bằng mock. Nguồn: [MongoDB SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912), [runner Ubuntu 22.04](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2204-Readme.md). Cần cập nhật runner khi MongoDB hỗ trợ kernel mới và trước khi label 22.04 hết hỗ trợ.

**CI Linux đã xác minh thành công:** [run 40736803473](https://github.com/nguyenbaolong2504/SmartEye/actions/runs/40736803473), commit `0b8c1b2`; cả backend, frontend và E2E đều success.

Đã chạy thêm smoke trọn worker, không thay các hàm huấn luyện bằng stub: 6.912 quan sát sinh riêng qua 8 ngày trong database `smarteye_forecast_smoke_<uuid>`, tạo cửa sổ, huấn luyện cả hai mô hình ở cả hai mốc 15/30 phút, lưu snapshot/báo cáo, áp dụng kiểm soát chất lượng và trả dự báo. Sau kiểm tra đã xóa đúng DB và artifact test vừa tạo. Dữ liệu có quy luật đơn giản nên điểm cao không được dùng làm bằng chứng độ chính xác ngoài thực tế. MongoDB kiểm thử 27019 đã dừng; MongoDB ứng dụng không bị dừng/xóa. Kiểm tra cuối thấy Docker Engine không phản hồi trong 8 giây và localhost:8081 không phản hồi, nên chưa áp dụng bản mới lên Docker local.

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

## Camera video ngày 12/11/2026

Các mục tháng 10 ở trên ghi lại trạng thái tại thời điểm kiểm thử đó. Lượt bổ sung camera video này đã chạy trên Docker với MongoDB; không dùng kết quả cũ thay cho lượt xác minh mới.

- Backend **45 passed** cho camera video, camera công khai, media/quan trắc và đoạn đường. Chạy trong Linux Docker với MongoDB thử riêng, gồm huấn luyện XGBoost thật, kiểm tra tách tập theo thời gian và không ghi kết quả demo vào quan trắc/registry thực.
- Playwright **10 passed** cho camera video, danh sách/bộ lọc camera và luồng Chương IV trên desktop/mobile. Sau khi siết đối chiếu đường dẫn API trong fixture, hai bài camera video được chạy lại và đều qua. Kiểm tra tua video, đồng bộ số xe và ba mốc dự báo, quyền giao diện và không tràn ngang. Video kiểm thử H.264 sáu giây được sinh cục bộ; không phụ thuộc Pexels trong E2E.
- Bản Docker thực tế đã tải, nén và chạy YOLO11n cho hai video Pexels gắn vào bốn camera mẫu. Clip khoảng 33 giây cho trung bình 10,2 xe/khung hình, đỉnh 18; clip khoảng 10 giây cho trung bình 8,6, đỉnh 13. Các con số là kết quả detector với ROI/sức chứa ước lượng, chưa có nhãn thủ công để tính độ chính xác.
- Kiểm tra trực tiếp trình duyệt trên Docker ở 1440×1000 và 390×844: video phát được, tua đến giây 5 cập nhật số xe, có ba thẻ 15/30/60 phút, không lỗi JavaScript và không tràn ngang. HTTP Range và tệp H.264 hoạt động. TypeScript/Vite và Docker build thành công; ba dịch vụ chạy, backend và MongoDB healthy, `/api/health` trả `ok`.
- Kiểm tra quyền xem camera riêng với quyền dự báo, thu hồi chia sẻ, thay đổi hiệu chỉnh, tác vụ không đúng camera, giới hạn phạm vi Quản lý, chặn hai phiên tạo tác vụ cạnh tranh và khôi phục lượt phân tích thất bại từ video đã chia sẻ trước đó.

Dự báo camera dùng XGBoost trên lịch sử tổng hợp với 11/12 mốc đầu vào minh họa; mốc cuối lấy số xe/mật độ từ clip. Không xác minh đúng tuyến quay, không có quan trắc trực tiếp, tốc độ, tracking hay đánh giá độ chính xác dự báo thực địa. Kết quả không được phát thành cảnh báo thật. Windows App Control chặn DLL XGBoost của môi trường Python cục bộ; lượt huấn luyện/kiểm thử ML này được thực hiện trong Linux Docker, không tuyên bố đã chạy ML native Windows.

## Bổ sung ô nhận diện và giải thích xác suất, 12/11/2026

- Backend **47 passed** cho camera video, camera công khai, media/quan trắc và đoạn đường trong Docker với database giả lập riêng. Bộ camera sau khi bổ sung kiểm tra lịch sử giải thích có **15 passed** trên MongoDB thật trong container thử riêng; sau đó thêm hai trường hợp bảo vệ tệp khi tác vụ bị gọi lặp và bộ camera **17 passed** với database giả lập. Kiểm tra mọi frame được xử lý, chuyển bbox từ ảnh cắt về tọa độ gốc, tổng bốn loại bằng số ô, cache đúng theo nguồn/ROI và không ghi sang quan trắc thực.
- Mô hình mật độ và ùn tắc được huấn luyện thật bằng XGBoost. Kiểm tra khoảng cách thời gian giữa train, early stopping, calibration, test; xác suất tổng bằng 1, xác suất JAM đúng trường được hiển thị, không ép thành 90%. Lịch sử giải thích không lấy ngày hiện tại hoặc tương lai, chỉ đếm đúng giờ và cùng thứ trong cửa sổ 100 ngày lịch.
- E2E camera video qua trên desktop/mobile, gồm đếm thay đổi trong cùng một giây, tua, ẩn/hiện lớp nhận diện, tổng từng loại, ba tỷ lệ và mở/đóng giải thích. Hai bài bộ lọc camera desktop/mobile cũng qua trong lượt chạy trước đó của bản sửa này. Có sửa lệch về khung hình ngay trước mốc tua trên mobile, rồi chạy lại hai bài video và đều qua.
- Đã xử lý **497 + 155 + 497 + 155 = 1.304 khung hình** cho bốn camera, 15fps. Toàn bộ frame có số xe bằng số bbox và tổng bốn loại. Clip trên cao trung bình 22,7, đỉnh 33; clip ngang trung bình 8,6, đỉnh 17. Các số này thay kết quả 1fps ở mục trước nhờ nhận diện toàn bộ frame và cắt vùng mặt đường; không phải bằng chứng độ chính xác nhận diện.
- Bản Docker đã kiểm tra cả bốn camera trên 1440×1000 và 390×844: lớp canvas có vẽ, số ô khớp tổng từng loại, phân bố phần trăm hợp lệ, phóng to/thu nhỏ, mở giải thích tự dừng video và không tràn ngang. TypeScript/Vite và Docker build qua. Đây là nhận diện theo từng khung hình, chưa đếm số xe duy nhất bằng tracking hoặc xác minh độ chính xác bằng nhãn thủ công.

Giao diện ghi rõ tỷ lệ dự báo chỉ được hiệu chỉnh trên lịch sử tổng hợp, hiển thị mốc thời gian tham chiếu và phân biệt tần suất lịch sử với xác suất mô hình. Không thể coi phần trăm này là xác suất ùn tắc đã được kiểm chứng trên đường thật hoặc là độ chính xác của bộ đếm xe.

## Đếm cộng dồn và tình huống 17:00, 13/11/2026

- Bộ camera có **18 passed** với database giả lập và **18 passed** trên MongoDB thật trong container tạm. Bổ sung kiểm tra ByteTrack không cộng lại một xe đứng yên qua nhiều frame hoặc bị mất quan sát ngắn; xe mới được xác nhận mới làm tăng tổng. Kiểm tra tổng theo loại, cache nhận diện, dự báo và quyền truy cập vẫn qua. Kiểm tra riêng lệnh tạo camera/tuyến giờ cao điểm chạy lặp không đổi tài nguyên cũ cũng qua.
- **4 E2E passed** cho video/cộng dồn và bộ lọc camera trên desktop/mobile. Kiểm tra số cộng dồn khác số đang xuất hiện, ẩn/hiện nhận diện không làm tăng bộ đếm và tua lùi trả về số cũ.
- Docker đã chuẩn bị thêm tuyến/camera mẫu Ngã Tư Sở, lịch sử tổng hợp một năm có tuyến mới và ba mục tiêu thời gian cho camera. Clip giao lộ Pexels mới có **126 frame, 15fps**, khoảng 8 giây. Bộ theo dõi ghi nhận **9 mã ở đầu, 68 mã cuối clip**; các tổng chỉ tăng theo trình tự thời gian. Đây là ID của tracker, chưa có nhãn kiểm đếm để khẳng định có đúng 68 xe thật.
- Trên 1440×1000 và 390×844, nút **Xem đoạn đông xe nhất** chuyển đến khoảng giây **3,07**. Tại đó có **18 ô nhận diện**, số cộng dồn **37 mã** (2 ô tô, 35 xe máy theo loại lúc mã được tính lần đầu). Dự báo chạy thử tại mốc giả định **17:00 ngày 12/11/2026** cho JAM khoảng **98,7% ở 17:15**, **93,9% ở 17:30** và **34,5% ở 18:00** tại khung hình này. Đây là xác suất do mô hình tổng hợp tính, không phải quan trắc hoặc dự báo thực Ngã Tư Sở. Khung hình khác cho kết quả khác.
- Kiểm tra trình duyệt trên Docker mở được giải thích cộng dồn, chỉ rõ giờ giả định, các mốc 17:15/17:30, tua lại về số ban đầu, không lỗi JavaScript hoặc tràn ngang. TypeScript/Vite và Docker build qua. ByteTrack/lap nằm trong requirements để build lại có đủ thư viện.

Chưa tìm được clip Ngã Tư Sở đúng địa điểm/giờ quay có quyền tải dùng đã xác minh. Clip mới được ghi rõ là giao lộ Việt Nam để minh họa; nguồn báo chí về ùn tắc Ngã Tư Sở khoảng 17–18 giờ chỉ dùng tham khảo, không lấy video báo chí làm tài sản dự án. Sức chứa 20 xe của vùng mẫu là ước lượng, chưa phải hiệu chỉnh thực địa. Cộng dồn theo mã có thể đếm lại khi bị che lâu/camera chuyển động; không suy ra lưu lượng qua một vạch đếm hoặc độ chính xác bộ đếm từ các kết quả này.
