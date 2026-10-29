# Pipeline XGBoost / GRU trên dữ liệu quan sát thực

**Phạm vi:** tài liệu này mô tả phần **Dữ liệu & mô hình** của Quản lý/Admin trong chế độ quan sát thực. Bản chạy thử hiện có XGBoost huấn luyện trên dữ liệu tổng hợp và các collection riêng; xem [DEMO.md](DEMO.md). Các điều kiện đánh giá dưới đây vẫn được giữ cho dữ liệu thực.

![Trang Tổng quan](previews/overview-redesign.png)

Ảnh giao diện lấy từ kiểm thử trình duyệt, dùng mạng đường demo công khai và DB kiểm thử riêng. Không phải kết quả dự báo giao thông Hà Nội. [Màn hình quản lý mô hình](previews/forecast-management.png) · [Giao diện điện thoại](previews/forecast-mobile.png).

## Sử dụng

Trang **Tổng quan** là điểm bắt đầu: Tình trạng & thống kê, Dự báo và Tìm đường. Nhận diện video đã được gỡ khỏi giao diện. Menu giữ đường dẫn bằng hash nên tải lại hoặc dùng nút Back vẫn về đúng màn hình.

1. Cập nhật và chạy Docker theo `docs/RUNNING.md`. Sau thay đổi này cần build **backend** để có `xgboost-cpu` và `scikit-learn`; PyTorch CPU đã có trong Dockerfile. Không cần cài TensorFlow.
2. Mở `http://localhost:8081/#forecast` nếu `.env` đang dùng `FRONTEND_PORT=8081`.
3. Người dùng chọn tuyến và mục tiêu: **Mật độ phương tiện** hoặc **Tình trạng ùn tắc**. Hai thẻ hiển thị mốc 15/30 phút, thời điểm dự báo và tên mô hình. Thiếu dữ liệu hoặc thiếu mô hình thì giữ trạng thái chưa có dự báo.
4. Quản lý/Admin mở **Dữ liệu & mô hình**, chọn tuyến và khoảng 7–90 ngày, bấm **Kiểm tra dữ liệu**.
5. Khi đủ dữ liệu, bấm **Huấn luyện XGBoost + GRU**. Một worker huấn luyện nền; có tiến độ và thao tác hủy. Chỉ một tác vụ chạy tại một thời điểm. Khởi động lại máy chủ sẽ đánh dấu tác vụ gián đoạn là thất bại, không tự phục hồi kết quả dở dang.
6. Xem bảng so sánh XGBoost / GRU / Giữ nguyên trạng thái, điểm validation, ma trận nhầm lẫn và tải CSV báo cáo.
7. **Admin** kích hoạt bản đủ điều kiện; mỗi mục tiêu có một bản đang phục vụ. Chỉ các mốc và tuyến đạt đánh giá được phép trả dự báo. Có thể kích hoạt lại một bản cũ hoặc ngừng phục vụ mà không xóa báo cáo.

Code cung cấp luồng huấn luyện thật, không kèm mô hình dự báo đã huấn luyện cho Hà Nội và không thêm số liệu tổng hợp vào các collection quan sát/nhãn/mô hình thực. Bộ mẫu nằm riêng trong `demo_profiles` và `demo_registry`.

## Chuẩn bị dữ liệu

- Nhập CSV có thời gian và nguồn quan sát đã được phép sử dụng. Dữ liệu video đã công bố từ bản cũ vẫn được đọc; màn hình tải video mới đã gỡ.
- Hoặc Quản lý/Admin nhập CSV số liệu đã quan sát. Tải mẫu tiêu đề ở `database/templates/traffic-observations.csv`. Các cột bắt buộc: `segment_id,observed_at,score,count,density`.
- Thời gian là ISO có múi giờ; score 0–1, count 0–10000, density LOW/NORMAL/HIGH. Mỗi dòng là một quan sát thật, không phải một hàng đại diện do hệ thống tự nhân lên.
- CSV tối đa 2 MB/5.000 dòng. **Kiểm tra CSV** không ghi DB; **Xác nhận nhập** mới ghi. Tất cả hàng được kiểm tra trước khi ghi. Nhập lại cùng tuyến/thời điểm bỏ qua bản đã có, không ghi đè. MongoDB không có transaction nhiều document: lỗi giữa lúc ghi có thể để lại một phần; nhập lại an toàn nhờ sample_key unique.
- CSV chỉ nhập mẫu mật độ; không tự tạo nhãn ùn tắc.

