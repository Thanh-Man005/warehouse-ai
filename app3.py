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

# --- 3. KHỞI TẠO DỮ LIỆU MẶC ĐỊNH ---
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

def get_default_data():
    data = {
        "SKU": ["BXS 100", "BXS 120", "QHKR3000", "Satla", "Thephop"],
        "Ten_San_Pham": ["Bánh xe sắt 100", "Bánh xe sắt 120", "Que hàn KR3000 - 3.2x350", "Sắt la các loại", "Thép hộp các loại"],
        "Ton_Kho": [992, 4, 304, 260, 747],
        "Gia_Tri_Ton": [16700800, 300000, 8590908, 3640260, 11826504]
    }
    return pd.DataFrame(data)

def clean_and_process_df(df_raw):
    """Hàm tự động quét tìm tiêu đề cột chính xác"""
    # Nếu file có dòng trống ở đầu, tìm dòng chứa chữ 'Tên vật tư' hoặc 'Mã VT'
    header_idx = 0
    for idx, row in df_raw.head(15).iterrows():
        row_str = " ".join([str(v) for v in row.values]).lower()
        if "tên vật tư" in row_str or "mã vt" in row_str or "tồn cuối" in row_str:
            header_idx = idx + 1
            break
            
    if header_idx > 0:
        df_raw.columns = df_raw.iloc[header_idx - 1]
        df = df_raw.iloc[header_idx:].copy()
    else:
        df = df_raw.copy()

    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]

    col_ma, col_ten, col_ton, col_gia = None, None, None, None

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

    if "Ten_San_Pham" not in df.columns:
        for c in df.columns:
            if df[c].dtype == 'object':
                df = df.rename(columns={c: "Ten_San_Pham"})
                break

    if "SKU" not in df.columns:
        df["SKU"] = df["Ten_San_Pham"] if "Ten_San_Pham" in df.columns else "SKU"

    df["Ton_Kho"] = pd.to_numeric(df.get("Ton_Kho", 0), errors="coerce").fillna(0)
    df["Gia_Tri_Ton"] = pd.to_numeric(df.get("Gia_Tri_Ton", 0), errors="coerce").fillna(0)

    # Loại bỏ hàng trống/tiêu đề thừa
    df = df.dropna(subset=["Ten_San_Pham"])
    df = df[~df["Ten_San_Pham"].astype(str).str.contains("Tổng cộng|Tên vật tư|STT|Mã VT", case=False, na=False)]
    
    return df

if "df_data" not in st.session_state:
    st.session_state.df_data = get_default_data()

# --- 4. HÀM PHÂN TÍCH DỮ LIỆU KHO CHO AI ---
def analyze_warehouse_data(query: str, df: pd.DataFrame) -> str:
    q = query.lower().strip()
    
    if df.empty or "Ten_San_Pham" not in df.columns:
        return "⚠️ Chưa có dữ liệu kho hàng hợp lệ. Vui lòng kiểm tra lại file tải lên."

    if any(k in q for k in ["cao nhất", "nhiều nhất", "lớn nhất", "max", "tồn nhiều"]):
        top_item = df.nlargest(1, "Ton_Kho").iloc[0]
        return (
            f"📦 **Mặt hàng tồn kho cao nhất hiện tại:**\n\n"
            f"- **Tên vật tư:** {top_item.get('Ten_San_Pham', 'N/A')}\n"
            f"- **Mã VT / SKU:** `{top_item.get('SKU', 'N/A')}`\n"
            f"- **Số lượng tồn kho:** **{int(top_item.get('Ton_Kho', 0)):,}** đơn vị\n"
            f"- **Tổng giá trị tồn:** {top_item.get('Gia_Tri_Ton', 0):,.0f} VNĐ"
        )

    if any(k in q for k in ["sắp hết", "thấp nhất", "bổ sung", "cảnh báo", "tối thiểu", "hết hàng", "cần nhập", "ít nhất"]):
        low_stock = df.nsmallest(5, "Ton_Kho")
        res = f"⚠️ **Top 5 vật tư có lượng tồn kho thấp nhất:**\n\n"
        for _, row in low_stock.iterrows():
            res += f"- **{row['Ten_San_Pham']}** (Mã: `{row['SKU']}`): Tồn **{int(row['Ton_Kho']):,}**\n"
        return res

    if any(k in q for k in ["tổng tồn", "tổng số", "tổng giá trị", "bao nhiêu", "tổng quan"]):
        return (
            f"📊 **Báo cáo tổng quan kho hàng:**\n\n"
            f"- **Tổng số mặt hàng (SKU):** {len(df):,} vật tư\n"
            f"- **Tổng số lượng tồn kho:** {int(df['Ton_Kho'].sum()):,} sản phẩm\n"
            f"- **Tổng giá trị vốn tồn kho:** {df['Gia_Tri_Ton'].sum():,.0f} VNĐ"
        )

    matched = df[df["Ten_San_Pham"].astype(str).str.lower().str.contains(q)]
    if not matched.empty:
        res = f"🔍 **Tìm thấy {len(matched)} vật tư phù hợp:**\n\n"
        for _, item in matched.head(3).iterrows():
            res += f"- **{item['Ten_San_Pham']}** (`{item['SKU']}`): Tồn **{int(item['Ton_Kho']):,}** | Giá trị: {item['Gia_Tri_Ton']:,.0f} VNĐ\n"
        return res

    return (
        f"🤖 **Trợ lý AI Kho Hàng:**
