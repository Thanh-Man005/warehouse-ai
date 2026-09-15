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

# --- 2. CSS ÉP NÚT AI CỐ ĐỊNH Ở GÓC DƯỚI BÊN PHẢI ---
st.markdown("""
    <style>
    /* Ghim phần container của nút AI cố định góc phải bên dưới màn hình */
    div[data-testid="stElementContainer"]:has(button[aria-label*="hỗ trợ"]),
    div[data-testid="stElementContainer"]:has(button[aria-label*="Hỗ trợ"]),
    div[data-testid="stElementContainer"]:has(button[aria-label*="Bạn cần hỗ trợ"]) {
        position: fixed !important;
        bottom: 25px !important;
        right: 25px !important;
        z-index: 999999 !important;
        width: auto !important;
    }

    /* Tạo style màu cam nổi bật cho nút AI giống MobileCity */
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
        transition: transform 0.2s ease, background-color
