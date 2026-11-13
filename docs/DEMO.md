# Dữ liệu minh họa và lịch sử một năm

**Bản mới:** xem [PLANNING.md](PLANNING.md) để dự báo ngày mai, chọn ngày/giờ và so sánh giờ khởi hành. Giao diện đã bỏ thanh nguồn phía trên và tên mô hình khỏi trang người dùng. Các mô tả màn hình chạy lại giờ hôm qua bên dưới chỉ áp dụng cho bản cũ; API ngắn hạn vẫn được giữ.

Bản này có chế độ **Mô phỏng để chạy thử**, tự chuẩn bị ở lần khởi động đầu trong môi trường development. Không cần tải video hay tự nhập hàng nghìn dòng dữ liệu.

## Chạy trên máy hiện tại

```powershell
cd C:\Users\Admin\Documents\GitHub\SmartEye
docker compose up -d --wait --wait-timeout 240
```

Mở http://localhost:8081. Ở đầu trang chọn **Mô phỏng để chạy thử**.

1. **Dự báo giao thông** → chọn Hoàng Quốc Việt hoặc tuyến khác → xem hiện tại và sau 15/30 phút.
2. Chọn **07:30 hôm qua** hoặc **17:30 hôm qua** để thử lại giờ cao điểm; các ngày/giờ trên thẻ là mốc chạy thử, không phải thời gian hiện tại.
3. **Tình trạng & thống kê** → tìm tên đường → chọn ngày/tháng → xem biểu đồ 24 giờ, khung giờ thường đông xe và bản đồ nhiệt. Bấm ô tháng để mở ngày đó.
4. **Tải CSV mẫu** để lấy dữ liệu ra làm báo cáo. CSV ghi rõ `source=synthetic`.
5. **Tìm tuyến đường** → nhập địa chỉ và chọn kết quả hoặc ghim A/B → chọn ưu tiên thời gian/khoảng cách. Tình trạng mô phỏng chỉ điều chỉnh ETA trên phần tuyến trùng tên các đường mẫu; những phần khác chưa có dữ liệu.
6. Đổi nguồn sang **Quan sát thực tế** để kiểm tra trạng thái thiếu dữ liệu. Mẫu mô phỏng không được đưa vào bảng quan sát thực hay tự kích hoạt mô hình thực.

Dừng bằng `docker compose stop`, chạy lại bằng `docker compose up -d`. Không cần tạo lại dữ liệu mỗi lần.

## Tạo hoặc huấn luyện lại

Docker:

```powershell
docker compose exec backend python scripts/prepare_demo.py --days 365
Invoke-RestMethod http://localhost:8081/api/demo/status
```

Local, sau khi MongoDB và `.env` đã đúng:

```powershell
.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.venv\Scripts\python.exe scripts/prepare_demo.py --days 365
```

Hoặc Admin mở **Quản trị hệ thống → Dữ liệu & mô hình**, hay Quản lý phụ trách toàn bộ tuyến có quyền mô hình mở **Giám sát & xử lý → Dữ liệu & thiết lập → Dữ liệu & mô hình**, rồi bấm **Cập nhật lịch sử** khi bộ mẫu cần chuẩn bị. Huấn luyện chạy nền; dữ liệu cũ tiếp tục dùng đến khi bộ mới hoàn tất. Khi đã sẵn sàng, script có thể tạo lại bộ mẫu mà không xóa dữ liệu thực.

Backend và frontend chạy local theo [RUNNING.md](RUNNING.md). Không cần `download_model.py` để dùng dự báo mới.

## Dữ liệu được tạo như thế nào?

