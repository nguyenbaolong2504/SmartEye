# Chạy SmartEye trên Windows với MongoDB

Tất cả lệnh dùng **PowerShell** trong `C:\Users\Admin\Documents\GitHub\SmartEye`. Chỉ copy lệnh trong khối code, không copy dấu nhắc `PS C:\...>`. Chọn local (mục 1–5), Docker đầy đủ (mục 6), hoặc Docker chỉ DB (mục 7).

Compass là phần mềm quản lý DB, không khởi chạy MongoDB Server. Kết nối đã lưu trong Compass không có nghĩa server đang hoạt động.

## 1. Chuẩn bị môi trường

Yêu cầu Windows x64, Python 3.11, Node.js 22+, mạng và đủ dung lượng tải dependency/model.

```powershell
cd C:\Users\Admin\Documents\GitHub\SmartEye
python --version
node --version
npm --version
if (!(Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install --no-cache-dir -r backend/requirements-db.txt
.venv\Scripts\python.exe scripts/setup_env.py --mode local
```

Nếu Python mặc định không phải 3.11, tạo venv bằng `py -3.11 -m venv .venv`. Không cần Activate.ps1; gọi Python trong `.venv` tránh lỗi execution policy.

`setup_env.py` sao lưu `.env` vào `.env.backup-...`, giữ Google/SMTP key, bỏ cấu hình SQL cũ và đặt MongoDB localhost không auth. Nếu dùng Atlas hoặc server có auth, sửa `.env` sau bước này. Không chạy lại `--mode local` sau khi điền Atlas URI.

## 2A. MongoDB local/portable

Kiểm tra server sẵn có:

```powershell
Test-NetConnection 127.0.0.1 -Port 27017
```

Nếu `TcpTestSucceeded=True`, không chạy thêm server cùng cổng; xác minh bằng `check_db.py` ở mục 3. Nếu server yêu cầu auth, để `MONGODB_URI=` trống, điền `MONGODB_USERNAME`, `MONGODB_PASSWORD`, `MONGODB_AUTH_SOURCE` đúng server đó. Đây không phải tài khoản website.

Nếu chưa có server, mở **Terminal MongoDB**:

```powershell
cd C:\Users\Admin\Documents\GitHub\SmartEye
.venv\Scripts\python.exe scripts/download_mongodb.py
New-Item -ItemType Directory -Force backend\data\mongo-local | Out-Null
& .\backend\data\tools\mongodb-8.0.32\mongod.exe --bind_ip 127.0.0.1 --port 27017 --dbpath .\backend\data\mongo-local --wiredTigerCacheSizeGB 0.25
```

Giữ terminal này chạy. `Ctrl+C` dừng an toàn. Sau khi restart máy, chạy lại lệnh `mongod.exe`. Script tải riêng executable khoảng 29 MiB nén từ ZIP chính thức, kiểm tra CRC, không cài service. Executable/data nằm trong `backend/data/`, không commit. Bản này dành cho local: loopback, không auth; không mở cổng Internet.

`.env` local:

```dotenv
MONGODB_URI=mongodb://127.0.0.1:27017/
MONGODB_DB=smarteye
APP_ENV=development
COOKIE_SECURE=false
APP_BASE_URL=http://127.0.0.1:5173
```

Compass → **Add new connection** → `mongodb://127.0.0.1:27017/` → Connect. DB `smarteye` xuất hiện sau khi khởi tạo ở mục 3.

## 2B. Atlas thay cho server local

Đã có Atlas thì không cần chạy MongoDB trên máy. Atlas → **Connect → Drivers → Python**, lấy URI; Database User cần quyền `readWrite` trên `smarteye`, Network Access cho phép IP hiện tại. User đăng nhập trang Atlas và Database User là hai tài khoản khác nhau.

Sửa `.env` trong editor:

```dotenv
MONGODB_URI=mongodb+srv://DB_USER:URL_ENCODED_PASSWORD@YOUR_CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=smarteye
```

Thay placeholder bằng URI thật; URL-encode ký tự đặc biệt trong password. Không gửi password vào chat/Git. Không suy ra được password từ ảnh Compass. Ứng dụng chọn database theo `MONGODB_DB`, độc lập phần tên DB trong URI. Compass dùng cùng URI để xem dữ liệu.

## 3. Tạo collection và tài khoản

Trong terminal khác với MongoDB:

```powershell
cd C:\Users\Admin\Documents\GitHub\SmartEye
.venv\Scripts\python.exe scripts/check_db.py
.venv\Scripts\python.exe scripts/init_db.py --demo-accounts
```

