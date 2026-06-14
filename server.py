# -*- coding: utf-8 -*-
import asyncio
import logging
import os
import sqlite3
import uuid
import time
import json
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from http import cookies
from urllib.parse import parse_qs

# --- Cấu hình ghi nhật ký ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
bộ_ghi_nhật_ký = logging.getLogger(__name__)

# Token bot và URL ứng dụng
MÃ_TOKEN = "8621133442:AAFhgCT-rpiR-Ahp1gXKZVjMwm-kfyoSIaE"
URL_ỨNG_DỤNG = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:10000")

# Thông tin Admin Web
ADMIN_USER = "nhớ em"
ADMIN_PASS = "Lynh"
phiên_đăng_nhập = {}

# Bộ nhớ tạm cấu hình Anti-DDoS
LỊCH_SỬ_REQUEST = {}

# --- Khởi tạo cơ sở dữ liệu ---
def khởi_tạo_cơ_sở_dữ_liệu():
    kết_nối = sqlite3.connect("he_thong_ban_key.db", check_same_thread=False)
    kết_nối.execute("PRAGMA journal_mode=WAL;")
    con_trỏ = kết_nối.cursor()
    
    # Bảng khách hàng mở rộng (thêm số dư và trạng thái block)
    con_trỏ.execute('''
        CREATE TABLE IF NOT EXISTS khach_hang (
            nguoi_dung_id TEXT PRIMARY KEY,
            ten_nguoi_dung TEXT,
            username TEXT,
            so_du REAL DEFAULT 0,
            trang_thai TEXT DEFAULT 'hoat_dong',
            ngay_tuong_tac TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Bảng cấu hình danh mục Game/Sản phẩm động trên Mini App
    con_trỏ.execute('''
        CREATE TABLE IF NOT EXISTS san_pham_game (
            id TEXT PRIMARY KEY,
            ten_game TEXT NOT NULL,
            mo_ta TEXT,
            gia_gio REAL DEFAULT 0,
            gia_ngay REAL DEFAULT 0,
            gia_thang REAL DEFAULT 0
        )
    ''')
    
    # Bảng lưu kho key phân loại thời hạn
    con_trỏ.execute('''
        CREATE TABLE IF NOT EXISTS kho_key_dong (
            id TEXT PRIMARY KEY,
            game_id TEXT,
            loai_key TEXT, -- 'gio', 'ngay', 'thang'
            ma_key TEXT UNIQUE,
            trang_thai TEXT DEFAULT 'con_hang',
            nguoi_mua TEXT,
            ngay_ban TEXT
        )
    ''')

    # Chèn dữ liệu mẫu nếu bảng game trống để Mini App luôn có hàng hiển thị ban đầu
    con_trỏ.execute("SELECT COUNT(*) FROM san_pham_game")
    if con_trỏ.fetchone()[0] == 0:
        con_trỏ.execute("INSERT INTO san_pham_game VALUES ('game_default', 'Liên Quân Mobile 🎮', 'Cung cấp Key VIP tự động', 5000, 20000, 150000)")

    kết_nối.commit()
    kết_nối.close()

khởi_tạo_cơ_sở_dữ_liệu()

bot_app = None

# --- GIAO DIỆN WEB CSS CHUNG ---
GIAO_DIỆN_CHUNG_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background: linear-gradient(135deg, #ffb6c1, #ff69b4, #ff1493, #ff69b4);
        background-size: 400% 400%;
        animation: gradientBG 12s ease infinite;
        min-height: 100vh; color: #fff; overflow-x: hidden;
    }
    @keyframes gradientBG {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    .sparkles { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1; }
    .sparkle {
        position: absolute; width: 4px; height: 4px; background: #fff; border-radius: 50%;
        animation: sparkleFloat 3s linear infinite; box-shadow: 0 0 10px #fff, 0 0 20px #ff69b4;
    }
    @keyframes sparkleFloat {
        0% { transform: translateY(100vh) scale(0); opacity: 0; }
        10% { opacity: 1; }
        100% { transform: translateY(-10vh) scale(1.5); opacity: 0; }
    }
    .main-box {
        position: relative; z-index: 2; background: rgba(255, 255, 255, 0.2);
        backdrop-filter: blur(15px); border-radius: 20px; border: 2px solid rgba(255,255,255,0.3);
    }
    .nav-tabs { display: flex; gap: 10px; margin-bottom: 20px; }
    .nav-tabs a {
        padding: 10px 20px; background: rgba(255,255,255,0.3); border-radius: 10px;
        color: white; text-decoration: none; font-weight: bold; transition: 0.3s;
    }
    .nav-tabs a.active, .nav-tabs a:hover { background: #ff1493; box-shadow: 0 0 10px #fff; }
"""

TRANG_ĐĂNG_NHẬP_ADMIN = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><title>🌸 Đăng nhập Quản trị viên</title>
    <style>
        {GIAO_DIỆN_CHUNG_CSS}
        .login-container {{ width: 100%; max-width: 400px; margin: 15vh auto; padding: 30px; text-align: center; }}
        h2 {{ margin-bottom: 20px; text-shadow: 0 0 15px #fff; }}
        .input-group {{ margin-bottom: 15px; text-align: left; }}
        label {{ font-weight: bold; font-size: 0.9em; }}
        input {{ width: 100%; padding: 12px; margin-top: 5px; border-radius: 10px; border: none; outline: none; font-size: 1em; }}
        .btn-submit {{
            width: 100%; padding: 12px; border: none; border-radius: 50px; margin-top: 15px;
            background: linear-gradient(135deg, #ff1493, #ff69b4); color: white; font-weight: bold; cursor: pointer;
            box-shadow: 0 5px 15px rgba(255,20,147,0.4); transition: 0.3s;
        }}
    </style>
</head>
<body>
    <div class="sparkles" id="sparkles"></div>
    <div class="main-box login-container">
        <h2>🌸 Admin Login 🌸</h2>
        {{error_placeholder}}
        <form method="POST" action="/admin/login">
            <div class="input-group"><label>Tài khoản ✨</label><input type="text" name="username" required></div>
            <div class="input-group"><label>Mật khẩu ✨</label><input type="password" name="password" required></div>
            <button type="submit" class="btn-submit">ĐĂNG NHẬP 💖</button>
        </form>
    </div>
    <script>
        for (let i = 0; i < 20; i++) {{
            let s = document.createElement('div'); s.className = 'sparkle';
            s.style.left = Math.random() * 100 + '%'; s.style.animationDelay = Math.random() * 3 + 's';
            document.getElementById('sparkles').appendChild(s);
        }}
    </script>
</body>
</html>
"""

TRANG_BẢNG_ĐIỀU_KHIỂN_ADMIN = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><title>🌸 Hệ Thống Quản Trị - Key Store</title>
    <style>
        {GIAO_DIỆN_CHUNG_CSS}
        .container {{ max-width: 1100px; margin: 30px auto; padding: 20px; position: relative; z-index: 2; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }}
        .btn-logout {{ padding: 10px 20px; background: #fff; color: #ff1493; border-radius: 20px; text-decoration: none; font-weight: bold; }}
        .card {{ padding: 20px; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; background: rgba(0,0,0,0.2); border-radius: 10px; overflow: hidden; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        th {{ background: rgba(0,0,0,0.4); }}
        input[type="number"], input[type="text"] {{ padding: 6px; border-radius: 5px; border: none; width: 100px; margin-right: 5px; }}
        .btn-action {{ padding: 6px 12px; border: none; border-radius: 5px; color: white; cursor: pointer; font-weight: bold; }}
        .btn-add {{ background: #00cdfe; }} .btn-ban {{ background: #ff0000; }}
        .alert {{ padding: 10px; background: #ffff00; color: #000; font-weight: bold; border-radius: 5px; margin-bottom: 15px; display: none; }}
    </style>
</head>
<body>
    <div class="sparkles" id="sparkles"></div>
    <div class="container">
        <div class="header">
            <h1>🌸 HỆ THỐNG QUẢN TRỊ VIP 🌸</h1>
            <a href="/admin/logout" class="btn-logout">Đăng xuất 👋</a>
        </div>
        
        <div class="nav-tabs">
            <a href="/admin" class="active">👥 Quản lý thành viên</a>
            <a href="/admin/miniapp">🎮 Quản lý Mini App & Key VIP</a>
        </div>

        <div id="alertBox" class="alert"></div>

        <div class="main-box card">
            <h3>👥 DANH SÁCH THÀNH VIÊN & CẤP VỐN NẠP TIỀN</h3>
            <table>
                <thead>
                    <tr>
                        <th>ID Người Dùng</th>
                        <th>Tên Hiển Thị</th>
                        <th>Username</th>
                        <th>Số Dư Hiện Tại</th>
                        <th>Hành Động Nạp Tiền</th>
                        <th>Quyền Truy Cập</th>
                    </tr>
                </thead>
                <tbody id="tableUsers"></tbody>
            </table>
        </div>
    </div>

    <script>
        async function taiThongTin() {{
            const res = await fetch('/api/admin/users');
            const users = await res.json();
            let html = '';
            users.forEach(u => {{
                html += `<tr>
                    <td>${{u.id}}</td>
                    <td><b>${{u.ten}}</b></td>
                    <td>${{u.username ? '@' + u.username : 'Không có'}}</td>
                    <td><span style="color:#ffd700; font-weight:bold;">${{u.so_du.toLocaleString()}}đ</span></td>
                    <td>
                        <input type="number" id="amt-${{u.id}}" placeholder="VND...">
                        <button class="btn-action btn-add" onclick="napTien('${{u.id}}')">Nạp 💎</button>
                    </td>
                    <td>
                        <button class="btn-action btn-ban" onclick="doiTrangThai('${{u.id}}', '${{u.trang_thai}}')">
                            ${{u.trang_thai === 'hoat_dong' ? 'Band Chặn 🚫' : 'Mở Khóa ✅'}}
                        </button>
                    </td>
                </tr>`;
            }});
            document.getElementById('tableUsers').innerHTML = html;
        }}

        async function napTien(uid) {{
            const val = document.getElementById(`amt-${{uid}}`).value;
            if(!val) return alert("Nhập số tiền cần nạp!");
            const res = await fetch('/api/admin/deposit', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{user_id: uid, amount: val}})
            }});
            const data = await res.json();
            if(data.success) {{ alert("✅ Đã nạp tiền thành công!"); taiThongTin(); }}
        }}

        async function doiTrangThai(uid, current) {{
            const nextIdx = current === 'hoat_dong' ? 'bi_ban' : 'hoat_dong';
            const res = await fetch('/api/admin/ban', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{user_id: uid, status: nextIdx}})
            }});
            const data = await res.json();
            if(data.success) {{ alert("⚙️ Cập nhật trạng thái thành viên thành công!"); taiThongTin(); }}
        }}

        taiThongTin();
    </script>
</body>
</html>
"""

TRANG_QUẢN_LÝ_MINIAPP_ADMIN = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><title>🌸 Cấu Hình Mini App & Thời Hạn Key</title>
    <style>
        {GIAO_DIỆN_CHUNG_CSS}
        .container {{ max-width: 1100px; margin: 30px auto; padding: 20px; position: relative; z-index: 2; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
        .card {{ padding: 20px; }}
        label {{ display: block; font-size: 0.9em; margin: 8px 0 4px; font-weight: bold; }}
        input, select, textarea {{ width: 100%; padding: 10px; border-radius: 8px; border: none; outline: none; margin-bottom: 5px; }}
        button {{ padding: 10px; background: linear-gradient(135deg, #ff1493, #ff69b4); border: none; color: #fff; font-weight: bold; border-radius: 8px; cursor: pointer; width: 100%; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌸 TRANG 2: QUẢN LÝ TÙY CHỈNH MINI APP 🌸</h1>
            <a href="/admin/logout" style="color:white; font-weight:bold;">Đăng xuất 👋</a>
        </div>
        
        <div class="nav-tabs">
            <a href="/admin">👥 Quản lý thành viên</a>
            <a href="/admin/miniapp" class="active">🎮 Quản lý Mini App & Key VIP</a>
        </div>

        <div class="grid">
            <div class="main-box card">
                <h3>🎮 THÊM / CẬP NHẬT GAME BÁN</h3>
                <form id="formGame">
                    <label>Tên trò chơi / Game mới</label>
                    <input type="text" name="ten_game" placeholder="Ví dụ: Free Fire 🔫, Liên Quân ⚔️" required>
                    <label>Mô tả ngắn</label>
                    <input type="text" name="mo_ta" placeholder="Bản hack mượt mà chống khóa acc">
                    <label>Giá cấu hình Key Giờ (VND)</label>
                    <input type="number" name="gia_gio" value="5000" required>
                    <label>Giá cấu hình Key Ngày (VND)</label>
                    <input type="number" name="gia_ngay" value="20000" required>
                    <label>Giá cấu hình Key Tháng (VND)</label>
                    <input type="number" name="gia_thang" value="150000" required>
                    <button type="submit" style="margin-top:10px;">LƯU DANH MỤC GAME ✨</button>
                </form>
            </div>

            <div class="main-box card">
                <h3>🔑 DÁN HÀNG LOẠT MÃ KEY THEO THỜI HẠN</h3>
                <form id="formAddKey">
                    <label>Chọn Game áp dụng</label>
                    <select name="game_id" id="selectGame" required></select>
                    <label>Chọn thời hạn Key</label>
                    <select name="loai_key">
                        <option value="gio">🔑 Key Giờ VIP</option>
                        <option value="ngay">📆 Key Ngày VIP</option>
                        <option value="thang">🚀 Key Tháng VIP</option>
                    </select>
                    <label>Dán danh sách Key của bạn vào đây (Mỗi key 1 dòng)</label>
                    <textarea name="danh_sach_key" rows="6" placeholder="KEY_CHARLIE_123&#10;KEY_DELTA_456" required></textarea>
                    <button type="submit" style="margin-top:10px; background:linear-gradient(135deg, #00cbfe, #0076fe);">BƠM KEY VÀO SERVER AUTO 🚀</button>
                </form>
            </div>
        </div>

        <div class="main-box card">
            <h3>📊 KHO GAME ĐANG HIỂN THỊ MINI APP</h3>
            <table>
                <thead>
                    <tr>
                        <th>Tên Game</th>
                        <th>Giá Giờ</th>
                        <th>Giá Ngày</th>
                        <th>Giá Tháng</th>
                        <th>Tồn Kho Key</th>
                    </tr>
                </thead>
                <tbody id="tableGames"></tbody>
            </table>
        </div>
    </div>

    <script>
        async function loadData() {{
            const res = await fetch('/api/admin/games_dashboard');
            const data = await res.json();
            
            let options = '';
            data.games.forEach(g => {{
                options += `<option value="${{g.id}}">${{g.ten_game}}</option>`;
            }});
            document.getElementById('selectGame').innerHTML = options;

            let tbody = '';
            data.games.forEach(g => {{
                tbody += `<tr>
                    <td><b>${{g.ten_game}}</b><br><small style="opacity:0.7">${{g.mo_ta}}</small></td>
                    <td>${{g.gia_gio.toLocaleString()}}đ</td>
                    <td>${{g.gia_ngay.toLocaleString()}}đ</td>
                    <td>${{g.gia_thang.toLocaleString()}}đ</td>
                    <td>
                        <span style="color:#00ffcc">⏱ Giờ: ${{data.counts[g.id]?.gio || 0}} cái</span><br>
                        <span style="color:#ffff00">📆 Ngày: ${{data.counts[g.id]?.ngay || 0}} cái</span><br>
                        <span style="color:#ff00ff">🚀 Tháng: ${{data.counts[g.id]?.thang || 0}} cái</span>
                    </td>
                </tr>`;
            }});
            document.getElementById('tableGames').innerHTML = tbody;
        }}

        document.getElementById('formGame').onsubmit = async (e) => {{
            e.preventDefault();
            const fd = new FormData(e.target);
            await fetch('/api/admin/add_game', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify(Object.fromEntries(fd))
            }});
            alert("🎮 Đã cập nhật danh mục trò chơi thành công!");
            e.target.reset(); loadData();
        }};

        document.getElementById('formAddKey').onsubmit = async (e) => {{
            e.preventDefault();
            const fd = new FormData(e.target);
            const res = await fetch('/api/admin/import_keys', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify(Object.fromEntries(fd))
            }});
            const data = await res.json();
            alert(`✅ Nhập kho thành công: ${{data.count}} Key mới!`);
            e.target.reset(); loadData();
        }};

        loadData();
    </script>
</body>
</html>
"""

# --- GIAO DIỆN MINI APP ĐỘNG (XÓA BỎ IMPORT LỖI PHỤ THUỘC) ---
TRANG_MINI_APP = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌸 Key Store VIP - Cửa Hàng Tự Động</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #ffb6c1, #ff69b4, #ff1493, #ff69b4);
            background-size: 400% 400%; animation: gradientBG 8s ease infinite;
            min-height: 100vh; color: #fff; padding: 15px;
        }
        @keyframes gradientBG { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        .container { max-width: 450px; margin: 0 auto; }
        .header { text-align: center; margin: 15px 0 25px; }
        .header h1 { font-size: 2.2em; text-shadow: 0 0 15px #fff; }
        .user-info { background: rgba(0,0,0,0.3); padding: 10px; border-radius: 12px; margin-bottom: 20px; font-size: 0.95em; text-align: center; border: 1px solid rgba(255,255,255,0.2); }
        .game-card { background: rgba(255, 255, 255, 0.2); backdrop-filter: blur(15px); border-radius: 20px; padding: 20px; margin-bottom: 20px; border: 2px solid rgba(255,255,255,0.3); }
        .game-title { font-size: 1.5em; font-weight: bold; margin-bottom: 5px; text-shadow: 0 0 8px #ff1493; }
        .game-desc { font-size: 0.85em; opacity: 0.9; margin-bottom: 15px; line-height: 1.4; }
        .buy-option { display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.2); padding: 10px; border-radius: 10px; margin-bottom: 8px; }
        .price-label { font-weight: bold; color: #ffd700; }
        .btn-buy { background: linear-gradient(135deg, #ff69b4, #ff1493); border: none; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; cursor: pointer; box-shadow: 0 3px 10px rgba(255,20,147,0.4); }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 100; justify-content: center; align-items: center; }
        .modal-content { background: rgba(255,105,180,0.95); backdrop-filter: blur(20px); border-radius: 20px; padding: 25px; width: 85%; max-width: 360px; text-align: center; border: 2px solid #fff; }
        .key-display { background: rgba(0,0,0,0.5); border-radius: 8px; padding: 12px; font-family: monospace; margin: 15px 0; word-break: break-all; border: 1px dashed white; }
        .btn-close { background: white; color: #ff1493; border: none; padding: 10px 25px; font-weight: bold; border-radius: 20px; cursor: pointer; }
    </style>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌸 Key Store VIP</h1>
            <p>Hệ thống cung cấp mã VIP tự động</p>
        </div>
        <div class="user-info" id="userInfo">Đang xác thực tài khoản Telegram...</div>
        <div id="shopContainer"></div>
    </div>

    <div class="modal" id="keyModal">
        <div class="modal-content">
            <h2 style="font-size:1.6em;">🎉 Giao dịch hoàn tất!</h2>
            <p style="margin-top:5px; font-size:0.9em;">Mã VIP thời hạn của bạn:</p>
            <div class="key-display" id="keyDisplay"></div>
            <button class="btn-close" onclick="document.getElementById('keyModal').style.display='none'">ĐÓNG CỬA SỔ ✨</button>
        </div>
    </div>

    <script>
        let telegramUser = null;
        if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.ready();
            telegramUser = window.Telegram.WebApp.initDataUnsafe?.user;
        }

        async function initShop() {
            let uid = telegramUser ? telegramUser.id : "guest_dev";
            let uname = telegramUser ? (telegramUser.first_name + ' ' + (telegramUser.last_name || '')) : "Khách Thử Nghiệm";
            let username = telegramUser ? (telegramUser.username || '') : "";

            const res = await fetch(`/api/sync_client?uid=${uid}&name=${encodeURIComponent(uname)}&username=${username}`);
            const client = await res.json();
            
            if(client.blocked) {
                document.body.innerHTML = "<div style='text-align:center; margin-top:40vh; font-weight:bold; font-size:1.3em; color:yellow;'>🚫 Tài khoản của bạn đã bị khóa khỏi hệ thống Mini App!</div>";
                return;
            }

            document.getElementById('userInfo').innerHTML = `👤 Khách hàng: <b>${client.name}</b> | 💰 Số dư: <b style="color:#ffd700">${client.balance.toLocaleString()}đ</b>`;

            let shopHtml = '';
            client.catalog.forEach(g => {
                shopHtml += `
                <div class="game-card">
                    <div class="game-title">${g.ten_game}</div>
                    <div class="game-desc">${g.mo_ta || 'Không có mô tả dữ liệu'}</div>
                    
                    <div class="buy-option">
                        <div>⏱ Key Giờ VIP <small style="opacity:0.6">(${g.stock_gio} sẵn)</small></div>
                        <div class="price-label">${g.gia_gio.toLocaleString()}đ</div>
                        <button class="btn-buy" onclick="clickMua('${g.id}', 'gio')">MUA 🛍</button>
                    </div>
                    <div class="buy-option">
                        <div>📆 Key Ngày VIP <small style="opacity:0.6">(${g.stock_ngay} sẵn)</small></div>
                        <div class="price-label">${g.gia_ngay.toLocaleString()}đ</div>
                        <button class="btn-buy" onclick="clickMua('${g.id}', 'ngay')">MUA 🛍</button>
                    </div>
                    <div class="buy-option">
                        <div>🚀 Key Tháng VIP <small style="opacity:0.6">(${g.stock_thang} sẵn)</small></div>
                        <div class="price-label">${g.gia_thang.toLocaleString()}đ</div>
                        <button class="btn-buy" onclick="clickMua('${g.id}', 'thang')">MUA 🛍</button>
                    </div>
                </div>`;
            });
            document.getElementById('shopContainer').innerHTML = shopHtml;
        }

        async function clickMua(gameId, loaiKey) {
            let uid = telegramUser ? telegramUser.id : "guest_dev";
            const res = await fetch('/api/purchase_key', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: uid, game_id: gameId, loai_key: loaiKey})
            });
            const data = await res.json();
            if(data.success) {
                document.getElementById('keyDisplay').textContent = data.key;
                document.getElementById('keyModal').style.display = 'flex';
                initShop();
            } else {
                alert("❌ Lỗi: " + data.message);
            }
        }

        initShop();
    </script>
</body>
</html>
"""

# --- MÁY CHỦ HTTP XỬ LÝ TOÀN BỘ LOGIC ---
class BộXửLýYêuCầu(BaseHTTPRequestHandler):
    def kiem_tra_ddos(self):
        ip_khach = self.client_address[0]
        thoi_gian_hien_tai = time.time()
        if ip_khach in LỊCH_SỬ_REQUEST:
            lich_su = LỊCH_SỬ_REQUEST[ip_khach]
            lich_su = [t for t in lich_su if thoi_gian_hien_tai - t < 1.0]
            LỊCH_SỬ_REQUEST[ip_khach] = lich_su
            if len(lich_su) > 15:
                return False
        else:
            LỊCH_SỬ_REQUEST[ip_khach] = []
        LỊCH_SỬ_REQUEST[ip_khach].append(thoi_gian_hien_tai)
        return True

    def xac_thuc_admin(self):
        cookies_header = self.headers.get('Cookie')
        if cookies_header:
            ck = cookies.SimpleCookie(cookies_header)
            if 'session_id' in ck:
                sid = ck['session_id'].value
                if sid in phiên_đăng_nhập and phiên_đăng_nhập[sid] > time.time():
                    return True
        return False

    def do_GET(self):
        if not self.kiem_tra_ddos():
            self.send_response(429); self.end_headers(); return

        try:
            if self.path in ["/", "/app"]:
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(TRANG_MINI_APP.encode("utf-8"))
                
            elif self.path == "/health":
                self.send_response(200)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write("OK".encode("utf-8"))

            elif self.path.startswith("/api/sync_client"):
                from urllib.parse import urlparse, parse_qs
                query = parse_qs(urlparse(self.path).query)
                uid = query.get('uid', ['guest_dev'])[0]
                name = query.get('name', ['Khách'])[0]
                username = query.get('username', [''])[0]

                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()
                con_tro.execute("SELECT so_du, trang_thai FROM khach_hang WHERE nguoi_dung_id=?", (uid,))
                row = con_tro.fetchone()
                if not row:
                    con_tro.execute("INSERT INTO khach_hang (nguoi_dung_id, ten_nguoi_dung, username, so_du) VALUES (?, ?, ?, 0)", (uid, name, username))
                    kn.commit()
                    so_du, trang_thai = 0, 'hoat_dong'
                else:
                    so_du, trang_thai = row[0], row[1]
                    # Đồng bộ cập nhật lại username mới nếu có thay đổi
                    con_tro.execute("UPDATE khach_hang SET ten_nguoi_dung=?, username=?, ngay_tuong_tac=CURRENT_TIMESTAMP WHERE nguoi_dung_id=?", (name, username, uid))
                    kn.commit()

                # Lấy danh mục game kèm tính số lượng tồn kho của từng thời hạn key
                con_tro.execute("SELECT id, ten_game, mo_ta, gia_gio, gia_ngay, gia_thang FROM san_pham_game")
                games = con_tro.fetchall()
                catalog = []
                for g in games:
                    con_tro.execute("SELECT loai_key, COUNT(*) FROM kho_key_dong WHERE game_id=? AND trang_thai='con_hang' GROUP BY loai_key", (g[0],))
                    stocks = {r[0]: r[1] for r in con_tro.fetchall()}
                    catalog.append({
                        "id": g[0], "ten_game": g[1], "mo_ta": g[2],
                        "gia_gio": g[3], "gia_ngay": g[4], "gia_thang": g[5],
                        "stock_gio": stocks.get('gio', 0),
                        "stock_ngay": stocks.get('ngay', 0),
                        "stock_thang": stocks.get('thang', 0)
                    })
                kn.close()

                res_body = {"name": name, "balance": so_du, "blocked": (trang_thai == 'bi_ban'), "catalog": catalog}
                self.send_response(200)
                self.send_header("Content-type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res_body).encode('utf-8'))

            elif self.path == "/admin":
                if self.xac_thuc_admin():
                    self.send_response(200); self.send_header("Content-type", "text/html; charset=utf-8"); self.end_headers()
                    self.wfile.write(TRANG_BẢNG_ĐIỀU_KHIỂN_ADMIN.encode("utf-8"))
                else:
                    self.send_response(302); self.send_header("Location", "/admin/login"); self.end_headers()

            elif self.path == "/admin/miniapp":
                if self.xac_thuc_admin():
                    self.send_response(200); self.send_header("Content-type", "text/html; charset=utf-8"); self.end_headers()
                    self.wfile.write(TRANG_QUẢN_LÝ_MINIAPP_ADMIN.encode("utf-8"))
                else:
                    self.send_response(302); self.send_header("Location", "/admin/login"); self.end_headers()

            elif self.path == "/admin/login":
                self.send_response(200); self.send_header("Content-type", "text/html; charset=utf-8"); self.end_headers()
                self.wfile.write(TRANG_ĐĂNG_NHẬP_ADMIN.replace("{error_placeholder}", "").encode("utf-8"))

            elif self.path == "/admin/logout":
                self.send_response(302); self.send_header("Set-Cookie", "session_id=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/"); self.send_header("Location", "/admin/login"); self.end_headers()

            elif self.path == "/api/admin/users":
                if not self.xac_thuc_admin():
                    self.send_response(401); self.end_headers(); return
                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()
                con_tro.execute("SELECT nguoi_dung_id, ten_nguoi_dung, username, so_du, trang_thai FROM khach_hang ORDER BY ngay_tuong_tac DESC")
                users = [{"id": r[0], "ten": r[1], "username": r[2], "so_du": r[3], "trang_thai": r[4]} for r in con_tro.fetchall()]
                kn.close()
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(users).encode('utf-8'))

            elif self.path == "/api/admin/games_dashboard":
                if not self.xac_thuc_admin():
                    self.send_response(401); self.end_headers(); return
                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()
                con_tro.execute("SELECT id, ten_game, mo_ta, gia_gio, gia_ngay, gia_thang FROM san_pham_game")
                games = [{"id": r[0], "ten_game": r[1], "mo_ta": r[2], "gia_gio": r[3], "gia_ngay": r[4], "gia_thang": r[5]} for r in con_tro.fetchall()]
                
                con_tro.execute("SELECT game_id, loai_key, COUNT(*) FROM kho_key_dong WHERE trang_thai='con_hang' GROUP BY game_id, loai_key")
                counts = {}
                for r in con_tro.fetchall():
                    if r[0] not in counts: counts[r[0]] = {}
                    counts[r[0]][r[1]] = r[2]
                kn.close()
                
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"games": games, "counts": counts}).encode('utf-8'))
            else:
                self.send_response(404); self.end_headers()
        except Exception as e:
            bộ_ghi_nhật_ký.error(f"Lỗi GET Router: {e}")
            self.send_response(500); self.end_headers()

    def do_POST(self):
        if not self.kiem_tra_ddos():
            self.send_response(429); self.end_headers(); return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)

            if self.path == "/admin/login":
                params = parse_qs(post_data.decode('utf-8'))
                u = params.get('username', [''])[0]
                p = params.get('password', [''])[0]
                if u == ADMIN_USER and p == ADMIN_PASS:
                    sid = str(uuid.uuid4())
                    phiên_đăng_nhập[sid] = time.time() + 3600
                    self.send_response(302); self.send_header("Set-Cookie", f"session_id={sid}; Path=/; HttpOnly"); self.send_header("Location", "/admin"); self.end_headers()
                else:
                    self.send_response(200); self.send_header("Content-type", "text/html; charset=utf-8"); self.end_headers()
                    err_msg = '<div class="error">❌ Sai tài khoản hoặc mật khẩu!</div>'
                    self.wfile.write(TRANG_ĐĂNG_NHẬP_ADMIN.replace("{error_placeholder}", err_msg).encode("utf-8"))

            elif self.path == "/api/purchase_key":
                req = json.loads(post_data.decode('utf-8'))
                uid = req.get('user_id')
                game_id = req.get('game_id')
                loai_key = req.get('loai_key') # 'gio', 'ngay', 'thang'

                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()
                
                # Kiểm tra trạng thái block tài khoản
                con_tro.execute("SELECT so_du, trang_thai FROM khach_hang WHERE nguoi_dung_id=?", (uid,))
                user_row = con_tro.fetchone()
                if user_row and user_row[1] == 'bi_ban':
                    self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "message": "Tài khoản bị khóa!"}).encode('utf-8'))
                    kn.close(); return

                # Nhận diện cấu hình giá tiền tương ứng
                con_tro.execute("SELECT gia_gio, gia_ngay, gia_thang FROM san_pham_game WHERE id=?", (game_id,))
                g_row = con_tro.fetchone()
                
                gia = 0
                if loai_key == 'gio': gia = g_row[0]
                elif loai_key == 'ngay': gia = g_row[1]
                elif loai_key == 'thang': gia = g_row[2]

                so_du_hien_tai = user_row[0] if user_row else 0
                if so_du_hien_tai < gia:
                    self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "message": "Số dư không đủ, vui lòng liên hệ Admin để nạp tiền!"}).encode('utf-8'))
                    kn.close(); return

                # Tìm và bốc key ra khỏi kho hàng
                con_tro.execute("SELECT id, ma_key FROM kho_key_dong WHERE game_id=? AND loai_key=? AND trang_thai='con_hang' LIMIT 1", (game_id, loai_key))
                k_row = con_tro.fetchone()
                
                if k_row:
                    kid, key_val = k_row[0], k_row[1]
                    # Trừ tiền tài khoản, cập nhật trạng thái Key sang đã bán
                    con_tro.execute("UPDATE khach_hang SET so_du = so_du - ? WHERE nguoi_dung_id=?", (gia, uid))
                    con_tro.execute("UPDATE kho_key_dong SET trang_thai='da_ban', nguoi_mua=?, ngay_ban=? WHERE id=?", (uid, datetime.now().isoformat(), kid))
                    kn.commit()
                    res = {"success": True, "key": key_val}
                else:
                    res = {"success": False, "message": "Thời hạn key này hiện tại đang hết hàng!"}
                
                kn.close()
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(res).encode('utf-8'))

            # --- API CHỨC NĂNG QUẢN TRỊ ADMIN ---
            elif self.path in ["/api/admin/deposit", "/api/admin/ban", "/api/admin/add_game", "/api/admin/import_keys"]:
                if not self.xac_thuc_admin():
                    self.send_response(401); self.end_headers(); return
                
                req = json.loads(post_data.decode('utf-8'))
                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()

                if self.path == "/api/admin/deposit":
                    uid = req.get('user_id')
                    amt = float(req.get('amount', 0))
                    con_tro.execute("UPDATE khach_hang SET so_du = so_du + ? WHERE nguoi_dung_id=?", (amt, uid))
                    kn.commit()

                elif self.path == "/api/admin/ban":
                    uid = req.get('user_id')
                    status = req.get('status') # 'hoat_dong' or 'bi_ban'
                    con_tro.execute("UPDATE khach_hang SET trang_thai=? WHERE nguoi_dung_id=?", (status, uid))
                    kn.commit()

                elif self.path == "/api/admin/add_game":
                    t_game = req.get('ten_game')
                    m_ta = req.get('mo_ta', '')
                    g_gio = float(req.get('gia_gio', 0))
                    g_ngay = float(req.get('gia_ngay', 0))
                    g_thang = float(req.get('gia_thang', 0))
                    con_tro.execute("INSERT INTO san_pham_game (id, ten_game, mo_ta, gia_gio, gia_ngay, gia_thang) VALUES (?, ?, ?, ?, ?, ?)",
                                    (str(uuid.uuid4()), t_game, m_ta, g_gio, g_ngay, g_thang))
                    kn.commit()

                elif self.path == "/api/admin/import_keys":
                    gid = req.get('game_id')
                    l_key = req.get('loai_key')
                    txt_keys = req.get('danh_sach_key', '')
                    arr_keys = [k.strip() for k in txt_keys.split('\n') if k.strip()]
                    
                    inserted = 0
                    for k_val in arr_keys:
                        try:
                            con_tro.execute("INSERT INTO kho_key_dong (id, game_id, loai_key, ma_key) VALUES (?, ?, ?, ?)",
                                            (str(uuid.uuid4()), gid, l_key, k_val))
                            inserted += 1
                        except Exception: pass
                    kn.commit()
                    kn.close()
                    self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                    self.wfile.write(json.dumps({"success": True, "count": inserted}).encode('utf-8'))
                    return

                kn.close()
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            else:
                self.send_response(404); self.end_headers()
        except Exception as e:
            bộ_ghi_nhật_ký.error(f"Lỗi POST Router: {e}")
            self.send_response(500); self.end_headers()

def chạy_máy_chủ_http(cổng=10000):
    may_chu = HTTPServer(('0.0.0.0', cổng), BộXửLýYêuCầu)
    bộ_ghi_nhật_ký.info(f"Máy chủ HTTP hoạt động tại cổng {cổng}")
    may_chu.serve_forever()

# --- CHỨC NĂNG PHÍA TELEGRAM BOT (TÍCH HỢP CHẶN USER BAN) ---
async def bắt_đầu(cập_nhật: Update, ngữ_cảnh: ContextTypes.DEFAULT_TYPE) -> None:
    uid = str(cập_nhật.effective_user.id)
    uname = cập_nhật.effective_user.first_name or "User"
    username = cập_nhật.effective_user.username or ""

    kn = sqlite3.connect("he_thong_ban_key.db")
    con_tro = kn.cursor()
    con_tro.execute("SELECT trang_thai FROM khach_hang WHERE nguoi_dung_id=?", (uid,))
    row = con_tro.fetchone()
    
    # Kiểm tra chặn tương tác Bot lập tức nếu bị Band
    if row and row[0] == 'bi_ban':
        await cập_nhật.message.reply_text("🚫 Tài khoản của bạn đã bị quản trị viên chặn khỏi hệ thống này!")
        kn.close(); return

    if not row:
        con_tro.execute("INSERT INTO khach_hang (nguoi_dung_id, ten_nguoi_dung, username, so_du) VALUES (?, ?, ?, 0)", (uid, uname, username))
        kn.commit()
    kn.close()

    ban_phim = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌸 MỞ CỬA HÀNG KEY 🌸", web_app=WebAppInfo(url=f"{URL_ỨNG_DỤNG}/app"))]
    ])
    await cập_nhật.message.reply_text(
        "╔══════════════════════╗\n║  🌸 KEY STORE VIP 🌸  ║\n╚══════════════════════╝\n\n"
        "💖 Chào mừng bạn quay trở lại với cửa hàng phân phối Key VIP tự động!\n✨ Hãy bấm vào nút dưới đây để mở giao diện Mini App ngay:",
        parse_mode="HTML", reply_markup=ban_phim
    )

# --- NÂNG CẤP MẠCH ĐẬP CHỐNG NGỦ ĐÔNG THÔNG MINH ĐỘC LẬP TỰ ĐỘNG ---
async def tự_ping_duy_trì_sự_sống(app: Application):
    import aiohttp
    await asyncio.sleep(10)
    while True:
        try:
            # Tự kích hoạt ping nội bộ vòng lặp không phụ thuộc lưu lượng bên ngoài
            async with aiohttp.ClientSession() as phiên:
                async with phiên.get(f"http://127.0.0.1:10000/health", timeout=5) as phản_hồi:
                    if phản_hồi.status == 200:
                        bộ_ghi_nhật_ký.info("⚡ [Mạch Sống Render]: Chu kỳ giữ luồng luôn thức hoạt động tốt 100%.")
        except Exception as e:
            bộ_ghi_nhật_ký.error(f"Lỗi đồng bộ giữ luồng: {e}")
        await asyncio.sleep(120) # Tự ping 2 phút một lần để chống Render đưa vào chế độ ngủ

async def khoi_tao_kem_ping(application: Application) -> None:
    asyncio.create_task(tự_ping_duy_trì_sự_sống(application))

# --- Hàm khởi chạy ứng dụng chính ---
def main():
    global bot_app
    luong_http = threading.Thread(target=chạy_máy_chủ_http, args=(10000,), daemon=True)
    luong_http.start()
    
    bot_app = Application.builder().token(MÃ_TOKEN).post_init(khoi_tao_kem_ping).build()
    bot_app.add_handler(CommandHandler("start", bắt_đầu))
    
    bộ_ghi_nhật_ký.info("🌸 Hệ thống Key Store động và Web Quản trị đang hoạt động...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