- Seed cố định 42, chu kỳ sáng/chiều, sự khác biệt từng đường, cuối tuần và nhiễu có tương quan theo thời gian. Thỉnh thoảng có một đợt đông xe ngoài giờ cao điểm.
- Mỗi 5 phút có chỉ số mật độ, số xe minh họa, tốc độ mẫu và nhãn FREE / SLOW / JAM. Nhãn mô phỏng dựa trên tỷ lệ tốc độ mẫu / tốc độ thông thoáng: dưới 0,30 là JAM, dưới 0,65 là SLOW, còn lại FREE. Đây là quy ước của bộ sinh, không phải tiêu chuẩn đánh giá giao thông thực.
- Tạo 365 ngày trước cùng ngày hiện tại cho tối đa 20 tuyến đang hoạt động, gồm Hoàng Quốc Việt. Nếu tuyến mẫu này chưa có, chỉ thêm bản ghi mới có `is_demo=true`; không sửa tuyến của bạn.
- XGBoost học từ 8 ngày trước, dùng 12 mốc lịch sử liên tiếp (60 phút), số xe, chỉ số/nhãn lịch sử, giờ, thứ và mã tuyến. Ngày hiện tại không tham gia huấn luyện.
- Hai mô hình cho 15 và 30 phút. Chia 60/20/20 theo thời gian; nhãn train/validation phải nằm trước phần kế tiếp. Chuẩn hóa chỉ fit trên train. Có báo cáo so với cách giữ nguyên trạng thái.
- Lúc dự báo chỉ đọc mốc đến thời điểm yêu cầu; không lấy nhãn tương lai từ bộ sinh để trả thay mô hình. Không coi điểm tốt trên dữ liệu tổng hợp là độ chính xác trên đường thật.
- Các ngày bị bỏ lỡ khi máy tắt được sinh bù trong cửa sổ 31 ngày khi xem báo cáo. Phần tương lai của ngày/tháng vẫn trống.

## Lưu ở đâu?

| Nơi lưu | Nội dung |
|---|---|
| MongoDB `demo_profiles` | Các mốc 5 phút được nhóm theo ngày và đường; có `source=synthetic`, mã bộ dữ liệu riêng |
| MongoDB `demo_registry` | Bộ mẫu đang dùng và trạng thái chuẩn bị |
| `backend/data/demo-forecasts/<UUID>/` | Hai mô hình XGBoost và metadata đánh giá |

Không ghi mẫu vào `observations`, `traffic_samples`, `traffic_labels`, `forecast_runs` hay `forecast_registry`. Dữ liệu/tài khoản cũ và các video lưu trữ được giữ nguyên. Compass kết nối MongoDB Docker qua **127.0.0.1:27018** bằng tài khoản database trong `.env` rồi mở DB theo `MONGODB_DB`; 27017 có thể là một server khác.

## Cấu hình và API

- `DEMO_DATA_ENABLED`: mặc định bật ở development, tắt ở production; chỉ bật ở production nếu chủ ý triển khai một bản demo có nhãn.
- `DEMO_AUTO_PREPARE=true`, `DEMO_HISTORY_DAYS=365`, `DEMO_ESTIMATORS=96`.
- `VIDEO_FEATURE_ENABLED=false`: tắt API tải video cá nhân và giao diện nhận diện cũ. Trang Camera vẫn phát và phân tích lại các video mẫu đã được chuẩn bị theo hướng dẫn bên dưới.
- `OSRM_URL=https://router.project-osrm.org`: nguồn ô tô nhanh; cache ứng viên 10 phút, trọng số và dữ liệu giao thông được tính lại theo từng yêu cầu. Xe máy dùng mạng OSM đầy đủ; không thay bằng tuyến xe đạp hay tuyến ô tô không kiểm tra quyền.
- `GET /api/demo/status`, `GET /api/demo/predict?segment_id=14`.
- `GET /api/demo/predict?segment_id=14&issue_at=<ISO có múi giờ trong 30 ngày đã qua (API ngắn hạn cũ)>`.
- `GET /api/demo/history?segment_id=14&period=month&value=2026-10` (thay ID/tháng bằng dữ liệu của bạn).
- `GET /api/demo/export.csv?segment_id=14`.
- `POST /api/demo/prepare` yêu cầu Admin hoặc Quản lý phụ trách toàn bộ tuyến có quyền `models.manage`, không cần gửi body.
- `GET /api/bootstrap?data_mode=demo` khởi tạo trang bằng một request.
- `POST /api/routes/search` có `provider=auto`, `algorithm=astar`, `traffic_mode=demo|observed`. Ô tô mặc định xếp hạng các ứng viên OSRM; `provider=demo|osm` dùng đồ thị đầy đủ và A*, còn `algorithm=compare` chỉ phục vụ kiểm chứng qua API.

## Khi cần dữ liệu thật

