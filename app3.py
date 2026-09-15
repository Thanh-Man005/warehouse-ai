import streamlit as st
import pandas as pd
import plotly.express as px

# --- 1. THIẾT LẬP TRANG GIAO DIỆN ---
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

# --- 3. DỮ LIỆU MẶC ĐỊNH & XỬ LÝ FILE MỘT CÁCH AN TOÀN tuyệt đối ---
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
    """Hàm xử lý file Excel chuẩn hóa không bao giờ sập"""
    try:
        uploaded_file.seek(0)
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file, header=None)
        else:
            xls = pd.ExcelFile(uploaded_file)
            sheet_name = "Tong hop" if "Tong hop" in xls.sheet_names else xls.sheet_names[0]
            uploaded_file.seek(0)
            df_raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)

        # Quét tìm dòng tiêu đề
        start_row = 6
        for idx in range(min(20, len(df_raw))):
            row_vals = [str(v).lower() for v in df_raw.iloc[idx].values if pd.notna(v)]
            row_str = " ".join(row_vals)
            if "mã vt" in row_str or "tên vật tư" in row_str:
                start_row = idx
                break

        data_rows = df_raw.iloc[start_row + 1:].copy().dropna(how='all')
        df_clean = pd.DataFrame()
        num_cols = data_rows.shape[1]

        # Đọc theo vị trí cột chuẩn trong sheet Tong hop
        col_ma = 1 if num_cols > 1 else 0
        col_ten = 2 if num_cols > 2 else 0
        col_nhap = 6 if num_cols > 6 else 4
        col_xuat = 8 if num_cols > 8 else 5
        col_ton = 10 if num_cols > 10 else 6
        col_giatri = 11 if num_cols > 11 else 7

        df_clean["SKU"] = data_rows.iloc[:, col_ma].fillna("").astype(str).str.strip()
        df_clean["Ten_San_Pham"] = data_rows.iloc[:, col_ten].fillna("").astype(str).str.strip()
        df_clean["Nhap_Trong_Thang"] = pd.to_numeric(data_rows.iloc[:, col_nhap], errors='coerce').fillna(0)
        df_clean["Xuat_Trong_Thang"] = pd.to_numeric(data_rows.iloc[:, col_xuat], errors='coerce').fillna(0)
        df_clean["Ton_Kho"] = pd.to_numeric(data_rows.iloc[:, col_ton], errors='coerce').fillna(0)
        df_clean["Gia_Tri_Ton"] = pd.to_numeric(data_rows.iloc[:, col_giatri], errors='coerce').fillna(0)

        df_clean["Nhom_Hang"] = "Vật tư kho"
        df_clean["Muc_Toi_Thieu"] = 10
        df_clean["Khu_Vuc"] = "Kho Chính"

        # Lọc bỏ dòng tiêu đề lặp và dòng Tổng cộng
        df_clean = df_clean[df_clean["Ten_San_Pham"] != ""]
        df_clean = df_clean[~df_clean["Ten_San_Pham"].str.contains("Tổng cộng|Tên vật tư|STT|Mã VT|nan|None", case=False, na=False)]
        df_clean = df_clean[~df_clean["SKU"].str.contains("Mã VT|STT|nan|None", case=False, na=False)]

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
if "username" not in st.session_state:
    st.session_state.username = ""
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "last_file_id" not in st.session_state:
    st.session_state.last_file_id = ""

# --- 4. HÀM PHÂN TÍCH CHO TRỢ LÝ AI ---
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
        return res

    if any(k in q for k in ["tổng tồn", "tổng số", "tổng giá trị", "bao nhiêu", "tổng quan"]):
        return (
            f"📊 **Báo cáo tổng quan kho hàng:**\n\n"
            f"- **Tổng SKU:** {len(df):,}\n"
            f"- **Tổng tồn kho:** {int(df['Ton_Kho'].sum()):,}\n"
            f"- **Nhập trong tháng:** {int(df['Nhap_Trong_Thang'].sum()):,}\n"
            f"- **Xuất trong tháng:** {int(df['Xuat_Trong_Thang'].sum()):,}\n"
            f"- **Tổng giá trị tồn kho:** {df['Gia_Tri_Ton'].sum():,.0f} VNĐ"
        )

    matched = df[df["Ten_San_Pham"].astype(str).str.lower().str.contains(q, na=False)]
    if not matched.empty:
        res = f"🔍 **Tìm thấy {len(matched)} mặt hàng phù hợp:**\n\n"
        for _, r in matched.head(3).iterrows():
            res += f"- **{r['Ten_San_Pham']}** (`{r['SKU']}`): Tồn **{int(r['Ton_Kho']):,}** | Giá trị: {r['Gia_Tri_Ton']:,.0f} VNĐ\n"
        return res

    return f"🤖 **Trợ lý AI Kho Hàng:** Đang quản lý **{len(df)}** mặt hàng. Bạn có thể hỏi: *'Sản phẩm tồn cao nhất'*, *'Sản phẩm sắp hết'*, *'Tổng giá trị kho'*."

