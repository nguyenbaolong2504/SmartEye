# Database SmartEye

## Mở được ngay

`smarteye-demo.sqlite3` là database mẫu độc lập, có **11 bảng, 3 tài khoản, 13 đoạn đường minh họa và 4 camera**. Không có phiên đăng nhập, token reset, dữ liệu cá nhân thật hay video thật. Mở file bằng DB Browser for SQLite hoặc DBeaver để xem bảng và quan hệ; không cần chạy PostgreSQL/Docker.

Tài khoản mẫu **chỉ dùng để thử local**:

| Vai trò | Email đăng nhập SmartEye | Mật khẩu demo |
|---|---|---|
| Admin | `admin@smarteye.test` | `SmartEyeAdmin@2026` |
| Analyst | `analyst@smarteye.test` | `SmartEyeAnalyst@2026` |
| User | `user@smarteye.test` | `SmartEyeUser@2026` |

Trong bảng `users`, cột `password` chứa **scrypt hash có salt**, không chứa mật khẩu đọc được. Backend lấy tài khoản từ bảng này và xác minh hash khi đăng nhập. Không thể lấy lại mật khẩu gốc từ hash; mật khẩu ở bảng trên được biết vì đây là tài khoản mẫu do script tạo. Các tài khoản thực dùng mật khẩu riêng và quy trình đặt lại.

## Gắn vào ứng dụng theo cách đơn giản nhất

Không ghi đè database hiện có. Khởi tạo/kiểm tra các bảng và thêm những tài khoản demo chưa tồn tại:

```powershell
.venv\Scripts\python.exe -m pip install --no-cache-dir -r backend/requirements-db.txt
.venv\Scripts\python.exe scripts/init_db.py --demo-accounts
```

Script dùng database đang cấu hình trong `.env`. Mặc định:

```dotenv
DATABASE_URL=sqlite:///./backend/data/smarteye.db
```

Script không đổi mật khẩu, vai trò hay trạng thái tài khoản cũ; nếu email demo đã có từ trước, thông tin đăng nhập đã thay đổi vẫn được giữ. `--demo-accounts` bị từ chối khi `APP_ENV=production`. Startup API không tự tạo các tài khoản công khai này.

Nếu muốn chạy đúng file mẫu mà không chạm dữ liệu cũ, tạo **bản sao làm việc** bằng Python có sẵn:

```powershell
python -c "from pathlib import Path; import shutil; target=Path('backend/data/smarteye-demo-local.sqlite3'); target.parent.mkdir(parents=True,exist_ok=True); assert not target.exists(), 'File da ton tai; hay chon ten khac'; shutil.copyfile('database/smarteye-demo.sqlite3',target)"
```

Đổi `.env`, sau đó restart backend:

```dotenv
DATABASE_URL=sqlite:///./backend/data/smarteye-demo-local.sqlite3
```

Không trỏ ứng dụng thẳng vào `database/smarteye-demo.sqlite3`: file trong Git là mẫu sạch; dữ liệu làm việc đặt ở `backend/data` và không được commit. Khởi tạo DB không thay việc cài các thư viện API/video khi chạy toàn ứng dụng.

## Nên chọn database nào?

| Phương án | Khi dùng trong SmartEye | Công cụ xem/quản lý |
|---|---|---|
| SQLite | Demo cá nhân, học cấu trúc bảng, máy cấu hình/dung lượng hạn chế; mở file ngay | DB Browser for SQLite / DBeaver |
| PostgreSQL | Bản chính của đề tài, triển khai máy chủ, nhiều tài khoản và nhiều tác vụ ghi dữ liệu | pgAdmin / DBeaver |
| PostgreSQL + PostGIS | Mở rộng truy vấn bán kính, đường gần nhất, polygon/geometry và spatial index | pgAdmin / QGIS |

Khuyến nghị: **PostgreSQL + pgAdmin cho bản chính; SQLite để chạy thử ngay.** Code hiện đã dùng SQLAlchemy/psycopg để hỗ trợ PostgreSQL. Geometry đang là JSON, chưa dùng PostGIS; cài extension không tự chuyển code sang truy vấn GIS.

