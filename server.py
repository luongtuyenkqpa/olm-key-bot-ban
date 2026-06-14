# -*- coding: utf-8 -*-
import asyncio
import logging
import os
import sqlite3
import uuid
import time
import json
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from http import cookies
from urllib.parse import parse_qs, urlparse

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
URL_ỨNG_DỤNG = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app-url.onrender.com")

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

    con_trỏ.execute('''
        CREATE TABLE IF NOT EXISTS lich_su_nap (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nguoi_dung_id TEXT,
            so_tien REAL,
            ngay_nap TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Bảng mới: Quản lý mã giảm giá
    con_trỏ.execute('''
        CREATE TABLE IF NOT EXISTS ma_giam_gia (
            ma_code TEXT PRIMARY KEY,
            phan_tram INTEGER DEFAULT 0,
            so_luong INTEGER DEFAULT 1
        )
    ''')

    con_trỏ.execute("SELECT COUNT(*) FROM san_pham_game")
    if con_trỏ.fetchone()[0] == 0:
        con_trỏ.execute("INSERT INTO san_pham_game VALUES ('game_default', 'NgoTran ⚡', 'API Ổn định, chống ban', 10000, 20000, 150000)")

    kết_nối.commit()
    kết_nối.close()

khởi_tạo_cơ_sở_dữ_liệu()

bot_app = None

# --- GIAO DIỆN WEB CSS CHUNG (ADMIN) ---
GIAO_DIỆN_CHUNG_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background: #1c0036;
        min-height: 100vh; color: #fff; overflow-x: hidden;
    }
    .main-box {
        position: relative; z-index: 2; background: rgba(255, 255, 255, 0.03);
        border-radius: 20px; border: 1px solid rgba(184, 41, 234, 0.3);
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(5px);
    }
    .nav-tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
    .nav-tabs a {
        padding: 10px 20px; background: rgba(184, 41, 234, 0.2); border-radius: 10px;
        color: white; text-decoration: none; font-weight: bold; transition: 0.3s; font-size: 14px;
    }
    .nav-tabs a.active, .nav-tabs a:hover { background: #b829ea; box-shadow: 0 0 15px rgba(184, 41, 234, 0.6); }
    /* Tùy chỉnh thanh cuộn đẹp hơn */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #b829ea; border-radius: 10px; }
"""

TRANG_ĐĂNG_NHẬP_ADMIN = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8"><title>Đăng nhập Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        {GIAO_DIỆN_CHUNG_CSS}
        .login-container {{ width: 90%; max-width: 400px; margin: 15vh auto; padding: 40px 30px; text-align: center; background: #250046; border: 1px solid rgba(255,255,255,0.1); border-radius: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.5); }}
        h2 {{ margin-bottom: 30px; font-size: 24px; color: #fff; text-shadow: 0 0 10px #b829ea; display: flex; justify-content: center; align-items: center; gap: 10px; }}
        .input-group {{ margin-bottom: 20px; text-align: left; }}
        label {{ font-weight: bold; font-size: 0.85em; color: #e0e0e0; margin-bottom: 8px; display: block; }}
        input {{ width: 100%; padding: 15px; border-radius: 12px; border: none; outline: none; background: #190033; color: white; font-size: 1em; box-shadow: inset 0 2px 5px rgba(0,0,0,0.5); }}
        .btn-submit {{
            width: 100%; padding: 15px; border: none; border-radius: 25px; margin-top: 10px;
            background: linear-gradient(90deg, #b829ea, #8a00e6); color: white; font-weight: bold; font-size: 16px; cursor: pointer;
            box-shadow: 0 5px 20px rgba(184, 41, 234, 0.5); transition: 0.3s;
        }}
        .btn-submit:hover {{ transform: scale(1.05); }}
    </style>
</head>
<body>
    <div class="login-container">
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
    <meta charset="UTF-8"><title>Quản Lý Server</title>
    <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
    <style>
        {GIAO_DIỆN_CHUNG_CSS}
        .container {{ max-width: 1200px; margin: 30px auto; padding: 20px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        .header h1 {{ font-size: 22px; display: flex; align-items: center; gap: 10px; }}
        .btn-logout {{ padding: 8px 20px; background: rgba(255,255,255,0.1); color: #fff; border-radius: 20px; text-decoration: none; font-size: 12px; border: 1px solid rgba(255,255,255,0.2); }}
        .card {{ padding: 20px; margin-bottom: 20px; overflow-x: auto; background: #250046; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; background: rgba(0,0,0,0.3); border-radius: 10px; overflow: hidden; }}
        th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.05); white-space: nowrap; font-size: 14px; }}
        th {{ background: rgba(184, 41, 234, 0.2); color: #e0aaff; font-weight: bold; text-transform: uppercase; font-size: 12px; }}
        input[type="number"], input[type="text"] {{ padding: 8px; border-radius: 5px; border: 1px solid #b829ea; width: 110px; margin-right: 5px; background: #190033; color: white; outline:none; }}
        .btn-action {{ padding: 8px 15px; border: none; border-radius: 5px; color: white; cursor: pointer; font-weight: bold; font-size: 12px; }}
        .btn-add {{ background: linear-gradient(90deg, #00cdfe, #0076fe); }} .btn-ban {{ background: linear-gradient(90deg, #ff0055, #cc0044); }}
        textarea.broadcast-input {{ width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #b829ea; background: #190033; color: white; margin-bottom: 10px; outline: none; resize: vertical; }}
        .btn-broadcast {{ padding: 10px 20px; background: linear-gradient(90deg, #ff9900, #ff5500); border: none; color: #fff; font-weight: bold; border-radius: 8px; cursor: pointer; transition: 0.3s; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛠 QUẢN LÝ SERVER</h1>
            <a href="/admin/logout" class="btn-logout">Đăng xuất</a>
        </div>
        <div class="nav-tabs">
            <a href="/admin" class="active">👥 Quản lý thành viên</a>
            <a href="/admin/miniapp">🎮 Quản lý Sản Phẩm & Key</a>
        </div>

        <div class="main-box card">
            <h3 style="color:#e0aaff; font-size: 16px; margin-bottom: 10px;">📢 THÔNG BÁO TỚI TẤT CẢ USER (Gửi vào Bot)</h3>
            <textarea id="broadcastMsg" class="broadcast-input" rows="3" placeholder="Nhập nội dung thông báo muốn gửi tới tất cả người dùng trong Bot Telegram..."></textarea>
            <button class="btn-broadcast" onclick="guiThongBao()">🚀 GỬI THÔNG BÁO</button>
            <span id="broadcastStatus" style="margin-left: 15px; font-size: 13px; color: #00ffcc;"></span>
        </div>

        <div class="main-box card">
            <h3 style="color:#e0aaff; font-size: 16px; margin-bottom: 10px;">👥 DANH SÁCH THÀNH VIÊN</h3>
            <table>
                <thead><tr><th>ID</th><th>Tên</th><th>Username</th><th>Số Dư</th><th>Nạp Tiền</th><th>Khóa/Mở</th></tr></thead>
                <tbody id="tableUsers"></tbody>
            </table>
        </div>
    </div>
    <script>
        function thongBao(msg, isSuccess=true) {{
            Swal.fire({{
                title: isSuccess ? 'Thành công!' : 'Thông báo',
                text: msg,
                icon: isSuccess ? 'success' : 'info',
                background: '#250046',
                color: '#fff',
                confirmButtonColor: '#b829ea',
                borderRadius: '15px'
            }});
        }}

        async function taiThongTin() {{
            const res = await fetch('/api/admin/users');
            const users = await res.json();
            let html = '';
            users.forEach(u => {{
                html += `<tr>
                    <td style="color:#a0a0b8">${{u.id}}</td><td><b>${{u.ten}}</b></td><td style="color:#b829ea">${{u.username ? '@' + u.username : '---'}}</td>
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
            thongBao("✅ Đã cộng tiền thành công cho người dùng!"); 
            taiThongTin();
        }}
        async function doiTrangThai(uid, current) {{
            const nextIdx = current === 'hoat_dong' ? 'bi_ban' : 'hoat_dong';
            await fetch('/api/admin/ban', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{user_id: uid, status: nextIdx}}) }});
            taiThongTin();
        }}
        async function guiThongBao() {{
            const msg = document.getElementById('broadcastMsg').value;
            if(!msg) {{
                Swal.fire({{ icon: 'error', title: 'Lỗi', text: 'Vui lòng nhập nội dung!', background: '#250046', color: '#fff' }});
                return;
            }}
            const st = document.getElementById('broadcastStatus');
            st.innerText = "Đang gửi...";
            const res = await fetch('/api/admin/broadcast', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{message: msg}}) }});
            const data = await res.json();
            st.innerText = `✅ Đã gửi thành công tới ${{data.count}} người dùng!`;
            document.getElementById('broadcastMsg').value = '';
            thongBao(`Đã gửi thông báo đến ${{data.count}} người dùng!`);
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
    <meta charset="UTF-8"><title>Quản Lý Server</title>
    <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
    <style>
        {GIAO_DIỆN_CHUNG_CSS}
        .container {{ max-width: 1200px; margin: 30px auto; padding: 20px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        .header h1 {{ font-size: 22px; display: flex; align-items: center; gap: 10px; }}
        .btn-logout {{ padding: 8px 20px; background: rgba(255,255,255,0.1); color: #fff; border-radius: 20px; text-decoration: none; font-size: 12px; border: 1px solid rgba(255,255,255,0.2); }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
        @media (max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
        .card {{ padding: 20px; background: #250046; }}
        label {{ display: block; font-size: 12px; margin: 10px 0 5px; color: #a0a0b8; }}
        input, select, textarea {{ width: 100%; padding: 12px; border-radius: 8px; border: 1px solid rgba(184, 41, 234, 0.5); background: #190033; color: white; margin-bottom: 5px; outline: none; }}
        button {{ padding: 12px; background: linear-gradient(90deg, #b829ea, #8a00e6); border: none; color: #fff; font-weight: bold; border-radius: 8px; cursor: pointer; width: 100%; transition: 0.3s; }}
        button:hover {{ box-shadow: 0 0 15px rgba(184, 41, 234, 0.6); }}
        th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 14px; }}
        th {{ background: rgba(184, 41, 234, 0.2); color: #e0aaff; font-weight: bold; text-transform: uppercase; font-size: 12px; }}
        .btn-delete {{ padding: 6px 12px; background: linear-gradient(90deg, #ff0055, #cc0044); border: none; color: white; border-radius: 5px; cursor: pointer; font-size: 11px; font-weight: bold; width: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📦 QUẢN LÝ SERVER</h1>
            <a href="/admin/logout" class="btn-logout">Đăng xuất</a>
        </div>
        <div class="nav-tabs">
            <a href="/admin">👥 Quản lý thành viên</a>
            <a href="/admin/miniapp" class="active">🎮 Quản lý Sản Phẩm & Key</a>
        </div>
        <div class="grid">
            <div class="main-box card">
                <h3 style="color:#e0aaff; font-size: 16px;">Thêm / Sửa Sản Phẩm</h3>
                <form id="formGame">
                    <label>Tên Sản Phẩm (VD: NgoTran, Beyond)</label><input type="text" name="ten_game" required>
                    <label>Mô tả ngắn</label><input type="text" name="mo_ta" placeholder="API ổn định...">
                    <label>Giá 1 Giờ (VND)</label><input type="number" name="gia_gio" value="5000" required>
                    <label>Giá 1 Ngày (VND)</label><input type="number" name="gia_ngay" value="20000" required>
                    <label>Giá 1 Tháng (VND)</label><input type="number" name="gia_thang" value="150000" required>
                    <button type="submit" style="margin-top:15px;">LƯU SẢN PHẨM</button>
                </form>
            </div>
            <div class="main-box card">
                <h3 style="color:#e0aaff; font-size: 16px;">Thêm Kho Key</h3>
                <form id="formAddKey">
                    <label>Chọn Sản Phẩm</label><select name="game_id" id="selectGame" required></select>
                    <label>Thời hạn</label>
                    <select name="loai_key"><option value="gio">1 Giờ</option><option value="ngay">1 Ngày</option><option value="thang">1 Tháng</option></select>
                    <label>Danh sách Key (Mỗi key 1 dòng)</label><textarea name="danh_sach_key" rows="6" required></textarea>
                    <button type="submit" style="margin-top:15px; background:linear-gradient(90deg, #00cbfe, #0076fe);">NHẬP KHO</button>
                </form>
            </div>
        </div>
        
        <div class="grid">
            <div class="main-box card">
                <h3 style="color:#e0aaff; font-size: 16px;">Tạo Mã Giảm Giá (%)</h3>
                <form id="formDiscount">
                    <label>Mã Code (VD: HELYVIP)</label><input type="text" name="ma_code" required>
                    <label>Phần trăm giảm (1 - 100%)</label><input type="number" name="phan_tram" max="100" min="1" required>
                    <label>Số lượng lượt dùng</label><input type="number" name="so_luong" value="10" required>
                    <button type="submit" style="margin-top:15px; background:linear-gradient(90deg, #ff9900, #ff5500);">TẠO MÃ GIẢM GIÁ</button>
                </form>
            </div>
            <div class="main-box card" style="overflow-x: auto;">
                <h3 style="color:#e0aaff; font-size: 16px; margin-bottom: 10px;">📋 DANH SÁCH MÃ GIẢM GIÁ</h3>
                <table style="width: 100%; background: rgba(0,0,0,0.3); border-radius: 10px; overflow: hidden; border-collapse: collapse;">
                    <thead><tr><th>Mã Code</th><th>Giảm (%)</th><th>Lượt Còn</th><th>Hành Động</th></tr></thead>
                    <tbody id="tableDiscounts"></tbody>
                </table>
            </div>
        </div>

        <div class="main-box card" style="overflow-x: auto;">
            <h3 style="color:#e0aaff; font-size: 16px; margin-bottom: 10px;">📊 KHO SẢN PHẨM HIỆN TẠI</h3>
            <table style="width: 100%; background: rgba(0,0,0,0.3); border-radius: 10px; overflow: hidden; border-collapse: collapse;">
                <thead><tr><th>Sản Phẩm</th><th>Giá Giờ</th><th>Giá Ngày</th><th>Giá Tháng</th><th>Tồn Kho</th><th>Hành Động</th></tr></thead>
                <tbody id="tableGames"></tbody>
            </table>
        </div>
    </div>
    <script>
        function thongBao(msg) {{
            Swal.fire({{ title: 'Thành công!', text: msg, icon: 'success', background: '#250046', color: '#fff', confirmButtonColor: '#b829ea', borderRadius: '15px' }});
        }}

        async function loadData() {{
            const res = await fetch('/api/admin/games_dashboard');
            const data = await res.json();
            document.getElementById('selectGame').innerHTML = data.games.map(g => `<option value="${{g.id}}">${{g.ten_game}}</option>`).join('');
            
            document.getElementById('tableGames').innerHTML = data.games.map(g => `<tr>
                <td><b style="color:white;">${{g.ten_game}}</b><br><small style="color:#a0a0b8;">${{g.mo_ta}}</small></td>
                <td>${{g.gia_gio.toLocaleString()}}đ</td><td>${{g.gia_ngay.toLocaleString()}}đ</td><td>${{g.gia_thang.toLocaleString()}}đ</td>
                <td style="color:#00ffcc">Giờ: ${{data.counts[g.id]?.gio||0}} | Ngày: ${{data.counts[g.id]?.ngay||0}} | Tháng: ${{data.counts[g.id]?.thang||0}}</td>
                <td><button class="btn-delete" onclick="xoaSanPham('${{g.id}}')">🗑 Xóa</button></td>
            </tr>`).join('');

            document.getElementById('tableDiscounts').innerHTML = data.discounts.map(d => `<tr>
                <td><b style="color:#00ffcc;">${{d.ma_code}}</b></td>
                <td><b style="color:#ff80ff;">${{d.phan_tram}}%</b></td>
                <td>${{d.so_luong}}</td>
                <td><button class="btn-delete" onclick="xoaMaGiamGia('${{d.ma_code}}')">🗑 Xóa</button></td>
            </tr>`).join('');
        }}
        
        async function xoaSanPham(id) {{
            Swal.fire({{
                title: 'Xoá Sản Phẩm?',
                text: "Toàn bộ key thuộc sản phẩm này sẽ bị xoá!",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#ff0055',
                cancelButtonColor: '#3085d6',
                confirmButtonText: 'Đồng ý',
                cancelButtonText: 'Huỷ',
                background: '#250046', color: '#fff'
            }}).then(async (result) => {{
                if (result.isConfirmed) {{
                    await fetch('/api/admin/delete_game', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{game_id: id}}) }});
                    thongBao("Đã xóa sản phẩm thành công!"); loadData();
                }}
            }});
        }}

        async function xoaMaGiamGia(code) {{
            await fetch('/api/admin/delete_discount', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{ma_code: code}}) }});
            thongBao("Đã xoá mã giảm giá!"); loadData();
        }}

        document.getElementById('formGame').onsubmit = async (e) => {{
            e.preventDefault();
            await fetch('/api/admin/add_game', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(Object.fromEntries(new FormData(e.target))) }});
            thongBao("Đã lưu sản phẩm thành công!"); e.target.reset(); loadData();
        }};
        
        document.getElementById('formAddKey').onsubmit = async (e) => {{
            e.preventDefault();
            const res = await fetch('/api/admin/import_keys', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(Object.fromEntries(new FormData(e.target))) }});
            const data = await res.json(); 
            thongBao(`Đã nhập thành công: ${{data.count}} Key vào kho!`); e.target.reset(); loadData();
        }};

        document.getElementById('formDiscount').onsubmit = async (e) => {{
            e.preventDefault();
            await fetch('/api/admin/add_discount', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(Object.fromEntries(new FormData(e.target))) }});
            thongBao("Đã tạo mã giảm giá thành công!"); e.target.reset(); loadData();
        }}
        loadData();
    </script>
</body>
</html>
"""

# --- GIAO DIỆN MINI APP ĐÃ NÂNG CẤP TAB MUA KEY ---
TRANG_MINI_APP = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>HELY SHOP</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
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

        /* Splash Screen */
        #splashScreen {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: #12002b; z-index: 9999; display: flex;
            justify-content: center; align-items: center; text-align: center;
            transition: opacity 0.5s ease-out; flex-direction: column;
            background-image: radial-gradient(circle at center, #2a005c 0%, #12002b 100%);
        }
        .splash-spinner {
            width: 50px; height: 50px; border: 4px solid rgba(200, 80, 192, 0.3); 
            border-top-color: #c850c0; border-radius: 50%; 
            animation: spin 1s linear infinite; margin-bottom: 25px;
        }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        .splash-text {
            color: #fff; font-size: 20px; font-weight: bold;
            background: var(--primary-gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            animation: pulse 2s infinite; padding: 0 20px; text-align: center;
        }
        @keyframes pulse { 0% { opacity: 0.8; transform: scale(0.98); } 50% { opacity: 1; transform: scale(1.02); } 100% { opacity: 0.8; transform: scale(0.98); } }

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
        .main-content { 
            height: calc(100vh - 70px - 75px); 
            overflow-y: auto; padding: 15px; position: relative; z-index: 1; 
            padding-bottom: 80px; -webkit-overflow-scrolling: touch;
        }
        .tab-section { display: none; animation: fadeIn 0.3s; }
        .tab-section.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        /* Components chung */
        .glass-card { background: var(--card-bg); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid var(--card-border); border-radius: 16px; padding: 15px; margin-bottom: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
        .section-title { font-size: 16px; font-weight: bold; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
        .icon-circle { width: 30px; height: 30px; border-radius: 50%; display: flex; justify-content: center; align-items: center; background: rgba(200, 80, 192, 0.2); color: #ff80ff;}

        /* --- SHOP NÂNG CẤP (MUA KEY Y HỆT ẢNH) --- */
        .shop-label { font-weight: bold; font-size: 14px; color: #e0aaff; margin-bottom: 10px; display: block; text-transform: uppercase; letter-spacing: 0.5px; }
        .custom-select { 
            width: 100%; padding: 15px; border-radius: 12px; 
            background: rgba(0,0,0,0.4); border: 1px solid var(--primary); 
            color: white; font-size: 15px; outline: none; appearance: none;
            background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23c850c0' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
            background-repeat: no-repeat; background-position: right 15px center; background-size: 16px;
        }
        
        .duration-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .duration-card { background: rgba(0,0,0,0.4); border: 1px solid var(--card-border); border-radius: 12px; padding: 15px 10px; text-align: center; cursor: pointer; transition: 0.2s; position: relative;}
        .duration-card.selected { background: rgba(200, 80, 192, 0.2); border-color: var(--primary); box-shadow: 0 0 15px rgba(200, 80, 192, 0.4); }
        .duration-card h3 { font-size: 14px; margin-bottom: 8px; color: #fff; text-transform: uppercase; }
        .duration-card p { font-size: 15px; color: #00ff88; font-weight: bold; margin-bottom: 5px;}
        
        /* Discount section in Shop */
        .discount-input-row { display: flex; gap: 10px; margin-top: 8px;}
        .discount-input-row input { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.05); color: white; outline: none; font-size: 14px;}
        .discount-input-row button { padding: 0 15px; border-radius: 8px; border: none; background: #00cdfe; color: white; font-weight: bold; font-size: 14px; cursor: pointer;}

        /* Bottom Fixed Bar cho Mua Key */
        .shop-bottom-bar { 
            position: fixed; bottom: 70px; left: 0; width: 100%; 
            background: rgba(18, 0, 43, 0.98); border-top: 1px solid var(--primary); 
            padding: 15px 20px; display: flex; flex-direction: column; gap: 12px; 
            z-index: 90; box-shadow: 0 -5px 20px rgba(0,0,0,0.5);
            padding-bottom: calc(15px + env(safe-area-inset-bottom));
        }
        .sbb-info { display: grid; grid-template-columns: 100px 1fr; gap: 5px; align-items: center; }
        .sbb-info-label { font-size: 13px; color: var(--text-sub); }
        .sbb-info-val { font-weight: bold; color: white; font-size: 15px; text-align: right; }
        .sbb-actions { display: flex; gap: 10px; }
        .btn-sbb { flex: 1; padding: 14px 0; border-radius: 12px; font-weight: bold; font-size: 14px; border: none; cursor: pointer; text-align: center; }
        .btn-sbb-detail { background: rgba(255,255,255,0.1); color: white; border: 1px solid rgba(255,255,255,0.2); }
        .btn-sbb-buy { background: var(--primary-gradient); color: white; box-shadow: 0 4px 15px rgba(200, 80, 192, 0.4); }
        .btn-sbb:active { transform: scale(0.96); }

        /* Tab Home & others... */
        .step-list { display: flex; flex-direction: column; gap: 10px; }
        .step-item { display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3); padding: 15px; border-radius: 12px; font-size: 15px;}
        .step-num { width: 30px; height: 30px; border-radius: 50%; background: var(--primary-gradient); display: flex; justify-content: center; align-items: center; font-weight: bold; }
        .system-status { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid var(--card-border); align-items: center;}
        .system-status:last-child { border-bottom: none; }
        .status-badge { background: transparent; color: #00ff88; padding: 5px 12px; border-radius: 15px; font-size: 13px; border: 1px solid #00ff88; }

        /* Tab Nạp tiền */
        .deposit-tabs { display: flex; background: rgba(0,0,0,0.5); border-radius: 12px; padding: 5px; margin-bottom: 20px; }
        .dt-btn { flex: 1; padding: 10px; text-align: center; color: var(--text-sub); border-radius: 8px; font-size: 14px; font-weight: bold; cursor:pointer;}
        .dt-btn.active { background: var(--card-bg); color: white; }
        .balance-display { padding: 15px; margin-bottom: 20px; text-align: center; }
        .balance-display p { font-size: 14px; color: var(--text-sub); }
        .balance-display h2 { font-size: 36px; font-weight: bold; margin-top: 5px; color: #fff;}

        /* Tab Profile */
        .profile-header { text-align: center; padding: 20px 0; }
        .profile-avatar { width: 80px; height: 80px; background: var(--primary-gradient); border-radius: 50%; margin: 0 auto 10px; display: flex; justify-content: center; align-items: center; font-size: 30px; font-weight: bold; border: 3px solid rgba(255,255,255,0.2); }
        .menu-list { display: flex; flex-direction: column; gap: 10px; }
        .menu-item { display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 20px; text-align: center; gap: 10px; cursor:pointer;}
        .menu-item .icon { font-size: 24px; color: #80d4ff; }

        /* List Items */
        .list-item { background: rgba(0,0,0,0.3); border: 1px solid var(--card-border); border-radius: 12px; padding: 15px; margin-bottom: 10px; }
        .list-item-header { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; font-weight: bold;}
        .list-item-body { font-size: 13px; color: var(--text-sub); word-break: break-all; }
        .list-item-time { font-size: 11px; color: #888; margin-top: 8px; text-align: right;}

        /* Sub-views */
        .sub-view { display: none; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: var(--bg-dark); z-index: 30; flex-direction: column; }
        .pd-header { display: flex; align-items: center; padding: 15px; border-bottom: 1px solid var(--card-border); background: var(--nav-bg); }
        .pd-back { background: none; border: none; color: white; font-size: 24px; margin-right: 15px; cursor: pointer; }

        /* Custom Modals */
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); backdrop-filter: blur(5px); z-index: 1000; display: none; justify-content: center; align-items: center; }
        .custom-modal { background: #1a0033; border: 1px solid var(--primary); border-radius: 20px; padding: 30px 20px; width: 85%; max-width: 350px; text-align: center; box-shadow: 0 0 30px rgba(200, 80, 192, 0.4); animation: popIn 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        @keyframes popIn { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        .modal-icon { font-size: 50px; margin-bottom: 15px; }
        .modal-title { font-size: 20px; font-weight: bold; margin-bottom: 10px; color: white; }
        .modal-desc { font-size: 14px; color: var(--text-sub); margin-bottom: 25px; line-height: 1.5; }
        .modal-buttons { display: flex; gap: 10px; justify-content: center; }
        .btn-modal { flex: 1; padding: 12px; border: none; border-radius: 12px; font-weight: bold; font-size: 15px; cursor: pointer; }
        .btn-cancel { background: rgba(255,255,255,0.1); color: white; }
        .btn-confirm { background: var(--primary-gradient); color: white; }

        /* Auto-Notify Toast */
        .toast { position: fixed; top: -100px; left: 50%; transform: translateX(-50%); background: rgba(0,255,136,0.2); border: 1px solid #00ff88; color: white; padding: 15px 25px; border-radius: 30px; font-weight: bold; z-index: 10000; transition: top 0.5s cubic-bezier(0.68, -0.55, 0.265, 1.55); backdrop-filter: blur(10px); display:flex; align-items:center; gap:10px; white-space:nowrap;}

        /* Bottom Navigation */
        .bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; height: 70px; background: var(--nav-bg); backdrop-filter: blur(20px); border-top: 1px solid var(--card-border); display: flex; justify-content: space-around; align-items: center; z-index: 100; padding-bottom: env(safe-area-inset-bottom); }
        .nav-item { display: flex; flex-direction: column; align-items: center; gap: 5px; color: var(--text-sub); font-size: 11px; text-decoration: none; cursor: pointer; width: 20%; transition: 0.2s;}
        .nav-item.active { color: var(--primary); }
        .nav-icon { font-size: 20px; margin-bottom: 2px;}
        .nav-item.active .nav-icon { filter: drop-shadow(0 0 5px var(--primary)); transform: translateY(-2px);}
    </style>
</head>
<body>
    <div id="splashScreen">
        <div class="splash-spinner"></div>
        <div class="splash-text">Đang mở shop Hely Shop...</div>
    </div>

    <div class="petals" id="petals-container"></div>
    
    <div id="notifyToast" class="toast">🎉 <span id="toastMsg">Tin nhắn</span></div>

    <div class="modal-overlay" id="mainModal">
        <div class="custom-modal">
            <div class="modal-icon" id="mdIcon">❓</div>
            <div class="modal-title" id="mdTitle">Tiêu đề</div>
            <div class="modal-desc" id="mdDesc">Nội dung</div>
            <div class="modal-buttons" id="mdButtons"></div>
        </div>
    </div>

    <div class="header">
        <div class="header-logo">
            <img src="https://ui-avatars.com/api/?name=HELY&background=12002b&color=c850c0" alt="Logo">
            <div class="header-text">
                <small>DESIGN BY HELY</small>
                <h2>HELY SHOP</h2>
            </div>
        </div>
        <div class="header-right">
            <div class="lang-btn">文A VI</div>
            <div class="user-avatar" id="topAvatar">US</div>
        </div>
    </div>

    <div class="main-content" id="scrollableArea">
        
        <div id="tab-home" class="tab-section active">
            <div class="glass-card">
                <p style="font-size: 12px; color: var(--text-sub); margin-bottom: 15px;">Luồng mua key gọn nhất</p>
                <div class="step-list">
                    <div class="step-item"><div class="step-num">1</div><span style="flex:1; text-align:right;">Chọn sản phẩm</span></div>
                    <div class="step-item"><div class="step-num">2</div><span style="flex:1; text-align:right; opacity:0.6;">Chọn thời hạn</span></div>
                    <div class="step-item"><div class="step-num">3</div><span style="flex:1; text-align:right; opacity:0.6;">Thanh toán</span></div>
                    <div class="step-item"><div class="step-num">4</div><span style="flex:1; text-align:right; opacity:0.6;">Nhận key</span></div>
                </div>
            </div>

            <div class="glass-card">
                <div class="section-title"><div class="icon-circle">📊</div> Trạng thái hệ thống</div>
                <div id="systemStatusList"></div>
            </div>
        </div>

        <div id="tab-shop" class="tab-section">
            
            <div class="glass-card">
                <label class="shop-label">1 - Chọn Sản Phẩm Muốn Thuê</label>
                <select id="shopGameSelect" class="custom-select" onchange="shopGameChanged()"></select>
            </div>

            <div class="glass-card">
                <label class="shop-label">2 - Chọn Thời Gian Thuê</label>
                <div class="duration-grid">
                    <div class="duration-card" id="shop-card-gio" onclick="selectShopDuration('gio')">
                        <h3>1 GIỜ</h3><p id="shop-price-gio">0đ</p><small id="shop-stock-gio" style="font-size:11px;">Sẵn sàng</small>
                    </div>
                    <div class="duration-card selected" id="shop-card-ngay" onclick="selectShopDuration('ngay')">
                        <h3>1 NGÀY</h3><p id="shop-price-ngay">0đ</p><small id="shop-stock-ngay" style="font-size:11px;">Sẵn sàng</small>
                    </div>
                    <div class="duration-card" id="shop-card-thang" onclick="selectShopDuration('thang')" style="grid-column: span 2;">
                        <h3>1 THÁNG</h3><p id="shop-price-thang">0đ</p><small id="shop-stock-thang" style="font-size:11px;">Sẵn sàng</small>
                    </div>
                </div>
            </div>

            <div class="glass-card" id="shopDiscountSection" style="display:none; border: 1px dashed var(--primary);">
                <label class="shop-label">3 - Nhập Mã Giảm Giá</label>
                <div class="discount-input-row">
                    <input type="text" id="shopInpDiscount" placeholder="Nhập mã ưu đãi...">
                    <button onclick="checkShopDiscount()">Áp dụng</button>
                </div>
                <p id="shopMsgDiscount" style="font-size:13px; margin-top: 8px; font-weight:bold; display:none;"></p>
            </div>

            <div style="height: 180px;"></div>

            <div class="shop-bottom-bar" id="shopBottomBar" style="display:none;">
                <div class="sbb-info">
                    <div class="sbb-info-label">Sản phẩm:</div>
                    <div class="sbb-info-val" id="sbb-name">Đang tải...</div>
                    <div class="sbb-info-label" style="margin-top:2px;">Giá tiền:</div>
                    <div class="sbb-info-val" id="sbb-price" style="color:#00ff88; font-size:18px;">0đ</div>
                </div>
                <div class="sbb-actions">
                    <button class="btn-sbb btn-sbb-detail" onclick="toggleShopDiscount()">Chi tiết / %</button>
                    <button class="btn-sbb btn-sbb-buy" onclick="confirmShopPurchase()">💳 THANH TOÁN</button>
                </div>
            </div>

        </div>

        <div id="tab-deposit" class="tab-section">
            <div class="deposit-tabs">
                <div class="dt-btn active" onclick="switchDepoTab('admin', this)">Nạp tiền (Admin)</div>
                <div class="dt-btn" onclick="switchDepoTab('auto', this)">Gạch thẻ tự động</div>
            </div>
            <div class="glass-card balance-display">
                <p>Số dư hiện tại</p>
                <h2 id="depoBalance">0đ</h2>
            </div>
            <div class="glass-card" id="depoContent">
                <p style="font-size: 15px; text-align:center; color: #ffb3ff; line-height: 1.6;">
                    Vui lòng nhắn tin trực tiếp cho Admin<br>
                    <b style="color:white; font-size:18px;">@luongtuyen20</b><br>
                    để tiến hành nạp tiền vào tài khoản!<br><br>
                    <span style="color:var(--text-sub); font-size:13px;">ID của bạn: </span><br>
                    <b id="depoUid" style="color:white;font-size:16px;">Đang tải...</b>
                </p>
            </div>
        </div>

        <div id="tab-keys" class="tab-section">
            <div class="glass-card">
                <div class="section-title"><div class="icon-circle">🔑</div> Key của tôi</div>
                <p style="font-size: 12px; color: var(--text-sub);">Danh sách key bạn đã thanh toán</p>
                <div id="myKeysContainer" style="margin-top: 15px;"></div>
            </div>
        </div>

        <div id="tab-account" class="tab-section">
            <div class="glass-card">
                <div class="profile-header">
                    <h3 id="accName" style="font-size:20px;">User</h3>
                    <p style="font-size:13px; color:var(--text-sub); margin-top:5px;">Thành viên HELY SHOP</p>
                </div>
            </div>
            <div class="menu-list">
                <div class="glass-card menu-item" onclick="openSubView('sv-orders')"><div class="icon">🧾</div><span>Đơn hàng</span></div>
                <div class="glass-card menu-item" onclick="openSubView('sv-history')"><div class="icon">🔄</div><span>Lịch sử nạp</span></div>
                <div class="glass-card menu-item" onclick="showCustomAlert('🎧', 'Hỗ trợ', 'Vui lòng liên hệ Admin @luongtuyen20')"><div class="icon">🎧</div><span>Hỗ trợ</span></div>
            </div>
        </div>
    </div>

    <div id="sv-orders" class="sub-view">
        <div class="pd-header">
            <button class="pd-back" onclick="closeSubView('sv-orders')">←</button>
            <h3>Danh sách đơn hàng</h3>
        </div>
        <div style="padding: 15px; flex:1; overflow-y:auto; padding-bottom: 20px;" id="ordersContainer"></div>
    </div>

    <div id="sv-history" class="sub-view">
        <div class="pd-header">
            <button class="pd-back" onclick="closeSubView('sv-history')">←</button>
            <h3>Lịch sử nạp tiền</h3>
        </div>
        <div style="padding: 15px; flex:1; overflow-y:auto; padding-bottom: 20px;" id="historyContainer"></div>
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
        // --- ẨN SPLASH SCREEN SAU 3.5 GIÂY ---
        setTimeout(() => {
            const splash = document.getElementById('splashScreen');
            if(splash) {
                splash.style.opacity = '0';
                setTimeout(() => splash.style.display = 'none', 500);
            }
        }, 3500);

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
        
        // Trạng thái Shop nâng cấp
        let currentProduct = null;
        let currentDuration = 'ngay';
        let currentPrice = 0;
        let currentDiscountCode = "";
        let currentDiscountPercent = 0;
        
        let lastBalance = 0;

        if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.ready();
            window.Telegram.WebApp.expand();
            telegramUser = window.Telegram.WebApp.initDataUnsafe?.user;
        }

        function formatName(name) {
            return name ? name.split(' ').map(n=>n[0]).join('').substring(0,2).toUpperCase() : 'KH';
        }

        function formatDate(isoString) {
            if(!isoString) return '';
            const d = new Date(isoString);
            return `${d.getDate().toString().padStart(2,'0')}/${(d.getMonth()+1).toString().padStart(2,'0')}/${d.getFullYear()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
        }

        // --- Custom UI Alerts ---
        function showCustomAlert(icon, title, desc, onConfirm = null) {
            document.getElementById('mdIcon').innerHTML = icon;
            document.getElementById('mdTitle').innerHTML = title;
            document.getElementById('mdDesc').innerHTML = desc;
            
            let btnHtml = '';
            if (onConfirm) {
                btnHtml = `
                    <button class="btn-modal btn-cancel" onclick="closeModal()">Huỷ</button>
                    <button class="btn-modal btn-confirm" onclick="executeCallback()">Đồng ý</button>
                `;
                window.modalCallback = onConfirm;
            } else {
                btnHtml = `<button class="btn-modal btn-confirm" style="width:100%" onclick="closeModal()">Đóng</button>`;
            }
            document.getElementById('mdButtons').innerHTML = btnHtml;
            document.getElementById('mainModal').style.display = 'flex';
        }

        function closeModal() { document.getElementById('mainModal').style.display = 'none'; }
        function executeCallback() { closeModal(); if(window.modalCallback) window.modalCallback(); }

        function showToast(msg) {
            const toast = document.getElementById('notifyToast');
            document.getElementById('toastMsg').innerHTML = msg;
            toast.style.top = '20px';
            setTimeout(() => { toast.style.top = '-100px'; }, 4000);
        }

        // --- Navigation ---
        function switchTab(tabId, el) {
            document.querySelectorAll('.tab-section').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById('tab-' + tabId).classList.add('active');
            el.classList.add('active');
            
            // Xử lý hiển thị Bottom Bar của Shop
            if(tabId === 'shop') {
                initShopUI();
                document.getElementById('shopBottomBar').style.display = 'flex';
            } else {
                document.getElementById('shopBottomBar').style.display = 'none';
            }
            
            document.getElementById('scrollableArea').scrollTo(0, 0);
        }

        function switchDepoTab(type, el) {
            document.querySelectorAll('.deposit-tabs .dt-btn').forEach(b => b.classList.remove('active'));
            el.classList.add('active');
            const box = document.getElementById('depoContent');
            if(type === 'admin') {
                box.innerHTML = `<p style="font-size: 15px; text-align:center; color: #ffb3ff; line-height: 1.6;">Vui lòng nhắn tin trực tiếp cho Admin<br><b style="color:white; font-size:18px;">@luongtuyen20</b><br>để tiến hành nạp tiền vào tài khoản!<br><br><span style="color:var(--text-sub); font-size:13px;">ID của bạn: </span><br><b style="color:white;font-size:16px;">${telegramUser ? telegramUser.id : "guest_123"}</b></p>`;
            } else {
                box.innerHTML = `<div style="text-align:center; padding: 20px;"><div style="font-size:40px; margin-bottom:10px;">🚧</div><h3 style="color:#ffcc00;">BẢO TRÌ</h3><p style="font-size:13px; color:var(--text-sub); margin-top:10px;">Hệ thống Gạch thẻ tự động đang được bảo trì nâng cấp. Vui lòng quay lại sau!</p></div>`;
            }
        }

        function openSubView(id) { document.getElementById(id).style.display = 'flex'; }
        function closeSubView(id) { document.getElementById(id).style.display = 'none'; }

        // --- Core App Logic ---
        async function fetchClientData() {
            let uid = telegramUser ? telegramUser.id : "guest_123";
            let uname = telegramUser ? (telegramUser.first_name + ' ' + (telegramUser.last_name || '')) : "Khách";
            let username = telegramUser ? (telegramUser.username || '') : "";

            const res = await fetch(`/api/sync_client?uid=${uid}&name=${encodeURIComponent(uname)}&username=${username}`);
            return await res.json();
        }

        async function initApp() {
            let uname = telegramUser ? (telegramUser.first_name + ' ' + (telegramUser.last_name || '')) : "Khách";
            let uid = telegramUser ? telegramUser.id : "guest_123";
            
            document.getElementById('topAvatar').innerText = formatName(uname);
            document.getElementById('accName').innerText = uname;
            document.getElementById('depoUid').innerText = uid;

            globalClient = await fetchClientData();
            
            if(globalClient.blocked) {
                document.body.innerHTML = "<div style='text-align:center; margin-top:40vh; color:red; font-size:20px; font-weight:bold;'>🚫 TÀI KHOẢN BỊ KHÓA</div>";
                return;
            }

            lastBalance = globalClient.balance;
            updateUI();
            
            setInterval(async () => {
                const newData = await fetchClientData();
                if(newData.balance > lastBalance) {
                    let diff = newData.balance - lastBalance;
                    showToast(`Admin vừa nạp cho bạn +${diff.toLocaleString()}đ siêu đẹp!`);
                    globalClient = newData;
                    lastBalance = newData.balance;
                    updateUI();
                }
            }, 10000);
        }

        function updateUI() {
            let bal = globalClient.balance.toLocaleString() + 'đ';
            document.getElementById('depoBalance').innerText = bal;

            let stHtml = '';
            globalClient.catalog.forEach(g => {
                stHtml += `<div class="system-status"><span style="font-weight:bold;">${g.ten_game}</span><span class="status-badge">Ổn định</span></div>`;
            });
            document.getElementById('systemStatusList').innerHTML = stHtml || '<p style="text-align:center;font-size:12px;opacity:0.5;">Chưa có dữ liệu</p>';

            let hisHtml = '';
            if(globalClient.history.length === 0) hisHtml = '<div style="text-align:center; padding:30px; opacity:0.5;">Chưa có giao dịch nạp</div>';
            globalClient.history.forEach(h => {
                hisHtml += `<div class="list-item">
                    <div class="list-item-header"><span style="color:#00ff88;">+ ${h.tien.toLocaleString()}đ</span><span>Admin nạp</span></div>
                    <div class="list-item-time">${formatDate(h.thoi_gian)}</div>
                </div>`;
            });
            document.getElementById('historyContainer').innerHTML = hisHtml;

            let keyHtml = '';
            if(globalClient.my_keys.length === 0) {
                keyHtml = '<div style="text-align: center; padding: 40px 20px; opacity: 0.6;"><div style="font-size: 40px; margin-bottom: 10px;">🔑</div><h4>Chưa có key</h4><p style="font-size: 12px;">Key bạn mua sẽ xuất hiện ở đây.</p></div>';
            } else {
                globalClient.my_keys.forEach(k => {
                    let loaiStr = k.loai === 'gio' ? '1 Giờ' : (k.loai === 'ngay' ? '1 Ngày' : '1 Tháng');
                    keyHtml += `<div class="list-item">
                        <div class="list-item-header"><span style="color:var(--primary);">${k.game} - ${loaiStr}</span></div>
                        <div class="list-item-body" style="font-family:monospace; background:rgba(0,0,0,0.5); padding:10px; border-radius:5px; margin-top:5px; border:1px dashed #b829ea; color:white; font-size:15px; text-align:center;">${k.key}</div>
                        <div class="list-item-time">Đã mua lúc: ${formatDate(k.thoi_gian)}</div>
                    </div>`;
                });
            }
            document.getElementById('myKeysContainer').innerHTML = keyHtml;
            document.getElementById('ordersContainer').innerHTML = keyHtml; 
            
            // Cập nhật giá/tồn kho nếu ở Shop
            if (currentProduct) {
                // Refresh product ref
                currentProduct = globalClient.catalog.find(g => g.id === currentProduct.id) || globalClient.catalog[0];
                updateShopUI();
            }
        }

        // --- SHOP LOGIC NÂNG CẤP ---
        function initShopUI() {
            if(!globalClient || globalClient.catalog.length === 0) return;
            const select = document.getElementById('shopGameSelect');
            
            // Chỉ render lại select nếu chưa có (để giữ lựa chọn khi chuyển tab)
            if(select.options.length === 0) {
                select.innerHTML = globalClient.catalog.map(g => `<option value="${g.id}">${g.ten_game}</option>`).join('');
                currentProduct = globalClient.catalog[0];
                currentDuration = 'ngay';
            }
            updateShopUI();
        }

        function shopGameChanged() {
            const select = document.getElementById('shopGameSelect');
            currentProduct = globalClient.catalog.find(g => g.id === select.value);
            // Hủy mã giảm giá khi đổi sản phẩm
            currentDiscountCode = "";
            currentDiscountPercent = 0;
            document.getElementById('shopInpDiscount').value = '';
            document.getElementById('shopMsgDiscount').style.display = 'none';
            updateShopUI();
        }

        function selectShopDuration(dur) {
            currentDuration = dur;
            updateShopUI();
        }

        function toggleShopDiscount() {
            const box = document.getElementById('shopDiscountSection');
            box.style.display = box.style.display === 'none' ? 'block' : 'none';
            if(box.style.display === 'block') {
                box.scrollIntoView({behavior: "smooth"});
            }
        }

        function updateShopUI() {
            if(!currentProduct) return;
            
            // Cập nhật card được chọn
            document.querySelectorAll('#tab-shop .duration-card').forEach(c => c.classList.remove('selected'));
            document.getElementById('shop-card-' + currentDuration).classList.add('selected');

            // Tính giá với giảm giá
            let p_gio = currentProduct.gia_gio * (1 - currentDiscountPercent/100);
            let p_ngay = currentProduct.gia_ngay * (1 - currentDiscountPercent/100);
            let p_thang = currentProduct.gia_thang * (1 - currentDiscountPercent/100);
            
            const fmt = (oldP, newP) => currentDiscountPercent > 0 ? `<s style="color:#888; font-size:12px;">${oldP.toLocaleString()}đ</s><br>${newP.toLocaleString()}đ` : `${newP.toLocaleString()}đ`;
            
            document.getElementById('shop-price-gio').innerHTML = fmt(currentProduct.gia_gio, p_gio);
            document.getElementById('shop-price-ngay').innerHTML = fmt(currentProduct.gia_ngay, p_ngay);
            document.getElementById('shop-price-thang').innerHTML = fmt(currentProduct.gia_thang, p_thang);

            const renderStock = (count) => count > 0 ? `<span style="color:#00ff88">Sẵn (${count})</span>` : '<span style="color:#ff4444;">Hết hàng</span>';
            document.getElementById('shop-stock-gio').innerHTML = renderStock(currentProduct.stock_gio);
            document.getElementById('shop-stock-ngay').innerHTML = renderStock(currentProduct.stock_ngay);
            document.getElementById('shop-stock-thang').innerHTML = renderStock(currentProduct.stock_thang);

            // Cập nhật Bottom Bar
            let loaiStr = currentDuration === 'gio' ? '1 GIỜ' : (currentDuration === 'ngay' ? '1 NGÀY' : '1 THÁNG');
            document.getElementById('sbb-name').innerText = `${currentProduct.ten_game} - ${loaiStr}`;
            
            let baseP = currentDuration === 'gio' ? currentProduct.gia_gio : (currentDuration === 'ngay' ? currentProduct.gia_ngay : currentProduct.gia_thang);
            currentPrice = baseP * (1 - currentDiscountPercent/100);
            
            document.getElementById('sbb-price').innerText = currentPrice.toLocaleString() + ' VNĐ';
        }

        async function checkShopDiscount() {
            const code = document.getElementById('shopInpDiscount').value.trim();
            const msgEl = document.getElementById('shopMsgDiscount');
            if(!code) return;
            
            const res = await fetch(`/api/check_discount?code=${code}`);
            const data = await res.json();
            msgEl.style.display = 'block';
            if(data.success) {
                currentDiscountPercent = data.percent;
                currentDiscountCode = code;
                msgEl.innerText = `✅ Đã áp dụng giảm ${data.percent}%`;
                msgEl.style.color = '#00ff88';
                updateShopUI();
            } else {
                currentDiscountPercent = 0;
                currentDiscountCode = "";
                msgEl.innerText = `❌ Mã không hợp lệ hoặc đã hết lượt`;
                msgEl.style.color = '#ff4444';
                updateShopUI();
            }
        }

        function confirmShopPurchase() {
            if(!currentProduct) return;
            if(currentProduct[`stock_${currentDuration}`] <= 0) {
                showCustomAlert('❌', 'Hết hàng', 'Gói thời hạn này hiện đang hết hàng. Vui lòng chọn gói khác!');
                return;
            }
            if(globalClient.balance < currentPrice) {
                showCustomAlert('💸', 'Không đủ tiền', `Tài khoản của bạn không đủ để thanh toán.<br><br>Cần: <b style="color:#ff4444">${currentPrice.toLocaleString()} VNĐ</b><br>Đang có: <b style="color:#00ff88">${globalClient.balance.toLocaleString()} VNĐ</b><br><br>Vui lòng chuyển qua Tab <b>Nạp tiền</b> để nạp thêm!`);
                return;
            }

            let loaiStr = currentDuration === 'gio' ? '1 Giờ' : (currentDuration === 'ngay' ? '1 Ngày' : '1 Tháng');
            showCustomAlert('🛒', 'Xác nhận thanh toán', `Bạn muốn mua key <b>${currentProduct.ten_game} - ${loaiStr}</b><br><br>Tổng tiền: <b style="color:#00ff88; font-size:18px;">${currentPrice.toLocaleString()} VNĐ</b>`, executeShopPurchase);
        }

        async function executeShopPurchase() {
            let uid = telegramUser ? telegramUser.id : "guest_123";
            const res = await fetch('/api/purchase_key', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: uid, game_id: currentProduct.id, loai_key: currentDuration, discount_code: currentDiscountCode})
            });
            const data = await res.json();
            if(data.success) {
                // Hiệu ứng pháo hoa siêu đẹp
                if (typeof confetti === 'function') {
                    var duration = 3000;
                    var end = Date.now() + duration;
                    (function frame() {
                        confetti({ particleCount: 5, angle: 60, spread: 55, origin: { x: 0 }, colors: ['#c850c0', '#4158d0', '#00ff88'] });
                        confetti({ particleCount: 5, angle: 120, spread: 55, origin: { x: 1 }, colors: ['#c850c0', '#4158d0', '#00ff88'] });
                        if (Date.now() < end) requestAnimationFrame(frame);
                    }());
                }
                
                showCustomAlert('🎉', 'Mua Key Thành Công!', `Giao dịch thành công. Key của bạn là:<br><br><span style="background:rgba(255,255,255,0.1); padding:10px 15px; border-radius:8px; display:inline-block; font-family:monospace; color:#00ffcc; font-size:16px; border:1px dashed #c850c0;">${data.key}</span><br><br><small style="color:#a0a0b8">Key đã được lưu vào Tab [Key của tôi]</small>`);
                globalClient = await fetchClientData();
                lastBalance = globalClient.balance;
                updateUI(); // Cập nhật lại UI tồn kho & tiền
            } else {
                showCustomAlert('❌', 'Lỗi giao dịch', data.message);
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
            if self.path == "/":
                self.send_response(302); self.send_header("Location", "/admin"); self.end_headers(); return
            elif self.path == "/app":
                self.send_response(200); self.send_header("Content-type", "text/html; charset=utf-8"); self.end_headers()
                self.wfile.write(TRANG_MINI_APP.encode("utf-8"))
            elif self.path == "/health":
                self.send_response(200); self.send_header("Content-type", "text/plain; charset=utf-8"); self.end_headers()
                self.wfile.write("OK".encode("utf-8"))
            elif self.path.startswith("/api/check_discount"):
                query = parse_qs(urlparse(self.path).query)
                code = query.get('code', [''])[0]
                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()
                con_tro.execute("SELECT phan_tram, so_luong FROM ma_giam_gia WHERE ma_code=?", (code,))
                row = con_tro.fetchone()
                kn.close()
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                if row and row[1] > 0:
                    self.wfile.write(json.dumps({"success": True, "percent": row[0]}).encode('utf-8'))
                else:
                    self.wfile.write(json.dumps({"success": False}).encode('utf-8'))

            elif self.path.startswith("/api/sync_client"):
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
                        "stock_gio": stocks.get('gio', 0), "stock_ngay": stocks.get('ngay', 0), "stock_thang": stocks.get('thang', 0)
                    })

                con_tro.execute("SELECT k.ma_key, g.ten_game, k.loai_key, k.ngay_ban FROM kho_key_dong k JOIN san_pham_game g ON k.game_id = g.id WHERE k.nguoi_mua=? ORDER BY k.ngay_ban DESC", (uid,))
                my_keys = [{"key": r[0], "game": r[1], "loai": r[2], "thoi_gian": r[3]} for r in con_tro.fetchall()]

                con_tro.execute("SELECT so_tien, ngay_nap FROM lich_su_nap WHERE nguoi_dung_id=? ORDER BY ngay_nap DESC", (uid,))
                history = [{"tien": r[0], "thoi_gian": r[1]} for r in con_tro.fetchall()]
                
                kn.close()

                res_body = {"name": name, "balance": so_du, "blocked": (trang_thai == 'bi_ban'), "catalog": catalog, "my_keys": my_keys, "history": history}
                self.send_response(200); self.send_header("Content-type", "application/json; charset=utf-8"); self.end_headers()
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
                
                con_tro.execute("SELECT ma_code, phan_tram, so_luong FROM ma_giam_gia")
                discounts = [{"ma_code": r[0], "phan_tram": r[1], "so_luong": r[2]} for r in con_tro.fetchall()]

                kn.close()
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"games": games, "counts": counts, "discounts": discounts}).encode('utf-8'))
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
                    err = '<div style="color:#ff0055; margin-bottom:15px; font-weight:bold;">❌ Sai tài khoản hoặc mật khẩu!</div>'
                    self.wfile.write(TRANG_ĐĂNG_NHẬP_ADMIN.replace("{error_placeholder}", err).encode("utf-8"))

            elif self.path == "/api/purchase_key":
                req = json.loads(post_data.decode('utf-8'))
                uid = req.get('user_id')
                game_id = req.get('game_id')
                loai_key = req.get('loai_key')
                discount_code = req.get('discount_code', '')

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
                
                gia_goc = g_row[0] if loai_key == 'gio' else (g_row[1] if loai_key == 'ngay' else g_row[2])
                giam_gia = 0

                if discount_code:
                    con_tro.execute("SELECT phan_tram, so_luong FROM ma_giam_gia WHERE ma_code=?", (discount_code,))
                    mg = con_tro.fetchone()
                    if mg and mg[1] > 0:
                        giam_gia = mg[0]
                
                gia_cuoi = int(gia_goc * (1 - giam_gia / 100.0))

                if (user_row[0] if user_row else 0) < gia_cuoi:
                    self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "message": "Số dư không đủ!"}).encode('utf-8'))
                    kn.close(); return

                con_tro.execute("SELECT id, ma_key FROM kho_key_dong WHERE game_id=? AND loai_key=? AND trang_thai='con_hang' LIMIT 1", (game_id, loai_key))
                k_row = con_tro.fetchone()
                
                if k_row:
                    con_tro.execute("UPDATE khach_hang SET so_du = so_du - ? WHERE nguoi_dung_id=?", (gia_cuoi, uid))
                    con_tro.execute("UPDATE kho_key_dong SET trang_thai='da_ban', nguoi_mua=?, ngay_ban=? WHERE id=?", (uid, datetime.now().isoformat(), k_row[0]))
                    if giam_gia > 0:
                        con_tro.execute("UPDATE ma_giam_gia SET so_luong = so_luong - 1 WHERE ma_code=?", (discount_code,))
                    kn.commit()
                    res = {"success": True, "key": k_row[1]}
                else:
                    res = {"success": False, "message": "Hết hàng!"}
                
                kn.close()
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(res).encode('utf-8'))
            
            elif self.path == "/api/admin/broadcast":
                if not self.xac_thuc_admin():
                    self.send_response(401); self.end_headers(); return
                req = json.loads(post_data.decode('utf-8'))
                msg = req.get('message', '')
                
                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()
                con_tro.execute("SELECT nguoi_dung_id FROM khach_hang")
                users = con_tro.fetchall()
                kn.close()

                thanh_cong = 0
                for u in users:
                    chat_id = u[0]
                    url = f"https://api.telegram.org/bot{MÃ_TOKEN}/sendMessage"
                    data = urllib.parse.urlencode({'chat_id': chat_id, 'text': msg}).encode('utf-8')
                    try:
                        urllib.request.urlopen(url, data=data, timeout=3)
                        thanh_cong += 1
                    except Exception:
                        pass

                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"success": True, "count": thanh_cong}).encode('utf-8'))

            elif self.path == "/api/admin/delete_game":
                if not self.xac_thuc_admin():
                    self.send_response(401); self.end_headers(); return
                req = json.loads(post_data.decode('utf-8'))
                gid = req.get('game_id')
                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()
                con_tro.execute("DELETE FROM san_pham_game WHERE id=?", (gid,))
                con_tro.execute("DELETE FROM kho_key_dong WHERE game_id=?", (gid,))
                kn.commit(); kn.close()
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            
            elif self.path == "/api/admin/delete_discount":
                if not self.xac_thuc_admin():
                    self.send_response(401); self.end_headers(); return
                req = json.loads(post_data.decode('utf-8'))
                code = req.get('ma_code')
                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()
                con_tro.execute("DELETE FROM ma_giam_gia WHERE ma_code=?", (code,))
                kn.commit(); kn.close()
                self.send_response(200); self.send_header("Content-type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))

            elif self.path in ["/api/admin/deposit", "/api/admin/ban", "/api/admin/add_game", "/api/admin/import_keys", "/api/admin/add_discount"]:
                if not self.xac_thuc_admin():
                    self.send_response(401); self.end_headers(); return
                
                req = json.loads(post_data.decode('utf-8'))
                kn = sqlite3.connect("he_thong_ban_key.db")
                con_tro = kn.cursor()

                if self.path == "/api/admin/deposit":
                    amt = float(req.get('amount', 0))
                    uid = req.get('user_id')
                    con_tro.execute("UPDATE khach_hang SET so_du = so_du + ? WHERE nguoi_dung_id=?", (amt, uid))
                    con_tro.execute("INSERT INTO lich_su_nap (nguoi_dung_id, so_tien) VALUES (?, ?)", (uid, amt))
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
                elif self.path == "/api/admin/add_discount":
                    ma_code = req.get('ma_code')
                    phan_tram = int(req.get('phan_tram', 0))
                    so_luong = int(req.get('so_luong', 0))
                    con_tro.execute("INSERT OR REPLACE INTO ma_giam_gia (ma_code, phan_tram, so_luong) VALUES (?, ?, ?)", (ma_code, phan_tram, so_luong))

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

    ban_phim = InlineKeyboardMarkup([[InlineKeyboardButton("🛍 MỞ HELY SHOP 🛍", web_app=WebAppInfo(url=f"{URL_ỨNG_DỤNG}/app"))]])
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
    cổng = int(os.environ.get("PORT", 10000))
    luong_http = threading.Thread(target=chạy_máy_chủ_http, args=(cổng,), daemon=True)
    luong_http.start()
    
    bot_app = Application.builder().token(MÃ_TOKEN).post_init(khoi_tao_kem_ping).build()
    bot_app.add_handler(CommandHandler("start", bắt_đầu))
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
