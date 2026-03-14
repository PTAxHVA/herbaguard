# HerbGuard - Trợ Lý AI Tra Cứu Tương Tác Thuốc & Thảo Dược

Dự án này là một hệ thống AI thông minh kết hợp Mô hình Ngôn ngữ Lớn (LLM - Gemini) với Knowledge Graph (Đồ thị tri thức) để xác định và cảnh báo các tương tác nguy hiểm giữa thuốc tây và thảo dược.

## 🚀 Tính Năng Chính

*   **Tra cứu tương tác**: Kiểm tra xem thuốc tây (ví dụ: Warfarin) có tương tác với thảo dược (ví dụ: Nhân sâm) hay không.
*   **Knowledge Graph**: Sử dụng cấu trúc đồ thị để tìm kiếm thực thể nhanh chóng và chính xác.
*   **AI Agent thông minh**: Hiểu ngôn ngữ tự nhiên tiếng Việt, nhớ ngữ cảnh hội thoại (ví dụ: "thuốc đó" là thuốc gì).
*   **Trực quan hóa**: Vẽ biểu đồ mạng lưới tương tác để người dùng dễ quan sát.

## 📂 Cấu Trúc Dự Án

*   **`agent_graph/`**: Chứa logic của Agent thế hệ mới sử dụng Knowledge Graph.
    *   `graph_agent.py`: File chạy chính của chatbot.
    *   `knowledge_graph.py`: Xây dựng đồ thị từ dữ liệu JSON.
    *   `visualize_graph.py`: Tạo file HTML để xem đồ thị.
*   **`database/`**: Chứa dữ liệu thô.
    *   `data.json`: Dữ liệu thảo dược.
    *   `data_drug.json`: Dữ liệu thuốc tây.
    *   `interaction.json`: Dữ liệu tương tác.

## 🛠️ Cài Đặt

### 1. Yêu cầu
*   Python 3.10+
*   Google Gemini API Key (Lấy tại [Google AI Studio](https://aistudio.google.com/))

### 2. Cài đặt thư viện
Mở terminal tại thư mục dự án và chạy:
```bash
pip install "pydantic-ai[google]" python-dotenv duckduckgo-search redis networkx pyvis trafilatura
```

### 3. Cấu hình biến môi trường
Tạo file `.env` tại thư mục này và dán API Key vào:
```env
GOOGLE_API_KEY=your_actual_api_key_here
```

## ▶️ Hướng Dẫn Chạy

### Cách 1: Chạy Chatbot AI (Graph Agent) - Khuyên Dùng
Đây là cách sử dụng chính để chat với AI.
```bash
python agent_graph/graph_agent.py
```

### Cách 2: Xem Biểu Đồ Tương Tác (Visualization)
Để tạo file HTML hiển thị mạng lưới thuốc và thảo dược:
```bash
python agent_graph/visualize_graph.py
```
Sau khi chạy, mở file `agent_graph/herb_drug_network.html` bằng trình duyệt web.


## 📝 Lưu ý
*   Hệ thống sử dụng DuckDuckGo để tra cứu thông tin thuốc mới nếu không có trong database.
*   Database nằm trong thư mục `database/`. Nếu bạn thêm thuốc/thảo dược mới, hãy cập nhật các file JSON tại đó.