Giữ dữ liệu mẫu để thử giao diện. Với nghiên cứu chính thức, dùng CSV quan trắc được phép sử dụng hoặc dữ liệu mở có thời gian/địa điểm rõ ràng; Admin hoặc Quản lý có quyền mô hình nhập lịch sử và nhãn đã kiểm chứng trong **Dữ liệu & mô hình**, huấn luyện rồi đánh giá trước khi kích hoạt. Không nhập CSV tổng hợp vào chế độ thực và gọi nó là dữ liệu thu thập tại Hà Nội. Pipeline GRU và XGBoost cho dữ liệu thực vẫn có tại [FORECASTING.md](FORECASTING.md).

## Ảnh từ Docker sau cập nhật

Các ảnh dưới đây dùng bộ dữ liệu mô phỏng riêng trong Docker, không phải camera hay tình trạng thực của Hà Nội.

![Dự báo giờ cao điểm mẫu](previews/forecast-demo-desktop.png)

[Dự báo trên điện thoại](previews/forecast-demo-mobile.png) · [Thống kê tháng trên máy tính](previews/traffic-demo-desktop.png) · [Thống kê tháng trên điện thoại](previews/traffic-demo-mobile.png).

## Video camera và dự báo mật độ

Trang **Camera giao thông** có video minh họa từ Pexels, ô nhận diện và số xe đồng bộ từng khung hình bằng YOLO11. Dự báo chạy thử sau 15, 30, 60 phút có phần trăm ùn tắc và nút **Vì sao?**. Bản hiện tại dùng bảy clip góc cao khác nhau cho bảy camera, có thêm khu vực minh họa TP.HCM và Đà Nẵng. Không khẳng định clip là camera thực tại tuyến đang chọn. [Cách tính theo kích thước và loại xe](ROAD-CAPACITY.md).

