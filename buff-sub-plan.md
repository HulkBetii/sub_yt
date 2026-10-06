# Project Plan: Hệ thống Buff Sub YouTube
**Role:** Tech Lead / Project Manager  
**Tổng estimate:** ~12–15 ngày làm việc (solo dev, coding ~4–6h/ngày)  
**Stack:** Python + Selenium + GPM Login + SQLite + FastAPI + React/Vite

---

## Tổng quan Architecture

```
nuoi-kenh-youtube (mở rộng)        buff-sub-yt (dự án mới)
├── brand_account_manager.py  ────► account_pool.py (shared DB)
├── [nuôi Brand Accounts]          ├── sub_engine.py
└── shared/account_pool.db ───────►├── order_manager.py
                                   ├── scheduler.py
                                   └── server/ + ui/
```

**Nguyên tắc triển khai:**
- Phase 0 và Phase 1 chạy **song song** (không chặn nhau)
- Dùng Gmail gốc để test trước → chờ Brand Accounts nuôi xong → mở rộng pool
- Code Phase 1 trước, Phase 0 làm trong lúc Phase 1 đang test

---

## Phase 0 — Brand Account Factory (nuoi-kenh-youtube)
> **Mục tiêu:** Tự động tạo 50 kênh/Gmail và đưa vào hệ thống nuôi  
> **Estimate tổng:** 4–5 ngày

### P0.T1 — Setup Shared Database
**File:** `D:\VibeCoding\shared\account_pool.db`  
**Estimate:** 2–3 giờ  
**Làm trước tất cả** — đây là Single Source of Truth giữa 2 hệ thống

```
Sub-tasks:
├── Tạo thư mục D:\VibeCoding\shared\
├── Viết schema SQL (gpm_profiles, sub_accounts, account_locks)
├── Viết script init_db.py để tạo DB và seed 10 Gmail gốc
└── Verify: query thử, đảm bảo constraints hoạt động đúng
```

**Definition of Done:** `init_db.py` chạy không lỗi, seed 10 rows vào `gpm_profiles` và `sub_accounts`.

---

### P0.T2 — Viết `brand_account_manager.py`
**File:** `nuoi_kenh/brand_account_manager.py`  
**Estimate:** 1.5–2 ngày  
**Depends on:** P0.T1

```
Sub-tasks:
├── [4h] create_brand_account(driver) → tự động điền tên và tạo 1 kênh
│       URL: https://www.youtube.com/create_channel
│       Selectors: input[name="channel-name"], #create-channel-button
│       Delay 10–20 phút ngẫu nhiên giữa mỗi lần tạo (tránh bị throttle)
│       Lấy channel_id (@handle) sau khi tạo xong
│
├── [3h] create_brand_accounts_batch(driver, gmail, count=50)
│       Tạo N kênh tuần tự, nghỉ giữa các lần
│       Tự động lưu channel_id vào shared DB sau mỗi lần tạo thành công
│       Retry khi gặp lỗi "Too many requests" (chờ 30–60 phút rồi thử lại)
│
├── [2h] get_existing_brand_accounts(driver) → scrape kênh đã tồn tại
│       URL: https://www.youtube.com/channel_switcher
│       Parse danh sách kênh (tên + channel_id)
│       Sync vào DB (upsert — không tạo trùng)
│
└── [2h] Test thực tế với 1 Gmail → tạo 3 kênh thử, verify DB
```

**Definition of Done:** Script tạo được 3+ kênh cho 1 Gmail, ghi đúng vào DB.

---

### P0.T3 — Switch Account + Nuôi Brand Account
**File:** `nuoi_kenh/brand_account_manager.py` (tiếp)  
**Estimate:** 1.5 ngày  
**Depends on:** P0.T2

