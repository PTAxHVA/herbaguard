# HerbaGuard AI

HerbaGuard AI là ứng dụng web tiếng Việt để kiểm tra tương tác **thuốc tây + thảo dược** từ dữ liệu local (`database/*.json`) với giao diện HTML/CSS/JS tĩnh và backend FastAPI.

## 1. Kiến trúc hiện tại

- Backend: FastAPI (`app.py`)
- Frontend static: `frontend/` (được serve trực tiếp bởi FastAPI)
- Persistence runtime: **MongoDB** (Atlas compatible)
- AI chat orchestration: Gemini (tùy chọn), fallback local grounded luôn hoạt động
- Source of truth y khoa: `database/herb.json`, `database/drug.json`, `database/interaction.json`

### Mongo collections runtime

- `users`
- `sessions`
- `medicines`
- `reminders`
- `user_settings`
- `check_history`
- `chat_messages`

## 2. Tính năng

- Auth: `register / login / me / logout`
- Settings: `GET/PUT /api/settings`
- Dashboard: `GET /api/dashboard`
- Medicines CRUD
- Reminders CRUD
- Check history
- Interaction check + search/autocomplete
- Chat memory/history theo `user + session`
- Frontend static hoạt động end-to-end với backend API

## 3. Cấu trúc thư mục chính

```text
.
├── app.py
├── config.py
├── models.py
├── requirements.txt
├── render.yaml
├── .env.example
├── database/
│   ├── __init__.py
│   ├── mongo.py
│   ├── herb.json
│   ├── drug.json
│   └── interaction.json
├── services/
│   ├── auth_service.py
│   ├── chat_memory_service.py
│   ├── chat_service.py
│   ├── user_data_service.py
│   ├── mongo_helpers.py
│   └── ...
├── frontend/
│   ├── index.html
│   ├── medicines.html
│   ├── chat.html
│   └── ...
├── scripts/
│   └── migrate_sqlite_to_mongo.py
└── tests/
```

## 4. Environment variables

Copy `.env.example` thành `.env` (hoặc set trực tiếp trên shell/Render):

- `MONGODB_URI` (required)
- `MONGODB_DB_NAME` (required)
- `GOOGLE_API_KEY` (optional)
- `GEMINI_MODEL` (optional, default `gemini-2.5-flash`)
- `GEMINI_TIMEOUT_SECONDS` (optional)
- `MONGODB_USE_MOCK` (optional, cho test/local mock)
- `HERBAGUARD_STATIC_DIR` (optional, default `frontend`)

## 5. Chạy local

Yêu cầu: Python 3.10+

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Cách 1: dùng MongoDB Atlas (khuyến nghị)

```bash
export MONGODB_URI="mongodb+srv://<user>:<pass>@<cluster>/?retryWrites=true&w=majority"
export MONGODB_DB_NAME="herbaguard"
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### Cách 2: dùng MongoDB local

```bash
export MONGODB_URI="mongodb://127.0.0.1:27017"
export MONGODB_DB_NAME="herbaguard"
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Truy cập: `http://127.0.0.1:8000`

## 6. Setup MongoDB Atlas Free Tier (nhanh)

1. Tạo project + cluster M0 trên Atlas.
2. Tạo DB user/password.
3. Network Access: thêm IP của bạn (hoặc `0.0.0.0/0` cho demo).
4. Lấy connection string `mongodb+srv://...`.
5. Set `MONGODB_URI` và `MONGODB_DB_NAME`.

## 7. Deploy Render Free + Atlas Free

Repo đã có `render.yaml` với:

- Build: `pip install -r requirements.txt`
- Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`

### Cách deploy

1. Push repo lên GitHub.
2. Trên Render: New + Blueprint (hoặc New Web Service).
3. Chọn repo.
4. Set env vars:
   - `MONGODB_URI`
   - `MONGODB_DB_NAME`
   - `GOOGLE_API_KEY` (optional)
   - `GEMINI_MODEL` (optional)
5. Deploy.
6. Health check: `GET /api/health`.

## 8. Migration từ SQLite cũ sang MongoDB

Runtime mới **không dùng SQLite**. Nếu bạn có dữ liệu cũ trong `herbaguard_auth.db`, chạy script migration một lần:

```bash
python scripts/migrate_sqlite_to_mongo.py \
  --sqlite-path ./herbaguard_auth.db \
  --mongodb-uri "$MONGODB_URI" \
  --mongodb-db-name "$MONGODB_DB_NAME"
```

Script sẽ migrate các bảng cũ:

- `users`
- `sessions`
- `medicines`
- `reminders`
- `user_settings`
- `check_history`
- `chat_messages`

Script được thiết kế để chạy lại an toàn (upsert theo khóa migration).

## 9. Chạy test

Test không cần Atlas thật; dùng `mongomock`.

```bash
python -m unittest discover -s tests -v
```

## 10. API chính

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `GET/PUT /api/settings`
- `GET /api/dashboard`
- `GET/POST/PUT/DELETE /api/medicines`
- `GET/POST/PUT/DELETE /api/reminders`
- `GET /api/check-history`
- `GET /api/search`
- `POST /api/check-interaction`
- `POST /api/chat`
- `GET/DELETE /api/chat/history`

## 11. Ghi chú

- Chat luôn grounded vào dữ liệu local; Gemini chỉ là lớp tổng hợp câu trả lời khi có API key.
- Frontend đã tương thích ID dạng string của MongoDB.
- Dữ liệu persistent trên cloud cần MongoDB (Atlas/instance Mongo), không dựa vào local disk.
