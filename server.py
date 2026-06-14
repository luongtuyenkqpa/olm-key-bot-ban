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

# --- Các thư viện Telegram ---
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Cấu hình ghi nhật ký ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
bộ_ghi_nhật_ký = logging.getLogger(__name__)

# Token bot và URL ứng dụng
MÃ_TOKEN = "8621133442:AAFhgCT-rpiR-Ahp1gXKZVjMwm-kfyoSIaE"
URL_ỨNG_DỤNG = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app-url.onrender.com") # Sửa lại URL Render của bạn nếu cần

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
    
    con_trỏ.execute('''
        CREATE TABLE IF NOT EXISTS kho_key_dong (
            id TEXT PRIMARY KEY,
            game_id TEXT,
            loai_key TEXT,
            ma_key TEXT UNIQUE,
            trang_thai TEXT DEFAULT 'con_hang',
            nguoi_mua TEXT,
            ngay_ban TEXT
        )
    ''')

    con_trỏ.execute("SELECT COUNT(*) FROM san_pham_game")
    if con_trỏ.fetchone()[0] == 0:
        con_trỏ.execute("INSERT INTO san_pham_game VALUES ('game_default', 'NgoTran ⚡', 'API Ổn định, chống ban', 10000, 20000, 150000)")

    kết_nối.commit()
    kết_nối.close()

khởi_tạo_cơ_sở_dữ_liệu()

bot_app = None