```
Sub-tasks:
├── [3h] switch_to_account(driver, channel_id)
│       URL: https://www.youtube.com/channel_switcher
│       Tìm và click vào kênh theo channel_id hoặc tên
│       Verify URL sau switch (phải thấy studio.youtube.com hoặc youtube.com/@handle)
│       Fallback: nếu channel_switcher load lỗi → thử lại 2 lần
│
├── [3h] warmup_brand_account_session(driver, account_row)
│       Reuse toàn bộ logic từ youtube.py (xem video, skip ad, scroll)
│       Xem 2–3 video trong niche của kênh (dùng niche field từ DB)
│       Cập nhật warmup_videos + warmup_days vào DB sau mỗi session
│       Tự động đổi warmup_status → 'ready' khi đạt ngưỡng
│
└── [2h] Integrate vào main.py: sau khi chạy Gmail gốc xong
        → pick N Brand Accounts chưa ready → chạy warmup session
        → giới hạn thời gian: tối đa 20 phút nuôi Brand Account/vòng lặp
```

**Definition of Done:** Sau 14 ngày chạy, Brand Accounts có `warmup_days >= 14` được tự động đánh dấu `ready`.

---

## Phase 1 — buff-sub-yt Core Engine
> **Mục tiêu:** Hệ thống sub chạy được với 10 Gmail gốc (test bed)  
> **Estimate tổng:** 4–5 ngày  
> **Bắt đầu song song với Phase 0**

### P1.T1 — Project Scaffold
**Estimate:** 2–3 giờ

```
Sub-tasks:
├── Tạo D:\VibeCoding\buff-sub-yt\ với cấu trúc thư mục đầy đủ
├── requirements.txt:
│       selenium, webdriver-manager, requests, fastapi, uvicorn,
│       apscheduler, aiosqlite, pydantic, HumanCursor (pip install humancursor)
├── Copy & adapt các modules từ nuoi-kenh:
│       gpm_api.py, human_behavior.py, selenium_utils.py,
│       cdp.py, logger.py, tab_guard.py → buff_sub/ (giữ nguyên 100%)
└── Verify imports: python -c "from buff_sub.gpm_bridge import *" không lỗi
```

---

### P1.T2 — Database Layer (`database.py`)
**Estimate:** 3–4 giờ  
**Depends on:** P1.T1

```
Sub-tasks:
├── [1h] Schema buff_sub.db (orders, sub_history)
├── [1h] CRUD functions:
│       create_order(channel_url, target, daily_cap) → order_id
│       get_order(order_id) → dict
│       update_order_status(order_id, status, delivered)
│       log_sub_attempt(order_id, account_id, result)
│       get_pending_sub_slots(order_id, limit) → list[account_id]
└── [1h] Test: tạo 1 order, log 3 attempts, query lịch sử
```

---

### P1.T3 — Account Pool Bridge (`account_pool.py`)
**Estimate:** 4–5 giờ  
**Depends on:** P0.T1, P1.T1

```
Sub-tasks:
├── [2h] get_ready_accounts(limit, exclude_on_cooldown=True)
│       Query shared DB: warmup_status='ready' AND cooldown_until < now()
│       Sort: ưu tiên tier 1 (gmail_root) trước, rồi theo last_sub_at ASC
│
├── [1h] lock_account(account_id, locked_by='buff_sub', duration_min=60)
│       Insert vào account_locks, tự động expire
│
├── [1h] release_lock(account_id)
│       Delete khỏi account_locks
│
├── [1h] update_cooldown(account_id, days=3)
│       Set cooldown_until = now() + 3 days
│       Increment subs_this_month
│
└── [30m] is_available(account_id) → bool (check lock + cooldown + monthly limit)
```

---

### P1.T4 — Sub Engine (`sub_engine.py`) ⭐ Task quan trọng nhất
**Estimate:** 2–2.5 ngày  
**Depends on:** P1.T1, P1.T2, P1.T3

