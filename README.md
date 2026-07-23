# 🏭 AI Kho Hàng — Hướng dẫn cài đặt

## Yêu cầu
- Python 3.10 trở lên
- Anthropic API Key (lấy tại https://console.anthropic.com)

---

## Cài đặt (5 bước)

### Bước 1 — Tải Python
Vào https://www.python.org/downloads/ → tải Python 3.11 → cài đặt.
Lưu ý: **tick vào "Add Python to PATH"** khi cài.

### Bước 2 — Mở Terminal / Command Prompt
- Windows: nhấn `Win + R` → gõ `cmd` → Enter
- Mac: nhấn `Cmd + Space` → gõ `Terminal` → Enter

### Bước 3 — Vào thư mục app và cài thư viện
```bash
cd đường_dẫn_đến_thư_mục_warehouse_ai

# Cài các thư viện cần thiết
pip install -r requirements.txt
```

### Bước 4 — Chạy app
```bash
streamlit run app.py
```
Trình duyệt sẽ tự mở tại http://localhost:8501

### Bước 5 — Sử dụng
1. Nhập **Anthropic API Key** vào sidebar bên trái
2. Tải lên file Excel của bạn (hoặc bấm "Tạo file mẫu")
3. Bật toggle **Mã hóa dữ liệu nhạy cảm**
4. Chuyển sang tab **Hỏi AI** và đặt câu hỏi!

---

## Cấu trúc file Excel

App hỗ trợ Excel nhiều sheet. Tên cột gợi ý:

| Tên cột | Ý nghĩa | Nhạy cảm? |
|---------|---------|-----------|
| ma_hang | Mã sản phẩm | Không |
| ten_hang | Tên sản phẩm | Không |
| don_vi | Đơn vị tính | Không |
| ton_kho | Số lượng tồn | **Có** |
| ton_kho_min | Ngưỡng tối thiểu | Không |
| nha_cung_cap | Tên nhà cung cấp | **Có** |
| gia_nhap | Giá nhập vào | **Có** |
| gia_ban | Giá bán ra | **Có** |

Bạn có thể đặt tên cột tự do — chỉnh danh sách field nhạy cảm trong sidebar.

---

## Bảo mật

- Khóa mã hóa AES-256 lưu tại `data/.secret.key` trên máy bạn
- File Excel lưu tại `data/warehouse.xlsx` — không upload lên cloud
- AI chỉ nhận token, không bao giờ thấy giá trị thật của field nhạy cảm

---

## Deploy lên Streamlit Cloud (tùy chọn)

Nếu muốn truy cập từ xa:
1. Tạo tài khoản tại https://streamlit.io
2. Push code lên GitHub (riêng tư)
3. Connect Streamlit Cloud với repo
4. Thêm `ANTHROPIC_API_KEY` vào Secrets

**Lưu ý:** Khi deploy cloud, không lưu file nhạy cảm trên repo — dùng Streamlit Secrets.
