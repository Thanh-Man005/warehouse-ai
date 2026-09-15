import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="AI Kho Hàng", layout="wide", initial_sidebar_state="collapsed")

# --- 1. KHỞI TẠO SESSION STATE ---
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "df_data" not in st.session_state:
    data = {
        "SKU": [f"SKU{i:03d}" for i in range(1, 21)],
        "Ten_San_Pham": [f"Sản phẩm {i}" for i in range(1, 21)],
        "Nhom_Hang": ["Thực phẩm", "Đồ điện tử", "Gia dụng", "Thực phẩm", "Đồ điện tử"] * 4,
        "Khu_Vuc": ["Kho A", "Kho B", "Kho C", "Kho A"] * 5,
        "Ton_Kho": [120, 5, 450, 8, 300, 15, 600, 0, 90, 210, 150, 4, 80, 500, 320, 2, 110, 240, 180, 95],
        "Muc_Toi_Thieu": [10] * 20,
        "Gia_Nhap": [50, 150, 20, 200, 100, 80, 30, 120, 60, 90, 110, 250, 40, 15, 70, 300, 85, 45, 65, 130],
        "Nhap_Thang": [50, 20, 100, 0, 50, 10, 200, 0, 30, 80, 40, 0, 20, 150, 100, 0, 30, 60, 50, 40],
        "Xuat_Thang": [30, 15, 80, 5, 40, 12, 150, 2, 20, 50, 30, 1, 15, 100, 80, 1, 25, 40, 30, 20]
    }
    df_init = pd.DataFrame(data)
    df_init["Gia_Tri_Ton"] = df_init["Ton_Kho"] * df_init["Gia_Nhap"]
    st.session_state.df_data = df_init

# --- 2. CSS CỐ ĐỊNH NÚT AI Ở GÓC DƯỚI BÊN PHẢI ---
css_code = """
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
    transition: transform 0.2s ease, background-color 0.2s ease !important;
}

div[data-testid="stElementContainer"]:has(button[aria-label*="hỗ trợ"]) button:hover,
div[data-testid="stElementContainer"]:has(button[aria-label*="Hỗ trợ"]) button:hover,
div[data-testid="stElementContainer"]:has(button[aria-label*="Bạn cần hỗ trợ"]) button:hover {
    background-color: #e68a00 !important;
    transform: scale(1.05) !important;
}
</style>
"""
st.markdown(css_code, unsafe_allow_html=True)

# --- 3. THANH TIÊU ĐỀ, ĐĂNG NHẬP VÀ CÀI ĐẶT ---
col_title, col_user, col_settings = st.columns([0.65, 0.2, 0.15])

with col_title:
    st.title("📦 AI Kho Hàng")

with col_user:
    st.write("")
    if not st.session_state.is_logged_in:
        with st.popover("👤 Đăng nhập", use_container_width=True):
            tab_login, tab_register = st.tabs(["Đăng nhập", "Đăng ký"])
            
            with tab_login:
                user_input
