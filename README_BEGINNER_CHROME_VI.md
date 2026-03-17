# HerbaGuard AI - Hướng Dẫn Chạy Trên Google Chrome

Tài liệu này dành cho người chưa biết lập trình hoặc chưa từng chạy project Python.

Mục tiêu: chạy được HerbaGuard trên máy của bạn và mở bằng Google Chrome.

---

## 1. Bạn cần chuẩn bị gì?

1. Một máy tính có internet.
2. Đã cài **Google Chrome**.
3. Đã cài **Python 3.10+**.

Kiểm tra Python:

```bash
python3 --version
```

Nếu hiện phiên bản kiểu `Python 3.10`, `3.11`, `3.12`, `3.13` là OK.

---

## 2. Mở đúng thư mục project

Giả sử project nằm ở:

`/Users/pta/Documents/CS/HNKH-KHTN/herbaguard`

Mở Terminal và chạy:

```bash
cd /Users/pta/Documents/CS/HNKH-KHTN/herbaguard
```

Kiểm tra bạn đang đứng đúng chỗ:

```bash
pwd
ls
```

Bạn phải thấy các file như `app.py`, `requirements.txt`, thư mục `[herbaguard] app`.

---

## 3. Cài môi trường chạy (chỉ cần làm lần đầu)

### Bước 1: tạo môi trường ảo

```bash
python3 -m venv .venv
```

### Bước 2: bật môi trường ảo

```bash
source .venv/bin/activate
```

Khi bật thành công, đầu dòng lệnh sẽ có `(.venv)`.

### Bước 3: cài thư viện

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## 4. Chạy backend HerbaGuard

### Cách an toàn (tránh đụng cổng 8000)

```bash
uvicorn app:app --host 127.0.0.1 --port 8010 --reload
```

Nếu chạy thành công, bạn sẽ thấy dòng gần giống:

`Uvicorn running on http://127.0.0.1:8010`

Giữ nguyên cửa sổ Terminal này, **không đóng**.

---

## 5. Mở bằng Google Chrome

Mở Chrome và truy cập:

`http://127.0.0.1:8010/login.html`

Bạn sẽ vào trang đăng nhập/đăng ký của HerbaGuard.

### Luồng dùng thử nhanh

1. Đăng ký tài khoản mới.
2. Đăng nhập.
3. Vào trang kiểm tra tương tác.
4. Nhập ví dụ:
   - `warfarin` + `nhân sâm`
   - `warfarin` + `bạch quả`
5. Bấm kiểm tra để xem kết quả thật từ dữ liệu local.
6. Vào trang chat để hỏi tiếp.

---

## 6. Nếu bị lỗi “This site can’t be reached”

Lỗi thường gặp: `ERR_CONNECTION_REFUSED`

Lý do: server chưa chạy hoặc chạy sai cổng.

### Cách xử lý

1. Quay lại Terminal xem có đang chạy `uvicorn` không.
2. Nếu không có, chạy lại lệnh ở mục 4.
3. Đảm bảo URL đúng cổng:
   - Nếu bạn chạy `--port 8010` thì URL phải là `127.0.0.1:8010`
4. Đừng mở chỉ `127.0.0.1` nếu bạn không chạy cổng mặc định.

---

## 7. Nếu báo “Address already in use”

Nghĩa là cổng đó đang bị app khác dùng.

Bạn đổi sang cổng khác, ví dụ 8020:

```bash
uvicorn app:app --host 127.0.0.1 --port 8020 --reload
```

Rồi mở:

`http://127.0.0.1:8020/login.html`

---

## 8. Tắt server khi dùng xong

Quay lại Terminal đang chạy `uvicorn` và nhấn:

`Ctrl + C`

---

## 9. Chạy lại lần sau (nhanh)

Mỗi lần mở lại project, bạn chỉ cần:

```bash
cd /Users/pta/Documents/CS/HNKH-KHTN/herbaguard
source .venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8010 --reload
```

Mở Chrome:

`http://127.0.0.1:8010/login.html`

---

## 10. (Tùy chọn) Bật Gemini cho chat

Core app vẫn chạy tốt khi không có Gemini key.

Nếu bạn có key:

```bash
export GOOGLE_API_KEY="your_google_api_key"
export GEMINI_MODEL="gemini-2.5-flash"
uvicorn app:app --host 127.0.0.1 --port 8010 --reload
```

---

## 11. Kiểm tra backend có sống hay không

Mở trình duyệt:

`http://127.0.0.1:8010/api/health`

Nếu thấy JSON kiểu:

```json
{"status":"ok","service":"HerbaGuard API"}
```

là backend đang chạy tốt.
