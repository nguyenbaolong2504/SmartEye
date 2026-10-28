# MongoDB SmartEye

Runtime dùng MongoDB/PyMongo. Không cần tạo database/collection bằng tay: `init_db.py` tạo collection, validators/index và seed. [Lệnh local/Docker/Atlas đầy đủ](../docs/RUNNING.md).

## Khởi tạo

MongoDB chạy và `.env` đúng trước khi thực hiện:

```powershell
.venv\Scripts\python.exe -m pip install --no-cache-dir -r backend/requirements-db.txt
.venv\Scripts\python.exe scripts/check_db.py
.venv\Scripts\python.exe scripts/init_db.py --demo-accounts
```

Docker đầy đủ: `docker compose exec backend python scripts/init_db.py --demo-accounts`.

| Vai trò | Email | Mật khẩu demo |
|---|---|---|
| Admin | admin@smarteye.test | SmartEyeAdmin@2026 |
| Analyst | analyst@smarteye.test | SmartEyeAnalyst@2026 |
| User | user@smarteye.test | SmartEyeUser@2026 |

Script chỉ thêm user chưa tồn tại, giữ password/role/active cũ. Startup không tự tạo các tài khoản này; demo bị từ chối ở production. Bản thật dùng `scripts/create_admin.py`. Password web là scrypt hash có salt, không thể đọc lại password gốc từ DB; khác DB username/password.

## 15 collection nghiệp vụ + 1 kỹ thuật

MongoDB dùng collection/document, tương ứng vai trò bảng/bản ghi trong SQL.

| Collection | Nội dung | Tham chiếu |
|---|---|---|
| users | Email unique, tên, password hash, role, active, auth_version | Tài khoản gốc |
| sessions | Hash cookie token, user_id, auth_version, thời hạn | users |
| reset_tokens | Hash token một lần, auth_version, thời hạn | users |
| segments | Đường, hai node, km, geometry, active/is_demo | Đường |
| cameras | segment_id, ROI, capacity, low/high_threshold, active | segments |
| video_jobs | UUID, user/camera, status/progress, config snapshot, result/samples | users, cameras |
| observations | Mật độ/score/nguồn/thời điểm/job_id, đường/camera/user | segments, cameras, users |
| favorites | Tên hành trình, input tìm tuyến request | users |
| alert_rules | Đường/mức theo dõi, active, last_sent | users, segments |
| notifications | Nội dung, read, created_at | users |
| audit | user_id, action, detail, created_at | users |
| traffic_samples | Mẫu mật độ theo thời điểm quay, số xe, camera, observation_id, sample_key unique | segments, cameras, observations |
| forecast_runs | Lần huấn luyện XGBoost/GRU, trạng thái và báo cáo | users, segments |
| traffic_labels | Nhãn ùn tắc thực tế, thời điểm, người xác nhận | users, segments |
| forecast_registry | Bản mô hình đang phục vụ theo mục tiêu | forecast_runs |
| counters | Sequence ID tăng nguyên tử | Kỹ thuật |

Mongo dùng `_id`, API giữ `id` số; video dùng UUID string, session/reset dùng token hash string. Geometry/ROI là mảng; request/config/result là document. Binary video/ảnh/model ở `backend/data`, không lưu trong Mongo.

MongoDB không có SQL foreign key: API kiểm tra quyền/tham chiếu trước ghi/xóa. Mỗi thao tác atomic trên một document, không dùng transaction nhiều document nên chạy standalone được. `auth_version` thu hồi session cũ khi đổi mật khẩu/quyền; reset token xóa/lấy nguyên tử và kiểm tra phiên bản. Worker chỉ hoàn tất job còn processing, tránh ghi đè cancelled.

Index: email unique; job_id unique chỉ khi string (nhiều quan sát thủ công được phép thiếu job); alert `(user_id,segment_id,density)` unique; index lịch sử/đường/trạng thái. Sessions/reset có TTL trên BSON Date `expires_on`; API kiểm tra hạn độc lập vì TTL chạy nền. Validator tạo cho collection mới, không tự áp/chỉnh collection có sẵn. Xem `mongodb/schema.json` và `backend/app/mongo_schema.py`.

## Xem bằng Compass

- Local portable/server: `mongodb://127.0.0.1:27017/`, DB smarteye.
- Docker: `127.0.0.1:27018`, Authentication user/password theo MONGODB_USERNAME/MONGODB_PASSWORD trong `.env`, Authentication Database smarteye.
- Atlas: cùng URI Atlas trong `.env`.

Refresh sau init. Trong users, Project `{ "email": 1, "name": 1, "role": 1, "active": 1 }` để xem tài khoản không lấy password hash. Compass không hiển thị password gốc.

## JSON mẫu cho Compass (tùy chọn)

`mongodb/` có 15 file collection JSON, counters.json và schema.json. Fixture sạch: 3 user demo, 13 đường, 4 camera; session/token/video/quan sát/mẫu lịch sử riêng tư trống. Không dump từ DB làm việc. Hash tương ứng password demo công khai. Không tạo số liệu ngày/tháng giả trong DB mẫu.

Khuyến nghị dùng init_db.py. Nếu muốn import thủ công, dùng DB mới `smarteye_import_demo`, sửa MONGODB_DB trong `.env`, chạy init_db.py trước để có validator/index. Trong Compass chỉ import users.json vào users bằng Add Data → Import JSON; đường/camera đã có từ init, không import trùng. Các array rỗng không cần import. Chạy init_db.py lại để đồng bộ counters theo ID lớn nhất.

Nếu công cụ import đã tạo collection trong DB trống, init sau đó tạo index/counters nhưng không tự áp JSONSchema lên collection có sẵn; nên khởi tạo app trước. schema.json là tài liệu validator, không phải collection để import. Không import fixture vào DB dữ liệu cá nhân.

Tái tạo fixture sạch, không kết nối/dump DB thật hoặc xuất secrets Admin/API:

```powershell
.venv\Scripts\python.exe scripts/build_demo_database.py
```

## SQL lịch sử

legacy-sql/ giữ SQLite/PostgreSQL cũ để tham khảo. App hiện không dùng DATABASE_URL/POSTGRES_*, không đọc SQLite, không tự chuyển dữ liệu cũ. Giữ nguyên DB cũ khi đổi kết nối. Không commit `.env`, dữ liệu làm việc, token hoặc video thật.