Kỳ vọng ping thành công, 11 collection nghiệp vụ + `counters`, 3 tài khoản, 13 đường và 4 camera. Script chạy lại được, giữ tài khoản cũ. Startup API không tự tạo tài khoản demo. Refresh Compass. Xem [danh sách collection](../database/README.md).

| Vai trò | Email | Mật khẩu demo |
|---|---|---|
| Admin | admin@smarteye.test | SmartEyeAdmin@2026 |
| Analyst | analyst@smarteye.test | SmartEyeAnalyst@2026 |
| User | user@smarteye.test | SmartEyeUser@2026 |

Tạo Admin riêng bằng lệnh dưới (hỏi email/mật khẩu nhập ẩn). Password web lưu scrypt hash, không thể đọc lại từ DB. Demo chỉ dùng thử; script từ chối `--demo-accounts` ở production.

```powershell
.venv\Scripts\python.exe scripts/create_admin.py
```

## 4. Cài backend/frontend và model

Torch CPU/model cần vài trăm MB. `--no-cache-dir` giảm cache pip, không giảm dung lượng thư viện đã cài.

```powershell
.venv\Scripts\python.exe -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install --no-cache-dir -r backend/requirements.txt
npm ci
.venv\Scripts\python.exe scripts/download_model.py
.venv\Scripts\python.exe -m pip check
```

`requirements-db.txt` chỉ phục vụ DB; cần `requirements.txt` để chạy API/video. Model tải một lần vào `backend/data/models/yolo11n.pt`.

## 5. Chạy backend và frontend

**Terminal Backend** (giữ chạy):

```powershell
cd C:\Users\Admin\Documents\GitHub\SmartEye
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

**Terminal Frontend** (giữ chạy):

```powershell
cd C:\Users\Admin\Documents\GitHub\SmartEye
npm run dev
```

**Terminal Kiểm tra**:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Start-Process http://127.0.0.1:5173
```

