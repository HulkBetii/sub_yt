# Project Execution Plan & Task Breakdown

**Project:** `buff-sub-yt`  
**Estimated Time:** 12 – 15 working days (Solo Engineer)  
**Methodology:** Incremental Delivery with Independent Subsystems  

---

## 1. Roadmap Tổng quan

```
Tuần 1:
├── Phase 0: Brand Account Factory (nuoi-kenh-youtube)  [P0.T1 -> P0.T3]
└── Phase 1: buff-sub-yt Core Engine                   [P1.T1 -> P1.T5]
    └── Milestone 1: Chạy thử nghiệm thành công 3-5 sub từ Master Gmail

Tuần 2:
├── Phase 2: Drip-feed Scheduler (APScheduler)         [P2.T1 -> P2.T2]
├── Phase 3: REST API & Web Dashboard                  [P3.T1 -> P3.T2]
└── Milestone 2: Tự động hóa hoàn toàn từ Dashboard tới luồng Sub

Tuần 3:
├── Phase 4: Production Hardening & Health Monitoring  [P4.T1 -> P4.T3]
└── Milestone 3: Brand Accounts đạt độ chín (14 ngày), bung toàn bộ 500 accounts
```

---

## 2. Chi tiết Phân rã Công việc (Work Breakdown Structure)

### Phase 0: Brand Account Factory (`nuoi-kenh-youtube`)

#### Task P0.T1 — Khởi tạo Shared Database (`shared/account_pool.db`)
* **Thời gian ước tính:** 2 – 3 giờ
* **Mục tiêu:** Tạo cơ sở dữ liệu chung làm nguồn chân lý duy nhất (Single Source of Truth) giữa hai hệ thống.
* **Chi tiết công việc:**
  1. Tạo thư mục `D:\VibeCoding\shared`.
  2. Viết file `shared/init_db.py` định nghĩa bảng `gpm_profiles`, `sub_accounts`, `account_locks`.
  3. Viết script import/seed 10 GPM profile hiện có vào bảng `gpm_profiles` và 10 dòng `gmail_root` ban đầu vào `sub_accounts`.
* **Definition of Done (DoD):** Chạy `python shared/init_db.py` thành công, kiểm tra SQLite Browser thấy đủ bảng và 10 bản ghi gốc.

#### Task P0.T2 — Module Tạo Kênh Tự động (`brand_account_manager.py`)
* **Thời gian ước tính:** 1.5 – 2 ngày
* **Mục tiêu:** Tự động tạo 50 kênh Brand Account cho mỗi Gmail mà không bị dính cờ spam của YouTube.
* **Chi tiết công việc:**
  1. Viết hàm `create_single_brand_account(driver, channel_name)`:
     - Điều hướng tới `https://www.youtube.com/create_channel`.
     - Tìm input tên kênh `input[name="channel-name"]`.
     - Tick checkbox đồng ý điều khoản Google.
     - Click xác nhận `#create-channel-button`.
     - Trích xuất `@handle` hoặc channel ID sau khi tạo xong.
  2. Viết hàm `batch_create_brand_accounts(driver, count=50)`:
     - Đặt thời gian nghỉ ngẫu nhiên từ 15 – 30 phút giữa mỗi lần tạo kênh.
     - Tự động bắt lỗi nếu gặp "Too many requests" hoặc yêu cầu SMS xác minh -> Dừng an toàn và ghi log.
  3. Viết hàm đồng bộ kênh đã có `sync_existing_channels(driver)`:
     - Đọc toàn bộ danh sách kênh trên `https://www.youtube.com/channel_switcher`.
     - Upsert vào bảng `sub_accounts`.
* **DoD:** Tạo thử nghiệm thành công 3 kênh mới trên 1 profile test và ghi thông tin vào DB.

