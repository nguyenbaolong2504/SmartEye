# Nghiệp vụ SmartEye

Yêu cầu cuối của tài liệu nguồn rút gọn thành video, ba mức mật độ và tìm tuyến tối ưu thời gian/km/tránh mật độ cao. Tài khoản, vận hành và báo cáo phục vụ hai chức năng chính; không đưa lại dashboard forecast/metric ML giả lập đã bị loại.

| Actor | Quyền |
|---|---|
| Khách | Xem đường/camera, tìm tuyến, điều khoản |
| User | Quyền khách; hồ sơ, video của mình, favorite, cảnh báo |
| Analyst | Quan sát thủ công, công bố video của mình, báo cáo |
| Admin | User/camera/đường/phiên/audit và kiểm duyệt video |
| Google | Tính tuyến/ETA/tốc độ; không truy cập DB |
| Worker | Nhận dạng xe từ video được tải lên |

## Tìm tuyến

A/B → phương tiện/nguồn/giờ → ưu tiên → validation → tuyến ứng viên → quan sát mới → score → loại tuyến bị trội → đề xuất → chi tiết/favorite.

- A khác B; tọa độ Hà Nội; khởi hành từ hiện tại đến 7 ngày sau.
- Demo chỉ có địa điểm trong danh sách. Google có tọa độ tùy chọn.
- `score=wt*ETA/maxETA+wd*km/maxKm+wr*risk`, chuẩn hóa tổng trọng số bằng 1.
- Tuyến bị trội nếu tuyến khác không kém ở ETA/km/risk và tốt hơn ở ít nhất một tiêu chí.
- Mật độ cao chỉ là rủi ro. Không hứa một tuyến đồng thời ngắn nhất và nhanh nhất khi tiêu chí mâu thuẫn.
- Thiếu quan sát không phải LOW, không phải lớp mật độ thứ tư.
- Thay tham số cần tìm lại; favorite giữ input, tính ETA mới khi mở.
- Camera hiện tại không phải forecast giờ tương lai; UI nêu rõ.
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
- Raw video xóa sau xử lý/hủy. Ảnh/kết quả riêng tư; xóa kết quả vẫn giữ observation đã công bố.

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
