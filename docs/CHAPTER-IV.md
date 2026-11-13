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
| UC09 · Thống kê theo giờ, đánh giá dự báo và xuất báo cáo | — | Theo phạm vi được phân công | — |
| UC10 · Quản lý tài khoản và phân quyền | — | — | Có |
| UC11 · Theo dõi dịch vụ, tình trạng tiếp nhận và nhật ký | — | Nhật ký vận hành giao thông, Quản lý toàn bộ tuyến có quyền xem dịch vụ | Toàn bộ nhật ký hệ thống |
| UC12 · Cấu hình, ánh xạ, kiểm tra và bật/tắt nguồn dữ liệu | — | Theo phạm vi được phân công | Có |
| UC14 · Xem camera giao thông công khai và chuyển sang dự báo tuyến | Có | Có, khi được cấp quyền xem camera công khai | Cấu hình và cấp quyền trong không gian quản trị |

UC13 là đăng ký dành cho khách truy cập. Khách có thể xem các trang công khai. Phản ánh, hành trình đã lưu và thông báo cá nhân cần tài khoản Người dùng hoặc Quản lý. Tìm tuyến và lưu hành trình là chức năng có sẵn của SmartEye ngoài danh mục Chương IV, dùng chung cho Người dùng và Quản lý. Quản lý cấu hình đoạn đường, hiệu chỉnh camera, chuẩn bị dữ liệu và huấn luyện mô hình trong phạm vi được giao. Tạo đoạn đường mới, kích hoạt/ngừng mô hình đang phục vụ, tạo lại bộ mẫu và xem trạng thái dịch vụ toàn hệ thống dành cho Admin hoặc Quản lý phụ trách toàn bộ tuyến có quyền tương ứng. Admin có các mục Nguồn dữ liệu, Đoạn đường, Người dùng, Dữ liệu & mô hình, Hệ thống & nhật ký và Camera & hiệu chỉnh. Báo cáo theo giờ thuộc không gian Quản lý.

## Chạy thử theo vai trò

1. **Người dùng.** Vào **Tình trạng & thống kê**, chọn tuyến và chiều để xem quan sát, thời điểm ghi nhận và lịch sử. Mở **Dự báo giao thông** để chọn giờ khởi hành, xem dự báo và so sánh với hiện tại khi có đủ dữ liệu cùng loại. Bật nhận cảnh báo trong **Hồ sơ cá nhân** nếu muốn nhận thông báo trong ứng dụng.
2. **Người dùng.** Vào **Phản ánh giao thông**, chọn tuyến, chiều, vị trí, thời điểm và loại sự cố. Có thể đính kèm ảnh JPG, PNG hoặc WebP tối đa 5 MB. Ghi lại mã phản ánh hoặc mở **Phản ánh của tôi** để theo dõi.
3. **Quản lý.** Vào **Giám sát & xử lý**, mở phản ánh trong phạm vi phụ trách, tiếp nhận và ghi căn cứ xác minh. Phản ánh hợp lệ chuyển sang xử lý rồi kết thúc. Thiếu căn cứ thì tiếp tục xác minh. Khi kết luận không hợp lệ, phải xác nhận từ chối và ghi lý do.
4. **Quản lý.** Tạo cảnh báo thủ công hoặc mở bản nháp do quy tắc đề xuất. Nếu xuất phát từ phản ánh, gắn mã phản ánh đã xác minh. Chọn giờ tự hết hiệu lực, xác minh rồi phát hành. Cảnh báo hiện ở Tổng quan, mục Cảnh báo và hộp thông báo của tài khoản đã bật nhận. Khi đến giờ, cảnh báo rời danh sách công khai và được giữ trong lịch sử xử lý.
5. **Quản lý.** Vào **Giám sát & xử lý → Dữ liệu & thiết lập → Nguồn dữ liệu**. Chọn loại tệp, dịch vụ hoặc camera, tuyến và chiều. Với tệp/dịch vụ, ánh xạ trường thời gian, tuyến, chiều và các chỉ số có sẵn. Kiểm tra mẫu hoặc kết nối, bật nguồn rồi nhận dữ liệu. Mở **Giám sát & xử lý → Báo cáo theo giờ** để lọc số liệu, đánh giá dự báo và tải CSV nếu được cấp quyền xuất. Quản lý toàn bộ tuyến có thể mở **Dữ liệu & thiết lập → Dịch vụ & nhật ký** khi được cấp quyền xem dịch vụ.
6. **Admin.** Vào **Quản trị hệ thống → Người dùng**, tìm hoặc tạo tài khoản, thay đổi vai trò, chọn tuyến phụ trách và cấp từng quyền thao tác. Có thể vô hiệu hóa tài khoản hoặc thu hồi phiên đăng nhập. Các mục cấu hình nguồn, đoạn đường, camera và mô hình nằm cùng không gian. Mở **Hệ thống & nhật ký** để xem trạng thái dịch vụ và toàn bộ nhật ký, gồm thao tác tài khoản.