#### Task P0.T3 — Cơ chế Chuyển Kênh & Nuôi Kênh Phụ (Account Switcher)
* **Thời gian ước tính:** 1.5 ngày
* **Mục tiêu:** Cho phép session nuôi chuyển đổi mượt mà sang các Brand Account để tích lũy Trust Score.
* **Chi tiết công việc:**
  1. Viết hàm `switch_to_brand_account(driver, target_channel_id)`:
     - Truy cập `https://www.youtube.com/channel_switcher`.
     - Tìm element tương ứng với kênh và click.
     - Đợi trang tải lại và xác nhận header profile đã chuyển sang đúng kênh.
  2. Tích hợp vào vòng lặp `main.py` của `nuoi-kenh-youtube`:
     - Sau khi nuôi Gmail gốc, chọn ngẫu nhiên 1 Brand Account chưa đạt trạng thái `ready`.
     - Chạy 1 session xem video ngắn (15-20 phút).
     - Cập nhật số ngày nuôi (`warmup_days`) và số video xem (`warmup_videos`).
* **DoD:** Profile tự động switch sang kênh phụ, xem 2 video và cập nhật số liệu vào DB.

---

### Phase 1: buff-sub-yt Core Engine

#### Task P1.T1 — Scaffold Dự án & Kế thừa Thư viện
* **Thời gian ước tính:** 2 – 3 giờ
* **Mục tiêu:** Dựng bộ khung dự án độc lập, kế thừa an toàn các module anti-detect đã được kiểm chứng.
* **Chi tiết công việc:**
  1. Thiết lập cấu trúc thư mục `buff-sub-yt`.
  2. Viết `requirements.txt` (`selenium`, `fastapi`, `uvicorn`, `apscheduler`, `humancursor`, `pydantic`).
  3. Copy các module từ `nuoi-kenh-youtube`: `gpm_api.py`, `human_behavior.py`, `selenium_utils.py`, `cdp.py`, `logger.py`, `tab_guard.py` vào thư mục `buff_sub/`.
* **DoD:** Môi trường ảo Python import toàn bộ module không gặp bất kỳ lỗi cú pháp hay thiếu package nào.

#### Task P1.T2 — Tầng Dữ liệu Nội bộ (`buff_sub/database.py`)
* **Thời gian ước tính:** 3 – 4 giờ
* **Chi tiết công việc:**
  1. Khởi tạo `buff_sub.db` với 2 bảng `orders` và `sub_history`.
  2. Xây dựng các hàm CRUD:
     - `create_order(...)`
     - `get_order_by_id(...)`
     - `update_order_progress(...)`
     - `record_sub_execution(...)`
* **DoD:** Unit test tạo order, update số lượng delivered và ghi log thực thi thành công.

#### Task P1.T3 — Điều phối Tài nguyên & Khóa Phân tán (`account_pool.py`)
* **Thời gian ước tính:** 4 – 5 giờ
* **Chi tiết công việc:**
  1. Viết hàm `fetch_eligible_accounts(order_id, limit)`:
     - Lọc `warmup_status IN ('ready')`.
     - Lọc `cooldown_until <= datetime('now')`.
     - Loại trừ tài khoản đã sub kênh này trong `sub_history`.
     - Loại trừ tài khoản trùng Master Gmail đã sub kênh này trong vòng 48h.
  2. Cơ chế khóa `acquire_account_lock(account_id, timeout_minutes=30)` và `release_account_lock(account_id)`.
* **DoD:** Chạy đồng thời 2 tiến trình yêu cầu cùng 1 account, tiến trình thứ 2 nhận thông báo lock và chuyển sang account tiếp theo.

#### Task P1.T4 — Động cơ Thực thi Sub Tự nhiên (`sub_engine.py`) ⭐
* **Thời gian ước tính:** 2.5 ngày
* **Chi tiết công việc:**
  1. Tích hợp `HumanCursor` điều khiển con trỏ theo đường cong Bézier vào Selenium CDP.
  2. Viết quy trình 5 bước:
     - Bước 1 (Warmup): Xem 1 video ngẫu nhiên trên trang chủ (40-60s).
     - Bước 2 (Discovery): Tìm kiếm hoặc vào trang kênh đích, cuộn tự nhiên.
     - Bước 3 (Watch): Chọn 1 video, xem từ 90s - 180s, tự động skip quảng cáo.
     - Bước 4 (Engage & Sub): 60% like video; di chuột Bézier đến nút Subscribe và click; verify text nút chuyển sang "Subscribed".
     - Bước 5 (Cooldown): Xem tiếp 1 video ngẫu nhiên khác 30s trước khi đóng browser.