```
Sub-tasks:
├── [3h] switch_to_account(driver, account_row)
│       Reuse logic từ brand_account_manager.py (hoặc call qua shared module)
│       Verify: driver.current_url hoặc channel_id trên YouTube
│
├── [4h] warmup_before_sub(driver, mood)
│       Vào YouTube homepage 30–60s
│       Tìm và xem 1 video trong niche (dùng GOOGLE_KEYWORDS tương tự nuoi-kenh)
│       Retention 40–70%, skip ad, scroll natural
│
├── [4h] visit_target_channel_and_watch(driver, channel_url)
│       Điều hướng tới channel_url
│       Scroll danh sách video 10–20s
│       Click video bất kỳ trong danh sách (random.choice từ 5 video đầu)
│       Xem: WATCH_SECONDS_MIN–MAX giây, skip ad
│       Đo retention thực tế (lưu vào sub_history)
│
├── [3h] do_like_if_needed(driver, probability=0.60)
│       CSS: #like-button button, ytd-like-button-renderer button
│       Check chưa like (aria-label không chứa "unlike")
│       HumanCursor di chuột đến nút → click
│       Verify: aria-label đổi sang "Unlike" (confirm đã like)
│
├── [4h] do_subscribe(driver) → bool
│       CSS: #subscribe-button button, ytd-subscribe-button-renderer button
│       Check chưa sub (text không phải "Subscribed" hoặc "Đã đăng ký")
│       Scroll lên đầu trang → hover channel name 1–2s
│       HumanCursor di chuột đến nút Subscribe → click
│       Xử lý confirm dialog nếu có (notification modal)
│       Verify: button text đổi sang "Subscribed" trong 5s → return True/False
│
├── [2h] cooldown_browsing(driver)
│       Xem 1 video không liên quan (homepage hoặc suggested)
│       30–90 giây → đóng browser
│
└── [3h] run_sub_session(gpm_profile_id, account_id, order_id) → result_dict
        Orchestrate toàn bộ flow:
        1. lock_account → 2. mo_profile_gpm → 3. switch_to_account
        4. warmup_before_sub → 5. visit_target_channel_and_watch
        6. do_like → 7. do_subscribe → 8. cooldown_browsing
        9. release_lock → 10. update_cooldown → 11. log_sub_attempt
        Exception handling: bất kỳ bước nào fail → log fail_reason, release_lock, close browser
```

---

### P1.T5 — Order Manager + CLI Runner
**Estimate:** 4–5 giờ  
**Depends on:** P1.T2, P1.T3, P1.T4

```
Sub-tasks:
├── [2h] order_manager.py:
│       assign_accounts_to_order(order_id) → list[account_id]
│       Chọn accounts theo priority tier, skip cooldown/locked
│       Không assign cùng account cho 2 orders khác nhau trong cùng ngày
│
├── [2h] main.py CLI:
│       python main.py --order-id 1 --dry-run   (print plan, không chạy thật)
│       python main.py --order-id 1              (chạy thật)
│       python main.py --list-orders             (xem danh sách orders)
│
└── [2h] Integration test:
        Tạo 1 order test (kênh test của chính mình)
        Chạy với 3 Gmail gốc → verify 3 sub thành công trong DB
        Confirm bằng mắt: vào kênh mục tiêu kiểm tra số sub tăng
```

**Definition of Done:** `python main.py --order-id 1` chạy thành công, 3 accounts sub 1 kênh test.

---

## Phase 2 — Drip-feed Scheduler
> **Mục tiêu:** Hệ thống tự động chạy theo lịch, không cần manual trigger  
> **Estimate tổng:** 2 ngày  
> **Depends on:** Phase 1 hoàn thành

### P2.T1 — APScheduler Integration
**Estimate:** 6–8 giờ

