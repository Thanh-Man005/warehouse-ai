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

# --- 3. DỮ LIỆU MẶC ĐỊNH & HÀM XỬ LÝ SAFE ---
def get_default_df():
    return pd.DataFrame({
        "SKU": ["BXS 100", "BXS 120", "QHKR3000", "Satla", "Thephop"],
        "Ten_San_Pham": ["Bánh xe sắt 100", "Bánh xe sắt 120", "Que hàn KR3000 - 3.2x350", "Sắt la các loại", "Thép hộp các loại"],
        "Ton_Kho": [992, 4, 304, 260, 747],
        "Gia_Tri_Ton": [16700800, 300000, 8590908, 3640260, 11826504]
    })

def process_uploaded_file(uploaded_file):
    try:
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file, header=6)
        else:
            xls = pd.ExcelFile(uploaded_file)
            sheet_name = "Tong hop" if "Tong hop" in xls.sheet_names else xls.sheet_names[0]
            df_raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=6)
        
        # Đặt tên cột thủ công dựa trên vị trí chuẩn của sheet Tong hop
        cols = list(df_raw.columns)
        
        # Tìm các cột chính dựa trên chỉ số hoặc từ khóa
        df = pd.DataFrame()
        df["SKU"] = df_raw.iloc[:, 1].astype(str).str.strip()  # Cột Mã VT
        df["Ten_San_Pham"] = df_raw.iloc[:, 2].astype(str).str.strip() # Cột Tên vật tư
        
        # Tìm cột tồn kho và giá trị (thường ở cột 10 và 11)
        df["Ton_Kho"] = pd.to_numeric(df_raw.iloc[:, 10], errors='coerce').fillna(0)
        df["Gia_Tri_Ton"] = pd.to_numeric(df_raw.iloc[:, 11], errors='coerce').fillna(0)
        
        # Lọc rác
        df = df.dropna(subset=["Ten_San_Pham"])
        df = df[~df["Ten_San_Pham"].str.contains("Tổng cộng|Tên vật tư|nan|STT", case=False, na=False)]
        df = df[df["Ten_San_Pham"] != ""]
        
        if df.empty:
            return get_default_df()
        return df
    except Exception as e:
        st.error(f"Lỗi đọc file: {e}")
        return get_default_df()

# Khởi tạo session state
if "df_data" not in st.session_state:
    st.session_state.df_data = get_default_df()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

# --- 4. HÀM PHÂN TÍCH CHO AI KHO HÀNG ---
def analyze_warehouse_data(query: str, df: pd.DataFrame) -> str:
    q = query.lower().strip()
    
    if df.empty:
        return "⚠️ Dữ liệu kho đang rỗng. Vui lòng tải file Excel trong mục Cài đặt."

    # Hỏi mặt hàng tồn kho cao nhất
    if any(k in q for k in ["cao nhất", "nhiều nhất", "lớn nhất", "max", "tồn nhiều"]):
        top_item = df.nlargest(1, "Ton_Kho").iloc[0]
        return (
            f"📦 **Mặt hàng tồn kho cao nhất:**\n\n"
            f"- **Tên vật tư:** {top_item['Ten_San_Pham']}\n"
            f"- **Mã VT:** `{top_item['SKU']}`\n"
            f"- **Số lượng tồn kho:** **{int(top_item['Ton_Kho']):,}** đơn vị\n"
            f"- **Tổng giá trị vốn:** {top_item['Gia_Tri_Ton']:,.0f} VNĐ"
        )

    # Hỏi mặt hàng tồn kho thấp / sắp hết
    if any(k in q for k in ["sắp hết", "thấp nhất", "bổ sung", "cảnh báo", "tối thiểu", "hết hàng", "cần nhập"]):
        low_stock = df.nsmallest(5, "Ton_Kho")
        res = f"⚠️ **Top 5 mặt hàng có lượng tồn thấp nhất:**\n\n"
        for _, r in low_stock.iterrows():
            res += f"- **{r['Ten_San_Pham']}** (Mã: `{r['SKU']}`): Tồn **{int(r['Ton_Kho']):,}**\n"
        return res

    # Hỏi tổng quan kho
    if any(k in q for k in ["tổng", "báo cáo", "bao nhiêu", "tổng quan"]):
        return (
            f"📊 **Báo cáo tổng quan kho hàng:**\n\n"
            f"- **Tổng số SKU vật tư:** {len(df):,} danh mục\n"
            f"- **Tổng số lượng tồn kho:** {int(df['Ton_Kho'].sum()):,} sản phẩm\n"
            f"- **Tổng giá trị vốn tồn kho:** {df['Gia_Tri_Ton'].sum():,.0f} VNĐ"
        )

    # Tra cứu mặt hàng cụ thể
    matched = df[df["Ten_San_Pham"].str.lower().str.contains(q, na=False)]
    if not matched.empty:
        res = f"🔍 **Tìm thấy {len(matched)} vật tư:**\n\n"
        for _, r in matched.head(3).iterrows():
            res += f"- **{r['Ten_San_Pham']}** (`{r['SKU']}`): Tồn **{int(r['Ton_Kho']):,}** | Giá trị: {r['Gia_Tri_Ton']:,.0f} VNĐ\n"
        return res

    top_3 = df.nlargest(3, "Ton_Kho")[["Ten_San_Pham", "Ton_Kho"]].to_dict('records')
    top_str = ", ".join([f"{i['Ten_San_Pham']} ({int(i['Ton_Kho'])} sp)" for i in top_3])
    return (
        f"🤖 **Hệ thống AI Kho Hàng:**\n\n"
        f"- Đang quản lý **{len(df)}** mặt hàng.\n"
        f"- Top tồn kho cao nhất: **{top_str}**.\n\n"
        f"Bạn có thể hỏi: *'sản phẩm nào tồn cao nhất'*, *'sản phẩm sắp hết'*, hoặc *'bánh xe'*."
    )

