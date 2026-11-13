# Đánh giá mật độ và dự báo theo từng vùng đường

Không có một số lượng xe cố định để kết luận mọi con đường đều ùn tắc. Cần xác định vùng quan sát, diện tích đường có thể sử dụng, loại xe và mức di chuyển. Quan hệ giữa mật độ, vận tốc và lưu lượng được giải thích trong [FHWA Freeway Management and Operations Handbook](https://ops.fhwa.dot.gov/freewaymgmt/publications/frwy_mgmt_handbook/chapter1_02.htm). Đường đô thị có đèn tín hiệu còn cần phân biệt xe chờ đèn với hàng xe không thoát được.

## Công thức chạy thử

Các giá trị sau là giả thiết minh họa của ứng dụng, chưa phải hệ số được kiểm định hoặc tiêu chuẩn áp dụng chung:

```text
Xe quy đổi E = số ô tô + 0,25 × số xe máy + 3 × số xe buýt + 2,5 × số xe tải
Diện tích sử dụng A = bề rộng mặt đường × chiều dài quan sát × phần có thể sử dụng
Sức chứa tĩnh C = A / 21 m² cho một ô tô quy đổi kể cả khoảng cách chờ
Mức sử dụng D = E / C
```

Mỗi camera có kích thước và phần diện tích sử dụng riêng. Số làn được lưu để đối chiếu, tổng bề rộng khai báo đã bao gồm những làn nằm trong vùng quan sát. Không lấy chiều dài toàn tuyến thay cho chiều dài nhìn thấy. Dải phân cách, vỉa hè, vùng bị che và vùng đỗ xe phải được loại khi chọn vùng và ước tính diện tích. Sức chứa ở đây là **số xe có thể hiện diện**, khác năng lực thông hành tính bằng xe/giờ.

Ví dụ cùng vùng dài 50 m và sử dụng được 100%:

| Đường | Sức chứa giả định | Có 10 ô tô | Diễn giải |
|---|---:|---:|---|
| Rộng 3,5 m | 8,33 ô tô quy đổi | Khoảng 120% | Vượt sức chứa ước tính, mật độ cao |
| Rộng 14 m | 33,33 ô tô quy đổi | Khoảng 30% | Còn nhiều sức chứa hơn |

Số xe cộng dồn từ đầu clip không dùng để tính D. Chỉ dùng những xe có ô nhận diện trong **khung hình hiện tại**. Khi có kích thước, số xe/sức chứa thủ công cũ không thay công thức diện tích. Camera chưa có kích thước vẫn hỗ trợ cách cũ để giữ tương thích, kèm yêu cầu hiệu chỉnh.

Ngưỡng mật độ thấp/cao là cấu hình từng camera. Với ngưỡng cao H, vùng này có mật độ cao từ khoảng `ceil(H × C)` ô tô, hoặc `ceil(H × C / 0,25)` xe máy nếu chỉ có một loại xe. Đây là ngưỡng **mật độ**, không phải ngưỡng chắc chắn ùn tắc.

## Chuyển động và xe chờ

ByteTrack theo dõi cùng mã xe. Hệ thống so vị trí trong khoảng trước khung hình đang xem, chuẩn hóa theo kích thước xe trong ảnh; hiệu chỉnh dịch chuyển toàn cảnh bằng phase correlation. Cần tối thiểu 0,75 giây và đủ số xe theo dõi trước khi hiển thị tỷ lệ xe đứng/nhích chậm. Một mã mới hoặc mất dấu không tự trở thành xe đang dừng.

Đây là chuyển động tương đối trong ảnh, không công bố thành km/h. Quy ước minh họa xét xe có chuyển động dưới 0,12 chiều dài chéo hộp/giây là đứng hoặc nhích chậm. Khi ít nhất 50% xe theo dõi nhích chậm, tải vùng đường từ 60% và duy trì 30 giây, giao diện ghi dấu hiệu hàng xe chờ kéo dài. Vẫn phải xem chu kỳ đèn, sự cố và bối cảnh; không biến một lần chờ đèn thành kết luận ùn tắc.

## Công thức phần trăm dự báo

XGBoost camera v4 nhận lịch sử theo thứ/giờ, tải đường đã chuẩn hóa, tỷ lệ đứng/nhích chậm khi đủ theo dõi, thời tiết và sự cố đã công bố. Kết quả có ba trạng thái thông thoáng, chậm và ùn tắc. Xác suất ùn tắc không được lấy trực tiếp từ D hoặc độ tin cậy của hộp nhận diện.

```text
p = phân bố ba trạng thái do XGBoost dự đoán
P(trạng thái i) = exp(log(p_i) / T) / tổng_j exp(log(p_j) / T)
Phần trăm ùn tắc = 100 × P(JAM)
```

T được chọn trên phần dữ liệu hiệu chỉnh độc lập để giảm sai lệch xác suất. Không đặt cố định 80%, 90%, không tăng số hiển thị để đạt mong muốn. Chỉ mục tiêu mật độ và mục tiêu ùn tắc được huấn luyện riêng. Đầu vào số xe được chuẩn hóa về cùng sức chứa tham chiếu, tránh học rằng đường rộng có nhiều xe hơn là mặc nhiên tắc hơn.

Mô hình camera v4 dùng tối đa 24 ngày đầy đủ gần nhất của lịch sử minh họa. Train, early stopping, hiệu chỉnh và test chia theo thời gian có khoảng cách theo mốc dự báo. Mốc 15/30/60 phút có báo cáo accuracy, Brier, log loss, ECE và baseline riêng. Mục tiêu accuracy từ 80% được báo đạt/chưa đạt theo kết quả giữ riêng; không chọn mô hình dựa trên việc ép tập test đạt con số mong muốn. Video chưa xác minh cùng đường/thời điểm và 11 mốc lịch sử trước khung hình vẫn là tổng hợp, nên chưa thể coi kết quả này là độ chính xác thực địa.

## Thao tác

Admin hoặc Quản lý được cấp quyền mở **Camera & hiệu chỉnh**, bật **Đánh giá theo kích thước vùng đường**, khai báo số làn, bề rộng, chiều dài và phần diện tích có thể dùng. Chọn nguồn kích thước là ước lượng hoặc đã đo. Lưu rồi phân tích lại video. Cấu hình cũ không được tiếp tục dùng cho kết quả mới.

Người xem mở **Camera giao thông**, chọn camera, phát/tua video, xem phần **Đường rộng hay hẹp được xét thế nào?** và **Xem cách tính**. Dự báo 15/30/60 phút có nút **Vì sao?**, ghi cả kết quả kiểm tra trên dữ liệu minh họa. Thiếu chuyển động hoặc thời tiết được ghi rõ.

## Bảy camera và video khác nhau

```powershell
docker compose exec backend python scripts/setup_camera_videos.py --rush-hour --regions
```

Lệnh giữ các đường hiện có, bổ sung riêng hai tuyến minh họa TP.HCM/Đà Nẵng nếu chưa có. Nếu bộ lịch sử chưa bao gồm tuyến mới, tạo lại bộ lịch sử tổng hợp và mô hình demo; dữ liệu quan trắc thật không đổi. Camera 1–5 dùng năm clip riêng, hai camera khu vực dùng hai clip khác; không quay vòng cùng một clip cho nhiều camera. Script từ chối nếu nội dung video trùng SHA-256 trong lượt chuẩn bị. Ghi chú nguồn ở từng camera luôn cho biết video không được xác minh tại tuyến minh họa. Nguồn và giấy phép nằm trong [manifest](../database/camera-video-sources.json).