```
Sub-tasks:
├── [2h] scheduler.py:
│       Job "drip_feed_tick" chạy mỗi 30 phút
│       Logic: với mỗi order đang running:
│           - Tính slots còn lại hôm nay (daily_cap - delivered_today)
│           - Nếu còn slot → gọi assign_accounts + run_sub_session
│           - Nếu hết slot → skip đến ngày mai
│
├── [2h] Drip-feed curve logic:
│       Ngày 1–3:  daily_cap * 0.3  (seeding)
│       Ngày 4–7:  daily_cap * 0.6  (growth)
│       Ngày 8–14: daily_cap * 0.9  (steady)
│       Ngày 15+:  daily_cap * 1.0  (mature)
│
├── [2h] Concurrency control:
│       Semaphore: tối đa MAX_PARALLEL_PROFILES jobs đồng thời
│       Nếu tất cả profiles đang bận → skip tick, chờ tick tiếp
│
└── [2h] server.py: endpoint POST /scheduler/start, POST /scheduler/stop
        Chạy APScheduler trong background thread của FastAPI
```

---

## Phase 3 — API + Dashboard
> **Estimate tổng:** 2.5–3 ngày  
> **Depends on:** Phase 2

### P3.T1 — FastAPI Backend
**Estimate:** 1 ngày

```
Endpoints:
├── POST /orders          → Tạo order mới
├── GET  /orders          → Danh sách tất cả orders
├── GET  /orders/{id}     → Chi tiết order + progress
├── PUT  /orders/{id}/pause   → Pause/resume
├── GET  /accounts        → Danh sách sub accounts + tier + trạng thái
├── GET  /stats           → Tổng quan: total delivered, active orders, pool size
└── WS   /ws/logs         → WebSocket stream real-time logs
```

### P3.T2 — React Dashboard
**Estimate:** 1.5–2 ngày

```
Views:
├── OrdersView:
│       Form tạo order (channel_url, target_subs, daily_cap)
│       Danh sách orders với progress bar + ETA
│       Nút Pause/Resume per order
│
├── AccountPoolView:
│       Bảng 500 accounts: Tier badge, warmup_days, subs_this_month, status
│       Filter theo: tier / status / gpm_profile
│       Highlight accounts đang bị lock (màu vàng) hoặc suspended (màu đỏ)
│
└── LiveLogsView:
        Terminal-style log stream qua WebSocket
        Filter theo order_id hoặc profile_id
```

---

## Phase 4 — Production Hardening
> **Estimate tổng:** 1–2 ngày (sau khi đã chạy thật vài ngày)

```
P4.T1 — Account health monitor:
    ├── Phát hiện accounts bị Google flag (redirect về accounts.google.com khi vào YT)
    ├── Auto-suspend: set warmup_status='suspended' + ghi lý do
    └── Alert log khi >20% accounts của 1 Gmail bị suspend cùng lúc (dấu hiệu proxy bị leak)

P4.T2 — Export báo cáo:
    ├── GET /orders/{id}/export → CSV: timestamp, account_id, success, watch_seconds
    └── Summary report per order: success rate, avg watch time, accounts used

P4.T3 — Retry + resilience:
    ├── Sub fail do mạng/timeout → retry sau 2 giờ (tối đa 2 lần)
    └── Nếu sub fail do account bị challenge (captcha, phone verify) → auto-suspend account
```

---

## Timeline Tổng quan

```
Tuần 1:
  Ngày 1:    P0.T1 (Shared DB) + P1.T1 (Scaffold)
  Ngày 2:    P0.T2 (Brand Account Creator)
  Ngày 3:    P0.T3 (Switch + Warmup) || P1.T2 (Database Layer)
  Ngày 4:    P1.T3 (Account Pool) + P1.T4 bắt đầu
  Ngày 5:    P1.T4 tiếp (Sub Engine — task nặng nhất)

Tuần 2:
  Ngày 6:    P1.T4 hoàn thành + P1.T5 (CLI + Integration Test)
  Ngày 7:    P2.T1 (Scheduler) — test drip-feed với 10 Gmail gốc
  Ngày 8:    P3.T1 (FastAPI)
  Ngày 9–10: P3.T2 (React Dashboard)

Tuần 3:
  Ngày 11+:  P4 (Hardening) — chạy song song với Brand Accounts đang được nuôi
  Ngày 14+:  Brand Accounts đạt ready → pool tăng lên 100+ accounts
```

