# HerbaGuard AI (Demo-Ready, Local-First)

Nếu bạn là người mới hoàn toàn và muốn chạy nhanh trên Google Chrome:
- Xem tài liệu từng bước: [README_BEGINNER_CHROME_VI.md](README_BEGINNER_CHROME_VI.md)

HerbaGuard AI là ứng dụng web tiếng Việt hỗ trợ:
- kiểm tra tương tác **thuốc tây + thảo dược** từ dữ liệu local
- giải thích kết quả dựa trên bằng chứng trong `database/*.json`
- chatbot grounded theo phong cách graph-agent:
  - Gemini làm lớp hội thoại/tổng hợp câu trả lời khi có API key
  - Graph + dữ liệu local là nguồn sự thật
  - fallback local khi không có Gemini
- quản lý tủ thuốc và lịch nhắc uống
- cài đặt trải nghiệm (giọng đọc, cỡ chữ lớn, theme, notification)

Core flow vẫn chạy **offline/local**. Gemini là lớp tăng cường hội thoại tùy chọn.

## 1. Tính năng đã hoàn thiện

- FastAPI backend + static frontend (HTML/CSS/vanilla JS) cùng một app.
- Đăng ký/đăng nhập/đăng xuất bằng SQLite local.
- Check tương tác end-to-end:
  - nhập >= 2 mục (thuốc tây hoặc thảo dược)
  - autocomplete từ `/api/search`
  - resolve tiếng Việt (lowercase, Unicode normalize, bỏ dấu, alias, partial)
  - trả kết quả động trên `result.html` (không hardcode)
- Severity heuristic deterministic (`high`/`medium`) + mapping UI (`danger`/`warning`/`safe`).
- Chatbot grounded:
  - endpoint `/api/chat`
  - memory backend theo `user_id + session_id` (SQLite)
  - endpoint history: `GET/DELETE /api/chat/history`
  - graph-agent style tools: `greet_user`, `identify_medical_entities_via_graph`, `check_interaction_pair_via_graph`, `search_drug_info`
  - Gemini orchestration khi có `GOOGLE_API_KEY`
  - trả lời tiếng Việt dựa trên bằng chứng graph/data
  - trả `grounding` + `citations` + `orchestrator`
  - fallback trung thực khi thiếu dữ liệu
- Tủ thuốc và lịch nhắc có CRUD thật (SQLite):
  - medicines CRUD
  - reminders CRUD
- Dashboard trang chủ nối dữ liệu thật:
  - alerts
  - upcoming reminders
  - recent check history
- Settings có tác dụng thật và lưu backend.
- Nút chia sẻ / xuất PDF / hỏi chatbot từ trang kết quả hoạt động thật.
- Không còn fake loading redirect hoặc result hardcoded.

## 2. Kiến trúc chính

```text
.
├── app.py
├── models.py
├── requirements.txt
├── services/
│   ├── auth_service.py
│   ├── chat_memory_service.py
│   ├── chat_service.py
│   ├── data_loader.py
│   ├── gemini_service.py
│   ├── graph_service.py
│   ├── interaction_service.py
│   ├── normalize.py
│   ├── resolver.py
│   └── user_data_service.py
├── database/
│   ├── herb.json
│   ├── drug.json
│   └── interaction.json
├── tests/
│   ├── test_chat_memory_api.py
│   └── test_core_logic.py
└── [herbaguard] app/
    ├── index.html / index.js
    ├── check.html / check.js
    ├── result.html / result.js
    ├── medicines.html / medicines.js
    ├── settings.html / settings.js
    ├── chat.html / chat.js
    ├── login.html / register.html / auth.js
    └── styles.css (+ page css)
```

## 3. Cài đặt và chạy local

Yêu cầu: Python 3.10+

```bash
cd /path/to/herbaguard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
uvicorn app:app --reload
```

Tùy chọn (để đổi file SQLite khi test):

```bash
HERBAGUARD_DB_PATH=/tmp/herbaguard_demo.db uvicorn app:app --reload
```

Tùy chọn bật Gemini orchestration:

```bash
export GOOGLE_API_KEY="your_google_api_key"
export GEMINI_MODEL="gemini-2.5-flash"
uvicorn app:app --reload
```

Mở trình duyệt:
- `http://127.0.0.1:8000`

Luồng vào app:
1. Vào `login.html`/`register.html` (được guard tự động).
2. Đăng ký tài khoản local.
3. Dùng toàn bộ chức năng demo.