Kỳ vọng health `status=ok`, `database=mongodb`. Website: [127.0.0.1:5173](http://127.0.0.1:5173). Swagger: [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). Dùng `127.0.0.1` nhất quán với APP_BASE_URL để cookie/Origin đúng. Vite proxy `/api`; browser không gọi DB trực tiếp.

Đăng nhập → tìm tuyến chế độ minh họa → tải video → đợi xử lý → xem mật độ. Admin cấu hình camera/đường, Analyst/Admin công bố clip mới. Không cần Google/SMTP key cho demo.

Những lần sau chỉ khởi động MongoDB (nếu portable), backend và frontend; không cài/seed/tải model lại.

## 6. Docker đầy đủ: DB + backend + frontend

Yêu cầu Docker Desktop Linux containers/WSL2, Engine Running. Không cần Node/Torch trên host; script cấu hình dùng Python + python-dotenv nhỏ.

```powershell
cd C:\Users\Admin\Documents\GitHub\SmartEye
docker version
docker info
if (!(Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
.venv\Scripts\python.exe -m pip install --no-cache-dir python-dotenv
.venv\Scripts\python.exe scripts/setup_env.py --mode docker
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 240
docker compose exec backend python scripts/init_db.py --demo-accounts
docker compose exec backend python scripts/download_model.py
docker compose ps
Invoke-RestMethod http://localhost:8080/api/health
Start-Process http://localhost:8080
```

Build đầu tải image/Torch nên có thể lâu. Nếu `--wait` hết thời gian, xem log và chờ dịch vụ khỏe trước các lệnh exec. Setup tạo password ngẫu nhiên, giữ key cũ và sao lưu `.env`; không in password. Không chạy backend local cùng cổng 8000 với Docker.

| Thành phần | Địa chỉ trên máy |
|---|---|
| Frontend + API qua Nginx | `http://localhost:8080` |
| Backend/Swagger | `http://localhost:8000/docs` |
| MongoDB từ Compass | `127.0.0.1:27018` |
| MongoDB từ backend container | `mongo:27017` (Compose tự cấu hình) |

Compass → Add new connection → URI `mongodb://127.0.0.1:27018/` → Advanced connection options → Authentication → Username/Password theo `MONGODB_USERNAME`/`MONGODB_PASSWORD` trong `.env`; Authentication Database theo `MONGODB_DB` (mặc định `smarteye`). App user mặc định `smarteye_app`, quyền readWrite; root chỉ dùng init/quản trị/healthcheck.

MongoDB lưu volume `mongo_data`; model/ảnh ở bind mount `backend/data`. Thay password trong `.env` khi volume đã khởi tạo **không tự đổi password user trong MongoDB**. Phải đổi qua quản trị DB rồi cập nhật `.env` tương ứng. Setup giữ password đang có.

```powershell
docker compose logs --tail 80 mongo backend frontend
docker compose stop
docker compose up -d --wait
```

`stop`/`down` giữ volume; không thêm `-v` nếu cần dữ liệu. Deploy thật dùng Admin/secret riêng, HTTPS, `APP_ENV=production`, `COOKIE_SECURE=true`, `APP_BASE_URL` đúng origin; hiện một backend worker.

## 7. Docker chỉ DB, backend/frontend trên Windows

Sau mục 1:

```powershell
.venv\Scripts\python.exe scripts/setup_env.py --mode db-docker
docker compose up -d --wait mongo
.venv\Scripts\python.exe scripts/check_db.py
.venv\Scripts\python.exe scripts/init_db.py --demo-accounts
```

Tiếp tục mục 4–5. Host backend/Compass dùng cổng 27018 và auth DB `smarteye`; script đã ghép credentials đúng. Không chạy lại `--mode local` vì sẽ về cổng 27017/no-auth. Không bật container backend cùng backend local trên cổng 8000.

## 8. Xử lý lỗi

| Lỗi | Kiểm tra/cách xử lý |
|---|---|
| Thiếu fastapi/pymongo/cv2 | Dùng đúng `.venv\Scripts\python.exe`; cài `backend/requirements.txt`. |
| Mongo timeout/refused | Server có chạy không? Compass chỉ là GUI. Chạy check_db.py; cổng local 27017, host Docker 27018, container 27017. |
| Authentication failed | Kiểm tra DB user/password/authSource; khác email/password web. Giá trị mới trong `.env` không đổi user của volume cũ. |
| Atlas timeout | Network Access/IP, Database User, DNS/mạng, URI đã thay placeholder/encode password. |
| API không startup | Xem log; API cố ý dừng khi MongoDB không kết nối được, không tự đổi DB. |
| Không login được | Đúng origin trong hướng dẫn, COOKIE_SECURE=false khi HTTP; restart backend sau sửa env. |
| Video thiếu model | Tải bằng đúng môi trường local/container; kiểm tra YOLO_MODEL_PATH. |
| Port đã dùng | Dừng phiên cũ Ctrl+C hoặc docker compose stop; tránh local/Docker cùng cổng 8000. |
| No space left | Giải phóng ổ chứa venv/Docker/data trước khi cài tiếp. |
| Docker Cannot connect | `docker info` phải có Server; mở Desktop và chờ Engine Running. |

Máy kiểm thử gặp lỗi Docker Desktop `Access is denied` / `The file cannot be accessed by the system` ở socket `Docker/run/dockerInference`, sau đó `docker-secrets-engine/engine.sock`. Đây là lỗi khởi động Docker trước khi project chạy. Khởi động lại Windows/Desktop, kiểm tra docker info; nếu còn lỗi xem [Docker Desktop #448](https://github.com/docker/desktop-feedback/issues/448) và [#531](https://github.com/docker/desktop-feedback/issues/531). Chưa xác minh build/run Compose trên máy này; không factory reset/xóa volume để thử. Dùng portable hoặc Atlas trong lúc xử lý Docker.

## 9. Kiểm thử (tùy chọn)

```powershell
.venv\Scripts\python.exe -m pip install --no-cache-dir -r backend/requirements-dev.txt
.venv\Scripts\python.exe -m pytest
npm run build
npx playwright install chromium
npm run test:e2e
```

Pytest mặc định mongomock; kiểm tra validator với server test local không auth:

```powershell
$env:SMARTEYE_TEST_MONGODB_URI='mongodb://127.0.0.1:27017/'
.venv\Scripts\python.exe -m pytest
Remove-Item Env:SMARTEYE_TEST_MONGODB_URI
```

Live tests tự tạo/xóa DB `smarteye_test_<uuid>` riêng, cần user test cho phép tạo/xóa DB này. User Docker readWrite riêng `smarteye` không có quyền đó. E2E dùng `smarteye_e2e`, API 8011/frontend 5174, cần MongoDB thật/model và quyền DB test. Local không auth dùng được ngay; Atlas/app user giới hạn DB cần quyền test riêng. Không test trên dữ liệu triển khai.

Nguồn: [MongoDB Windows ZIP](https://www.mongodb.com/docs/v8.0/tutorial/install-mongodb-on-windows-zip/), [Compass connections](https://www.mongodb.com/docs/compass/current/connect/), [Docker Official Image Mongo](https://hub.docker.com/_/mongo).