# --- 5. GIAO DIỆN CHÍNH ---
col_title, col_settings = st.columns([0.8, 0.2])

with col_title:
    st.title("📦 AI Quản Lý Kho Hàng")

with col_settings:
    st.write("")
    with st.popover("⚙️ Cài đặt & Upload"):
        st.subheader("📁 Tải file kho")
        file_up = st.file_uploader("Upload file Excel/CSV kho", type=["xlsx", "xls", "csv"])
        if file_up is not None:
            st.session_state.df_data = process_uploaded_file(file_up)
            st.success("Đã cập nhật dữ liệu kho!")

# --- 6. DASHBOARD CHỈ SỐ ---
df = st.session_state.df_data

st.subheader("📊 Chỉ số KPI kho hàng")
k1, k2, k3, k4 = st.columns(4)
k1.metric("📦 Tổng số SKU", f"{len(df):,}")
k2.metric("📊 Tổng tồn kho (SL)", f"{int(df['Ton_Kho'].sum()):,}")
k3.metric("💰 Giá trị vốn tồn kho", f"{df['Gia_Tri_Ton'].sum():,.0f} VNĐ")
k4.metric("🔴 Vật tư tồn thấp (<=10)", f"{len(df[df['Ton_Kho'] <= 10]):,}")

st.markdown("---")

c_chart, c_table = st.columns([0.55, 0.45])
with c_chart:
    if not df.empty:
        top10 = df.nlargest(10, "Ton_Kho")
        fig = px.bar(top10, x="Ton_Kho", y="Ten_San_Pham", orientation="h",
                     title="Top 10 vật tư tồn kho cao nhất", text_auto=True,
                     color="Ton_Kho", color_continuous_scale="Blues")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)

with c_table:
    st.write("📋 **Danh sách tồn kho chi tiết**")
    st.dataframe(df[["SKU", "Ten_San_Pham", "Ton_Kho", "Gia_Tri_Ton"]].head(10), use_container_width=True)

# --- 7. CHATBOT AI NỔI GÓC DƯỚI ---
with st.popover("💬 Bạn cần hỗ trợ?"):
    st.markdown("### 🤖 Trợ lý AI Kho Hàng")
    
    chat_box = st.container(height=320)
    with chat_box:
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    if p := st.chat_input("Nhập câu hỏi (vd: sản phẩm tồn cao nhất)..."):
        st.session_state.messages.append({"role": "user", "content": p})
        with chat_box:
            with st.chat_message("user"):
                st.markdown(p)
            with st.chat_message("assistant"):
                ans = analyze_warehouse_data(p, st.session_state.df_data)
                st.markdown(ans)
                st.session_state.messages.append({"role": "assistant", "content": ans})