Ví dụ định dạng (minh họa cấu trúc, không phải dữ liệu thực):

```csv
segment_id,observed_at,score,count,density
1,2026-01-15T07:01:00+07:00,0.40,12,NORMAL
```

Đối với mục tiêu **ùn tắc**, Quản lý/Admin phải xác nhận nhãn FREE/SLOW/JAM sau khi xem căn cứ thực tế. Mốc nhãn là **kết thúc ô 5 phút**: nhãn 07:05 mô tả ô 07:00–07:05. Có tên người xác nhận, căn cứ và nhật ký. API không chấp nhận nhãn tương lai hoặc mốc không chia hết 5 phút. Có thể nhập hàng loạt bằng CSV nhãn riêng (`segment_id,observed_at,state,note`), kiểm tra trước rồi xác nhận nhập. Mốc đã có được cập nhật và gắn người nhập hiện tại; không sinh mẫu mật độ. Có thể sửa nhãn; bộ dữ liệu của các lần huấn luyện đã lưu giữ nguyên để truy vết.

## Cửa sổ và đặc trưng

- Chuẩn hóa từng camera/ô 5 phút, lấy mức cao nhất trên đoạn đường như thống kê lịch sử.
- Một ô dùng cho ML cần quan sát ở ít nhất **3 phút khác nhau**, đã kết thúc; một khung hình không đủ đại diện cho cả ô.
- Cần **12 ô liên tiếp (60 phút)**. Khoảng trống không được thay bằng 0 hoặc điền từ tương lai.
- Đặc trưng từng bước: chỉ số mật độ, log(1+số xe), cờ mật độ cao/thấp, sin/cos giờ và thứ UTC+7, mã tuyến one-hot.
- XGBoost nhận cửa sổ làm vector; GRU nhận ma trận 12 bước × số đặc trưng. Chuẩn hóa chỉ fit trên train, sau đó áp nguyên tham số cho validation/test/inference.
- Nhãn dự báo nằm đúng mốc kết thúc ô ở t+15 hoặc t+30. Mục tiêu mật độ dùng mức đã hiệu chỉnh camera; mục tiêu ùn tắc dùng nhãn thực tế độc lập. Persistence dùng nhãn tại t; mục tiêu ùn tắc cần có nhãn cả t và t+h để so sánh công bằng.

## Huấn luyện và đánh giá

Mỗi mốc có một XGBoost classifier và một GRU classifier ba lớp. XGBoost dùng cây tăng cường histogram/CPU, dừng sớm trên validation. GRU một lớp 32 hidden units, đầu ra tuyến tính ba lớp, weighted cross entropy, Adam và dừng sớm trên validation. Seed 42; GRU mặc định tối đa 25 epoch. Không dùng kết quả định tuyến Google làm dữ liệu huấn luyện.

Điều kiện thử nghiệm ban đầu: ít nhất 7 ngày khác nhau, 180 cửa sổ mỗi mốc; train có tối thiểu 10 ví dụ mỗi lớp, mỗi phần dữ liệu có ít nhất 25 cửa sổ. Khoảng truy vấn tối đa 300.000 mẫu/quan sát, 40.000 cửa sổ/mốc và 20 tuyến. Đây là giới hạn vận hành và sàng lọc ban đầu, không chứng minh đủ đại diện cho mọi điều kiện giao thông.

Chia theo mốc thời gian chung giữa các tuyến: train / validation / test khoảng 60 / 20 / 20. Nhãn train phải xảy ra **trước** thời điểm bắt đầu validation; tương tự validation/test. Không shuffle các phần dữ liệu qua thời gian. Shuffle mini-batch chỉ nằm trong tập train.

Mô hình thắng được chọn bằng Macro-F1 trên **validation**. Báo cáo test có Macro-F1, accuracy, recall lớp cao/ùn tắc, số mẫu từng lớp và ma trận nhầm lẫn; giữ cả kết quả hai mô hình và baseline. Có báo cáo theo từng tuyến.

