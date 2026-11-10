# Nghiệp vụ SmartEye theo Chương IV

## Phân quyền theo tác nhân

| Use case | Người dùng | Quản lý | Admin (phòng IT) |
| --- | --- | --- | --- |
| LOGIN.1–3, UC01 · Đăng nhập, khôi phục mật khẩu, đăng xuất và hồ sơ cá nhân | Có | Có | Có |
| UC02 · Xem tuyến, tình trạng, chỉ số, lịch sử và bản đồ | Có | Có | — |
| UC03 · Chọn mốc, xem dự báo, xu hướng và so sánh với hiện tại | Có | Có | — |
| UC04 · Xem cảnh báo, nhận thông báo, gửi và theo dõi phản ánh của mình | Có | Có | — |
| UC05 · Giám sát giao thông và xem camera được cấp quyền | — | Theo phạm vi được phân công | — |
| UC06 · Tiếp nhận, xác minh và xử lý phản ánh | — | Theo phạm vi được phân công | — |
| UC07 · Xác minh, phát hành và quản lý cảnh báo | — | Theo phạm vi được phân công | — |
| UC08 · Quản lý quy tắc đề xuất cảnh báo | — | Theo phạm vi được phân công | — |
| UC09 · Thống kê theo giờ và xuất báo cáo | — | — | Có |
| UC10 · Quản lý tài khoản và phân quyền | — | — | Có |
| UC11 · Theo dõi hệ thống, tình trạng tiếp nhận và tra cứu nhật ký | — | — | Có |
| UC12 · Cấu hình, ánh xạ, kiểm tra và bật/tắt nguồn dữ liệu | — | — | Có |

UC13 là đăng ký dành cho khách truy cập. Khách có thể xem các trang công khai. Phản ánh, hành trình đã lưu và thông báo cá nhân cần tài khoản Người dùng hoặc Quản lý. Tìm tuyến và lưu hành trình là chức năng có sẵn của SmartEye ngoài danh mục Chương IV, dùng chung cho Người dùng và Quản lý. Cấu hình đoạn đường, hiệu chỉnh camera và quản lý mô hình nằm trong không gian kỹ thuật của Admin.

## Chạy thử theo vai trò

1. **Người dùng.** Vào **Tình trạng & thống kê**, chọn tuyến và chiều để xem quan sát, thời điểm ghi nhận và lịch sử. Mở **Dự báo giao thông** để chọn giờ khởi hành, xem dự báo và so sánh với hiện tại khi có đủ dữ liệu cùng loại. Bật nhận cảnh báo trong **Hồ sơ cá nhân** nếu muốn nhận thông báo trong ứng dụng.
2. **Người dùng.** Vào **Phản ánh giao thông**, chọn tuyến, chiều, vị trí, thời điểm và loại sự cố. Có thể đính kèm ảnh JPG, PNG hoặc WebP tối đa 5 MB. Ghi lại mã phản ánh hoặc mở **Phản ánh của tôi** để theo dõi.
3. **Quản lý.** Vào **Giám sát & xử lý**, mở phản ánh trong phạm vi phụ trách, tiếp nhận và ghi căn cứ xác minh. Phản ánh hợp lệ chuyển sang xử lý rồi kết thúc. Thiếu căn cứ thì tiếp tục xác minh. Khi kết luận không hợp lệ, phải xác nhận từ chối và ghi lý do.
4. **Quản lý.** Tạo cảnh báo thủ công hoặc mở bản nháp do quy tắc đề xuất. Nếu xuất phát từ phản ánh, gắn mã phản ánh đã xác minh. Chọn giờ tự hết hiệu lực, xác minh rồi phát hành. Cảnh báo hiện ở Tổng quan, mục Cảnh báo và hộp thông báo của tài khoản đã bật nhận. Khi đến giờ, cảnh báo rời danh sách công khai và được giữ trong lịch sử xử lý.
5. **Admin.** Vào **Quản trị hệ thống → Nguồn dữ liệu**. Chọn loại tệp, dịch vụ hoặc camera, tuyến và chiều. Với tệp/dịch vụ, ánh xạ trường thời gian, tuyến, chiều và các chỉ số có sẵn. Kiểm tra mẫu hoặc kết nối, bật nguồn rồi nhận dữ liệu. Dùng **Báo cáo theo giờ** để lọc và tải CSV. Dùng **Hệ thống & nhật ký** để xem trạng thái, lỗi và dấu vết xử lý.

