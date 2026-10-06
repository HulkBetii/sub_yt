# Buff Sub YouTube — Enterprise Organic Subscription Engine

Hệ thống buff subscriber tự nhiên cho kênh YouTube dựa trên cụm tài khoản GPM Login (Anti-detect Browser) và Brand Account Farming, mô phỏng 100% hành vi người dùng thật nhằm vượt qua các đợt quét thuật toán (Spam Purge) và rà soát của YouTube Partner Program (YPP).

---

## 1. Kiến trúc cốt lõi

```
┌────────────────────────────────────────────────────────┐
│                   HỆ THỐNG PHÂN CẤP                    │
│                                                        │
│  10 Gmail Profiles (GPM Login — Isolated Fingerprint)  │
│     └── Mỗi Gmail sở hữu 50 Brand Account Channels     │
│         └── Tổng cộng: 500 Sub Accounts                │
└──────────────────────────┬─────────────────────────────┘
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│     nuoi-kenh-youtube        │    │         buff-sub-yt          │
│  (Hệ thống nuôi & warm-up)   │    │     (Hệ thống thực thi sub)  │
│  - Tạo 50 kênh/Gmail         │    │  - Quản lý orders            │
│  - Duyệt web sinh học US     │    │  - Drip-feed scheduler       │
│  - Tăng Trust Score          │    │  - Sub session flow tự nhiên │
└──────────────┬───────────────┘    └──────────────┬───────────────┘
               │                                   │
               └───────────────┬───────────────────┘
                               ▼
               ┌──────────────────────────────┐
               │  shared/account_pool.db      │
               │  (SQLite - State & Lock Bus) │
               └──────────────────────────────┘
```

---

## 2. 4 Tầng Phòng Thủ Chống Quét (Anti-Purge Defense)

1. **Fingerprint & Network Isolation (Tầng phần cứng/mạng):**
   - Mỗi Gmail chạy trên một GPM Login profile độc lập.
   - Canvas, WebGL, AudioContext, Font, ClientRects, WebRTC và Residential US Proxy riêng biệt.
2. **Behavioral Warm-up (Tầng tiền sử duyệt web):**
   - Không sử dụng tài khoản trắng/rỗng.
   - Tài khoản Brand Account được nuôi tối thiểu 14 ngày, có lịch sử xem video, tương tác đa nền tảng (Google Search, Maps, Reddit, News).
3. **Organic Sub Flow (Tầng hành vi phiên tương tác):**
   - Không paste URL kênh rồi click sub ngay lập tức.
   - Chuỗi hành động: `Warm-up (xem 1 video ngoài) -> Vào kênh mục tiêu -> Xem video (retention 40–70%) -> Like ngẫu nhiên (60%) -> Di chuột Bézier (HumanCursor) -> Click Subscribe -> Cool-down`.
4. **Drip-feed Curve & Anti-Clustering (Tầng điều phối nhịp độ):**
   - Tăng trưởng theo đường cong tự nhiên (Sigmoid curve), không bao giờ sub dồn dập trong 24h.
   - Jitter timing ngẫu nhiên ±5–15 phút.
   - Ràng buộc cứng: Tối đa 2–3 sub/kênh/giờ, không bao giờ dùng 2 accounts từ cùng 1 Gmail cho cùng 1 kênh mục tiêu trong ngày.

---

## 3. Cấu trúc Thư mục

```
D:\VibeCoding\buff-sub-yt\
├── README.md                  # Tài liệu tổng quan dự án
├── AGENTS.md                  # Quy chuẩn code & chỉ thị dành cho AI / Dev
├── requirements.txt           # Thư viện phụ thuộc Python
├── main.py                    # CLI Runner điều khiển hệ thống
├── docs/                      # Tài liệu kỹ thuật chuyên sâu
│   ├── ARCHITECTURE.md        # Thiết kế hệ thống, DB Schema, luồng dữ liệu
│   └── PROJECT_PLAN.md        # Kế hoạch dự án, phân rã công việc & estimate
├── buff_sub/                  # Package lõi của hệ thống
│   ├── __init__.py
│   ├── config.py              # Tham số cấu hình tập trung
│   ├── gpm_bridge.py          # Kết nối GPM Login API & CDP
│   ├── account_pool.py        # Giao tiếp với shared/account_pool.db & locks
│   ├── sub_engine.py          # Luồng sub tự nhiên (Warmup -> Watch -> Like -> Sub)
│   ├── order_manager.py       # Quản lý vòng đời đơn hàng buff sub
│   ├── scheduler.py           # Bộ lập lịch Drip-feed (APScheduler)
│   ├── database.py            # Local SQLite database (buff_sub.db)
│   └── logger.py              # Hệ thống log màu & UTF-8
├── server/                    # FastAPI Backend
│   ├── app.py                 # REST API endpoints
│   ├── schemas.py             # Pydantic models
│   └── log_streamer.py        # WebSocket real-time log streaming
├── ui/                        # Web Dashboard (React + Vite + Tailwind)
├── data/                      # Lưu trữ database nội bộ
│   └── buff_sub.db
└── logs/                      # Log files theo phiên
```

---

## 4. Hướng dẫn Cài đặt & Khởi chạy

### Yêu cầu tiên quyết
- Python 3.11+ (Khuyến nghị 64-bit)
- Ứng dụng GPM Login đang mở và API kích hoạt tại `http://127.0.0.1:19995`
- Tối thiểu 10 profile GPM Login đã cấu hình Proxy US và đăng nhập sẵn Gmail

### Cài đặt môi trường
```powershell
cd D:\VibeCoding\buff-sub-yt
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Khởi tạo Database dùng chung
```powershell
python ..\shared\init_db.py
```

### Sử dụng CLI
```powershell
# Xem danh sách lệnh hỗ trợ
python main.py --help

# Xem danh sách đơn hàng
python main.py --list-orders

# Tạo đơn hàng mới (Ví dụ: buff 100 sub cho kênh test, cap 20 sub/ngày)
python main.py --create-order --channel "https://www.youtube.com/@ChannelHandle" --target 100 --daily-cap 20

# Chạy thử nghiệm mô phỏng (Dry-run không click thật)
python main.py --order-id 1 --dry-run

# Chạy thực tế đơn hàng
python main.py --order-id 1
```

### Khởi chạy Dashboard Server
```powershell
python -m uvicorn server.app:app --host 127.0.0.1 --port 8088 --reload
```
Truy cập dashboard tại `http://127.0.0.1:8088`.