# --- 5. THANH TIÊU ĐỀ & POPUP CÀI ĐẶT / ĐĂNG NHẬP ---
col_title, col_user, col_settings = st.columns([0.65, 0.2, 0.15])

with col_title:
    st.title("📦 AI Kho Hàng")

with col_user:
    st.write("")
    if not st.session_state.is_logged_in:
        with st.popover("👤 Đăng nhập", use_container_width=True):
            tab_login, tab_register = st.tabs(["Đăng nhập", "Đăng ký"])
            with tab_login:
                u_in = st.text_input("Tên đăng nhập", key="login_u")
                p_in = st.text_input("Mật khẩu", type="password", key="login_p")
                if st.button("Xác nhận đăng nhập", use_container_width=True):
                    if u_in:
                        st.session_state.is_logged_in = True
                        st.session_state.username = u_in
                        st.rerun()
            with tab_register:
                st.text_input("Tên tài khoản", key="reg_u")
                st.text_input("Mật khẩu", type="password", key="reg_p")
                if st.button("Tạo tài khoản", use_container_width=True):
                    st.success("Tạo tài khoản thành công!")
    else:
        with st.popover(f"👤 {st.session_state.username}", use_container_width=True):
            if st.button("Đăng xuất", use_container_width=True):
                st.session_state.is_logged_in = False
                st.session_state.username = ""
                st.rerun()

with col_settings:
    st.write("")
    with st.popover("⚙️ Cài đặt", use_container_width=True):
        st.subheader("🛠️ Cấu hình hệ thống")
        st.session_state.api_key = st.text_input("🔑 API Key", value=st.session_state.api_key, type="password")
        
        st.markdown("---")
        st.subheader("📁 Tải tài liệu kho")
        file_up = st.file_uploader("Tải file Excel/CSV kho hàng", type=["xlsx", "xls", "csv"], key="file_up_widget")
        if file_up is not None:
            cur_id = f"{file_up.name}_{file_up.size}"
            if st.session_state.last_file_id != cur_id:
                st.session_state.df_data = process_excel_warehouse(file_up)
                st.session_state.last_file_id = cur_id
                st.success("Đã cập nhật dữ liệu kho hàng thành công!")

# --- 6. 6 CHỈ SỐ KPI CHÍNH ---
df = st.session_state.df_data

st.subheader("📊 Chỉ số KPI chính")
k1, k2, k3, k4, k5, k6 = st.columns(6)

k1.metric("📦 Tổng SKU", f"{len(df):,}")
k2.metric("📊 Tổng tồn kho", f"{int(df['Ton_Kho'].sum()):,}")
k3.metric("📥 Nhập trong tháng", f"{int(df['Nhap_Trong_Thang'].sum()):,}")
k4.metric("📤 Xuất trong tháng", f"{int(df['Xuat_Trong_Thang'].sum()):,}")
k5.metric("⚠️ SKU dưới tối thiểu", f"{len(df[df['Ton_Kho'] <= df['Muc_Toi_Thieu']]):,}")
k6.metric("💰 Giá trị tồn kho", f"{df['Gia_Tri_Ton'].sum():,.0f} VNĐ")

st.markdown("---")

# --- 7. BỐ CỤC BIỂU ĐỒ & BẢNG (2 CỘT CHUẨN GÓC) ---
col_left, col_right = st.columns(2)

with col_left:
    # 1. Biểu đồ Top 10 sản phẩm tồn nhiều nhất
    if not df.empty:
        top10 = df.nlargest(10, "Ton_Kho")
        fig_top10 = px.bar(top10, x="Ton_Kho", y="Ten_San_Pham", orientation="h",
                           title="Top 10 sản phẩm tồn nhiều nhất", text_auto=True,
                           color="Ton_Kho", color_continuous_scale="Blues")
        fig_top10.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_top10, use_container_width=True)

    # 2. Biểu đồ Phân bổ tồn kho theo nhóm hàng
    if "Nhom_Hang" in df.columns and not df.empty:
        df_nhom = df.groupby("Nhom_Hang")["Ton_Kho"].sum().reset_index()
        fig_pie = px.pie(df_nhom, values="Ton_Kho", names="Nhom_Hang", 
                         title="Phân bổ tồn kho theo nhóm hàng", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

with col_right:
    # 1. Bảng Top sản phẩm sắp hết (Dưới mức tối thiểu)
    st.write("⚠️ **Top sản phẩm sắp hết (Dưới mức tối thiểu)**")
    df_low = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]][["SKU", "Ten_San_Pham", "Ton_Kho", "Muc_Toi_Thieu"]]
    if df_low.empty:
        df_low = df.nsmallest(5, "Ton_Kho")