## Đối chiếu theo nhóm use case

| Nhóm | Luồng chính và nhánh ngoại lệ |
| --- | --- |
| LOGIN.1–3, UC01, UC13 | Đăng ký có xác nhận mật khẩu, đăng nhập bằng tên đăng nhập hoặc email, sửa hồ sơ, đổi mật khẩu, khôi phục qua email khi đã cấu hình và đăng xuất. Dữ liệu trùng được báo lỗi. Đổi mật khẩu thu hồi các phiên cũ. |
| UC02–03, UC05 | Quan sát và dự báo theo tuyến, chiều, thời điểm và nguồn. Thiếu mẫu, mẫu cũ hoặc mô hình chưa sẵn sàng có trạng thái riêng. Camera chỉ hiển thị từ nguồn được bật trong phạm vi quản lý. |
| UC04, UC06 | Người gửi theo dõi phản ánh của mình. Quản lý đúng phạm vi mới có quyền tiếp nhận và xử lý. Lưu căn cứ, người thao tác, thời điểm và lịch sử. Cập nhật từ phiên bản cũ yêu cầu tải lại. |
| UC07–08 | Cảnh báo qua xác minh rồi phát hành. Theo yêu cầu cập nhật, sửa và hủy áp dụng cho bản nháp. Bản đã phát hành chỉ để xem và tự kết thúc theo giờ đã đặt. Quy tắc cần thử trước khi bật và chỉ đề xuất bản nháp. Gửi lại thông báo giữ một bản cho mỗi người nhận và phiên bản. |
| UC09–10 | Báo cáo theo giờ và CSV dùng chung bộ lọc quan trắc. Giờ thiếu mẫu không được ghi nhận là thông thoáng. Admin quản lý tài khoản, phân quyền theo tuyến, vô hiệu hóa có lưu lịch sử và bảo vệ quản trị viên cuối. |
| UC11–12 | Nhật ký chỉ đọc, có bộ lọc và che thông tin xác thực. Nguồn chỉ nhận sau kiểm tra. Đổi cấu hình hoặc ánh xạ yêu cầu kiểm tra lại. Lượt nhận ghi số mẫu hợp lệ, sai và trùng. Lưu lượng chỉ được tính khi có thời lượng đếm. |

## Điều kiện dữ liệu

Dự báo theo giờ đối chiếu 100 ngày lịch, tách ngày làm việc và cuối tuần, rồi đếm số ngày đủ dữ liệu đúng khung giờ và chiều đường. Với ngày đã qua, chỉ lấy dữ liệu trước ngày được chọn. Khi thiếu quan trắc, tuyến đã có bộ mẫu có thể hiển thị kết quả gắn nhãn **Lịch sử minh họa**. Tìm địa chỉ bao phủ Việt Nam qua nguồn bản đồ. Mỗi địa chỉ cần được liên kết với đoạn đường và lịch sử quan trắc của SmartEye để có dự báo thực.

Trong **Quản trị hệ thống → Người dùng → Phân quyền**, Admin có thể bỏ chọn từng quyền của một tài khoản Người dùng hoặc Quản lý. Ví dụ, giữ **Xem phản ánh của mình** và bỏ **Gửi phản ánh** để tài khoản chỉ xem được. Quyền thao tác của Quản lý còn phụ thuộc quyền xem nhóm chức năng, tuyến được phân công và trạng thái hồ sơ. Tài khoản đăng nhập lại sau khi quyền thay đổi.

Tệp Chương IV dẫn chiếu Phụ lục B. Bản này áp dụng chính sách mật khẩu đang dùng và cho phép cấu hình các tham số nguồn, thời hạn dữ liệu, ngưỡng quy tắc. Đăng ký tạo tài khoản dùng được ngay. Khôi phục mật khẩu cần SMTP. Camera cần địa chỉ HTTPS được phép sử dụng, trả ảnh JPG/PNG/WebP hoặc clip MP4/WebM. Dịch vụ lấy số liệu thật cần địa chỉ nguồn và thông tin xác thực nếu nguồn yêu cầu.