# --- GIAO DIỆN WEB CSS CHUNG (CHO ADMIN) ---
GIAO_DIỆN_CHUNG_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background: linear-gradient(135deg, #1a0033, #330066, #4d0099);
        min-height: 100vh; color: #fff; overflow-x: hidden;
    }
    .main-box {
        position: relative; z-index: 2; background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(15px); border-radius: 20px; border: 1px solid rgba(255,255,255,0.1);
    }
    .nav-tabs { display: flex; gap: 10px; margin-bottom: 20px; }
    .nav-tabs a {
        padding: 10px 20px; background: rgba(255,255,255,0.1); border-radius: 10px;
        color: white; text-decoration: none; font-weight: bold; transition: 0.3s;
    }
    .nav-tabs a.active, .nav-tabs a:hover { background: #b829ea; box-shadow: 0 0 10px #b829ea; }
"""

TRANG_ĐĂNG_NHẬP_ADMIN = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><title>Đăng nhập Quản trị viên</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        {GIAO_DIỆN_CHUNG_CSS}
        .login-container {{ width: 90%; max-width: 400px; margin: 15vh auto; padding: 30px; text-align: center; }}
        h2 {{ margin-bottom: 20px; text-shadow: 0 0 15px #b829ea; }}
        .input-group {{ margin-bottom: 15px; text-align: left; }}
        label {{ font-weight: bold; font-size: 0.9em; opacity: 0.8; }}
        input {{ width: 100%; padding: 12px; margin-top: 5px; border-radius: 10px; border: none; outline: none; background: rgba(0,0,0,0.3); color: white; font-size: 1em; }}
        .btn-submit {{
            width: 100%; padding: 12px; border: none; border-radius: 50px; margin-top: 15px;
            background: linear-gradient(135deg, #b829ea, #7a00cc); color: white; font-weight: bold; cursor: pointer;
            box-shadow: 0 5px 15px rgba(184, 41, 234, 0.4); transition: 0.3s;
        }}
    </style>
</head>
<body>
    <div class="main-box login-container">
        <h2>🛠 HỆ THỐNG ADMIN</h2>
        {{error_placeholder}}
        <form method="POST" action="/admin/login">
            <div class="input-group"><label>Tài khoản</label><input type="text" name="username" required></div>
            <div class="input-group"><label>Mật khẩu</label><input type="password" name="password" required></div>
            <button type="submit" class="btn-submit">ĐĂNG NHẬP</button>
        </form>
    </div>
</body>
</html>
"""

TRANG_BẢNG_ĐIỀU_KHIỂN_ADMIN = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><title>Hệ Thống Quản Trị</title>
    <style>
        {GIAO_DIỆN_CHUNG_CSS}
        .container {{ max-width: 1100px; margin: 30px auto; padding: 20px; position: relative; z-index: 2; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }}
        .btn-logout {{ padding: 10px 20px; background: rgba(255,255,255,0.1); color: #fff; border-radius: 20px; text-decoration: none; font-weight: bold; border: 1px solid rgba(255,255,255,0.2); }}
        .card {{ padding: 20px; margin-bottom: 20px; overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; background: rgba(0,0,0,0.2); border-radius: 10px; overflow: hidden; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); white-space: nowrap; }}
        th {{ background: rgba(0,0,0,0.4); color: #b829ea; }}
        input[type="number"], input[type="text"] {{ padding: 6px; border-radius: 5px; border: none; width: 100px; margin-right: 5px; background: rgba(255,255,255,0.8); }}
        .btn-action {{ padding: 6px 12px; border: none; border-radius: 5px; color: white; cursor: pointer; font-weight: bold; }}
        .btn-add {{ background: #00cdfe; }} .btn-ban {{ background: #ff0055; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛠 ADMIN DASHBOARD</h1>
            <a href="/admin/logout" class="btn-logout">Đăng xuất</a>
        </div>
        <div class="nav-tabs">
            <a href="/admin" class="active">👥 Quản lý thành viên</a>
            <a href="/admin/miniapp">🎮 Quản lý Sản Phẩm & Key</a>
        </div>
        <div class="main-box card">
            <h3>👥 DANH SÁCH THÀNH VIÊN</h3>
            <table>
                <thead>
                    <tr>
                        <th>ID</th><th>Tên</th><th>Username</th><th>Số Dư</th><th>Nạp Tiền</th><th>Khóa/Mở</th>
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
                    <td>${{u.id}}</td><td><b>${{u.ten}}</b></td><td>${{u.username ? '@' + u.username : '---'}}</td>
                    <td style="color:#00ffcc; font-weight:bold;">${{u.so_du.toLocaleString()}}đ</td>
                    <td><input type="number" id="amt-${{u.id}}" placeholder="VND..."><button class="btn-action btn-add" onclick="napTien('${{u.id}}')">Nạp</button></td>
                    <td><button class="btn-action btn-ban" onclick="doiTrangThai('${{u.id}}', '${{u.trang_thai}}')">${{u.trang_thai === 'hoat_dong' ? 'Khóa 🚫' : 'Mở ✅'}}</button></td>
                </tr>`;
            }});
            document.getElementById('tableUsers').innerHTML = html;
        }}
        async function napTien(uid) {{
            const val = document.getElementById(`amt-${{uid}}`).value;
            if(!val) return;
            await fetch('/api/admin/deposit', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{user_id: uid, amount: val}}) }});
            alert("✅ Nạp tiền thành công!"); taiThongTin();
        }}
        async function doiTrangThai(uid, current) {{
            const nextIdx = current === 'hoat_dong' ? 'bi_ban' : 'hoat_dong';
            await fetch('/api/admin/ban', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{user_id: uid, status: nextIdx}}) }});
            taiThongTin();
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
    <meta charset="UTF-8"><title>Quản lý Sản Phẩm</title>
    <style>
        {GIAO_DIỆN_CHUNG_CSS}
        .container {{ max-width: 1100px; margin: 30px auto; padding: 20px; position: relative; z-index: 2; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
        @media (max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
        .card {{ padding: 20px; }}
        label {{ display: block; font-size: 0.9em; margin: 8px 0 4px; font-weight: bold; color: #e0aaff; }}
        input, select, textarea {{ width: 100%; padding: 10px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2); background: rgba(0,0,0,0.3); color: white; margin-bottom: 5px; }}
        button {{ padding: 12px; background: linear-gradient(135deg, #b829ea, #7a00cc); border: none; color: #fff; font-weight: bold; border-radius: 8px; cursor: pointer; width: 100%; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📦 QUẢN LÝ SẢN PHẨM & KEY</h1>
            <a href="/admin/logout" class="nav-tabs a" style="color:white; text-decoration:none;">Đăng xuất</a>
        </div>
        <div class="nav-tabs">
            <a href="/admin">👥 Quản lý thành viên</a>
            <a href="/admin/miniapp" class="active">🎮 Quản lý Sản Phẩm & Key</a>
        </div>
        <div class="grid">
            <div class="main-box card">
                <h3>Thêm / Sửa Sản Phẩm</h3>
                <form id="formGame">
                    <label>Tên Sản Phẩm (VD: NgoTran, Beyond)</label><input type="text" name="ten_game" required>
                    <label>Mô tả ngắn</label><input type="text" name="mo_ta" placeholder="API ổn định...">
                    <label>Giá 1 Giờ (VND)</label><input type="number" name="gia_gio" value="5000" required>
                    <label>Giá 1 Ngày (VND)</label><input type="number" name="gia_ngay" value="20000" required>
                    <label>Giá 1 Tháng (VND)</label><input type="number" name="gia_thang" value="150000" required>
                    <button type="submit" style="margin-top:10px;">LƯU SẢN PHẨM</button>
                </form>
            </div>
            <div class="main-box card">
                <h3>Thêm Kho Key</h3>
                <form id="formAddKey">
                    <label>Chọn Sản Phẩm</label><select name="game_id" id="selectGame" required></select>
                    <label>Thời hạn</label>
                    <select name="loai_key"><option value="gio">1 Giờ</option><option value="ngay">1 Ngày</option><option value="thang">1 Tháng</option></select>
                    <label>Danh sách Key (Mỗi key 1 dòng)</label><textarea name="danh_sach_key" rows="5" required></textarea>
                    <button type="submit" style="margin-top:10px; background:linear-gradient(135deg, #00cbfe, #0076fe);">NHẬP KHO</button>
                </form>
            </div>
        </div>
        <div class="main-box card" style="overflow-x: auto;">
            <h3>📊 KHO HÀNG HIỆN TẠI</h3>
            <table style="width: 100%;">
                <thead><tr><th>Sản Phẩm</th><th>Giá Giờ</th><th>Giá Ngày</th><th>Giá Tháng</th><th>Tồn Kho</th></tr></thead>
                <tbody id="tableGames"></tbody>
            </table>
        </div>
    </div>
    <script>
        async function loadData() {{
            const res = await fetch('/api/admin/games_dashboard');
            const data = await res.json();
            document.getElementById('selectGame').innerHTML = data.games.map(g => `<option value="${{g.id}}">${{g.ten_game}}</option>`).join('');
            document.getElementById('tableGames').innerHTML = data.games.map(g => `<tr>
                <td><b>${{g.ten_game}}</b><br><small style="opacity:0.6">${{g.mo_ta}}</small></td>
                <td>${{g.gia_gio.toLocaleString()}}đ</td><td>${{g.gia_ngay.toLocaleString()}}đ</td><td>${{g.gia_thang.toLocaleString()}}đ</td>
                <td>Giờ: ${{data.counts[g.id]?.gio||0}} | Ngày: ${{data.counts[g.id]?.ngay||0}} | Tháng: ${{data.counts[g.id]?.thang||0}}</td>
            </tr>`).join('');
        }}
        document.getElementById('formGame').onsubmit = async (e) => {{
            e.preventDefault();
            await fetch('/api/admin/add_game', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(Object.fromEntries(new FormData(e.target))) }});
            alert("✅ Đã lưu sản phẩm!"); e.target.reset(); loadData();
        }};
        document.getElementById('formAddKey').onsubmit = async (e) => {{
            e.preventDefault();
            const res = await fetch('/api/admin/import_keys', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(Object.fromEntries(new FormData(e.target))) }});
            const data = await res.json(); alert(`✅ Nhập thành công: ${{data.count}} Key!`); e.target.reset(); loadData();
        }};
        loadData();
    </script>
</body>
</html>
"""

# --- GIAO DIỆN MINI APP ĐƯỢC LÀM LẠI HOÀN TOÀN GIỐNG ẢNH ---
TRANG_MINI_APP = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>ALEX SHOP</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg-dark: #12002b;
            --card-bg: rgba(255, 255, 255, 0.05);
            --card-border: rgba(255, 255, 255, 0.1);
            --primary: #c850c0;
            --primary-gradient: linear-gradient(135deg, #c850c0 0%, #4158d0 100%);
            --text-main: #ffffff;
            --text-sub: #a0a0b8;
            --nav-bg: rgba(18, 0, 43, 0.95);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; -webkit-tap-highlight-color: transparent; }
        body { background-color: var(--bg-dark); color: var(--text-main); height: 100vh; overflow: hidden; position: relative; }
        
        /* Hiệu ứng cánh hoa rơi */
        .petals { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 0; overflow: hidden; }
        .petal { position: absolute; background: rgba(255, 150, 200, 0.3); border-radius: 150% 0 150% 0; box-shadow: 0 0 10px rgba(255,100,200,0.2); animation: falling linear infinite; }
        @keyframes falling {
            0% { transform: translateY(-10vh) rotate(0deg) scale(0.5); opacity: 0; }
            10% { opacity: 1; }
            90% { opacity: 1; }
            100% { transform: translateY(100vh) rotate(360deg) scale(1.2); opacity: 0; }
        }

        /* Top Header */
        .header { display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; background: transparent; z-index: 10; position: relative; border-bottom: 1px solid var(--card-border); }
        .header-logo { display: flex; align-items: center; gap: 10px; }
        .header-logo img { width: 40px; height: 40px; border-radius: 50%; border: 2px solid var(--primary); }
        .header-text { line-height: 1.2; }
        .header-text small { color: var(--primary); font-size: 10px; font-weight: bold; letter-spacing: 1px; }
        .header-text h2 { font-size: 16px; font-weight: 900; text-transform: uppercase; }
        .header-right { display: flex; align-items: center; gap: 10px; }
        .lang-btn { background: var(--card-bg); border: 1px solid var(--card-border); color: white; padding: 5px 10px; border-radius: 15px; font-size: 12px; }
        .user-avatar { width: 35px; height: 35px; background: var(--primary-gradient); border-radius: 50%; display: flex; justify-content: center; align-items: center; font-weight: bold; }

        /* Main Scroll Area */
        .main-content { height: calc(100vh - 140px); overflow-y: auto; padding: 15px; position: relative; z-index: 1; padding-bottom: 80px;}
        .tab-section { display: none; animation: fadeIn 0.3s; }
        .tab-section.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        /* Components chung */
        .glass-card { background: var(--card-bg); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid var(--card-border); border-radius: 16px; padding: 15px; margin-bottom: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
        .section-title { font-size: 16px; font-weight: bold; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
        .text-gradient { background: var(--primary-gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .icon-circle { width: 30px; height: 30px; border-radius: 50%; display: flex; justify-content: center; align-items: center; background: rgba(200, 80, 192, 0.2); color: #ff80ff;}

        /* Tab Home */
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px; }
        .stat-box { text-align: center; padding: 15px 10px; }
        .stat-val { font-size: 20px; font-weight: bold; color: #00e6e6; margin-bottom: 5px; }
        .stat-label { font-size: 12px; color: var(--text-sub); }
        .step-list { display: flex; flex-direction: column; gap: 10px; }
        .step-item { display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3); padding: 12px 15px; border-radius: 10px; }
        .step-num { width: 25px; height: 25px; border-radius: 50%; background: var(--primary-gradient); display: flex; justify-content: center; align-items: center; font-size: 12px; font-weight: bold; }
        .system-status { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--card-border); }
        .system-status:last-child { border-bottom: none; }
        .status-badge { background: rgba(0, 255, 100, 0.2); color: #00ff88; padding: 3px 10px; border-radius: 12px; font-size: 12px; border: 1px solid #00ff88; }

        /* Tab Shop (Mua key) */
        .shop-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .product-card { display: flex; align-items: center; gap: 10px; padding: 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); border-radius: 12px; cursor: pointer; transition: 0.2s; }
        .product-card:active { transform: scale(0.95); background: rgba(255,255,255,0.1); }
        .product-icon { width: 40px; height: 40px; border-radius: 10px; background: var(--card-bg); display: flex; justify-content: center; align-items: center; font-size: 20px;}
        .product-info h4 { font-size: 14px; margin-bottom: 3px; }
        .product-info p { font-size: 11px; color: var(--text-sub); }

        /* Màn hình chi tiết sản phẩm */
        #product-details { display: none; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: var(--bg-dark); z-index: 20; flex-direction: column; }
        .pd-header { display: flex; align-items: center; padding: 15px; border-bottom: 1px solid var(--card-border); background: var(--nav-bg); }
        .pd-back { background: none; border: none; color: white; font-size: 24px; margin-right: 15px; cursor: pointer; }
        .duration-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; padding: 15px; }
        .duration-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 15px; padding: 20px 10px; text-align: center; cursor: pointer; transition: 0.2s; }
        .duration-card.selected { background: rgba(200, 80, 192, 0.3); border-color: var(--primary); box-shadow: 0 0 15px rgba(200, 80, 192, 0.4); }
        .duration-card h3 { font-size: 16px; margin-bottom: 5px; color: #fff; }
        .duration-card p { font-size: 14px; color: #ff80ff; font-weight: bold; }
        .buy-action-bar { position: absolute; bottom: 0; left: 0; width: 100%; padding: 20px; background: var(--nav-bg); border-top: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center; }
        .buy-price { font-size: 22px; font-weight: bold; color: white; }
        .btn-buy-now { background: var(--primary-gradient); border: none; padding: 12px 30px; border-radius: 25px; color: white; font-weight: bold; font-size: 16px; cursor: pointer; }

        /* Tab Nạp tiền */
        .deposit-tabs { display: flex; background: rgba(0,0,0,0.5); border-radius: 12px; padding: 5px; margin-bottom: 20px; }
        .dt-btn { flex: 1; padding: 10px; text-align: center; color: var(--text-sub); border-radius: 8px; font-size: 14px; font-weight: bold; }
        .dt-btn.active { background: var(--card-bg); color: white; }
        .balance-display { padding: 15px; margin-bottom: 20px; }
        .balance-display p { font-size: 14px; color: var(--text-sub); }
        .balance-display h2 { font-size: 32px; font-weight: bold; margin-top: 5px; }
        .amount-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }
        .amount-btn { padding: 15px; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; color: white; text-align: center; font-weight: bold; font-size: 16px; }
        .amount-btn.active { background: var(--primary-gradient); border: none; }

        /* Tab Profile */
        .profile-header { text-align: center; padding: 20px 0; }
        .profile-avatar { width: 80px; height: 80px; background: var(--primary-gradient); border-radius: 50%; margin: 0 auto 10px; display: flex; justify-content: center; align-items: center; font-size: 30px; font-weight: bold; border: 3px solid rgba(255,255,255,0.2); }
        .menu-list { display: flex; flex-direction: column; gap: 10px; }
        .menu-item { display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 20px; text-align: center; gap: 10px; }
        .menu-item .icon { font-size: 24px; color: #ff80ff; }

        /* Music Player Floating */
        .music-player { position: absolute; bottom: 85px; right: 15px; background: rgba(30, 20, 50, 0.95); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 10px 15px; display: flex; align-items: center; gap: 10px; z-index: 50; box-shadow: 0 5px 20px rgba(0,0,0,0.5); width: calc(100% - 100px); max-width: 280px; }
        .disk { width: 40px; height: 40px; border-radius: 50%; background: #000; display: flex; justify-content: center; align-items: center; animation: spin 4s linear infinite; }
        .disk::after { content: ''; width: 10px; height: 10px; background: #333; border-radius: 50%; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        .music-info h4 { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 150px; }
        .music-info p { font-size: 10px; color: var(--text-sub); }

        /* Bottom Navigation */
        .bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; height: 70px; background: var(--nav-bg); backdrop-filter: blur(20px); border-top: 1px solid var(--card-border); display: flex; justify-content: space-around; align-items: center; z-index: 100; padding-bottom: env(safe-area-inset-bottom); }
        .nav-item { display: flex; flex-direction: column; align-items: center; gap: 5px; color: var(--text-sub); font-size: 11px; text-decoration: none; cursor: pointer; width: 20%; transition: 0.2s;}
        .nav-item.active { color: var(--primary); }
        .nav-icon { font-size: 20px; margin-bottom: 2px;}
        .nav-item.active .nav-icon { filter: drop-shadow(0 0 5px var(--primary)); transform: translateY(-2px);}

        /* Custom Alert */
        .alert-box { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.8); border: 1px solid var(--primary); padding: 15px 20px; border-radius: 12px; z-index: 999; display: none; text-align: center; width: 80%; backdrop-filter: blur(5px);}
    </style>
</head>
<body>
    <div class="petals" id="petals-container"></div>
    
    <div id="alertBox" class="alert-box"></div>

    <div class="header">
        <div class="header-logo">
            <img src="https://ui-avatars.com/api/?name=ALEX&background=12002b&color=c850c0" alt="Logo">
            <div class="header-text">
                <small>DESIGN BY ALEXLASVEGAS</small>
                <h2>ALEX SHOP</h2>
            </div>
        </div>
        <div class="header-right">
            <div class="lang-btn">文A VI</div>
            <div class="user-avatar" id="topAvatar">LT</div>
        </div>
    </div>

    <div class="main-content">
        
        <div id="tab-home" class="tab-section active">
            <div class="stats-grid">
                <div class="glass-card stat-box">
                    <div class="stat-val">0</div>
                    <div class="stat-label">Đơn pending</div>
                </div>
                <div class="glass-card stat-box">
                    <div class="stat-val">0</div>
                    <div class="stat-label">Key còn hạn</div>
                </div>
                <div class="glass-card stat-box" style="grid-column: span 2;">
                    <div class="stat-val" style="color: #ffb3ff;" id="homeBalance">0đ</div>
                    <div class="stat-label">Số dư hiện tại</div>
                </div>
            </div>

            <div class="glass-card">
                <div class="section-title"><div class="icon-circle">⏱</div> Hướng dẫn nhanh</div>
                <p style="font-size: 12px; color: var(--text-sub); margin-bottom: 15px;">Luồng mua key gọn nhất</p>
                <div class="step-list">
                    <div class="step-item"><div class="step-num">1</div><span>Chọn sản phẩm</span></div>
                    <div class="step-item"><div class="step-num">2</div><span style="opacity:0.5">Chọn thời hạn</span></div>
                    <div class="step-item"><div class="step-num">3</div><span style="opacity:0.5">Thanh toán</span></div>
                    <div class="step-item"><div class="step-num">4</div><span style="opacity:0.5">Nhận key</span></div>
                </div>
            </div>

            <div class="glass-card">
                <div class="section-title"><div class="icon-circle">📊</div> Trạng thái hệ thống</div>
                <div class="system-status"><span>NgoTran</span><span class="status-badge">Ổn định</span></div>
                <div class="system-status"><span>Beyond</span><span class="status-badge">Ổn định</span></div>
            </div>
        </div>

        <div id="tab-shop" class="tab-section">
            <div class="glass-card" style="padding: 10px 15px; margin-bottom: 15px; display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size: 14px; font-weight:bold;">Danh mục sản phẩm</span>
            </div>
            <div class="shop-grid" id="catalogContainer">
                </div>
        </div>

        <div id="tab-deposit" class="tab-section">
            <div class="deposit-tabs">
                <div class="dt-btn active">Nạp tiền (Admin)</div>
                <div class="dt-btn">Gạch thẻ tự động</div>
            </div>
            <div class="glass-card balance-display">
                <p>Số dư hiện tại</p>
                <h2 id="depoBalance">0đ</h2>
            </div>
            <div class="glass-card">
                <p style="font-size: 14px; text-align:center; color: #ffb3ff; line-height: 1.5;">
                    Hệ thống Nạp tự động đang bảo trì.<br><br>
                    Vui lòng liên hệ Admin <b>@Lynh</b> để nạp tiền vào tài khoản!<br>
                    ID của bạn: <span id="depoUid" style="color:white;font-weight:bold;">Đang tải...</span>
                </p>
            </div>
        </div>

        <div id="tab-keys" class="tab-section">
            <div class="glass-card">
                <div class="section-title"><div class="icon-circle">🔑</div> Key của tôi</div>
                <p style="font-size: 12px; color: var(--text-sub);">Tab riêng cho danh sách key đã mua</p>
                
                <div class="deposit-tabs" style="margin-top: 15px;">
                    <div class="dt-btn active" style="border-radius:20px;">Tất cả</div>
                    <div class="dt-btn" style="border-radius:20px;">Còn hạn</div>
                    <div class="dt-btn" style="border-radius:20px;">Hết hạn</div>
                </div>

                <div style="text-align: center; padding: 40px 20px; opacity: 0.6;">
                    <div style="font-size: 40px; margin-bottom: 10px;">🔑</div>
                    <h4 style="margin-bottom: 5px;">Không có key phù hợp</h4>
                    <p style="font-size: 12px;">Key đã mua từ bot Telegram sẽ hiển thị tại đây.</p>
                </div>
            </div>
        </div>

        <div id="tab-account" class="tab-section">
            <div class="glass-card">
                <div class="profile-header">
                    <div class="profile-avatar" id="accAvatar">LT</div>
                    <h3 id="accName">User</h3>
                    <p style="font-size:12px; color:var(--text-sub); margin-top:5px;">Thành viên ALEX SHOP</p>
                </div>
            </div>
            <div class="menu-list">
                <div class="glass-card menu-item"><div class="icon">🧾</div><span>Đơn hàng</span></div>
                <div class="glass-card menu-item"><div class="icon">🎧</div><span>Hỗ trợ</span></div>
                <div class="glass-card menu-item"><div class="icon">🔄</div><span>Lịch sử nạp</span></div>
            </div>
        </div>

    </div> <div id="product-details">
        <div class="pd-header">
            <button class="pd-back" onclick="closeProductDetail()">←</button>
            <h3 id="pd-title">Tên Sản Phẩm</h3>
        </div>
        <div style="padding: 15px; flex:1; overflow-y:auto; padding-bottom: 100px;">
            <div class="glass-card" style="display:flex; align-items:center; gap: 15px;">
                <div class="product-icon" style="width:50px; height:50px; font-size:25px;" id="pd-icon">🎮</div>
                <div>
                    <h3 id="pd-name" style="margin-bottom:5px;">Sản Phẩm</h3>
                    <p style="font-size:12px; color:var(--text-sub);" id="pd-desc">Mô tả</p>
                </div>
            </div>
            
            <h4 style="margin: 20px 0 10px; font-size: 14px;">Chọn thời hạn:</h4>
            <div class="duration-grid">
                <div class="duration-card" onclick="selectDuration('gio')" id="card-gio">
                    <h3>1 Giờ</h3><p id="price-gio">--đ</p><small id="stock-gio" style="font-size:10px;color:#00ff88;">Sẵn sàng</small>
                </div>
                <div class="duration-card selected" onclick="selectDuration('ngay')" id="card-ngay">
                    <h3>1 Ngày</h3><p id="price-ngay">--đ</p><small id="stock-ngay" style="font-size:10px;color:#00ff88;">Sẵn sàng</small>
                </div>
                <div class="duration-card" onclick="selectDuration('thang')" id="card-thang" style="grid-column: span 2;">
                    <h3>1 Tháng</h3><p id="price-thang">--đ</p><small id="stock-thang" style="font-size:10px;color:#00ff88;">Sẵn sàng</small>
                </div>
            </div>
        </div>
        
        <div class="buy-action-bar">
            <div><p style="font-size:12px; color:var(--text-sub);">Tổng thanh toán</p><div class="buy-price" id="pd-total">--đ</div></div>
            <button class="btn-buy-now" onclick="processPurchase()">Mua ngay</button>
        </div>
    </div>

    <div class="music-player">
        <div class="disk"></div>
        <div class="music-info">
            <h4>[MASHUP] 🎶 Anh cứ đi đi...</h4>
            <p>Gnasche?</p>
        </div>
    </div>

    <div class="bottom-nav">
        <div class="nav-item active" onclick="switchTab('home', this)">
            <div class="nav-icon">🏠</div><span>Home</span>
        </div>
        <div class="nav-item" onclick="switchTab('shop', this)">
            <div class="nav-icon">🛍</div><span>Mua key</span>
        </div>
        <div class="nav-item" onclick="switchTab('deposit', this)">
            <div class="nav-icon">💳</div><span>Nạp tiền</span>
        </div>
        <div class="nav-item" onclick="switchTab('keys', this)">
            <div class="nav-icon">🔑</div><span>Key của tôi</span>
        </div>
        <div class="nav-item" onclick="switchTab('account', this)">
            <div class="nav-icon">👤</div><span>Tài khoản</span>
        </div>
    </div>

    <script>
        // --- Animation Cánh Hoa ---
        function createPetals() {
            const container = document.getElementById('petals-container');
            for(let i=0; i<25; i++) {
                let petal = document.createElement('div');
                petal.className = 'petal';
                petal.style.left = Math.random() * 100 + 'vw';
                petal.style.width = Math.random() * 15 + 10 + 'px';
                petal.style.height = Math.random() * 10 + 5 + 'px';
                petal.style.animationDuration = Math.random() * 5 + 4 + 's';
                petal.style.animationDelay = Math.random() * 5 + 's';
                container.appendChild(petal);
            }
        }
        createPetals();

        // --- Logic Telegram & App ---
        let telegramUser = null;
        let globalClient = null;
        let currentProduct = null;
        let currentDuration = 'ngay';
        let currentPrice = 0;

        if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.ready();
            window.Telegram.WebApp.expand();
            telegramUser = window.Telegram.WebApp.initDataUnsafe?.user;
        }

        function showAlert(msg) {
            const box = document.getElementById('alertBox');
            box.innerHTML = msg;
            box.style.display = 'block';
            setTimeout(() => box.style.display='none', 3000);
        }

        function switchTab(tabId, el) {
            document.querySelectorAll('.tab-section').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + tabId).classList.add('active');
            el.classList.add('active');
            if(tabId === 'shop') renderCatalog();
        }

        function formatName(name) {
            return name ? name.split(' ').map(n=>n[0]).join('').substring(0,2).toUpperCase() : 'KH';
        }

        async function initApp() {
            let uid = telegramUser ? telegramUser.id : "guest_123";
            let uname = telegramUser ? (telegramUser.first_name + ' ' + (telegramUser.last_name || '')) : "Khách";
            let username = telegramUser ? (telegramUser.username || '') : "";

            // Cập nhật UI cơ bản
            document.getElementById('topAvatar').innerText = formatName(uname);
            document.getElementById('accAvatar').innerText = formatName(uname);
            document.getElementById('accName').innerText = uname;
            document.getElementById('depoUid').innerText = uid;

            const res = await fetch(`/api/sync_client?uid=${uid}&name=${encodeURIComponent(uname)}&username=${username}`);
            globalClient = await res.json();
            
            if(globalClient.blocked) {
                document.body.innerHTML = "<div style='text-align:center; margin-top:40vh; color:red; font-size:20px; font-weight:bold;'>🚫 TÀI KHOẢN BỊ KHÓA</div>";
                return;
            }

            let bal = globalClient.balance.toLocaleString() + 'đ';
            document.getElementById('homeBalance').innerText = bal;
            document.getElementById('depoBalance').innerText = bal;
        }

        // --- Logic Shop ---
        function renderCatalog() {
            if(!globalClient) return;
            const container = document.getElementById('catalogContainer');
            let html = '';
            const icons = ['🤖','⚡','🔥','🎯','💎','🚀'];
            globalClient.catalog.forEach((g, idx) => {
                let icon = icons[idx % icons.length];
                html += `
                <div class="product-card" onclick="openProductDetail('${g.id}', '${icon}')">
                    <div class="product-icon">${icon}</div>
                    <div class="product-info">
                        <h4>${g.ten_game}</h4>
                        <p>${g.gia_ngay.toLocaleString()}đ / Ngày</p>
                    </div>
                </div>`;
            });
            container.innerHTML = html;
        }

        function openProductDetail(id, icon) {
            currentProduct = globalClient.catalog.find(g => g.id === id);
            if(!currentProduct) return;

            document.getElementById('pd-title').innerText = currentProduct.ten_game;
            document.getElementById('pd-name').innerText = currentProduct.ten_game;
            document.getElementById('pd-desc').innerText = currentProduct.mo_ta || 'Sản phẩm chất lượng';
            document.getElementById('pd-icon').innerText = icon;

            document.getElementById('price-gio').innerText = currentProduct.gia_gio.toLocaleString() + 'đ';
            document.getElementById('price-ngay').innerText = currentProduct.gia_ngay.toLocaleString() + 'đ';
            document.getElementById('price-thang').innerText = currentProduct.gia_thang.toLocaleString() + 'đ';
            
            document.getElementById('stock-gio').innerText = currentProduct.stock_gio > 0 ? `Sẵn (${currentProduct.stock_gio})` : 'Hết hàng';
            document.getElementById('stock-ngay').innerText = currentProduct.stock_ngay > 0 ? `Sẵn (${currentProduct.stock_ngay})` : 'Hết hàng';
            document.getElementById('stock-thang').innerText = currentProduct.stock_thang > 0 ? `Sẵn (${currentProduct.stock_thang})` : 'Hết hàng';

            selectDuration('ngay');
            document.getElementById('product-details').style.display = 'flex';
        }

        function closeProductDetail() {
            document.getElementById('product-details').style.display = 'none';
        }

        function selectDuration(dur) {
            currentDuration = dur;
            document.querySelectorAll('.duration-card').forEach(c => c.classList.remove('selected'));
            document.getElementById('card-' + dur).classList.add('selected');
            
            if(dur === 'gio') currentPrice = currentProduct.gia_gio;
            if(dur === 'ngay') currentPrice = currentProduct.gia_ngay;
            if(dur === 'thang') currentPrice = currentProduct.gia_thang;
            
            document.getElementById('pd-total').innerText = currentPrice.toLocaleString() + 'đ';
        }

        async function processPurchase() {
            let uid = telegramUser ? telegramUser.id : "guest_123";
            
            // Check stock local trc
            if(currentProduct[`stock_${currentDuration}`] <= 0) {
                showAlert('❌ Gói thời hạn này đang tạm hết hàng!');
                return;
            }
            if(globalClient.balance < currentPrice) {
                showAlert('❌ Số dư không đủ, vui lòng nạp thêm!');
                return;
            }

            const res = await fetch('/api/purchase_key', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: uid, game_id: currentProduct.id, loai_key: currentDuration})
            });
            const data = await res.json();
            if(data.success) {
                closeProductDetail();
                document.getElementById('alertBox').style.background = "rgba(0,255,100,0.9)";
                showAlert(`🎉 MUA THÀNH CÔNG!<br><br><b>${data.key}</b><br><br><small>Vui lòng copy key.</small>`);
                initApp(); // reload balance
            } else {
                showAlert("❌ " + data.message);
            }
        }

        initApp();
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
            if len(lich_su) > 15: return False
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
            # 1. YÊU CẦU: Vào link gốc (/) sẽ tự động sang Admin
            if self.path == "/":
                self.send_response(302)
                self.send_header("Location", "/admin")
                self.end_headers()
                return

            # 2. VÀO MINI APP (chỉ khi gọi đúng endpoint /app)
            elif self.path == "/app":
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
                uid = query.get('uid', ['guest_123'])[0]
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
                    con_tro.execute("UPDATE khach_hang SET ten_nguoi_dung=?, username=?, ngay_tuong_tac=CURRENT_TIMESTAMP WHERE nguoi_dung_id=?", (name, username, uid))
                    kn.commit()

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
            bộ_ghi_nhật_ký.error(f"Lỗi GET: {e}")
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
                    err = '<div style="color:#ff0055; margin-bottom:10px;">❌ Sai tài khoản hoặc mật khẩu!</div>'
                    self.wfile.write(TRANG_ĐĂNG_NHẬP_ADMIN.replace("{error_placeholder}", err).encode("utf-8"))

            elif self.path == "/api/purchase_key":
                req = json.loads(post_data.decode('utf-8'))
                uid, game_id, loai_key = req.get('user_id'), req.get('game_id'), req.get('loai_key')

                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()
                
                con_tro.execute("SELECT so_du, trang_thai FROM khach_hang WHERE nguoi_dung_id=?", (uid,))
                user_row = con_tro.fetchone()
                if user_row and user_row[1] == 'bi_ban':
                    self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "message": "Tài khoản bị khóa!"}).encode('utf-8'))
                    kn.close(); return

                con_tro.execute("SELECT gia_gio, gia_ngay, gia_thang FROM san_pham_game WHERE id=?", (game_id,))
                g_row = con_tro.fetchone()
                
                gia = g_row[0] if loai_key == 'gio' else (g_row[1] if loai_key == 'ngay' else g_row[2])
                if (user_row[0] if user_row else 0) < gia:
                    self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "message": "Số dư không đủ!"}).encode('utf-8'))
                    kn.close(); return

                con_tro.execute("SELECT id, ma_key FROM kho_key_dong WHERE game_id=? AND loai_key=? AND trang_thai='con_hang' LIMIT 1", (game_id, loai_key))
                k_row = con_tro.fetchone()
                
                if k_row:
                    con_tro.execute("UPDATE khach_hang SET so_du = so_du - ? WHERE nguoi_dung_id=?", (gia, uid))
                    con_tro.execute("UPDATE kho_key_dong SET trang_thai='da_ban', nguoi_mua=?, ngay_ban=? WHERE id=?", (uid, datetime.now().isoformat(), k_row[0]))
                    kn.commit()
                    res = {"success": True, "key": k_row[1]}
                else:
                    res = {"success": False, "message": "Hết hàng!"}
                
                kn.close()
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(res).encode('utf-8'))

            elif self.path in ["/api/admin/deposit", "/api/admin/ban", "/api/admin/add_game", "/api/admin/import_keys"]:
                if not self.xac_thuc_admin():
                    self.send_response(401); self.end_headers(); return
                
                req = json.loads(post_data.decode('utf-8'))
                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()

                if self.path == "/api/admin/deposit":
                    con_tro.execute("UPDATE khach_hang SET so_du = so_du + ? WHERE nguoi_dung_id=?", (float(req.get('amount', 0)), req.get('user_id')))
                elif self.path == "/api/admin/ban":
                    con_tro.execute("UPDATE khach_hang SET trang_thai=? WHERE nguoi_dung_id=?", (req.get('status'), req.get('user_id')))
                elif self.path == "/api/admin/add_game":
                    con_tro.execute("INSERT INTO san_pham_game (id, ten_game, mo_ta, gia_gio, gia_ngay, gia_thang) VALUES (?, ?, ?, ?, ?, ?)",
                                    (str(uuid.uuid4()), req.get('ten_game'), req.get('mo_ta',''), float(req.get('gia_gio',0)), float(req.get('gia_ngay',0)), float(req.get('gia_thang',0))))
                elif self.path == "/api/admin/import_keys":
                    gid, l_key = req.get('game_id'), req.get('loai_key')
                    inserted = 0
                    for k_val in [k.strip() for k in req.get('danh_sach_key', '').split('\n') if k.strip()]:
                        try:
                            con_tro.execute("INSERT INTO kho_key_dong (id, game_id, loai_key, ma_key) VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), gid, l_key, k_val))
                            inserted += 1
                        except Exception: pass
                    kn.commit(); kn.close()
                    self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                    self.wfile.write(json.dumps({"success": True, "count": inserted}).encode('utf-8'))
                    return

                kn.commit(); kn.close()
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            else:
                self.send_response(404); self.end_headers()
        except Exception as e:
            self.send_response(500); self.end_headers()

def chạy_máy_chủ_http(cổng):
    may_chu = HTTPServer(('0.0.0.0', cổng), BộXửLýYêuCầu)
    bộ_ghi_nhật_ký.info(f"Máy chủ HTTP hoạt động tại cổng {cổng}")
    may_chu.serve_forever()

async def bắt_đầu(cập_nhật: Update, ngữ_cảnh: ContextTypes.DEFAULT_TYPE) -> None:
    uid = str(cập_nhật.effective_user.id)
    kn = sqlite3.connect("he_thong_ban_key.db")
    con_tro = kn.cursor()
    con_tro.execute("SELECT trang_thai FROM khach_hang WHERE nguoi_dung_id=?", (uid,))
    row = con_tro.fetchone()
    
    if row and row[0] == 'bi_ban':
        await cập_nhật.message.reply_text("🚫 Tài khoản của bạn đã bị quản trị viên chặn khỏi hệ thống này!")
        kn.close(); return
    if not row:
        con_tro.execute("INSERT INTO khach_hang (nguoi_dung_id, ten_nguoi_dung, username, so_du) VALUES (?, ?, ?, 0)", 
                        (uid, cập_nhật.effective_user.first_name or "User", cập_nhật.effective_user.username or ""))
        kn.commit()
    kn.close()

    ban_phim = InlineKeyboardMarkup([[InlineKeyboardButton("🛍 MỞ ALEX SHOP 🛍", web_app=WebAppInfo(url=f"{URL_ỨNG_DỤNG}/app"))]])
    await cập_nhật.message.reply_text("Chào mừng bạn đến với hệ thống cung cấp Key Tự động!\nBấm nút bên dưới để mở ứng dụng.", reply_markup=ban_phim)

async def tự_ping_duy_trì_sự_sống(app: Application):
    import aiohttp
    await asyncio.sleep(10)
    cổng = int(os.environ.get("PORT", 10000))
    while True:
        try:
            async with aiohttp.ClientSession() as phiên:
                async with phiên.get(f"http://127.0.0.1:{cổng}/health", timeout=5) as phản_hồi:
                    pass
        except Exception: pass
        await asyncio.sleep(120)

async def khoi_tao_kem_ping(application: Application) -> None:
    asyncio.create_task(tự_ping_duy_trì_sự_sống(application))

def main():
    global bot_app
    # Fix cổng Render: Render cung cấp biến môi trường PORT động. Nếu không có (chạy local) thì dùng mặc định 10000.
    cổng = int(os.environ.get("PORT", 10000))
    luong_http = threading.Thread(target=chạy_máy_chủ_http, args=(cổng,), daemon=True)
    luong_http.start()
    
    bot_app = Application.builder().token(MÃ_TOKEN).post_init(khoi_tao_kem_ping).build()
    bot_app.add_handler(CommandHandler("start", bắt_đầu))
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