## Đối chiếu theo nhóm use case

| Nhóm | Luồng chính và nhánh ngoại lệ |
| --- | --- |
| LOGIN.1–3, UC01, UC13 | Đăng ký có xác nhận mật khẩu, đăng nhập bằng tên đăng nhập hoặc email, sửa hồ sơ, đổi mật khẩu, khôi phục qua email khi đã cấu hình và đăng xuất. Dữ liệu trùng được báo lỗi. Đổi mật khẩu thu hồi các phiên cũ. |
| UC02–03, UC05 | Quan sát và dự báo theo tuyến, chiều, thời điểm và nguồn. Thiếu mẫu, mẫu cũ hoặc mô hình chưa sẵn sàng có trạng thái riêng. Camera chỉ hiển thị từ nguồn được bật trong phạm vi quản lý. |
| UC04, UC06 | Người gửi theo dõi phản ánh của mình. Quản lý đúng phạm vi mới có quyền tiếp nhận và xử lý. Lưu căn cứ, người thao tác, thời điểm và lịch sử. Cập nhật từ phiên bản cũ yêu cầu tải lại. |
| UC07–08 | Cảnh báo qua xác minh rồi phát hành. Theo yêu cầu cập nhật, sửa và hủy áp dụng cho bản nháp. Bản đã phát hành chỉ để xem và tự kết thúc theo giờ đã đặt. Quy tắc cần thử trước khi bật và chỉ đề xuất bản nháp. Gửi lại thông báo giữ một bản cho mỗi người nhận và phiên bản. |
| UC09–10 | Báo cáo theo giờ và CSV dùng chung bộ lọc quan trắc. Giờ thiếu mẫu không được ghi nhận là thông thoáng. Admin quản lý tài khoản, phân quyền theo tuyến, vô hiệu hóa có lưu lịch sử và bảo vệ quản trị viên cuối. |
| UC11–12 | Admin xem toàn bộ nhật ký hệ thống. Quản lý toàn bộ tuyến có quyền xem dịch vụ được xem nhật ký vận hành giao thông. Nhật ký chỉ đọc, có bộ lọc và che thông tin xác thực. Nguồn chỉ nhận sau kiểm tra. Đổi cấu hình hoặc ánh xạ yêu cầu kiểm tra lại. Lượt nhận ghi số mẫu hợp lệ, sai và trùng. Lưu lượng chỉ được tính khi có thời lượng đếm. |

## Điều kiện dữ liệu

Dự báo theo giờ đối chiếu 100 ngày lịch, tách ngày làm việc và cuối tuần, rồi đếm số ngày đủ dữ liệu đúng khung giờ và chiều đường. Với ngày đã qua, chỉ lấy dữ liệu trước ngày được chọn. Khi thiếu quan trắc, tuyến đã có bộ mẫu có thể hiển thị kết quả gắn nhãn **Lịch sử minh họa**. Tìm địa chỉ bao phủ Việt Nam qua nguồn bản đồ. Mỗi địa chỉ cần được liên kết với đoạn đường và lịch sử quan trắc của SmartEye để có dự báo thực.

