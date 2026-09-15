import streamlit as st
import pandas as pd
import plotly.express as px
import time

# --- 1. THIẾT LẬP TRANG GIAO DIỆN ---
st.set_page_config(page_title="AI Kho Hàng", layout="wide", initial_sidebar_state="collapsed")

# --- 2. CSS CUSTOM CHO NÚT AI CỐ ĐỊNH GÓC DƯỚI / TRÊN ---
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

# --- 3. DỮ LIỆU MẶC ĐỊNH THEO CHUẨN MẪU BAN ĐẦU ---
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

def clean_and_process_df(df_raw):
    """Hàm tự động quét tìm tiêu đề cột chính xác từ file kho thực tế"""
    df = df_raw.copy()
    
    # Chuẩn hóa tên cột
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    
    col_ma = next((c for c in df.columns if any(k in c.lower() for k in ["mã vt", "ma vt", "sku"])), None)
    col_ten = next((c for c in df.columns if any(k in c.lower() for k in ["tên vật tư", "ten vat tu", "tên sản phẩm"])), None)
    col_ton = next((c for c in df.columns if "tồn cuối" in c.lower() or "tồn kho" in c.lower()), None)
    col_nhap = next((c for c in df.columns if "nhập trong kỳ" in c.lower() or "nhập" in c.lower()), None)
    col_xuat = next((c for c in df.columns if "xuất trong kỳ" in c.lower() or "xuất" in c.lower()), None)
    col_gia = next((c for c in df.columns if "thành tiền" in c.lower() or "giá trị" in c.lower()), None)
    
    rename_map = {}
    if col_ma: rename_map[col_ma] = "SKU"
    if col_ten: rename_map[col_ten] = "Ten_San_Pham"
    if col_ton: rename_map[col_ton] = "Ton_Kho"
    if col_nhap: rename_map[col_nhap] = "Nhap_Trong_Thang"
    if col_xuat: rename_map[col_xuat] = "Xuat_Trong_Thang"
    if col_gia: rename_map[col_gia] = "Gia_Tri_Ton"
    
    df = df.rename(columns=rename_map)

    # Đảm bảo các cột tối thiểu tồn tại
    if "Ten_San_Pham" not in df.columns:
        for c in df.columns:
            if df[c].dtype == 'object':
                df = df.rename(columns={c: "Ten_San_Pham"})
                break

    if "SKU" not in df.columns:
        df["SKU"] = df.get("Ten_San_Pham", "SKU")
    if "Nhom_Hang" not in df.columns:
        df["Nhom_Hang"] = "Khác"
    if "Muc_Toi_Thieu" not in df.columns:
        df["Muc_Toi_Thieu"] = 10
    if "Khu_Vuc" not in df.columns:
        df["Khu_Vuc"] = "Khu A"

    df["Ton_Kho"] = pd.to_numeric(df.get("Ton_Kho", 0), errors="coerce").fillna(0)
    df["Nhap_Trong_Thang"] = pd.to_numeric(df.get("Nhap_Trong_Thang", 0), errors="coerce").fillna(0)
    df["Xuat_Trong_Thang"] = pd.to_numeric(df.get("Xuat_Trong_Thang", 0), errors="coerce").fillna(0)
    df["Gia_Tri_Ton"] = pd.to_numeric(df.get("Gia_Tri_Ton", 0), errors="coerce").fillna(0)

    # Lọc dòng tiêu đề rác
    df = df.dropna(subset=["Ten_San_Pham"])
    df = df[~df["Ten_San_Pham"].astype(str).str.contains("Tổng cộng|Tên vật tư|STT|Mã VT", case=False, na=False)]
    
    return df

# Khởi tạo session state
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

# --- 4. HÀM AI TRẢ LỜI THÔNG MINH ---
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
            res += f"- **{r['Ten_San_Pham']}** (Mã: `{r['SKU']}`): Tồn **{int(r['Ton_Kho']):,}** (Tối thiểu: {r['Muc_Toi_Thieu']})\n"
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
            res += f"- **{r['Ten_San_Pham']}** (`{r['SKU']}`): Tồn **{int(r['Ton_Kho']):,}**\n"
        return res

    return f"🤖 **Trợ lý AI Kho Hàng:** Đang quản lý **{len(df)}** mặt hàng. Bạn có thể hỏi: *'Sản phẩm tồn cao nhất'*, *'Sản phẩm sắp hết'*, *'Tổng tồn kho'*."

