import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests
import json

# --- 1. THIẾT LẬP TRANG GIAO DIỆN ---
st.set_page_config(
    page_title="AI Kho Hàng - Nâng Cấp Toàn Diện", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- 2. DỮ LIỆU MẶC ĐỊNH & XỬ LÝ EXCEL / CSV ---
def get_default_df():
    return pd.DataFrame({
        "SKU": [f"SKU{i:03d}" for i in range(1, 16)],
        "Ten_San_Pham": [f"Vật tư / Sản phẩm {i}" for i in range(1, 16)],
        "Nhom_Hang": ["Đồ điện tử", "Gia dụng", "Vật tư cơ khí", "Đồ điện tử", "Gia dụng"] * 3,
        "Ton_Kho": [450, 320, 250, 180, 90, 80, 60, 40, 20, 10, 8, 5, 4, 2, 0],
        "Nhap_Trong_Thang": [100, 50, 40, 30, 20, 10, 10, 5, 5, 0, 0, 0, 0, 0, 0],
        "Xuat_Trong_Thang": [120, 90, 80, 50, 40, 30, 20, 15, 10, 5, 4, 3, 2, 1, 0],
        "Muc_Toi_Thieu": [15] * 15,
        "Gia_Tri_Ton": [1500000, 1200000, 800000, 600000, 400000, 300000, 200000, 150000, 100000, 50000, 40000, 30000, 20000, 10000, 0],
        "Khu_Vuc": ["Kho A", "Kho B", "Kho C", "Kho A", "Kho B"] * 3
    })

def process_excel_warehouse(uploaded_file):
    try:
        uploaded_file.seek(0)
        if uploaded_file.name.lower().endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file, header=None)
        else:
            xls = pd.ExcelFile(uploaded_file)
            sheet_name = "Tong hop" if "Tong hop" in xls.sheet_names else xls.sheet_names[0]
            uploaded_file.seek(0)
            df_raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)

        start_row = 6
        for idx in range(min(25, len(df_raw))):
            row_vals = [str(v).lower() for v in df_raw.iloc[idx].values if pd.notna(v)]
            row_str = " ".join(row_vals)
            if "mã vt" in row_str or "tên vật tư" in row_str or "sku" in row_str:
                start_row = idx
                break

        data_rows = df_raw.iloc[start_row + 1:].copy().dropna(how='all')
        if data_rows.empty:
            return df_raw, get_default_df()

        num_cols = data_rows.shape[1]
        col_ma = 1 if num_cols > 1 else 0
        col_ten = 2 if num_cols > 2 else 0
        col_nhap = 6 if num_cols > 6 else 4
        col_xuat = 8 if num_cols > 8 else 5
        col_ton = 10 if num_cols > 10 else 6
        col_giatri = 11 if num_cols > 11 else 7

        df_clean = pd.DataFrame()
        df_clean["SKU"] = data_rows.iloc[:, col_ma].fillna("N/A").astype(str).str.strip()
        df_clean["Ten_San_Pham"] = data_rows.iloc[:, col_ten].fillna("Vật tư chưa tên").astype(str).str.strip()
        df_clean["Nhap_Trong_Thang"] = pd.to_numeric(data_rows.iloc[:, col_nhap], errors='coerce').fillna(0)
        df_clean["Xuat_Trong_Thang"] = pd.to_numeric(data_rows.iloc[:, col_xuat], errors='coerce').fillna(0)
        df_clean["Ton_Kho"] = pd.to_numeric(data_rows.iloc[:, col_ton], errors='coerce').fillna(0)
        df_clean["Gia_Tri_Ton"] = pd.to_numeric(data_rows.iloc[:, col_giatri], errors='coerce').fillna(0)
        df_clean["Nhom_Hang"] = "Vật tư kho"
        df_clean["Muc_Toi_Thieu"] = 10
        df_clean["Khu_Vuc"] = "Kho Chính"

        df_clean = df_clean[df_clean["Ten_San_Pham"] != ""]
        df_clean = df_clean[~df_clean["Ten_San_Pham"].str.contains("Tổng cộng|Tên vật tư|STT|Mã VT|nan|None", case=False, na=False)]
        df_clean = df_clean[~df_clean["SKU"].str.contains("Mã VT|STT|nan|None", case=False, na=False)]

        return df_raw, df_clean.reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame(), get_default_df()

# Khởi tạo Session State
if "df_data" not in st.session_state:
    st.session_state.df_data = get_default_df()
if "df_raw" not in st.session_state:
    st.session_state.df_raw = pd.DataFrame()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "last_file_id" not in st.session_state:
    st.session_state.last_file_id = ""
if "gemini_api_key" not in st.session_state:
    st.session_state.gemini_api_key = ""

# --- 2.1. HÀM GỌI GEMINI AI DỰ PHÒNG THÔNG MINH (BULLETPROOF) ---
def call_gemini_api_bulletproof(api_key: str, prompt: str, system_instruction: str = "") -> str:
    """Tự động quét danh sách model khả dụng của API Key để tránh lỗi 404/Quota."""
    if not api_key:
        return None

    models_to_try = []
    
    # Bước 1: Hỏi Google API lấy danh sách model mà API Key này được cấp quyền
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        res = requests.get(list_url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for m in data.get("models", []):
                name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods and "computer-use" not in name:
                    models_to_try.append(name)
    except Exception:
        pass

    # Danh sách dự phòng cứng nếu quét danh sách thất bại
    default_candidates = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    for c in default_candidates:
        if c not in models_to_try:
            models_to_try.append(c)

    # Bước 2: Thử gọi từng model theo thứ tự khả dụng
    payload = {
        "contents": [{"role": "user", "parts": [{"text": f"{system_instruction}\n\nCÂU HỎI: {prompt}"}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096}
    }

    last_err = ""
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                r_json = resp.json()
                candidates_res = r_json.get("candidates", [])
                if candidates_res and "content" in candidates_res[0]:
                    parts = candidates_res[0]["content"].get("parts", [])
                    txt = "".join([p.get("text", "") for p in parts]).strip()
                    if txt:
                        return f"🤖 **[Phân tích bởi Gemini ({model_name})]**\n\n{txt}"
            else:
                err_msg = resp.json().get("error", {}).get("message", resp.text)
                last_err = f"[{model_name}]: {err_msg}"
        except Exception as e:
            last_err = str(e)

    raise Exception(f"Không thể kết nối Google AI. Lỗi chi tiết: {last_err}")

# --- 3. ĐỘNG CƠ AI PHÂN TÍCH & DỰ BÁO ---
def analyze_warehouse_data_advanced(query: str, df: pd.DataFrame) -> str:
    q = query.lower().strip()
    if df.empty:
        return "⚠️ Dữ liệu kho đang rỗng. Vui lòng kiểm tra lại file tải lên."

    # Ưu tiên gọi Gemini AI nếu người dùng đã nhập API Key
    api_key = st.session_state.gemini_api_key.strip()
    if api_key:
        try:
            data_summary = df.head(50).to_csv(index=False)
            sys_prompt = f"""Bạn là chuyên gia phân tích kho hàng. Dưới đây là dữ liệu kho hàng hiện tại (tối đa 50 dòng):
```csv
{data_summary}
