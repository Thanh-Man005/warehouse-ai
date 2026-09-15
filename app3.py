import streamlit as st
import pandas as pd
import plotly.express as px
import time

# --- 1. THIẾT LẬP TRANG ---
st.set_page_config(page_title="AI Kho Hàng", layout="wide", initial_sidebar_state="collapsed")

# --- 2. CSS NÚT AI CỐ ĐỊNH GÓC PHẢI ---
custom_css = """
<style>
div[data-testid="stElementContainer"]:has(button[aria-label*="hỗ trợ"]),
div[data-testid="stElementContainer"]:has(button[aria-label*="Hỗ trợ"]),
div[data-testid="stElementContainer"]:has(button[aria-label*="Bạn cần hỗ trợ"]) {
    position: fixed !important;
    bottom: 25px !important;
    right: 25px !important;
    z-index: 999999 !important;
    width: auto !important;
}

div[data-testid="stElementContainer"]:has(button[aria-label*="hỗ trợ"]) button,
div[data-testid="stElementContainer"]:has(button[aria-label*="Hỗ trợ"]) button,
div[data-testid="stElementContainer"]:has(button[aria-label*="Bạn cần hỗ trợ"]) button {
    background-color: #ff9800 !important;
    color: white !important;
    border: none !important;
    border-radius: 30px !important;
    padding: 10px 20px !important;
    box-shadow: 0 4px 15px rgba(0,0,0,0.3) !important;
    font-weight: 600 !important;
    font-size: 15px !important;
}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# --- 3. KHỞI TẠO DỮ LIỆU ---
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

def clean_and_process_df(df_raw):
    """Hàm xử lý và nhận diện cột linh hoạt từ file Excel kho thực tế"""
    df = df_raw.copy()
    
    # Làm sạch tên cột (xóa xuống dòng, khoảng trắng thừa)
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    
    col_ma = None
    col_ten = None
    col_ton = None
    col_gia = None

    for c in df.columns:
        c_low = c.lower()
        if any(k in c_low for k in ["mã vt", "ma vt", "mã vật tư", "sku"]):
            col_ma = c
        elif any(k in c_low for k in ["tên vật tư", "ten vat tu", "tên sản phẩm", "ten san pham"]):
            col_ten = c
        elif "tồn cuối" in c_low or "tồn kho" in c_low:
            if "số lượng" in c_low or col_ton is None:
                col_ton = c
        elif "thành tiền" in c_low or "giá" in c_low:
            if col_gia is None:
                col_gia = c

    rename_map = {}
    if col_ma: rename_map[col_ma] = "SKU"
    if col_ten: rename_map[col_ten] = "Ten_San_Pham"
    if col_ton: rename_map[col_ton] = "Ton_Kho"
    if col_gia: rename_map[col_gia] = "Gia_Tri_Ton"

    df = df.rename(columns=rename_map)

    # Đảm bảo có các cột cơ bản
    if "Ten_San_Pham" not in df.columns:
        # Lấy cột chữ đầu tiên làm tên sản phẩm nếu không tìm thấy
        for c in df.columns:
            if df[c].dtype == 'object':
                df = df.rename(columns={c: "Ten_San_Pham"})
                break

    if "SKU" not in df.columns:
        df["SKU"] = df["Ten_San_Pham"] if "Ten_San_Pham" in df.columns else "SKU"

    if "Ton_Kho" not in df.columns:
        df["Ton_Kho"] = 0
    else:
        df["Ton_Kho"] = pd.to_numeric(df["Ton_Kho"], errors="coerce").fillna(0)

    if "Gia_Tri_Ton" not in df.columns:
        df["Gia_Tri_Ton"] = 0
    else:
        df["Gia_Tri_Ton"] = pd.to_numeric(df["Gia_Tri_Ton"], errors="coerce").fillna(0)

    # Lọc bỏ dòng tiêu đề rác / tổng cộng
    df = df.dropna(subset=["Ten_San_Pham"])
    df = df[~df["Ten_San_Pham"].astype(str).str.contains("Tổng cộng|Tên vật tư|STT|Mã VT", case=False, na=False)]
