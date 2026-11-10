# Nghiệp vụ SmartEye theo Chương IV

## Chạy thử theo vai trò

1. **Người dùng.** Vào **Tình trạng & thống kê**, chọn tuyến và chiều để xem quan sát, thời điểm ghi nhận và lịch sử. Mở **Dự báo giao thông** để chọn giờ khởi hành, xem dự báo và so sánh với hiện tại khi có đủ dữ liệu cùng loại. Bật nhận cảnh báo trong **Hồ sơ cá nhân** nếu muốn nhận thông báo trong ứng dụng.
2. **Người dùng.** Vào **Phản ánh giao thông**, chọn tuyến, chiều, vị trí, thời điểm và loại sự cố. Có thể đính kèm ảnh JPG, PNG hoặc WebP tối đa 5 MB. Ghi lại mã phản ánh hoặc mở **Phản ánh của tôi** để theo dõi.
3. **Quản lý.** Vào **Giám sát & xử lý**, mở phản ánh trong phạm vi phụ trách, tiếp nhận và ghi căn cứ xác minh. Phản ánh hợp lệ chuyển sang xử lý rồi kết thúc. Thiếu căn cứ thì tiếp tục xác minh. Khi kết luận không hợp lệ, phải xác nhận từ chối và ghi lý do.
4. **Quản lý.** Tạo cảnh báo thủ công hoặc mở cảnh báo do quy tắc đề xuất. Xác minh, rồi thực hiện thao tác phát hành riêng. Khách có thể xem cảnh báo đã phát hành. Người dùng đã bật nhận thông báo thấy cảnh báo trong hộp thông báo.
5. **Admin.** Vào **Quản trị hệ thống → Nguồn dữ liệu**. Chọn loại tệp, dịch vụ hoặc camera, tuyến và chiều. Với tệp/dịch vụ, ánh xạ trường thời gian, tuyến, chiều và các chỉ số có sẵn. Kiểm tra mẫu hoặc kết nối, bật nguồn rồi nhận dữ liệu. Dùng **Báo cáo theo giờ** để lọc và tải CSV. Dùng **Hệ thống & nhật ký** để xem trạng thái, lỗi và dấu vết xử lý.

## Đối chiếu theo nhóm use case

| Nhóm | Luồng chính và nhánh ngoại lệ |
| --- | --- |
| LOGIN.1–3, UC01, UC13 | Đăng ký có xác nhận mật khẩu, đăng nhập bằng tên đăng nhập hoặc email, sửa hồ sơ, đổi mật khẩu, khôi phục qua email khi đã cấu hình và đăng xuất. Dữ liệu trùng được báo lỗi. Đổi mật khẩu thu hồi các phiên cũ. |
| UC02–03, UC05 | Quan sát và dự báo theo tuyến, chiều, thời điểm và nguồn. Thiếu mẫu, mẫu cũ hoặc mô hình chưa sẵn sàng có trạng thái riêng. Camera chỉ hiển thị từ nguồn được bật trong phạm vi quản lý. |
| UC04, UC06 | Người gửi theo dõi phản ánh của mình. Quản lý đúng phạm vi mới có quyền tiếp nhận và xử lý. Lưu căn cứ, người thao tác, thời điểm và lịch sử. Cập nhật từ phiên bản cũ yêu cầu tải lại. |
| UC07–08 | Cảnh báo qua bước xác minh trước khi phát hành. Bản đang công khai được giữ trong lúc duyệt bản sửa. Kết thúc và hủy là hai thao tác riêng. Quy tắc cần thử trước khi bật và chỉ đề xuất cảnh báo chờ xác minh. Gửi lại thông báo không tạo bản trùng cho cùng người nhận và phiên bản. |
| UC09–10 | Báo cáo theo giờ và CSV dùng chung bộ lọc quan trắc. Giờ thiếu mẫu không được ghi nhận là thông thoáng. Admin quản lý tài khoản, phân quyền theo tuyến, vô hiệu hóa có lưu lịch sử và bảo vệ quản trị viên cuối. |
| UC11–12 | Nhật ký chỉ đọc, có bộ lọc và che thông tin xác thực. Nguồn chỉ nhận sau kiểm tra. Đổi cấu hình hoặc ánh xạ yêu cầu kiểm tra lại. Lượt nhận ghi số mẫu hợp lệ, sai và trùng. Lưu lượng chỉ được tính khi có thời lượng đếm. |

## Điều kiện dữ liệu

Dữ liệu minh họa một năm dùng để thử thống kê và dự báo theo ngày, giờ. Dự báo từ quan trắc cần chuỗi quan sát đủ mới và mô hình đã kích hoạt cho tuyến đó. Mô hình hiện có phục vụ chiều đi. Chiều về có thể nhận và xem quan trắc riêng khi tuyến cho phép.

Tệp Chương IV dẫn chiếu Phụ lục B. Bản này áp dụng chính sách mật khẩu đang dùng và cho phép cấu hình các tham số nguồn, thời hạn dữ liệu, ngưỡng quy tắc. Đăng ký tạo tài khoản dùng được ngay. Khôi phục mật khẩu cần SMTP. Camera cần địa chỉ HTTPS được phép sử dụng, trả ảnh JPG/PNG/WebP hoặc clip MP4/WebM. Dịch vụ lấy số liệu thật cần địa chỉ nguồn và thông tin xác thực nếu nguồn yêu cầu.
