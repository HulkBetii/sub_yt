# Guidelines & Development Rules for AI Agents and Engineers

Tài liệu này định nghĩa các nguyên tắc phát triển bắt buộc khi làm việc trên codebase `buff-sub-yt`.

---

## 1. Giao tiếp & Ngôn ngữ (Language & Encoding)
- **Chuẩn mã hóa UTF-8:** Bắt buộc sử dụng UTF-8 (No BOM) cho toàn bộ file `.py`, `.json`, `.sql`, `.md`, `.tsx`. Mọi hàm mở file trong Python phải có `encoding="utf-8"`.
- **Ngôn ngữ trong mã nguồn:** Toàn bộ tên biến, tên hàm, class, schema column, docstring và inline code comment **bắt buộc dùng tiếng Anh**.
- **Ngôn ngữ trao đổi:** Giải thích kỹ thuật và phản hồi người dùng bằng **tiếng Việt chuẩn mực, mạch lạc, trực diện, không xu nịnh sáo rỗng**.

---

## 2. Nguyên tắc Tự động hóa Trình duyệt (Browser Automation & Anti-Detect)
- **Cấm tuyệt đối tương tác thô:**
  - Không bao giờ gọi `element.click()` hoặc JavaScript click trực tiếp trên các nút quan trọng như Subscribe, Like, trừ khi đó là trường hợp fallback khẩn cấp.
  - Luôn sử dụng giải thuật di chuyển chuột giả lập người thật (`HumanCursor` / Bézier curve) thông qua Selenium CDP.
- **Xử lý YouTube Shadow DOM (Polymer Elements):**
  - Giao diện YouTube liên tục thay đổi giữa các phiên bản. Mọi selector tương tác trên YouTube phải viết dưới dạng fallback chain (danh sách ưu tiên nhiều selector) hoặc có fallback script truy vấn xuyên qua `shadowRoot`.
  - Luôn kiểm tra `element.is_displayed()` và `element.is_enabled()` trước khi thao tác.
- **Quản lý Vòng đời Trình duyệt (Resource Hygiene):**
  - Sau khi hoàn thành một session sub hoặc khi gặp exception ngoài ý muốn, bắt buộc phải giải phóng lock tài nguyên trong `account_locks` và đóng profile GPM thông qua `safe_quit()` hoặc API `/api/v3/profiles/close/{id}`.
  - Tuyệt đối không để xảy ra hiện tượng "Orphan Chromium Process" làm tràn RAM (32GB trên máy này chịu được tối đa 5-8 instances, nhưng giới hạn an toàn là 2 instances song song).

---

## 3. Quản lý Cơ sở dữ liệu & Tính nhất quán (State Management)
- **Single Source of Truth:**
  - Danh mục 500 tài khoản nằm tại `D:\VibeCoding\shared\account_pool.db`.
  - Thông tin đơn hàng và nhật ký thực thi nằm tại `D:\VibeCoding\buff-sub-yt\data\buff_sub.db`.
- **Khóa tránh xung đột (Locking):**
  - Mọi thao tác lấy tài khoản để nuôi hoặc để sub bắt buộc phải acquire lock với hạn timeout cụ thể.
  - Không được xóa trực tiếp dòng khóa của process khác nếu hạn lock chưa hết (`expires_at > datetime('now')`).

---

## 4. Tinh thần Phẫu thuật Mã nguồn (Surgical Diffs)
- Chỉ sửa đổi chính xác các dòng cần thiết để giải quyết tác vụ.
- Không tự ý refactor các module đã hoạt động ổn định được copy từ `nuoi-kenh-youtube` (như `cdp.py`, `human_behavior.py`, `selenium_utils.py`, `gpm_api.py`) trừ khi có yêu cầu tối ưu cụ thể.