Trong **Quản trị hệ thống → Người dùng → Phân quyền**, Admin có thể bỏ chọn từng quyền của một tài khoản Người dùng hoặc Quản lý. Ví dụ, giữ **Xem phản ánh của mình** và bỏ **Gửi phản ánh** để tài khoản chỉ xem được. Quyền thao tác của Quản lý còn phụ thuộc quyền xem nhóm chức năng, tuyến được phân công và trạng thái hồ sơ. Tài khoản đăng nhập lại sau khi quyền thay đổi.

Tệp Chương IV dẫn chiếu Phụ lục B. Bản này áp dụng chính sách mật khẩu đang dùng và cho phép cấu hình các tham số nguồn, thời hạn dữ liệu, ngưỡng quy tắc. Đăng ký tạo tài khoản dùng được ngay. Khôi phục mật khẩu cần SMTP. Camera cần địa chỉ HTTPS được phép sử dụng, trả ảnh JPG/PNG/WebP hoặc clip MP4/WebM. Dịch vụ lấy số liệu thật cần địa chỉ nguồn và thông tin xác thực nếu nguồn yêu cầu. Nguồn mới dùng mã truy cập trong biến môi trường phải trỏ đến máy chủ HTTPS đã cấu hình trước bằng biến cùng tên thêm hậu tố `_HOST`, dùng cổng 443. Ví dụ mã `TRAFFIC_SOURCE_DEMO` có máy chủ cho phép tại `TRAFFIC_SOURCE_DEMO_HOST=traffic.example.org`. Giao diện chỉ chọn tên biến, không hiển thị giá trị mã.


## UC14. Xem camera giao thông

**Tác nhân** gồm Người dùng và Quản lý có quyền xem camera công khai. Trang cho phép xem camera công khai trước khi đăng nhập. Admin cấu hình nguồn và quyền xem trong không gian quản trị.

**Điều kiện** gồm đoạn đường đã khai báo, camera có vị trí theo tọa độ hoặc theo đoạn đường. Nguồn ảnh/video phải được phép sử dụng, kiểm tra kết nối, bật nguồn và xác nhận cho người dùng xem. Nguồn riêng tư không được đưa vào danh sách công khai.

**Luồng chính**

1. Người xem mở **Giao thông → Camera giao thông**.
2. Hệ thống tải bộ lọc và camera đầu tiên, kèm tuyến, vị trí và trạng thái kết nối. Bản đồ và danh sách đầy đủ chỉ mở khi chọn **Xem bản đồ camera**.
3. Người xem chọn lần lượt tỉnh/thành phố, tuyến đường và vị trí camera. Đổi tỉnh/thành phố đặt lại bộ lọc tuyến và camera.
4. Người xem chọn một dòng trong danh sách hoặc ghim trên bản đồ. Hệ thống hiển thị cùng camera trong khung quan sát.
5. Ảnh nguồn được cập nhật theo chu kỳ đã cấu hình, có thể tạm dừng, tải lại và phóng to. Video MP4/WebM được phát bằng nút điều khiển. Hình ảnh lưu từ trước được ghi rõ loại và thời điểm ghi hình.
6. Mở **Thông tin camera và nguồn video** để xem nguồn, thời điểm ghi hình nếu có và lần kiểm tra kết nối. Nguồn không cung cấp thời điểm ghi hình được ghi nhận rõ. Ghim theo đoạn đường có ghi chú về vị trí.
7. Trong phần thông tin, chọn **Xem dự báo tuyến đường** nếu được cấp quyền dự báo. Hệ thống mở đúng tuyến và chiều của camera.
8. Với camera có video mẫu đã nhận diện, người xem phát/tua video, ẩn/hiện ô nhận diện hoặc phóng to video. Chọn **15 phút / 30 phút / 1 giờ**, nhấn **Phân tích**. Hệ thống tổng hợp tối đa 10 giây cuối video, đối chiếu lịch sử và điều kiện có thông tin, trả một kết quả cho mốc đã chọn.
9. Kết quả hiển thị khả năng Thông thoáng, Di chuyển chậm và Ùn tắc. Trạng thái có tỷ lệ cao nhất từ 80% được làm nổi bật, kể cả thông thoáng. Nếu chưa trạng thái nào đạt 80%, ghi **Xu hướng chưa rõ**. Tua video không thay đổi kết quả đã phân tích; đổi mốc hoặc camera xóa kết quả cũ và yêu cầu phân tích lại.
10. Nhấn **Vì sao?** để xem đoạn video đã xét, khung hình đại diện và số xe từng loại, sức chứa từng đường, chuyển động, lịch sử cùng giờ/cùng thứ, thời tiết, sự cố và công thức. Không dùng tổng xe cộng dồn thay cho mật độ. Các căn cứ được giữ theo đúng lượt phân tích. Nguồn video minh họa và giới hạn vị trí nằm trong phần thông tin. Mỗi camera demo dùng clip khác nhau. [Công thức và giới hạn](ROAD-CAPACITY.md).

