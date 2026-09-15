import streamlit as st
import pandas as pd
import plotly.express as px
import time

# --- 1. THIẾT LẬP GIAO DIỆN ---
st.set_page_config(page_title="AI Kho Hàng", layout="wide", initial_sidebar_state="collapsed")

# --- 2. CSS CUSTOM CHO NÚT AI NỔI GÓC DƯỚI ---
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

# --- 3. DỮ LIỆU MẶC ĐỊNH & XỬ LÝ FILE SAFE ---
def get_default_df():
    return pd.DataFrame({
        "SKU": [f"SKU{i:03d}" for i in range(1, 21)],
        "Ten_San_Pham": [f"Sản phẩm {i}" for i in range(1, 21)],
        "Nhom_Hang": ["Đồ điện tử", "Thực phẩm", "Gia dụng", "Đồ điện tử", "Thực phẩm"] * 4,
        "Ton_Kho": [450, 400, 350, 320, 300, 280, 250, 210, 180, 150, 90, 80, 60, 40, 20, 8, 5, 4, 2, 0],
        "Nhap_Trong_Thang": [50] * 20,
        "Xuat_Trong_Thang": [20] * 20,
        "Muc_Toi_Thieu": [10] * 20,
        "Gia_Tri_Ton": [1000000] * 20,
        "Khu_Vuc": ["Khu A", "Khu B", "Khu C", "Khu A", "Khu B"] * 4
    })

def process_excel_warehouse(uploaded_file):
    """Xử lý an toàn file Bảng Tổng hợp Nhập Xuất Tồn Excel"""
    try:
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file, header=None)
        else:
            xls = pd.ExcelFile(uploaded_file)
            sheet_name = "Tong hop" if "Tong hop" in xls.sheet_names else xls.sheet_names[0]
            df_raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)

        # Quét tìm dòng chứa từ khóa tiêu đề (Mã VT / Tên vật tư)
        start_row = 6
        for idx in range(min(15, len(df_raw))):
            row_str = " ".join([str(v) for v in df_raw.iloc[idx].values]).lower()
            if "mã vt" in row_str or "tên vật tư" in row_str:
                start_row = idx
                break

        data_rows = df_raw.iloc[start_row:].copy()
        df_clean = pd.DataFrame()

        num_cols = data_rows.shape[1]
        col_ma_idx = 1 if num_cols > 1 else 0
        col_ten_idx = 2 if num_cols > 2 else 0
        col_nhap_idx = 6 if num_cols > 6 else 4
        col_xuat_idx = 8 if num_cols > 8 else 5
        col_ton_idx = 10 if num_cols > 10 else 6
        col_giatri_idx = 11 if num_cols > 11 else 7

        df_clean["SKU"] = data_rows.iloc[:, col_ma_idx].astype(str).str.strip()
        df_clean["Ten_San_Pham"] = data_rows.iloc[:, col_ten_idx].astype(str).str.strip()
        df_clean["Nhap_Trong_Thang"] = pd.to_numeric(data_rows.iloc[:, col_nhap_idx], errors='coerce').fillna(0)
        df_clean["Xuat_Trong_Thang"] = pd.to_numeric(data_rows.iloc[:, col_xuat_idx], errors='coerce').fillna(0)
        df_clean["Ton_Kho"] = pd.to_numeric(data_rows.iloc[:, col_ton_idx], errors='coerce').fillna(0)
        df_clean["Gia_Tri_Ton"] = pd.to_numeric(data_rows.iloc[:, col_giatri_idx], errors='coerce').fillna(0)

        df_clean["Nhom_Hang"] = "Vật tư kho"
        df_clean["Muc_Toi_Thieu"] = 10
        df_clean["Khu_Vuc"] = "Kho Chính"

        # Lọc bỏ dòng tiêu đề và dòng Tổng cộng
        df_clean = df_clean.dropna(subset=["Ten_San_Pham"])
        df_clean = df_clean[~df_clean["Ten_San_Pham"].str.contains("Tổng cộng|Tên vật tư|Mã VT|STT|nan|None", case=False, na=False)]
        df_clean = df_clean[~df_clean["SKU"].str.contains("Mã VT|STT|nan|None", case=False, na=False)]
        df_clean = df_clean[df_clean["Ten_San_Pham"] != ""]

        if df_clean.empty:
            return get_default_df()
        return df_clean.reset_index(drop=True)

    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        return get_default_df()

# Khởi tạo Session State
if "df_data" not in st.session_state:
    st.session_state.df_data = get_default_df()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "username" not in