| Video | Tác giả | Nguồn và quyền sử dụng |
|---|---|---|
| Bustling Hanoi Street Captured from Above | Nimit N | [Video gốc](https://www.pexels.com/video/bustling-hanoi-street-captured-from-above-31873135/), [Pexels License](https://www.pexels.com/license/) |
| High Angle Footage Of The City Traffic · đang sử dụng | K | [Video gốc](https://www.pexels.com/video/high-angle-footage-of-the-city-traffic-3696011/), [Pexels License](https://www.pexels.com/license/) |
| High Angle Footage Of The Road With Traffic | mostafa meraji | [Video gốc](https://www.pexels.com/video/high-angle-footage-of-the-road-with-traffic-3078540/), [Pexels License](https://www.pexels.com/license/) |
| A view of traffic on a highway with cars | Sururi Ballıdağ Director | [Video gốc](https://www.pexels.com/video/a-view-of-traffic-on-a-highway-with-cars-18553054/), [Pexels License](https://www.pexels.com/license/) |
| Urban Traffic Flow on Busy City Highway | David Lomax | [Video gốc](https://www.pexels.com/video/urban-traffic-flow-on-busy-city-highway-29519571/), [Pexels License](https://www.pexels.com/license/) |
| Aerial View of Busy City Intersection with Cars | K | [Video gốc](https://www.pexels.com/video/aerial-view-of-busy-city-intersection-with-cars-32176022/), [Pexels License](https://www.pexels.com/license/) |
| Aerial View of Busy Urban Traffic Intersection | Marc Espejo | [Video gốc](https://www.pexels.com/video/aerial-view-of-busy-urban-traffic-intersection-31843333/), [Pexels License](https://www.pexels.com/license/) |

Tên địa điểm theo mô tả của người đăng, chưa xác minh đường và thời điểm ghi hình. Clip góc cao mới không được khẳng định quay tại Hà Nội/Ngã Tư Sở. Nguồn, tác giả, ngày công bố, giấy phép và ghi chú vị trí được giữ trong `database/camera-video-sources.json`, metadata của tác vụ và trang xem. Video được bỏ âm thanh, nén H.264 tối đa 960px, 15fps để phát nhanh. Dữ liệu lớn nằm trong `backend/data`, không đưa lên GitHub.

**Cài hoặc cập nhật bằng PowerShell**

```powershell
cd C:\Users\Admin\Documents\GitHub\SmartEye
docker compose up -d --build --wait --wait-timeout 240
docker compose exec backend python scripts/download_model.py
docker compose exec backend python scripts/setup_camera_videos.py --rush-hour --regions
```

Nếu báo chưa có lịch sử minh họa, chạy `docker compose exec backend python scripts/prepare_demo.py --days 365` rồi chạy lại bước chuẩn bị video. Bước này dành cho môi trường demo có `DEMO_DATA_ENABLED=true`. Không cần bật `VIDEO_FEATURE_ENABLED`.

Script chuẩn bị mô hình mật độ riêng, tải/nén các video nếu chưa có và chạy YOLO. Mặc định gắn bốn camera; thêm --rush-hour --regions để có đủ bảy camera với bảy clip khác nhau. Camera được chọn sẽ được bật và chia sẻ video. Vùng quan sát/sức chứa mẫu được áp dụng cho camera mới mặc định hoặc camera còn giữ đúng hiệu chỉnh của clip mẫu cũ; không ghi đè hiệu chỉnh riêng. Khi đã hoàn tất, chạy lại sẽ dùng kết quả cũ nếu video, cấu hình, phiên bản mô hình và bộ lịch sử không đổi. Có thể chỉ định `--camera-id 1 --camera-id 3` hoặc thêm `--refresh` để phân tích lại. Tuyến ngoài bộ lịch sử minh họa vẫn xem được mật độ video nhưng sẽ báo chưa đủ dữ liệu dự báo.

**Lần sau chạy** chỉ cần `docker compose up -d`, mở [Camera giao thông](http://localhost:8081/#cameras), chọn camera và nhấn phát. Chọn **15 phút / 30 phút / 1 giờ** rồi nhấn **Phân tích** để nhận một kết quả. Nếu khả năng cao nhất từ 80%, trạng thái tương ứng được làm nổi bật, gồm cả thông thoáng; nếu thấp hơn, hiển thị **Xu hướng chưa rõ**. Ba tỷ lệ được tính riêng, không lấy khả năng thông thoáng bằng 100% trừ ùn tắc vì còn trạng thái di chuyển chậm. Không đặt sẵn kết quả 80–90%.

Ô nhận diện đồng bộ với video, có thể ẩn/hiện hoặc phóng to. Kết quả phân tích giữ nguyên khi tua video; đổi mốc thời gian/camera sẽ xóa kết quả cũ. Mở **Vì sao?** để xem số xe, vùng đường, lịch sử, thời tiết, sự cố, cách tính và giới hạn. **Thông tin camera và nguồn video** chứa nguồn, giấy phép, thời điểm ghi hình nếu có và liên kết dự báo tuyến. Bản đồ và danh sách camera mở bằng **Xem bản đồ camera**. Trong Camera & hiệu chỉnh, Admin hoặc Quản lý có quyền `network.manage` đúng phạm vi có thể nhận diện lại video. Video cũ vẫn xem được trong khi xử lý; đổi hiệu chỉnh yêu cầu nhận diện lại.

**Cách phân tích**

- YOLO11n, hoặc YOLO11s cho nguồn cần giữ đầy đủ ngữ cảnh, nhận diện mọi khung hình của clip 15fps, không chỉ lấy một ảnh mỗi giây. Mặc định cắt vùng mặt đường trước khi nhận diện; hai nguồn nhìn thẳng xuống giữ toàn ảnh rồi lọc ô theo vùng quan sát, đầu vào 960px, chỉ bốn lớp phương tiện, ngưỡng tin cậy 0,25, NMS không phân biệt lớp với IoU 0,5 để giảm ô đếm trùng. Tọa độ được trả lại trên toàn ảnh; ô và tên loại xe được vẽ ngay trên video theo thời điểm khung hình trình duyệt đang hiển thị. Tổng xe bằng số ô và tổng bốn loại xe ở cùng khung hình. Nhận diện có thể bỏ sót/nhầm xe nhỏ, bị che; chưa có nhãn thủ công để cam kết đếm đúng 100%.
- Chỉ số mật độ là giá trị lớn hơn giữa tỷ lệ vùng quan sát bị xe che phủ và số xe/sức chứa camera, giới hạn trong 0–1. Diện tích hộp chồng nhau chỉ tính một lần. Hai ngưỡng camera phân thành Thấp, Vừa, Cao. Đây là quy ước chạy thử cần hiệu chỉnh, không phải xác suất ùn tắc.
- Các xe có thể xuất hiện ở nhiều khung hình. Số xe/khung hình không phải lưu lượng xe/giờ; không suy ra tốc độ hay ùn tắc chắc chắn từ riêng số xe.
- **Xe đã ghi nhận từ đầu video** dùng ByteTrack để theo dõi mã xe qua các khung hình và chỉ cộng mỗi mã đã xác nhận một lần. Có tổng và bốn loại riêng; phân loại cộng dồn chốt khi mã được tính lần đầu để không nhảy số giữa các loại khi detector đổi nhãn. **Xe đang xuất hiện** vẫn là toàn bộ ô của khung hình hiện tại, dùng để tính mật độ. Khi tua lùi, số cộng dồn hiển thị kết quả đã tính đến mốc cũ, không cộng thêm do thao tác phát/tua. Bộ theo dõi có thể mất mã khi che khuất lâu, camera di chuyển hoặc xe ra/vào lại; chưa được xem số mã là số xe thật đã kiểm đếm chính xác hay số xe qua một vạch đếm.
- XGBoost có hai mục tiêu riêng: mật độ (Thấp/Vừa/Cao) và ùn tắc (FREE/SLOW/JAM), cho ba mốc 15/30/60 phút. Mô hình camera v4 học từ tối đa 24 ngày hoàn chỉnh gần nhất của lịch sử minh họa, bổ sung điều kiện thời tiết/sự cố giả lập có ảnh hưởng đến mật độ và tốc độ giả lập; nhãn ùn tắc được xác định từ tốc độ so với tốc độ thông thoáng, không đổi nhãn mật độ cao trực tiếp thành ùn tắc. Các phần train, early stopping, hiệu chỉnh xác suất và test tách theo thời gian, có khoảng cách giữa thời điểm nhãn và phần tiếp theo. Chuẩn hóa chỉ tính trên train. Hiệu chỉnh temperature scaling chỉ fit trên phần hiệu chỉnh; test không dùng chọn nhiệt độ hoặc dừng cây. Metadata có log loss, Brier cho lớp cao/ùn tắc và so sánh với giữ trạng thái hiện tại trên tập test.
- Phần trăm ùn tắc là xác suất lớp JAM từ `predict_proba`, sau temperature scaling. Không đặt cố định 90%, không dùng độ tin cậy hộp YOLO làm xác suất ùn tắc. Giải thích bổ sung số ngày có dữ liệu và số ngày ùn tắc cùng giờ/cùng thứ trong 100 ngày lịch trước ngày tham chiếu. Tần suất này được trình bày riêng, không giả làm xác suất do mô hình tính.
- Khi nhấn Phân tích, hệ thống lấy trung vị mật độ/mức sử dụng và số xe trong tối đa 10 giây cuối clip, trung bình tỷ lệ xe đứng/nhích chậm trên các khung có chuyển động hợp lệ (tối thiểu 30% số khung của đoạn). Mốc mới nhất trong cửa sổ 60 phút được thay bằng số liệu tổng hợp này; **11 mốc trước đó vẫn là dữ liệu tổng hợp**. Tất cả mốc trong một clip dùng cùng thời điểm tham chiếu chạy thử, không có thời điểm ghi hình thực đã xác minh. Phần dự báo vì vậy luôn ghi **chạy thử**. Không gọi kết quả đánh giá trên mẫu tổng hợp là độ chính xác ngoài đường.

Pipeline này không ghi vào `observations`, `traffic_samples`, `traffic_labels`, registry/mô hình dự báo thực hoặc cảnh báo thật. Nó lưu metadata, kết quả và video trong `video_jobs`, `cameras`, `backend/data/uploads`, `backend/data/camera_previews`, cache phát hiện theo nội dung tại `backend/data/camera-detections` và mô hình riêng tại `backend/data/camera-density/<UUID>/v4`. Clip tối đa 120 giây/1800 khung hình. Cache giữ bbox gốc theo SHA video, trọng số, ROI, phiên bản và tham số nhận diện; đổi sức chứa/ngưỡng chỉ tính lại mật độ, đổi ROI/trọng số cần nhận diện lại. Pipeline video cá nhân cũ giữ nguyên 1fps để tương thích, không tự mở lại giao diện upload. Bộ dự báo thực XGBoost/GRU giữ nguyên theo [FORECASTING.md](FORECASTING.md). Muốn đánh giá dự báo thật cần video/quan trắc liên tục, đúng tuyến và thời gian, nhãn đã kiểm chứng, rồi kiểm thử trên giai đoạn chưa dùng huấn luyện. Clip vài chục giây không cung cấp đủ lịch sử để chứng minh độ chính xác 80–90%.

Tham khảo triển khai: [cấu hình nhận diện Ultralytics](https://docs.ultralytics.com/modes/predict/), [đồng bộ khung hình trình duyệt](https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback), [ý nghĩa và đánh giá hiệu chỉnh xác suất](https://scikit-learn.org/stable/modules/calibration.html).

## Tình huống đông xe lúc 17:00

```powershell
docker compose exec backend python scripts/setup_camera_videos.py --rush-hour
```

Lệnh bổ sung tuyến **Ngã Tư Sở (minh họa)** và camera **Ngã Tư Sở · Tình huống 17:00**, giữ nguyên các tuyến/camera cũ. Nếu tuyến mới chưa có trong bộ mẫu, tạo lại lịch sử tổng hợp một năm và huấn luyện bộ dự báo demo có tuyến này trước khi phân tích camera. Không sửa dữ liệu quan trắc hoặc mô hình phục vụ dữ liệu thực. Mở Camera giao thông, chọn tuyến này, phát/tua clip, chọn **15 phút**, **30 phút** hoặc **1 giờ**, nhấn **Phân tích** rồi mở **Vì sao?** cho từng mốc **17:15**, **17:30** hoặc **18:00**.

Clip hiện tại là [High Angle Footage Of The City Traffic](https://www.pexels.com/video/high-angle-footage-of-the-city-traffic-3696011/) của **K**, Pexels License, công bố 06/02/2020. Clip dài khoảng 22 giây, quay giao lộ từ trên cao gần hơn để thấy xe rõ; thay clip quay trên xe máy trước đây. **Không phải camera tại Hà Nội/Ngã Tư Sở hoặc lúc 17:00**; ứng dụng ghi rõ là hình ảnh minh họa cho tình huống. Giờ 17:00 ngày hôm trước lúc chuẩn bị được dùng làm mốc giả định, không ghi thành thời điểm quay. Vùng quan sát lấy gần toàn bộ giao lộ, vùng đường ước lượng 14 × 65 m với phần sử dụng 70%, tương ứng khoảng 30,33 ô tô quy đổi, chưa phải hiệu chỉnh thực địa. Tỷ lệ do mô hình tính lại, không đặt sẵn kết quả ùn tắc.

Ví dụ có căn cứ về giờ cao điểm: [Dân trí ghi nhận Ngã Tư Sở ngày 11/01/2023](https://dantri.com.vn/thoi-su/duong-vanh-dai-2-tren-cao-un-tac-dai-gan-3km-tu-nga-tu-vong-ve-nga-tu-so-20230111184108866.htm) cho biết ùn tắc khoảng 16h, hơn 17h và gần 18h. Bài báo chỉ là nguồn tham khảo cho lựa chọn tình huống; không lấy nó thay dữ liệu huấn luyện, không tải lại video báo chí hoặc khẳng định mọi ngày đều tắc vào khung giờ đó.

Thuật toán theo dõi dùng [ByteTrack của Ultralytics](https://docs.ultralytics.com/reference/trackers/byte_tracker/), với ngưỡng khởi tạo/xác nhận 0,25 phù hợp ngưỡng detector, buffer khoảng hai giây. `lap` được cài qua requirements/Docker, không trông chờ tự tải thư viện khi người dùng mở trang.

## Thời tiết, sự cố và điều kiện đường trong dự báo camera

1. Mở **Camera giao thông**, chọn tuyến và xem video. Chọn mốc thời gian, nhấn **Phân tích**, rồi **Vì sao?** để xem mưa, tầm nhìn, gió; tai nạn, công trình, vật cản, ngập và khả năng đường ướt.
2. Thời tiết lấy từ [Open-Meteo](https://open-meteo.com/en/docs) theo điểm giữa tuyến và mốc chạy thử. Chỉ lấy giờ không muộn hơn mốc; cache 10 phút, lỗi cache 1 phút và giới hạn chờ 5 giây. Nếu nguồn thiếu số liệu hoặc mốc ngoài phạm vi ±7 ngày, hiện **Chưa có dữ liệu**, không thay bằng trời khô. Đây là thời tiết mô hình khu vực, không đo tại camera. Nguồn Open-Meteo được ghi theo CC BY 4.0; dịch vụ miễn phí dành cho sử dụng phi thương mại.
3. Sự cố lấy từ snapshot cảnh báo đã xác minh và công bố, đúng tuyến/chiều, đã phát hành trước mốc và còn hiệu lực tại mốc. Không lấy phản ánh chưa được xác minh hoặc thông tin riêng. Cảnh báo tự hết hạn sau thời điểm replay vẫn được xét nếu nó có hiệu lực ở mốc cũ. Không có cảnh báo không chứng minh không có sự cố.
4. Giao diện người xem tự lấy điều kiện có thông tin và không hiện bộ giả định kỹ thuật. API điều kiện giả định cũ vẫn được giữ để tương thích, chỉ áp dụng cho yêu cầu đó; không sửa nguồn, cảnh báo công khai hoặc kết quả dùng chung.
5. Nhấn **Vì sao?** để xem đúng khung hình, điều kiện và tỷ lệ của kết quả vừa chọn. Không cộng phần trăm bằng tay. XGBoost camera v4 học các đặc trưng điều kiện và chuyển động, có cờ thiếu dữ liệu; bộ sinh giả lập tạo ảnh hưởng đến tốc độ/mật độ và nhãn. Kết quả vẫn chỉ được đánh giá trên dữ liệu giả lập, chưa thể cam kết đúng 80–90% thực địa. Địa điểm/giờ của video chưa khớp nguồn thời tiết và cảnh báo, nên màn hình ghi rõ giới hạn này.


### Yêu cầu phân tích gọn

- `GET /api/traffic/cameras/recordings/{id}/analysis?include_forecast=false`: trả ô nhận diện và mã `analysis_id`, bỏ timeline dự báo cũ để giảm dữ liệu tải ban đầu. Mặc định API vẫn trả timeline để tương thích.
- `POST /api/traffic/cameras/recordings/{id}/forecast` với `{ "horizon_minutes": 30, "whole_video": true, "analysis_id": "UUID từ GET" }`: chỉ tính một mốc và một đoạn tổng hợp, trả `scope=video`, `summary`, `basis` là khung thật đại diện và `road_geometry`. Không nhận diện YOLO lại mỗi khi bấm Phân tích; dùng kết quả nhận diện đã lưu.
- `summary` mô tả số liệu tổng hợp; `basis` minh họa một khung gần trung vị, không phải khung đông nhất. Cả hai thuộc cùng bản video. Lượt nhận diện đã thay đổi hoặc chưa trùng bản phát trả 409. Cần cả quyền xem camera và dự báo; thiếu quyền trả 403.
- Các tỷ lệ là kết quả XGBoost sau hiệu chỉnh trên dữ liệu tổng hợp. Chọn ngưỡng thông báo 80% không phải chứng minh hệ thống chính xác 80%. Cách tổng hợp video mới chưa có kiểm chứng xác suất ngoài thực địa.

### Kiểm tra giao diện phân tích gọn

Đã kiểm tra 55 trường hợp backend trên MongoDB tạm, tách dữ liệu ứng dụng: tổng hợp cuối clip, thiếu chuyển động, không dùng tổng cộng dồn/khung đông nhất, giữ nguyên dữ liệu chia sẻ, từ chối bản video cũ, chọn đúng mốc và quyền xem. Tám trường hợp E2E trên máy tính/điện thoại kiểm tra video/ô nhận diện, bộ lọc, bản đồ, tỷ lệ cao cho cả ba trạng thái, ngưỡng 80%, tỷ lệ không hợp lệ, thử lại và đổi camera khi yêu cầu cũ chưa xong. Đã mở bản Docker với cả bảy video, kiểm tra ba mốc trên tình huống giờ cao điểm, nguồn video và phần giải thích; không có lỗi JavaScript hoặc tràn ngang trong các lần kiểm tra này.

Ảnh từ bản Docker, với video và lịch sử minh họa; tỷ lệ là kết quả chạy thử, không chứng minh tình trạng thực tế của tuyến được đặt tên:

![Một kết quả sau khi chọn mốc và nhấn Phân tích](previews/camera-simple-desktop.png)

![Thông báo khả năng thông thoáng cao](previews/camera-simple-free-desktop.png)

[Giao diện trên điện thoại](previews/camera-simple-mobile.png), [kết quả thông thoáng trên điện thoại](previews/camera-simple-free-mobile.png).