Nguồn: [SQLite — appropriate uses](https://www.sqlite.org/whentouse.html), [PostgreSQL Windows installer gồm pgAdmin](https://www.postgresql.org/download/windows/), [PostGIS getting started](https://postgis.net/documentation/getting_started/).

## Kết nối PostgreSQL local, không cần viết URL mật khẩu

1. Cài PostgreSQL + pgAdmin từ trang chính thức; máy đang ít dung lượng ổ C có thể chọn vị trí cài/data trên D khi installer cho phép.
2. Trong pgAdmin, kết nối server bằng tài khoản quản trị PostgreSQL. Tạo Login/Group Role `smarteye`, bật login và đặt mật khẩu riêng. Tạo database `smarteye`, owner là role `smarteye`.
3. Thêm/sửa các dòng sau trong `.env` (xem `.env.postgresql.example`):

```dotenv
DATABASE_URL=
DB_ENGINE=postgresql
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=smarteye
POSTGRES_USER=smarteye
POSTGRES_PASSWORD=mat_khau_database_ban_da_dat
```

`DATABASE_URL` cần để trống để các trường riêng có hiệu lực. SQLAlchemy ghép URL và xử lý ký tự đặc biệt trong password. Nếu có URL đầy đủ, `DATABASE_URL` được ưu tiên; cả dạng `postgresql://` được chuyển sang driver `psycopg`.

4. Cài gói DB và khởi tạo:

```powershell
.venv\Scripts\python.exe -m pip install --no-cache-dir -r backend/requirements-db.txt
.venv\Scripts\python.exe scripts/init_db.py --demo-accounts
```

5. Restart backend. Trong pgAdmin: database `smarteye` → Schemas → public → Tables → Refresh. Login web bằng email/mật khẩu SmartEye ở bảng đầu tài liệu.

**Hai loại tài khoản khác nhau:** `POSTGRES_USER`/`POSTGRES_PASSWORD` kết nối server DB; email/mật khẩu trong `users` đăng nhập website. Vai trò Admin trong web không phải PostgreSQL superuser. Bản thật dùng `scripts/init_db.py` không có `--demo-accounts`, rồi `scripts/create_admin.py` để tạo mật khẩu riêng.

Đổi `.env` sang PostgreSQL chỉ đổi nơi lưu từ lần khởi động sau, **không tự chuyển dữ liệu cũ từ SQLite**. Các file SQL mẫu chỉ dành cho database mới; chưa có công cụ chuyển toàn bộ dữ liệu thực.

Nếu đã có Docker Engine, có thể chạy **riêng PostgreSQL** mà chưa build backend/video:

```powershell
# Đặt POSTGRES_PASSWORD trong .env trước.
docker compose -f docker-compose.yml -f deploy/compose.db-local.yml up -d database
```

pgAdmin/local backend dùng host `127.0.0.1`, port `5432`, database/user `smarteye`, password bạn đã đặt. Override chỉ mở cổng trên máy này, dùng cùng volume với Compose đầy đủ. Khi backend chạy bên trong Docker, host là `database`; Compose đã cấu hình sẵn. Mật khẩu được ghép bằng URL.create, không yêu cầu bỏ ký tự đặc biệt. Cổng 5432 cần trống.

## Import SQL thủ công

- SQLite trống: chạy `schema.sqlite.sql`, sau đó `seed.demo.sqlite.sql` bằng DB Browser/DBeaver.
- PostgreSQL trống: mở Query Tool đúng database, chạy `schema.postgresql.sql`, sau đó `seed.demo.postgresql.sql`. Không chạy script PostgreSQL trong SQLite hoặc ngược lại.
- Chọn **init_db.py hoặc import SQL**; không import schema/seed lần nữa vào DB đã có dữ liệu. Script không chứa `DROP TABLE` hay xóa dữ liệu cũ. Seed PostgreSQL chỉnh sequence ID sau insert để tài khoản mới không trùng ID.
- Các file SQL được sinh từ đúng metadata SQLAlchemy; tái tạo bằng `python scripts/build_demo_database.py`. Builder tạo DB sạch riêng, không dump DB hiện có hoặc đọc secrets Admin để đưa vào mẫu.

## 11 bảng và nhiệm vụ

| Bảng | Dữ liệu chính | Quan hệ |
|---|---|---|
| `users` | Email, tên, password hash, role, trạng thái | Gốc tài khoản |
| `sessions` | Hash token đăng nhập, hạn sử dụng | `user_id → users` |
| `reset_tokens` | Hash token reset, hạn sử dụng | `user_id → users` |
| `segments` | Tên đoạn đường, hai nút, km, geometry, demo/active | Gốc đường |
| `cameras` | Camera, ROI, sức chứa, hai ngưỡng | `segment_id → segments` |
| `video_jobs` | Tệp, trạng thái/tiến độ, cấu hình snapshot, kết quả/sample | `user_id → users`, `camera_id → cameras` |
| `observations` | Mật độ/score/số xe, nguồn, thời điểm, ID job đã công bố | `segment_id → segments`, `camera_id → cameras`, `user_id → users` |
| `favorites` | Tên hành trình và input tìm tuyến JSON | `user_id → users` |
| `alert_rules` | Đường/mức cần theo dõi, trạng thái, lần gửi cuối | `user_id → users`, `segment_id → segments` |
| `notifications` | Nội dung, trạng thái đọc, thời điểm | `user_id → users` |
| `audit` | Người thao tác, hành động, chi tiết, thời điểm | `user_id → users` |

`observations.job_id` unique để một video công bố một lần, nhưng cố ý không có foreign key tới `video_jobs` để xóa kết quả video vẫn giữ nguồn gốc observation. Các cột JSON là geometry, ROI, camera_config, result và request. Raw video/ảnh nằm ngoài DB tại storage, không nhét BLOB vào bảng. Xem chi tiết cột/kiểu/NOT NULL/index trong hai file schema.

Ví dụ truy vấn xem tài khoản mà không lấy password hash:

```sql
SELECT id, email, name, role, active FROM users ORDER BY id;
```

## Kiểm tra và giới hạn

SQLite mẫu và SQL restore có kiểm tra integrity, foreign key, đủ bảng, số fixture và khả năng login/phân quyền. PostgreSQL có bài kiểm thử riêng trong CI với server PostgreSQL, bao gồm restore SQL, sequence và JSON. Kết quả kiểm thử trên máy/CI được ghi theo lần chạy; không suy luận đã chạy PostgreSQL chỉ vì sinh được file SQL.
