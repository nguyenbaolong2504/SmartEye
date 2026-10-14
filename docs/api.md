# API

Swagger `/docs` trên backend. Cookie cùng origin, không lưu token trong localStorage.

| Nhóm | Endpoint | Quyền |
|---|---|---|
| Public | `GET /api/health`, `/config`, `/places`, `/segments`, `/cameras` | Public |
| Auth | `POST /api/auth/register`, `/login`, `/logout` | Public/cookie |
| Profile | `GET /api/auth/me`, `PATCH /api/auth/profile`, `POST /api/auth/password` | Own |
| Reset | `POST /api/auth/forgot-password`, `/reset-password` | Public/token |
| Route | `POST /api/routes/search` | Public, 20/min/IP |
| Upload | `POST /api/videos` multipart file/camera_id/observed_at? | User |
| Jobs/frames | `GET /api/videos`, `/{id}`, `/{id}/frames/{second}` | Own/Admin |
| Cancel/delete | `POST /api/videos/{id}/cancel`, `DELETE /api/videos/{id}` | Own/Admin |
| Publish | `POST /api/videos/{id}/publish` | Own Analyst/Admin |
| Observation | `POST /api/observations` | Analyst/Admin |
| Favorites | `GET/POST /api/favorites`, `DELETE /api/favorites/{id}` | Own |
| Alerts | `GET/POST /api/alerts`, `DELETE /api/alerts/{id}` | Own |
| Notices | `POST /api/notifications/{id}/read` | Own |
| Reports | `GET /api/reports`, `/api/reports/export` | Analyst/Admin |
| Cameras | `POST /api/cameras`, `PUT/DELETE /api/cameras/{id}` | Admin |
| Segments | `POST /api/segments`, `PUT/DELETE /api/segments/{id}` | Admin |
| Users | `GET /api/admin/users?q=`, `PATCH /api/admin/users/{id}`, `POST /api/admin/users/{id}/revoke` | Admin |
| System/audit | `GET /api/admin/system` | Admin |

Reports: `segment_id`, `start`, `end` ISO timestamp có timezone. Server UTC, UI giờ Việt Nam. Favorite chỉ input, không polyline/ETA. Job UUID; ảnh giây 0/10/20/…

```json
{"origin":{"lat":21.0287,"lng":105.8524,"node":"hoankiem","name":"Hồ Hoàn Kiếm"},"destination":{"lat":21.0333,"lng":105.7984,"node":"caugiay","name":"Cầu Giấy"},"provider":"demo","mode":"DRIVE","departure_at":null,"weights":{"time":0.45,"distance":0.2,"density":0.35}}
```

Client xử lý 401/403/404/409/413/415/422/429/502/503/504. `detail` có thể chuỗi hoặc validation list. Lỗi file/Google không trả key/traceback. Không bật permissive CORS.