**Luồng ngoại lệ**

- Khu vực không có camera được chia sẻ hiển thị danh sách trống và hướng dẫn chọn khu vực khác.
- Camera tắt hoặc chưa có ảnh hiển thị trạng thái tương ứng. Dữ liệu thiếu không được diễn giải thành đường thông thoáng.
- Mất kết nối hoặc sai định dạng có thông báo và nút tải lại. Ảnh cũ còn hiển thị được giữ cùng mốc nhận ảnh cũ.
- Nguồn bị tắt hoặc thu hồi chia sẻ chặn ngay yêu cầu ảnh tiếp theo, kể cả khi ảnh đã nằm trong bộ nhớ đệm máy chủ.
- Tài khoản bị bỏ quyền xem camera không được mở trang hoặc gọi API xem ảnh. Quyền dự báo được kiểm tra riêng.
- Tuyến chưa đủ lịch sử mở trang dự báo với thông báo thiếu dữ liệu theo luồng dự báo hiện có.
- Video mẫu đang xử lý hiển thị tiến độ; thiếu mô hình/lịch sử hiển thị lỗi phù hợp và cho thử lại. Đổi hiệu chỉnh hoặc đổi bản video làm kết quả cũ hết phù hợp. API kiểm tra mã lượt nhận diện trùng với video đang chia sẻ, từ chối lượt cũ bằng HTTP 409. Tỷ lệ thiếu/sai không được thay bằng 90% hoặc thông thoáng. Admin/Quản lý có quyền quản lý camera đúng phạm vi có thể nhận diện lại. Không cho gửi trùng tác vụ, giữ video cũ trong khi xử lý và có thể thử lại nếu thất bại.

**Cấu hình để chạy thử**

Admin mở **Quản trị hệ thống → Nguồn dữ liệu → Thêm nguồn**, chọn Camera, đoạn đường, chiều, định dạng Ảnh hoặc Video và URL nguồn được phép sử dụng. Nhập tên giao lộ và tọa độ nếu có. Tích **Cho phép người dùng xem camera trên trang Camera giao thông**, xác nhận quyền sử dụng, lưu, kiểm tra nguồn rồi bật nguồn. Ảnh hỗ trợ JPG/PNG/WebP. Video chia sẻ cần URL MP4/WebM công khai, không chứa mã truy cập. Nguồn ảnh có mã truy cập được lấy qua máy chủ và giữ kín mã. Camera nguồn không tự tạo nhãn ùn tắc hoặc dữ liệu huấn luyện chỉ bằng thao tác xem.

Để có clip mẫu kèm nhận diện thực bằng YOLO11 và dự báo mật độ minh họa bằng XGBoost, dùng `scripts/setup_camera_videos.py` theo [DEMO.md](DEMO.md#video-camera-và-dự-báo-mật-độ). Dữ liệu tổng hợp và video không xác minh đúng tuyến không được công bố thành quan trắc hay cảnh báo thực tế.
