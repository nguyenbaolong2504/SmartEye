# Nghiệp vụ SmartEye

Yêu cầu cuối của tài liệu nguồn rút gọn thành video, ba mức mật độ và tìm tuyến tối ưu thời gian/km/tránh mật độ cao. Tài khoản, vận hành và báo cáo phục vụ hai chức năng chính; không đưa lại dashboard forecast/metric ML giả lập đã bị loại.

| Actor | Quyền |
|---|---|
| Người dùng (User) | Tra cứu đường/camera, tìm tuyến, điều khoản; đăng nhập để quản lý hồ sơ, video của mình, favorite, cảnh báo |
| Quản lý (role analyst) | Quyền User; quan sát thủ công, công bố video của mình, thống kê và báo cáo |
| Admin | Quyền nghiệp vụ, quản lý user/camera/đường/phiên/audit và video thuộc quyền quản trị |

Sơ đồ Actor nghiệp vụ dùng ba nhóm trên. Google là dịch vụ tích hợp; worker YOLO là thành phần xử lý nội bộ. Chức năng công khai vẫn sử dụng được trước đăng nhập.

## Tìm tuyến

A/B → phương tiện/nguồn/giờ → ưu tiên → validation → tuyến ứng viên → quan sát mới → score → loại tuyến bị trội → đề xuất → chi tiết/favorite.

- A khác B; tọa độ Hà Nội; khởi hành từ hiện tại đến 7 ngày sau.
- Demo chỉ có địa điểm trong danh sách. Google có tọa độ tùy chọn.
- `score=wt*ETA/maxETA+wd*km/maxKm+wr*risk`, chuẩn hóa tổng trọng số bằng 1.
- Tuyến bị trội nếu tuyến khác không kém ở ETA/km/risk và tốt hơn ở ít nhất một tiêu chí.
- Mật độ cao chỉ là rủi ro. Không hứa một tuyến đồng thời ngắn nhất và nhanh nhất khi tiêu chí mâu thuẫn.
- Thiếu quan sát không phải LOW, không phải lớp mật độ thứ tư.
- Thay tham số cần tìm lại; favorite giữ input, tính ETA mới khi mở.
- Giờ khởi hành cách hiện tại trên 5 phút chỉ dùng camera dưới dạng lịch sử đủ bằng chứng: 28 ngày gần nhất, cùng thứ/giờ. UI ghi rõ tham khảo lịch sử, chưa phải forecast được huấn luyện.
- Chấp nhận Google trả một tuyến, không tạo tuyến thay thế giả.

## Video

Login → camera → file/thời điểm → queued → processing → completed/failed/cancelled → xem → Analyst/Admin xác nhận → observation → định tuyến/cảnh báo.

- Một worker, hàng đợi tối đa 5, một sample/giây; chỉ car/motorcycle/motorbike/bus/truck.
- Snapshot ROI/capacity/ngưỡng. Tổng hợp trung vị mật độ, count là xe hiện diện từng ảnh.
- Clip cũ/không có thời gian quay chỉ dùng lịch sử; upload time không tự thay recorded time.
- TTL 15 phút; timestamp tương lai bị từ chối; publish một lần.
- Camera đổi đoạn/ngừng: job cũ không publish được.
- Đổi geometry đường đã có quan sát: tạo đường mới để bảo toàn lịch sử.
- Restart: job chưa xong thành failed có giải thích, user tải lại.
- Mặc định xóa raw video sau xử lý/hủy. Người tải có thể chọn giữ video riêng tư trước phân tích. Quản lý/Admin xác nhận chia sẻ riêng để ảnh/video xuất hiện trên trang Camera. Xóa kết quả xóa cả video giữ lại và ảnh/video chia sẻ, vẫn giữ observation/mẫu số liệu đã công bố.
- Video cũ có thời điểm quay được lưu qua Archive; không cần trong 15 phút và không làm mới trạng thái hiện tại. Cả Publish/Archive lưu mẫu theo thời điểm bắt đầu cộng số giây trong clip, không theo thời điểm tải lên.

## Camera và lịch sử ngày/tháng

Trang Camera dùng nguồn video tải lên đã được cho phép chia sẻ, có thời điểm quay rõ; chưa tích hợp nguồn RTSP trực tiếp. Thống kê UTC+7 theo đường/ngày/tháng; ô thiếu dữ liệu giữ trống. Mẫu được gộp theo camera và ô 5 phút, rồi chọn mức mật độ cao nhất của camera trên cùng đường. Mỗi ô đường chỉ có một trọng số. Khung giờ lặp lại cần 3 ngày có ít nhất 3 ô/ngày và tổng 12 ô; danh sách giờ thường mật độ cao chỉ lấy các giờ có từ 50% ô HIGH. Dữ liệu kiểm thử không được đưa vào DB vận hành. Xem [CAMERAS.md](CAMERAS.md).

## Cảnh báo/tài khoản

Theo dõi đường/mức → quan sát mới, còn hiệu lực và được xác nhận → notification → đánh dấu đọc. Không tạo rule trùng user/đường/mức; cooldown 10 phút/rule. Dữ liệu cũ không cảnh báo. Đây là cảnh báo trong ứng dụng, chưa có SMS/push nền.

Signup luôn User. Chỉ Admin đổi vai trò/khóa/mở/thu hồi phiên; không tự khóa/hạ quyền Admin đang thao tác. Thay quyền/mật khẩu thu hồi phiên cũ. Password reset SMTP: token băm, một lần, 30 phút, không trả token ra API.

Ngừng camera/đường có thể khôi phục qua sửa trạng thái, giữ lịch sử. Ngừng đường tự ngừng camera liên quan. CSV chỉ có dữ liệu ứng dụng, chống formula injection. Audit không ghi secrets.

## Ngoại lệ

| Trường hợp | Hành vi |
|---|---|
| Google chưa cấu hình | 503; UI khóa lựa chọn |
| Timeout/quota/key lỗi | 504/429/502, không lộ key |
| Google không có tuyến | 404, không bịa tuyến |
| Chưa YOLO | 503, Admin tải trọng số |
| Video codec lỗi | Job failed và xóa raw |
| Quá 150MB/300s | 413 hoặc failed có giải thích |
| Video người khác | 403 cả ảnh/job |
| Chưa login/không đủ quyền | 401/403 server |
| Quan sát cũ | Chỉ trong báo cáo, không định tuyến/cảnh báo |

## Nghiệm thu

Chạy từ repo sạch; login/signup; inference thật sau tải model; hiệu chỉnh camera; ba mức mật độ; dữ liệu cũ không coi là hiện tại; A/B/trọng số; fallback minh họa có nhãn; favorite tính lại; CSV; RBAC server; quản trị user/camera/road; kiểm thử và giới hạn được ghi rõ.

## Dự báo học máy

XGBoost/GRU là mô hình huấn luyện từ dữ liệu quan sát, có split theo thời gian, baseline và báo cáo riêng. Chưa có mô hình đã huấn luyện cho Hà Nội đi kèm source. Thiếu dữ liệu hoặc chưa qua kích hoạt thì không hiển thị dự báo; nhãn ùn tắc độc lập với mức mật độ YOLO. Xem FORECASTING.md.