Điều kiện kích hoạt ban đầu:

- Validation F1 hơn Persistence ít nhất 0,01.
- Test F1 tối thiểu 0,45 và không thấp hơn Persistence.
- Recall lớp cao/ùn tắc trên test ít nhất 0,5; mỗi lớp test có ít nhất 5 ví dụ.
- Từng tuyến được phục vụ cũng phải đủ số mẫu và vượt baseline trên validation, không thấp hơn baseline trên test; tuyến không đạt bị loại khỏi phạm vi phục vụ.

Đây là ngưỡng kiểm soát sản phẩm, không phải kết luận khoa học về độ chính xác thực địa. Phải tiếp tục theo dõi hiệu năng trên dữ liệu mới; test đã xem không được sử dụng để tinh chỉnh nhiều lần rồi coi là tập kiểm thử độc lập.

## Phục vụ dự báo và tìm đường

Chỉ đọc mô hình Admin đã kích hoạt, có tệp đầy đủ, đúng tuyến và đúng mục tiêu. Cần 60 phút dữ liệu liên tiếp đủ chất lượng; ô mới nhất kết thúc không quá 10 phút trước. Mô hình có khoảng dữ liệu huấn luyện kết thúc quá 45 ngày cần huấn luyện lại. Không hiển thị tỷ lệ “chắc chắn tắc” chưa được hiệu chỉnh xác suất.

Với tìm tuyến khởi hành trong tương lai, dự báo chỉ được ghép khi thời điểm dự báo lệch giờ khởi hành tối đa 2,5 phút, trong phạm vi 35 phút tới. Ưu tiên mô hình ùn tắc nếu có, sau đó mật độ; thiếu dự báo thì dùng lịch sử đủ bằng chứng. Quan sát hiện tại vẫn phục vụ tìm tuyến ngay bây giờ. Camera/dự báo chỉ bổ sung rủi ro, giữ ETA của Google. Đây chưa phải mô hình dự báo theo thời điểm đến từng cạnh của tuyến.

## Database và tệp

Ba collection mới: `forecast_runs` (tác vụ/báo cáo), `traffic_labels` (nhãn độc lập), `forecast_registry` (bản kích hoạt theo mục tiêu). Startup tạo collection/index mới, không xóa dữ liệu cũ. Tổng cộng 15 collection nghiệp vụ + counters.

`backend/data/forecasts/<uuid>/` lưu snapshot NPZ, XGBoost JSON, GRU state_dict và metadata. Không có endpoint cho tải pickle hoặc nạp model do người dùng gửi lên. GRU chỉ load state_dict bằng `weights_only=True`. Tệp huấn luyện và mô hình không được commit GitHub. Thư mục có thể tăng theo các lần huấn luyện; tác vụ đã hủy có thể còn tệp dở dang, cần dọn theo chính sách lưu trữ khi vận hành lâu dài.

## API

| API | Quyền |
|---|---|
| GET `/api/forecast/status`, GET `/api/forecast/predict?segment_id=1&target=density` | Công khai, metadata và dự báo đã kích hoạt |
| POST `/api/forecast/readiness`, GET/POST `/api/forecast/runs` | Quản lý/Admin |
| POST `/api/forecast/runs/{uuid}/cancel` | Người tạo tác vụ hoặc Admin |
| POST `/api/forecast/runs/{uuid}/activate`, DELETE `/api/forecast/active/{target}` | Admin |
| GET `/api/forecast/runs/{uuid}/report.csv` | Quản lý/Admin |
| GET/POST `/api/forecast/labels`, POST `/api/forecast/labels/import?dry_run=true/false` | Quản lý/Admin |
| POST `/api/forecast/import?dry_run=true/false` | Quản lý/Admin |

## Chạy sau cập nhật

```powershell
cd C:\Users\Admin\Documents\GitHub\SmartEye
docker compose up --build -d --wait
```

Mở cổng frontend theo `.env` (máy hiện dùng 8081). Lần sau chỉ cần `docker compose up -d --wait`. Ổ chứa Docker cần đủ chỗ cho các lớp image và quá trình giải nén. Không cần chạy lại seed tài khoản hoặc nhập fixture DB khi nâng cấp.