## 4. Demo scenarios (đã verify với dữ liệu local)

- `warfarin` + `nhân sâm`
- `warfarin` + `bạch quả`
- `aspirin` + `nghệ`
- `aspirin` + `gừng`
- `metformin` + `nhân sâm`

Ví dụ no-match:
- `warfarin` + `bạc hà`

## 5. API chính

### `GET /api/health`

```json
{
  "status": "ok",
  "service": "HerbaGuard API"
}
```

### `GET /api/search?q=warfarin`

Trả gợi ý từ cả drug + herb.

### `POST /api/check-interaction`

Request:

```json
{
  "items": ["warfarin", "nhân sâm"]
}
```

Response gồm:
- `resolved_items`
- `interaction_pairs`
- `summary`
- `unresolved_items`

### `POST /api/chat`

Request:

```json
{
  "session_id": "demo-session-01",
  "message": "Nhân sâm có tương tác với warfarin không?",
  "history": []
}
```

Response gồm:
- `answer`
- `session_id`
- `used_memory`
- `orchestrator` (`gemini` hoặc `local`)
- `grounding.entities`
- `grounding.interactions`
- `grounding.evidence`
- `citations`
- `fallback`

### `GET /api/chat/history?session_id=...`

Trả lịch sử hội thoại đã lưu ở backend cho đúng phiên chat.

### `DELETE /api/chat/history?session_id=...`

Xóa lịch sử hội thoại của phiên chat đó.

### Auth / User data

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `GET/PUT /api/settings`
- `GET /api/dashboard`
- `GET/POST/PUT/DELETE /api/medicines`
- `GET/POST/PUT/DELETE /api/reminders`
- `GET /api/check-history`

## 6. Cách chatbot grounded hoạt động

- Dữ liệu nguồn: `database/herb.json`, `database/drug.json`, `database/interaction.json`.
- `KnowledgeGraphService` dựng lớp graph in-memory:
  - node: herb/drug entities
  - alias index
  - edge: interaction pair (drug_id, herb_id)
  - graph query methods: resolve/search/check pair/evidence/related entities
- `ChatService`:
  - lấy ngữ cảnh hội thoại từ `ChatMemoryService` (SQLite)
  - dùng graph-agent-style tools (greeting/entity lookup/interaction lookup/entity info)
  - build grounded prompt từ graph evidence + memory
  - gọi `GeminiService` để tổng hợp câu trả lời tiếng Việt khi có key
  - fallback sang local grounded response khi key thiếu/lỗi
  - đính kèm grounding + citations
  - fallback trung thực khi thiếu bằng chứng

## 7. Kiểm thử

Chạy test backend core:

```bash
python3 -m unittest discover -s tests -v
```

Nội dung test:
- normalization
- dedup inputs
- graph resolver + graph tool methods
- interaction matching + severity
- chat grounded + follow-up + fallback
- session memory history APIs
- behavior when Gemini key is absent

## 8. Kịch bản demo 3-5 phút

1. Đăng ký tài khoản mới.
2. Vào **Kiểm Tra Tương Tác**, nhập `warfarin` + `bạch quả`, chạy check.
3. Ở trang kết quả:
   - đọc banner severity
   - xem cơ chế/hậu quả/khuyến nghị
   - bấm **Chia sẻ** hoặc **Xuất PDF**
4. Bấm **Hỏi Trợ Lý AI** từ kết quả, hỏi thêm: “Tại sao nguy hiểm?”
5. Vào **Tủ Thuốc**:
   - thêm một thuốc mới
   - tạo lịch nhắc
   - sửa/xóa nhanh một bản ghi
6. Vào **Cài Đặt**:
   - bật cỡ chữ lớn / đổi theme / test giọng đọc

## 9. Giới hạn hiện tại

- Notification trình duyệt phụ thuộc quyền của browser.
- Xuất PDF dùng print-friendly flow (`window.print` -> Save as PDF).
- Dữ liệu y khoa chỉ giới hạn trong bộ JSON local hiện có.
- Nếu không có `GOOGLE_API_KEY`, chat dùng local grounded mode (vẫn an toàn và có bằng chứng).

## 10. Ghi chú dữ liệu

- Flow chính dùng **`database/*.json`** làm source of truth.
- `data.json` và `data_drug.json` là file prototype cũ, không dùng cho core demo.