---

## 2 Rủi ro Kỹ thuật Lớn nhất

### ⚠️ Rủi ro 1: YouTube UI thay đổi Selector — SEVERITY: CAO

**Mô tả:**  
Nút Subscribe/Like của YouTube được render bởi Polymer Web Components với Shadow DOM sâu. Google thường xuyên thay đổi class name, cấu trúc DOM, và attribute trong các lần update UI mà không thông báo. Một lần deploy UI mới có thể khiến toàn bộ sub_engine.py không tìm được nút và fail 100%.

**Biểu hiện:**  
- `NoSuchElementException` trên selector `#subscribe-button button`
- Hoặc tìm được element nhưng `is_displayed() = False` (element bị wrap trong shadow root)

**Kế hoạch giảm thiểu:**
```python
# Thay vì 1 selector cứng, dùng selector chain fallback:
SUBSCRIBE_SELECTORS = [
    "#subscribe-button button",
    "ytd-subscribe-button-renderer button",
    "[aria-label*='Subscribe']",
    "button[class*='subscribe']",
    # Fallback cuối: tìm theo text
]

# Kết hợp JavaScript injection để bypass Shadow DOM nếu cần:
driver.execute_script("""
    return document.querySelector('ytd-subscribe-button-renderer')
        ?.shadowRoot?.querySelector('button')
""")
```
Thiết lập **Alert tự động**: nếu success rate trong ngày < 50%, ghi WARNING vào log để operator biết UI đã bị thay đổi.

---

### ⚠️ Rủi ro 2: Google Account Clustering Detection — SEVERITY: RẤT CAO

**Mô tả:**  
Google có mô hình machine learning phát hiện các cụm tài khoản có hành vi tương đồng bất thường. Mặc dù mỗi GPM profile có fingerprint và proxy riêng, nếu **timing pattern** của các accounts sub cùng 1 kênh trong cùng 1 ngày quá đồng đều (ví dụ: mỗi account cách nhau đúng 30 phút), hệ thống phát hiện ra đây là automation.

Nguy hiểm hơn: nếu bị phát hiện ở tầng này, Google không chỉ xóa sub mà có thể **suspend toàn bộ Gmail accounts** liên quan.

**Biểu hiện:**  
- Sub tăng đột ngột rồi về 0 sau 24–48h (Spam Purge)
- Nhiều Gmail nhận email "Unusual activity detected"
- Không còn sub được dù fingerprint/proxy vẫn hoạt động

**Kế hoạch giảm thiểu:**
```
1. Jitter timing: Không chạy theo cron cố định mỗi 30 phút
   → Thêm random jitter ±5–15 phút vào mỗi scheduled job

2. Max 2–3 accounts sub cùng 1 kênh trong 1 giờ
   → hard limit trong scheduler: if accounts_subbed_last_hour >= 3: skip

3. Không bao giờ dùng accounts từ cùng 1 Gmail để sub cùng 1 kênh
   → Constraint trong assign_accounts_to_order():
      accounts từ Gmail A và Gmail B nhưng không 2 accounts từ Gmail A

4. Xen kẽ các orders: nếu có 3 orders đang chạy
   → round-robin giữa các orders, không tập trung 1 order liên tục

5. Monitor: Alert khi > 5 accounts sub cùng 1 kênh trong 1 ngày
```

---

## Checklist trước khi bắt đầu code

- [ ] GPM Login đang chạy, API `http://127.0.0.1:19995` accessible
- [ ] 10 Gmail đã được import vào GPM, proxy US đang hoạt động
- [ ] `nuoi-kenh-youtube` đang chạy bình thường (ít nhất 1 vòng thành công gần đây)
- [ ] Có 1 kênh YouTube "test" của riêng mình để verify sub trong Phase 1
- [ ] Python 3.11+ và `pip install humancursor` thành công