# --- 5. THANH HEADER (TIÊU ĐỀ & ĐĂNG NHẬP / CÀI ĐẶT) ---
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
        file_up = st.file_uploader("Tải file Excel/CSV kho hàng", type=["xlsx", "xls", "csv"])
        if file_up is not None:
            try:
                if file_up.name.endswith('.csv'):
                    df_raw = pd.read_csv(file_up, header=6)
                else:
                    xls = pd.ExcelFile(file_up)
                    sheet_name = "Tong hop" if "Tong hop" in xls.sheet_names else xls.sheet_names[0]
                    df_raw = pd.read_excel(file_up, sheet_name=sheet_name, header=6)
                
                df_processed = clean_and_process_df(df_raw)
                st.session_state.df_data = df_processed
                st.success(f"Tải thành công {len(df_processed)} vật tư!")
            except Exception as e:
                st.error(f"Lỗi đọc file: {e}")

# --- 6. DASHBOARD CHỈ SỐ KPI (6 THÔNG SỐ CHUẨN) ---
df = st.session_state.df_data

st.subheader("📊 Chỉ số KPI chính")
k1, k2, k3, k4, k5, k6 = st.columns(6)

tong_sku = len(df)
tong_ton = df["Ton_Kho"].sum()
nhap_thang = df["Nhap_Trong_Thang"].sum()
xuat_thang = df["Xuat_Trong_Thang"].sum()
duoi_min = len(df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]])
gia_tri = df["Gia_Tri_Ton"].sum()

k1.metric("📦 Tổng SKU", f"{tong_sku:,}")
k2.metric("📊 Tổng tồn kho", f"{int(tong_ton):,}")
k3.metric("📥 Nhập trong tháng", f"{int(nhap_thang):,}")
k4.metric("📤 Xuất trong tháng", f"{int(xuat_thang):,}")
k5.metric("⚠️ SKU dưới tối thiểu", f"{duoi_min:,}")
k6.metric("💰 Giá trị tồn kho", f"{gia_tri:,.0f} VNĐ")

st.markdown("---")

# --- 7. BỐ CỤC BIỂU ĐỒ & BẢNG (CHUẨN VIDEO GỐC) ---
col_left, col_right = st.columns(2)

with col_left:
    # 1. Top 10 sản phẩm tồn nhiều nhất
    if not df.empty:
        top10 = df.nlargest(10, "Ton_Kho")
        fig_top10 = px.bar(top10, x="Ton_Kho", y="Ten_San_Pham", orientation="h",
                           title="Top 10 sản phẩm tồn nhiều nhất", text_auto=True,
                           color="Ton_Kho", color_continuous_scale="Blues")
        fig_top10.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_top10, use_container_width=True)

    # 2. Phân bổ tồn kho theo nhóm hàng
    if "Nhom_Hang" in df.columns and not df.empty:
        df_nhom = df.groupby("Nhom_Hang")["Ton_Kho"].sum().reset_index()
        fig_pie = px.pie(df_nhom, values="Ton_Kho", names="Nhom_Hang", 
                         title="Phân bổ tồn kho theo nhóm hàng", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

with col_right:
    # 1. Top sản phẩm sắp hết (Dưới mức tối thiểu)
    st.write("⚠️ **Top sản phẩm sắp hết (Dưới mức tối thiểu)**")
    df_low = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]][["SKU", "Ten_San_Pham", "Ton_Kho", "Muc_Toi_Thieu"]]
    if df_low.empty:
        df_low = df.nsmallest(5, "Ton_Kho")[["SKU", "Ten_San_Pham", "Ton_Kho", "Muc_Toi_Thieu"]]
    st.dataframe(df_low, use_container_width=True)

    # 2. Tồn kho theo từng khu vực/kho (Biểu đồ cột)
    if "Khu_Vuc" in df.columns and not df.empty:
        df_khu = df.groupby("Khu_Vuc")["Ton_Kho"].sum().reset_index()
        fig_khu = px.bar(df_khu, x="Khu_Vuc", y="Ton_Kho", color="Khu_Vuc",
                         title="Tồn kho theo từng khu vực/kho", text_auto=True)
        st.plotly_chart(fig_khu, use_container_width=True)

# --- 8. NÚT TRỢ LÝ AI NỔI GÓC PHẢI ---
with st.popover("💬 Bạn cần hỗ trợ?"):
    st.markdown("### 🤖 Trợ lý AI Kho Hàng")
    
    chat_box = st.container(height=300)
    with chat_box:
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    if p := st.chat_input("Nhập câu hỏi kho hàng..."):
        st.session_state.messages.append({"role": "user", "content": p})
        with chat_box:
            with st.chat_message("user"):
                st.markdown(p)
            with st.chat_message("assistant"):
                ans = analyze_warehouse_data(p, st.session_state.df_data)
                st.markdown(ans)
                st.session_state.messages.append({"role": "assistant", "content": ans})
