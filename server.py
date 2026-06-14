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
from urllib.parse import parse_qs  # Fix: Import chuẩn thư viện hệ thống
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

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
phiên_đăng_nhập = {} # Lưu trữ session_id: expiry_time

# Bộ nhớ tạm cấu hình Anti-DDoS (Rate Limit: tối đa 5 requests/giây mỗi IP)
LỊCH_SỬ_REQUEST = {}

# --- Khởi tạo cơ sở dữ liệu ---
def khởi_tạo_cơ_sở_dữ_liệu():
    kết_nối = sqlite3.connect("he_thong_ban_key.db", check_same_thread=False)
    # Bật chế độ WAL để ghi và đọc dữ liệu đồng thời không bị khóa DB (Chống die luồng)
    kết_nối.execute("PRAGMA journal_mode=WAL;")
    con_trỏ = kết_nối.cursor()
    
    # Bảng sản phẩm
    con_trỏ.execute('''
        CREATE TABLE IF NOT EXISTS san_pham (
            id TEXT PRIMARY KEY,
            ten TEXT NOT NULL,
            mo_ta TEXT,
            gia REAL NOT NULL,
            so_luong INTEGER DEFAULT 0,
            ngay_tao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Bảng key
    con_trỏ.execute('''
        CREATE TABLE IF NOT EXISTS key_san_pham (
            id TEXT PRIMARY KEY,
            san_pham_id TEXT NOT NULL,
            key_gia_tri TEXT NOT NULL UNIQUE,
            trang_thai TEXT DEFAULT 'con_hang',
            ngay_tao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ngay_ban TIMESTAMP,
            nguoi_mua TEXT,
            FOREIGN KEY (san_pham_id) REFERENCES san_pham (id)
        )
    ''')
    
    # Bảng giao dịch
    con_trỏ.execute('''
        CREATE TABLE IF NOT EXISTS giao_dich (
            id TEXT PRIMARY KEY,
            nguoi_dung_id TEXT NOT NULL,
            ten_nguoi_dung TEXT,
            san_pham_id TEXT NOT NULL,
            key_id TEXT NOT NULL,
            gia REAL NOT NULL,
            ngay_mua TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (san_pham_id) REFERENCES san_pham (id),
            FOREIGN KEY (key_id) REFERENCES key_san_pham (id)
        )
    ''')
    
    # Bảng lưu danh sách khách hàng để gửi thông báo hàng loạt
    con_trỏ.execute('''
        CREATE TABLE IF NOT EXISTS khach_hang (
            nguoi_dung_id TEXT PRIMARY KEY,
            ten_nguoi_dung TEXT,
            ngay_tuong_tac TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    kết_nối.commit()
    kết_nối.close()

khởi_tạo_cơ_sở_dữ_liệu()

# --- BIẾN TOÀN CỤC LƯU TRỮ ỨNG DỤNG BOT ---
bot_app = None

# --- GIAO DIỆN WEB ---
GIAO_DIỆN_CHUNG_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background: linear-gradient(135deg, #ffb6c1, #ff69b4, #ff1493, #ff69b4);
        background-size: 400% 400%;
        animation: gradientBG 12s ease infinite;
        min-height: 100vh;
        color: #fff;
        overflow-x: hidden;
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
"""

TRANG_ĐĂNG_NHẬP_ADMIN = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>🌸 Đăng nhập Quản trị viên</title>
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
        .btn-submit:hover {{ transform: scale(1.03); box-shadow: 0 8px 20px rgba(255,20,147,0.6); }}
        .error {{ color: #ffff00; font-weight: bold; margin-bottom: 15px; text-shadow: 0 0 5px #000; }}
    </style>
</head>
<body>
    <div class="sparkles" id="sparkles"></div>
    <div class="main-box login-container">
        <h2>🌸 Admin Login 🌸</h2>
        {{error_placeholder}}
        <form method="POST" action="/admin/login">
            <div class="input-group">
                <label>Tài khoản ✨</label>
                <input type="text" name="username" required placeholder="Nhập tài khoản...">
            </div>
            <div class="input-group">
                <label>Mật khẩu ✨</label>
                <input type="password" name="password" required placeholder="Nhập mật khẩu...">
            </div>
            <button type="submit" class="btn-submit">ĐĂNG NHẬP 💖</button>
        </form>
    </div>
    <script>
        for (let i = 0; i < 30; i++) {{
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
    <meta charset="UTF-8">
    <title>🌸 Hệ Thống Quản Trị - Key Store</title>
    <style>
        {GIAO_DIỆN_CHUNG_CSS}
        .container {{ max-width: 1000px; margin: 30px auto; padding: 20px; position: relative; z-index: 2; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }}
        .header h1 {{ text-shadow: 0 0 15px #fff; }}
        .btn-logout {{ padding: 10px 20px; background: #fff; color: #ff1493; border-radius: 20px; text-decoration: none; font-weight: bold; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }}
        @media(max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
        .card {{ padding: 20px; }}
        .card h3 {{ margin-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.4); padding-bottom: 5px; }}
        .form-group {{ margin-bottom: 12px; }}
        label {{ display: block; font-size: 0.9em; margin-bottom: 5px; font-weight: bold; }}
        input, select, textarea {{ width: 100%; padding: 10px; border-radius: 8px; border: none; outline: none; }}
        button {{
            padding: 10px 20px; background: linear-gradient(135deg, #ff1493, #ff69b4); border: none;
            color: #fff; font-weight: bold; border-radius: 8px; cursor: pointer; width: 100%; margin-top: 10px;
        }}
        button:hover {{ opacity: 0.9; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; background: rgba(0,0,0,0.2); border-radius: 10px; overflow: hidden; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        th {{ background: rgba(0,0,0,0.4); }}
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
        
        <div id="alertBox" class="alert"></div>

        <div class="grid">
            <div class="main-box card">
                <h3>⚡ TÙY CHỈNH GIÁ SẢN PHẨM</h3>
                <form id="formGia">
                    <div class="form-group">
                        <label>Chọn sản phẩm</label>
                        <select name="product_id" id="selectSpGia" required></select>
                    </div>
                    <div class="form-group">
                        <label>Giá tiền mới (VNĐ)</label>
                        <input type="number" name="gia" required placeholder="Ví dụ: 60000">
                    </div>
                    <button type="submit">CẬP NHẬT GIÁ 💎</button>
                </form>
            </div>

            <div class="main-box card">
                <h3>📦 THÊM KEY MỚI VÀO KHO</h3>
                <form id="formKey">
                    <div class="form-group">
                        <label>Chọn sản phẩm</label>
                        <select name="product_id" id="selectSpKey" required></select>
                    </div>
                    <div class="form-group">
                        <label>Giá trị của Key</label>
                        <input type="text" name="key_val" required placeholder="Nhập mã key...">
                    </div>
                    <button type="submit">THÊM KEY VÀO HỆ THỐNG 🔑</button>
                </form>
            </div>
        </div>

        <div class="main-box card" style="margin-bottom: 30px;">
            <h3>📢 GỬI THÔNG BÁO TELEGRAM MINI APP</h3>
            <p style="font-size: 0.85em; margin-bottom: 10px; color: #ffff00;">* Hệ thống sẽ gửi tin nhắn thông báo này đến toàn bộ khách hàng đã từng mở bot.</p>
            <form id="formNotify">
                <div class="form-group">
                    <label>Nội dung thông báo thông điệp lấp lánh</label>
                    <textarea name="message" rows="3" required placeholder="Nhập nội dung sự kiện, khuyến mãi tại đây..."></textarea>
                </div>
                <button type="submit" style="background: linear-gradient(135deg, #00cbfe, #0076fe);">PHÁT ĐỒNG LOẠT THÔNG BÁO 🚀</button>
            </form>
        </div>

        <div class="main-box card">
            <h3>📊 DANH SÁCH SẢN PHẨM HIỆN TẠI</h3>
            <table>
                <thead>
                    <tr>
                        <th>ID sản phẩm</th>
                        <th>Tên sản phẩm</th>
                        <th>Giá hiện tại</th>
                        <th>Số lượng tồn kho</th>
                    </tr>
                </thead>
                <tbody id="tableSp"></tbody>
            </table>
        </div>
    </div>

    <script>
        for (let i = 0; i < 40; i++) {{
            let s = document.createElement('div'); s.className = 'sparkle';
            s.style.left = Math.random() * 100 + '%'; s.style.animationDelay = Math.random() * 3 + 's';
            document.getElementById('sparkles').appendChild(s);
        }}

        function showAlert(msg) {{
            const box = document.getElementById('alertBox');
            box.textContent = msg; box.style.display = 'block';
            setTimeout(() => box.style.display = 'none', 4000);
        }}

        async function taiThongTin() {{
            const res = await fetch('/api/products');
            const data = await res.json();
            let tbody = '', options = '';
            data.forEach(sp => {{
                tbody += `<tr><td>${{sp.id}}</td><td><b>${{sp.ten}}</b></td><td>${{sp.gia.toLocaleString()}}đ</td><td>${{sp.so_luong}} cái</td></tr>`;
                options += `<option value="${{sp.id}}">${{sp.ten}} (${{sp.gia.toLocaleString()}}đ)</option>`;
            }});
            document.getElementById('tableSp').innerHTML = tbody;
            document.getElementById('selectSpGia').innerHTML = options;
            document.getElementById('selectSpKey').innerHTML = options;
        }}

        document.getElementById('formGia').onsubmit = async (e) => {{
            e.preventDefault();
            const formData = new FormData(e.target);
            const res = await fetch('/api/admin/update_price', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(Object.fromEntries(formData))
            }});
            const data = await res.json();
            if(data.success) {{ showAlert("✅ Đã cập nhật giá bán mới!"); taiThongTin(); }}
        }};

        document.getElementById('formKey').onsubmit = async (e) => {{
            e.preventDefault();
            const formData = new FormData(e.target);
            const res = await fetch('/api/admin/add_key', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(Object.fromEntries(formData))
            }});
            const data = await res.json();
            if(data.success) {{ showAlert("✅ Đã thêm mã key mới thành công!"); e.target.reset(); taiThongTin(); }}
        }};

        document.getElementById('formNotify').onsubmit = async (e) => {{
            e.preventDefault();
            const formData = new FormData(e.target);
            const res = await fetch('/api/admin/send_notification', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(Object.fromEntries(formData))
            }});
            const data = await res.json();
            showAlert(`🚀 Kết quả thông báo: ${{data.message}}`);
            if(data.success) e.target.reset();
        }};

        taiThongTin();
    </script>
</body>
</html>
"""

# Import mã HTML trang Mini app của bạn
from biệt_danh_giao_dien_gốc import TRANG_MINI_APP_GỐC
TRANG_MINI_APP = TRANG_MINI_APP_GỐC if 'TRANG_MINI_APP_GỐC' in globals() else """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌸 Key Store - Cửa hàng Key Tự Động</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #ffb6c1, #ff69b4, #ff1493, #ff69b4);
            background-size: 400% 400%; animation: gradientBG 8s ease infinite;
            min-height: 100vh; color: #fff; overflow-x: hidden; position: relative;
        }
        @keyframes gradientBG { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        .sparkles { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1; }
        .sparkle { position: absolute; width: 4px; height: 4px; background: #fff; border-radius: 50%; animation: sparkleFloat 3s linear infinite; box-shadow: 0 0 10px #fff, 0 0 20px #ff69b4, 0 0 30px #ff1493; }
        @keyframes sparkleFloat { 0% { transform: translateY(100vh) scale(0); opacity: 0; } 10% { opacity: 1; } 90% { opacity: 1; } 100% { transform: translateY(-10vh) scale(1.5); opacity: 0; } }
        .container { position: relative; z-index: 2; max-width: 450px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; padding: 30px 20px 20px; position: relative; }
        .header h1 { font-size: 2.5em; font-weight: 800; text-shadow: 0 0 20px rgba(255,255,255,0.8), 0 0 40px #ff1493; animation: titleGlow 2s ease-in-out infinite alternate; }
        @keyframes titleGlow { from { text-shadow: 0 0 20px rgba(255,255,255,0.8), 0 0 40px #ff1493; } to { text-shadow: 0 0 30px rgba(255,255,255,1), 0 0 60px #ff69b4, 0 0 80px #ff1493; } }
        .header p { font-size: 1.1em; opacity: 0.9; margin-top: 5px; }
        .product-card { background: rgba(255, 255, 255, 0.2); backdrop-filter: blur(15px); border-radius: 20px; padding: 25px; margin: 15px 0; border: 2px solid rgba(255,255,255,0.3); transition: transform 0.3s ease, box-shadow 0.3s ease; animation: cardFloat 3s ease-in-out infinite; }
        @keyframes cardFloat { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-10px); } }
        .product-card:hover { transform: translateY(-5px) scale(1.02); box-shadow: 0 15px 35px rgba(255,20,147,0.5); }
        .product-name { font-size: 1.8em; font-weight: 700; text-shadow: 0 0 10px #ff1493; margin-bottom: 8px; }
        .product-desc { font-size: 0.95em; opacity: 0.8; margin-bottom: 12px; }
        .product-price { font-size: 2em; font-weight: 800; text-shadow: 0 0 15px #ffd700; margin-bottom: 15px; }
        .btn-buy { background: linear-gradient(135deg, #ff69b4, #ff1493); color: white; border: none; padding: 14px 35px; font-size: 1.2em; font-weight: 700; border-radius: 50px; cursor: pointer; box-shadow: 0 8px 25px rgba(255,20,147,0.5); transition: all 0.3s ease; width: 100%; letter-spacing: 1px; }
        .btn-buy:hover { transform: scale(1.05); box-shadow: 0 12px 35px rgba(255,20,147,0.8); }
        .btn-buy:active { transform: scale(0.95); }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 100; justify-content: center; align-items: center; }
        .modal-content { background: rgba(255,105,180,0.95); backdrop-filter: blur(20px); border-radius: 20px; padding: 30px; width: 90%; max-width: 400px; text-align: center; border: 2px solid #fff; animation: modalIn 0.4s ease; }
        @keyframes modalIn { from { transform: scale(0.5); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        .modal h2 { font-size: 2em; margin-bottom: 15px; text-shadow: 0 0 15px #fff; }
        .key-display { background: rgba(0,0,0,0.4); border-radius: 10px; padding: 15px; font-family: monospace; font-size: 1.1em; margin: 15px 0; word-break: break-all; border: 1px dashed #fff; }
        .btn-close { background: white; color: #ff1493; border: none; padding: 12px 30px; font-size: 1em; font-weight: 700; border-radius: 50px; cursor: pointer; margin-top: 15px; }
        .loading { display: none; position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 200; }
        .loading-spinner { width: 60px; height: 60px; border: 5px solid rgba(255,255,255,0.3); border-top-color: #fff; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .footer { text-align: center; padding: 30px 20px; opacity: 0.7; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="sparkles" id="sparklesContainer"></div>
    <div class="container">
        <div class="header">
            <h1>🌸 Key Store</h1>
            <p>✨ Cửa hàng key tự động ✨</p>
        </div>
        <div id="productsContainer"></div>
        <div class="footer">
            <p>💖 Cảm ơn bạn đã tin tưởng! 💖</p>
            <p>Hỗ trợ: @admin</p>
        </div>
    </div>
    <div class="modal" id="keyModal">
        <div class="modal-content">
            <h2>🎉 Mua thành công!</h2>
            <p>Key của bạn:</p>
            <div class="key-display" id="keyDisplay">Đang tải key...</div>
            <button class="btn-close" onclick="dongModal()">ĐÓNG ✨</button>
        </div>
    </div>
    <div class="loading" id="loading"><div class="loading-spinner"></div></div>

    <script>
        function taoLapLanh() {
            const container = document.getElementById('sparklesContainer');
            for (let i = 0; i < 40; i++) {
                const sparkle = document.createElement('div');
                sparkle.className = 'sparkle';
                sparkle.style.left = Math.random() * 100 + '%';
                sparkle.style.animationDelay = Math.random() * 3 + 's';
                container.appendChild(sparkle);
            }
        }
        function hienLoading() { document.getElementById('loading').style.display = 'block'; }
        function anLoading() { document.getElementById('loading').style.display = 'none'; }
        function dongModal() { document.getElementById('keyModal').style.display = 'none'; }

        async function taiDanhSachSanPham() {
            try {
                const res = await fetch('/api/products');
                const data = await res.json();
                let html = '';
                data.forEach(p => {
                    html += `
                    <div class="product-card">
                        <div class="product-name">🎮 ${p.ten}</div>
                        <div class="product-desc">${p.mo_ta}</div>
                        <div class="product-price">${p.gia.toLocaleString()}đ</div>
                        <p style="font-size:0.85em; margin-bottom:10px;">📦 Còn lại: ${p.so_luong} key</p>
                        <button class="btn-buy" onclick="muaKey('${p.id}')">MUA NGAY 💖</button>
                    </div>`;
                });
                document.getElementById('productsContainer').innerHTML = html;
            } catch (e) { console.error(e); }
        }

        async function muaKey(sanPhamId) {
            hienLoading();
            try {
                const tg = window.Telegram?.WebApp;
                let userId = 'guest'; let userName = 'Khách';
                if (tg?.initDataUnsafe?.user) {
                    userId = tg.initDataUnsafe.user.id;
                    userName = tg.initDataUnsafe.user.first_name || 'User';
                }
                const response = await fetch('/buy', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ product_id: sanPhamId, user_id: String(userId), user_name: userName })
                });
                const data = await response.json();
                anLoading();
                if (data.success) {
                    document.getElementById('keyDisplay').textContent = data.key;
                    document.getElementById('keyModal').style.display = 'flex';
                    taiDanhSachSanPham();
                } else { alert('❌ ' + (data.message || 'Lỗi khi mua hàng')); }
            } catch (error) { anLoading(); alert('❌ Lỗi kết nối: ' + error.message); }
        }
        taoLapLanh(); taiDanhSachSanPham();
    </script>
</body>
</html>
"""

# --- MÁY CHỦ HTTP ---
class BộXửLýYêuCầu(BaseHTTPRequestHandler):
    
    def kiem_tra_ddos(self):
        ip_khach = self.client_address[0]
        thoi_gian_hien_tai = time.time()
        if ip_khach in LỊCH_SỬ_REQUEST:
            lich_su = LỊCH_SỬ_REQUEST[ip_khach]
            lich_su = [t for t in lich_su if thoi_gian_hien_tai - t < 1.0]
            LỊCH_SỬ_REQUEST[ip_khach] = lich_su
            if len(lich_su) > 5:
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
                
            elif self.path == "/api/products":
                ket_noi = sqlite3.connect("he_thong_ban_key.db")
                con_tro = ket_noi.cursor()
                con_tro.execute("SELECT id, ten, mo_ta, gia, so_luong FROM san_pham")
                sp_list = [{"id": r[0], "ten": r[1], "mo_ta": r[2], "gia": r[3], "so_luong": r[4]} for r in con_tro.fetchall()]
                ket_noi.close()
                self.send_response(200)
                self.send_header("Content-type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(sp_list).encode('utf-8'))

            elif self.path == "/admin":
                if self.xac_thuc_admin():
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(TRANG_BẢNG_ĐIỀU_KHIỂN_ADMIN.encode("utf-8"))
                else:
                    self.send_response(302); self.send_header("Location", "/admin/login"); self.end_headers()

            elif self.path == "/admin/login":
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(TRANG_ĐĂNG_NHẬP_ADMIN.replace("{error_placeholder}", "").encode("utf-8"))

            elif self.path == "/admin/logout":
                self.send_response(302)
                self.send_header("Set-Cookie", "session_id=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/")
                self.send_header("Location", "/admin/login")
                self.end_headers()
            else:
                self.send_response(404); self.end_headers()
        except Exception as e:
            bộ_ghi_nhật_ký.error(f"Lỗi hệ thống luồng GET: {e}")
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
                    self.send_response(302)
                    self.send_header("Set-Cookie", f"session_id={sid}; Path=/; HttpOnly")
                    self.send_header("Location", "/admin")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.end_headers()
                    err_msg = '<div class="error">❌ Sai tài khoản hoặc mật khẩu rồi!</div>'
                    self.wfile.write(TRANG_ĐĂNG_NHẬP_ADMIN.replace("{error_placeholder}", err_msg).encode("utf-8"))

            elif self.path == "/buy":
                data = json.loads(post_data.decode('utf-8'))
                san_pham_id = data.get('product_id')
                nguoi_dung_id = str(data.get('user_id', 'guest'))
                ten_nguoi_dung = data.get('user_name', 'Khách')
                
                if nguoi_dung_id != 'guest':
                    kn = sqlite3.connect("he_thong_ban_key.db")
                    kn.execute("INSERT OR REPLACE INTO khach_hang (nguoi_dung_id, ten_nguoi_dung) VALUES (?, ?)", (nguoi_dung_id, ten_nguoi_dung))
                    kn.commit(); kn.close()

                ket_noi = sqlite3.connect("he_thong_ban_key.db")
                con_tro = ket_noi.cursor()
                con_tro.execute("SELECT id, key_gia_tri FROM key_san_pham WHERE san_pham_id=? AND trang_thai='con_hang' LIMIT 1", (san_pham_id,))
                key_data = con_tro.fetchone()
                
                if key_data:
                    key_id, key_gia_tri = key_data
                    con_tro.execute("UPDATE key_san_pham SET trang_thai='da_ban', ngay_ban=?, nguoi_mua=? WHERE id=?", (datetime.now().isoformat(), nguoi_dung_id, key_id))
                    con_tro.execute("UPDATE san_pham SET so_luong = so_luong - 1 WHERE id=?", (san_pham_id,))
                    con_tro.execute("INSERT INTO giao_dich (id, nguoi_dung_id, ten_nguoi_dung, san_pham_id, key_id, gia) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), nguoi_dung_id, ten_nguoi_dung, san_pham_id, key_id, 0))
                    ket_noi.commit()
                    phan_hoi = {"success": True, "key": key_gia_tri}
                else:
                    phan_hoi = {"success": False, "message": "Hết hàng mất rồi bạn ơi!"}
                ket_noi.close()
                
                self.send_response(200)
                self.send_header("Content-type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(phan_hoi).encode("utf-8"))

            elif self.path in ["/api/admin/update_price", "/api/admin/add_key", "/api/admin/send_notification"]:
                if not self.xac_thuc_admin():
                    self.send_response(401); self.end_headers(); return
                
                req_data = json.loads(post_data.decode('utf-8'))
                ket_noi = sqlite3.connect("he_thong_ban_key.db")
                con_tro = ket_noi.cursor()
                
                if self.path == "/api/admin/update_price":
                    sp_id = req_data.get('product_id')
                    gia_moi = float(req_data.get('gia', 0))
                    con_tro.execute("UPDATE san_pham SET gia=? WHERE id=?", (gia_moi, sp_id))
                    ket_noi.commit()
                    res_body = {"success": True}

                elif self.path == "/api/admin/add_key":
                    sp_id = req_data.get('product_id')
                    key_val = req_data.get('key_val')
                    con_tro.execute("INSERT INTO key_san_pham (id, san_pham_id, key_gia_tri) VALUES (?, ?, ?)", (str(uuid.uuid4()), sp_id, key_val))
                    con_tro.execute("UPDATE san_pham SET so_luong = so_luong + 1 WHERE id=?", (sp_id,))
                    ket_noi.commit()
                    res_body = {"success": True}

                elif self.path == "/api/admin/send_notification":
                    noi_dung = req_data.get('message', '')
                    con_tro.execute("SELECT nguoi_dung_id FROM khach_hang")
                    ids_khach = [r[0] for r in con_tro.fetchall()]
                    
                    thành_công = 0
                    if bot_app and noi_dung:
                        for cid in ids_khach:
                            try:
                                asyncio.run_coroutine_threadsafe(
                                    bot_app.bot.send_message(chat_id=int(cid), text=f"🌸 <b>THÔNG BÁO CỬA HÀNG:</b>\n\n{noi_dung}", parse_mode="HTML"),
                                    bot_app.loop
                                )
                                thành_công += 1
                            except Exception:
                                pass
                    res_body = {"success": True, "message": f"Đã đẩy yêu cầu gửi tới {thành_công}/{len(ids_khach)} khách hàng!"}

                ket_noi.close()
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(res_body).encode('utf-8'))
            else:
                self.send_response(404); self.end_headers()
        except Exception as e:
            bộ_ghi_nhật_ký.error(f"Lỗi xử lý luồng POST: {e}")
            self.send_response(500); self.end_headers()

    def log_message(self, format, *args):
        pass

def chạy_máy_chủ_http(cổng=10000):
    may_chu = HTTPServer(('0.0.0.0', cổng), BộXửLýYêuCầu)
    bộ_ghi_nhật_ký.info(f"Máy chủ HTTP đang chạy trên cổng {cổng}")
    may_chu.serve_forever()

# --- CHỨC NĂNG CỦA BOT TELEGRAM ---
async def bắt_đầu(cập_nhật: Update, ngữ_cảnh: ContextTypes.DEFAULT_TYPE) -> None:
    uid = str(cập_nhật.effective_user.id)
    uname = cập_nhật.effective_user.first_name or "User"
    kn = sqlite3.connect("he_thong_ban_key.db")
    kn.execute("INSERT OR REPLACE INTO khach_hang (nguoi_dung_id, ten_nguoi_dung) VALUES (?, ?)", (uid, uname))
    kn.commit(); kn.close()

    ban_phim = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌸 MỞ CỬA HÀNG KEY 🌸", web_app=WebAppInfo(url=f"{URL_ỨNG_DỤNG}/app"))],
        [InlineKeyboardButton("📋 Xem sản phẩm", callback_data="xem_san_pham")],
        [InlineKeyboardButton("📊 Lịch sử mua", callback_data="lich_su")],
    ])
    await cập_nhật.message.reply_text(
        "╔══════════════════════╗\n║  🌸 KEY STORE VIP 🌸  ║\n╚══════════════════════╝\n\n"
        "💖 Chào mừng đến với cửa hàng bán key tự động lấp lánh!\n✨ Chọn bên dưới để bắt đầu mua sắm:",
        parse_mode="HTML", reply_markup=ban_phim
    )

async def xem_san_pham(cập_nhật: Update, ngữ_cảnh: ContextTypes.DEFAULT_TYPE) -> None:
    query = cập_nhật.callback_query; await query.answer()
    ket_noi = sqlite3.connect("he_thong_ban_key.db")
    con_tro = ket_noi.cursor()
    con_tro.execute("SELECT id, ten, gia, so_luong FROM san_pham")
    san_phams = con_tro.fetchall(); ket_noi.close()
    
    if not san_phams:
        await query.edit_message_text("🌸 Chưa có sản phẩm nào trên hệ thống!")
        return
    
    ban_phim = []
    for sp in san_phams:
        ban_phim.append([InlineKeyboardButton(f"{sp[1]} - {sp[2]:,.0f}đ (Còn: {sp[3]})", callback_data=f"chon_sp_{sp[0]}")])
    ban_phim.append([InlineKeyboardButton("🔙 Quay lại", callback_data="quay_lai")])
    await query.edit_message_text("📋 <b>DANH SÁCH SẢN PHẨM:</b>\n\nChọn sản phẩm:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(ban_phim))

async def chon_san_pham(cập_nhật: Update, ngữ_cảnh: ContextTypes.DEFAULT_TYPE) -> None:
    query = cập_nhật.callback_query; await query.answer()
    sp_id = query.data.replace("chon_sp_", "")
    ket_noi = sqlite3.connect("he_thong_ban_key.db")
    con_tro = ket_noi.cursor()
    con_tro.execute("SELECT ten, mo_ta, gia, so_luong FROM san_pham WHERE id=?", (sp_id,))
    sp = con_tro.fetchone(); ket_noi.close()
    
    if not sp:
        await query.edit_message_text("❌ Sản phẩm không tồn tại!"); return
    
    ban_phim = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌸 MUA NGAY TRÊN WEB APP", web_app=WebAppInfo(url=f"{URL_ỨNG_DỤNG}/app"))],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="xem_san_pham")],
    ])
    await query.edit_message_text(f"🛍 <b>{sp[0]}</b>\n📝 {sp[1]}\n💰 Giá: {sp[2]:,.0f}đ\n📦 Còn: {sp[3]} key\n\n✨ Nhấn nút dưới để mua:", parse_mode="HTML", reply_markup=ban_phim)

async def lich_su_mua(cập_nhật: Update, ngữ_cảnh: ContextTypes.DEFAULT_TYPE) -> None:
    query = cập_nhật.callback_query; await query.answer()
    user_id = str(query.from_user.id)
    ket_noi = sqlite3.connect("he_thong_ban_key.db")
    con_tro = ket_noi.cursor()
    con_tro.execute("SELECT g.ngay_mua, s.ten FROM giao_dich g JOIN san_pham s ON g.san_pham_id = s.id WHERE g.nguoi_dung_id=? ORDER BY g.ngay_mua DESC LIMIT 10", (user_id,))
    giao_dichs = con_tro.fetchall(); ket_noi.close()
    
    if not giao_dichs:
        await query.edit_message_text("📊 Bạn chưa có giao dịch nào!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌸 Mua ngay", web_app=WebAppInfo(url=f"{URL_ỨNG_DỤNG}/app"))]]))
        return
    noi_dung = "📊 <b>LỊCH SỬ MUA HÀNG GẦN ĐÂY:</b>\n\n"
    for gd in giao_dichs: noi_dung += f"🛍 {gd[1]} - 📅 {gd[0][:16]}\n"
    await query.edit_message_text(noi_dung, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data="quay_lai")]]))

