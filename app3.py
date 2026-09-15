import streamlit as st
import pandas as pd
import plotly.express as px

# --- 1. THIẾT LẬP TRANG ---
st.set_page_config(page_title="AI Kho Hàng", layout="wide", initial_sidebar_state="expanded")

# --- 2. DỮ LIỆU MẶC ĐỊNH & XỬ LÝ FILE EXCEL ---
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
    """Hàm đọc file Excel kho chuẩn hóa dữ liệu"""
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
            if "mã vt" in row_str or "tên vật tư" in row_str:
                start_row = idx
                break

        data_rows = df_raw.iloc[start_row + 1:].copy().dropna(how='all')
        if data_rows.empty:
            return get_default_df()

        num_cols = data_rows.shape[1]
        col_ma = 1 if num_cols > 1 else 0
        col_ten = 2 if num_cols > 2 else 0
        col_nhap = 6 if num_cols > 6 else 4
        col_xuat = 8 if num_cols > 8 else 5
        col_ton = 10 if num_cols > 10 else 6
        col_giatri = 11 if num_cols > 11 else 7

        df_clean = pd.DataFrame()
        df_clean["SKU"] = data_rows.iloc[:, col_ma].fillna("N/A").astype(str).str.strip()
        df_clean["Ten_San_Pham"] = data_rows.iloc[:, col_ten].fillna("Vật tư không tên").astype(str).str.strip()
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

        df_clean = df_clean.reset_index(drop=True)
        return df_clean if not df_clean.empty else get_default_df()
    except Exception as e:
        return get_default_df()

# Khởi tạo Session State
if "df_data" not in st.session_state:
    st.session_state.df_data = get_default_df()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "last_file_id" not in st.session_state:
    st.session_state.last_file_id = ""

# --- 3. HÀM PHÂN TÍCH CHO TRỢ LÝ AI ---
def analyze_warehouse_data(query: str, df: pd.DataFrame) -> str:
    q = query.lower().strip()
    if df.empty:
        return "⚠️ Dữ liệu kho đang rỗng. Vui lòng kiểm tra lại file tải lên."

    if any(k in q for k in ["cao nhất", "nhiều nhất", "lớn nhất", "max", "tồn nhiều"]):
        top_item = df.nlargest(1, "Ton_Kho").iloc[0]
        return (
            f"📦 **Mặt hàng tồn kho cao nhất hiện tại:**\n\n"
            f"- **Tên vật tư:** {top_item['Ten_San_Pham']}\n"
            f"- **Mã VT / SKU:** `{top_item['SKU']}`\n"
            f"- **Số lượng tồn kho:** **{int(top_item['Ton_Kho']):,}**\n"
            f"- **Tổng giá trị tồn:** {top_item['Gia_Tri_Ton']:,.0f} VNĐ"
        )

    if any(k in q for k in ["sắp hết", "thấp nhất", "bổ sung", "cảnh báo", "tối thiểu", "hết hàng", "cần nhập"]):
        low_stock = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]].head(5)
        if low_stock.empty:
            low_stock = df.nsmallest(5, "Ton_Kho")
        res = f"⚠️ **Top mặt hàng tồn kho dưới ngưỡng / sắp hết:**\n\n"
        for _, r in low_stock.iterrows():
            res += f"- **{r['Ten_San_Pham']}** (Mã: `{r['SKU']}`): Tồn **{int(r['Ton_Kho']):,}**\n"