* **DoD:** Chạy thực tế thành công luồng Sub trên 1 kênh test cá nhân, nút Subscribe được kích hoạt và giữ nguyên trạng thái.

#### Task P1.T5 — CLI Runner & Kiểm thử Tích hợp
* **Thời gian ước tính:** 4 – 5 giờ
* **Chi tiết công việc:**
  1. Hoàn thiện `main.py` với các tham số dòng lệnh CLI (`--create-order`, `--order-id`, `--dry-run`, `--list-orders`).
  2. Chạy thử nghiệm 3 Master Gmail gốc sub 1 kênh test đích.
* **DoD:** CLI báo cáo hoàn tất 3/3 sub, cơ sở dữ liệu `buff_sub.db` ghi nhận đủ 3 dòng lịch sử với thời gian xem thực tế.

---

### Phase 2: Drip-feed Scheduler (Tự động hóa theo lịch)

#### Task P2.T1 — Bộ Lập lịch Drip-feed (`scheduler.py`)
* **Thời gian ước tính:** 1.5 – 2 ngày
* **Chi tiết công việc:**
  1. Cấu hình APScheduler chạy chu kỳ nền mỗi 20-30 phút.
  2. Hiện thực hóa thuật toán giới hạn tốc độ (Sigmoid Rate Limiter):
     - Tính toán quota sub còn lại trong ngày của từng order.
     - Bổ sung độ trễ ngẫu nhiên Jitter $\pm 10$ phút.
     - Ràng buộc: Tối đa 2 sub/kênh/giờ.
  3. Quản lý luồng thực thi: Tối đa 2 GPM profile chạy song song để đảm bảo hiệu năng RAM/CPU.
* **DoD:** Bật scheduler và để máy chạy tự động trong 4 tiếng; kiểm tra log thấy các job được kích hoạt đúng nhịp độ, không bị dồn dập.

---

### Phase 3: REST API & Web Dashboard

#### Task P3.T1 — FastAPI Backend (`server/`)
* **Thời gian ước tính:** 1 ngày
* **Chi tiết công việc:**
  1. Các endpoints:
     - `POST /api/orders`: Tạo đơn hàng mới.
     - `GET /api/orders`: Lấy danh sách trạng thái các đơn hàng.
     - `GET /api/pool/stats`: Báo cáo số lượng tài khoản theo từng Tier.
     - `POST /api/orders/{id}/toggle`: Tạm dừng / Tiếp tục đơn hàng.
  2. WebSocket `/ws/logs`: Stream log console theo thời gian thực về giao diện.
* **DoD:** Swagger UI (`/docs`) thực thi thành công toàn bộ API.

#### Task P3.T2 — React Dashboard (`ui/`)
* **Thời gian ước tính:** 1.5 – 2 ngày
* **Chi tiết công việc:**
  1. Màn hình Quản lý đơn hàng (Orders View): Form nhập URL + Target Sub, thanh tiến độ Drip-feed.
  2. Màn hình Bể tài khoản (Account Pool View): Bảng hiển thị 500 tài khoản, phân loại màu theo Tier 1-4, trạng thái Cooldown/Lock.
  3. Màn hình Live Terminal: Xem log luồng sub trực tiếp qua WebSocket.
* **DoD:** Giao diện điều khiển mượt mà, tạo đơn và xem tiến độ hiển thị đúng thời gian thực.

---

### Phase 4: Production Hardening & Bảo trì

#### Task P4.T1 — Giám sát Sức khỏe Tài khoản (Health Monitor)
* **Thời gian ước tính:** 1 ngày
* **Chi tiết công việc:**
  1. Bắt lỗi nhận diện tài khoản bị Google challenge (Verify phone, re-login).
  2. Tự động chuyển `warmup_status = 'suspended'` để loại khỏi hàng đợi sub.
  3. Cảnh báo khẩn cấp nếu phát hiện > 3 tài khoản thuộc cùng 1 Master Gmail bị lỗi đồng thời.
* **DoD:** Hệ thống tự động cô lập tài khoản lỗi mà không làm dừng toàn bộ tiến trình chung.