async def quay_lai(cập_nhật: Update, ngữ_cảnh: ContextTypes.DEFAULT_TYPE) -> None:
    query = cập_nhật.callback_query; await query.answer()
    ban_phim = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌸 MỞ CỬA HÀNG KEY 🌸", web_app=WebAppInfo(url=f"{URL_ỨNG_DỤNG}/app"))],
        [InlineKeyboardButton("📋 Xem sản phẩm", callback_data="xem_san_pham")],
        [InlineKeyboardButton("📊 Lịch sử mua", callback_data="lich_su")],
    ])
    await query.edit_message_text("╔══════════════════════╗\n║  🌸 KEY STORE VIP 🌸  ║\n╚══════════════════════╝\n\n💖 Chọn chức năng:", parse_mode="HTML", reply_markup=ban_phim)

# --- Cơ chế chống ngủ đông cho server Render Free ---
async def tự_ping_duy_trì_sự_sống(app: Application):
    import aiohttp
    await asyncio.sleep(15)
    while True:
        try:
            async with aiohttp.ClientSession() as phiên:
                async with phiên.get(f"{URL_ỨNG_DỤNG}/health", timeout=10) as phản_hồi:
                    if phản_hồi.status == 200:
                        bộ_ghi_nhật_ký.info("Chống ngủ đông Render: Đã kích hoạt mạch đập thành công.")
        except Exception as e:
            bộ_ghi_nhật_ký.error(f"Lỗi mạch duy trì sự sống: {e}")
        await asyncio.sleep(300)

async def khoi_tao_kem_ping(application: Application) -> None:
    asyncio.create_task(tự_ping_duy_trì_sự_sống(application))

# --- Hàm chính điều phối hệ thống ---
def main():
    global bot_app
    luong_http = threading.Thread(target=chạy_máy_chủ_http, args=(10000,), daemon=True)
    luong_http.start()
    
    bot_app = Application.builder().token(MÃ_TOKEN).post_init(khoi_tao_kem_ping).build()
    
    bot_app.add_handler(CommandHandler("start", bắt_đầu))
    bot_app.add_handler(CallbackQueryHandler(xem_san_pham, pattern="^xem_san_pham$"))
    bot_app.add_handler(CallbackQueryHandler(chon_san_pham, pattern="^chon_sp_"))
    bot_app.add_handler(CallbackQueryHandler(lich_su_mua, pattern="^lich_su$"))
    bot_app.add_handler(CallbackQueryHandler(quay_lai, pattern="^quay_lai$"))
    
    bộ_ghi_nhật_ký.info("🌸 Bot Key Store và Hệ thống Admin Web đang vận hành...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
