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
    """Hàm chuẩn hóa dữ liệu kho từ file Excel thực tế"""
    df = df_raw.copy()
    
    # Chuẩn hóa tên cột
    cols = [str(c).strip() for c in df.columns]
    df.columns = cols
    
    # Tìm cột Mã VT, Tên vật tư, Tồn cuối kỳ
    col_ma = next((c for c in df.columns if "mã vt" in c.lower() or "sku" in c.lower()), "Mã VT")
    col_ten = next((c for c in df.columns if "tên vật tư" in c.lower() or "tên sản phẩm" in c.lower()), "Tên vật tư")
    
    # Lấy cột số lượng tồn cuối
    col_ton = None
    for c in df.columns:
        if "tồn cuối" in c.lower() or "tồn kho" in c.lower():
            if "số lượng" in str(df[c].iloc[0]).lower() or "số lượng" in c.lower() or col_ton is None:
                col_ton = c
    if not col_ton:
        col_ton = "Tồn kho"

    # Lọc bỏ dòng tiêu đề phụ/tổng cộng
    df = df.dropna(subset=[col_ten])
    df = df[~df[col_ten].astype(str).str.contains("Tổng cộng|Tên vật tư|STT", case=False, na=False)]
    
    # Đổi tên cột chuẩn
    rename_dict = {}
    if col_ma in df.columns: rename_dict[col_ma] = "SKU"
    if col_ten in df.columns: rename_dict[col_ten] = "Ten_San_Pham"
    if col_ton in df.columns: rename_dict[col_ton] = "Ton_Kho"
    
    df = df.rename(columns=rename_dict)
    
    # Chuyển Tồn kho sang dạng số
    if "Ton_Kho" in df.columns:
        df["Ton_Kho"] = pd.to_numeric(df["Ton_Kho"], errors="coerce").fillna(0)
    else:
        df["Ton_Kho"] = 0
        
    if "SKU" not in df.columns:
        df["SKU"] = df["Ten_San_Pham"]
        
    return df

if "df_data" not in st.session_state:
    # Mẫu mặc định
    data = {
        "SKU": ["BXS 100", "BXS 120", "QHKR3000", "Satla", "Thephop"],
        "Ten_San_Pham": ["Bánh xe sắt 100", "Bánh xe sắt 120", "Que hàn KR3000 - 3.2x350", "Sắt la các loại", "Thép hộp các loại"],
        "Nhom_Hang": ["Vật tư", "Vật tư", "Que hàn", "Sắt thép", "Sắt thép"],
        "Khu_Vuc": ["Kho A", "Kho A", "Kho B", "Kho C", "Kho C"],
        "Ton_Kho": [992, 4, 304, 260, 747],
        "Muc_Toi_Thieu": [10, 5, 50, 50, 100],
        "Gia_Nhap": [16835, 75000, 28259, 14001, 15832]
    }
    df_init = pd.DataFrame(data)
    df_init["Gia_Tri_Ton"] = df_init["Ton_Kho"] * df_init["Gia_Nhap"]
    st.session_state.df_data = df_init

# --- 4. HÀM PHÂN TÍCH DỮ LIỆU KHO CHO AI ---
def analyze_warehouse_data(query: str, df: pd.DataFrame) -> str:
    q = query.lower()
    
    if df.empty:
        return "⚠️ Chưa có dữ liệu kho hàng. Vui lòng tải file dữ liệu lên trong mục Cài đặt."
    
    # Hỏi về mặt hàng tồn kho cao nhất
    if any(k in q for k in ["cao nhất", "nhiều nhất", "lớn nhất", "max"]):
        top_item = df.nlargest(1, "Ton_Kho").iloc[0]
        sku = top_item.get("SKU", "N/A")
        name = top_item.get("Ten_San_Pham", "N/A")
        qty = top_item.get("Ton_Kho", 0)
        return (
            f"📦 **Mặt hàng tồn kho cao nhất hiện tại:**\n\n"
            f"- **Tên vật tư:** {name}\n"
            f"- **Mã VT:** `{sku}`\n"
            f"- **Số lượng tồn kho:** **{int(qty):,}** đơn vị.\n\n"
            f"💡 **Đề xuất:** Lượng tồn dồi dào, hiện chưa cần ưu tiên nhập thêm mặt hàng này."
        )

    # Hỏi về sản phẩm sắp hết / cần nhập thêm
    if any(k in q for k in ["sắp hết", "thấp nhất", "bổ sung", "cảnh báo", "tối thiểu", "hết hàng", "cần nhập"]):
        if "Muc_Toi_Thieu" in df.columns:
            low_stock = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]].sort_values("Ton_Kho")
        else:
            low_stock = df.nsmallest(5, "Ton_Kho")
            
        if len(low_stock) > 0:
            res = f"⚠️ **Các sản phẩm có lượng tồn kho thấp nhất cần lưu ý:**\n\n"
            for _, row in low_stock.head(5).iterrows():
                res += f"- **{row['Ten_San_Pham']}** (Mã: `{row['SKU']}`): Tồn **{int(row['Ton_Kho']):,}**\n"
            res += "\n📌 **Khuyến nghị:** Lập kế hoạch kiểm tra kho và nhập bổ sung."
            return res

    # Hỏi về tổng quan kho
    if any(k in q for k in ["tổng tồn", "tổng số", "tổng giá trị", "bao nhiêu", "tổng quan"]):
        tong_sku = len(df)
        tong_ton = df["Ton_Kho"].sum()
        gia_tri = df["Gia_Tri_Ton"].sum() if "Gia_Tri_Ton" in df.columns else 0
        return (
            f"📊 **Báo cáo tổng quan kho hàng:**\n\n"
            f"- **Tổng số mặt hàng (SKU):** {tong_sku:,} vật tư\n"
            f"- **Tổng số lượng tồn kho:** {int(tong_ton):,} sản phẩm\n"
            f"- **Tổng giá trị vốn tồn kho:** {gia_tri:,.0f} VNĐ"
        )

    # Tìm kiếm tên vật tư cụ thể
    matched = df[df["Ten_San_Pham"].astype(str).str.lower().str.contains(q)]
    if not matched.empty:
        item = matched.iloc[0]
        return (
            f"🔍 **Thông tin vật tư tìm thấy:**\n\n"
            f"- **Tên vật tư:** {item['Ten_San_Pham']}\n"
            f"- **Mã VT:** `{item['SKU']}`\n"
            f"- **Tồn kho hiện tại:** **{int(item['Ton_Kho']):,}** đơn vị"
        )

    # Phản hồi mặc định
    top_3 = df.nlargest(3, "Ton_Kho")[["Ten_San_Pham", "Ton_Kho"]].to_dict('records')
    top_str = ", ".join([f"{item['Ten_San_Pham']} ({int(item['Ton_Kho'])} sp)" for item in top_3])
    return (
        f"🤖 **Thông tin kho hàng hiện tại:**\n\n"
        f"- Top 3 vật tư tồn nhiều nhất: **{top_str}**.\n"
        f"Bạn có thể hỏi: *'tồn kho cao nhất'*, *'sản phẩm sắp hết'*, hoặc tên vật tư cụ thể (vd: *'bánh xe'*, *'que hàn'*)."
    )

# --- 5. THANH TIÊU ĐỀ & MENU BÊN TRÊN ---
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
                    else:
                        st.error("Vui lòng nhập tên đăng nhập!")
            with tab_register:
                st.text_input("Họ và tên", key="reg_fn")
                st.text_input("Tên tài khoản", key="reg_u")
                st.text_input("Mật khẩu", type="password", key="reg_p")
                if st.button("Tạo tài khoản", use_container_width=True):
                    st.success("Tạo tài khoản thành công!")
    else:
        with st.popover(f"👤 {st.session_state.username}", use_container_width=True):
            st.write(f"Xin chào, **{st.session_state.username}**!")
            if st.button("Đăng xuất", use_container_width=True):
                st.session_state.is_logged_in = False
                st.session_state.username = ""
                st.rerun()

with col_settings:
    st.write("")
    with st.popover("⚙️ Cài đặt", use_container_width=True):
        st.subheader("🛠️ Cấu hình hệ thống")
        input_key = st.text_input("🔑 API Key", value=st.session_state.api_key, type="password")
        if input_key != st.session_state.api_key:
            st.session_state.api_key = input_key
            st.success("Đã cập nhật API Key!")

        st.markdown("---")
        st.subheader("📁 Tải tài liệu kho")
        uploaded_file = st.file_uploader("Tải file Excel/CSV kho hàng", type=["xlsx", "xls", "csv"])
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_raw = pd.read_csv(uploaded_file, header=6)
                else:
                    # Tự động đọc đúng sheet 'Tong hop' nếu có
                    xls = pd.ExcelFile(uploaded_file)
                    sheet_name = "Tong hop" if "Tong hop" in xls.sheet_names else xls.sheet_names[0]
                    df_raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=6)
                
                df_processed = clean_and_process_df(df_raw)
                st.session_state.df_data = df_processed
                st.success(f"Tải thành công! Đã xử lý {len(df_processed)} vật tư.")
            except Exception as e:
                st.error(f"Không thể đọc file: {e}")

# --- 6. KHU VỰC DASHBOARD METRICS & CHARTS ---
df = st.session_state.df_data

st.subheader("📊 Chỉ số KPI chính")
k1, k2, k3, k4 = st.columns(4)

tong_sku = len(df)
tong_ton = df["Ton_Kho"].sum() if "Ton_Kho" in df.columns else 0
gia_tri_ton = df["Gia_Tri_Ton"].sum() if "Gia_Tri_Ton" in df.columns else 0

k1.metric("📦 Tổng số SKU", f"{tong_sku:,}")
k2.metric("📊 Tổng tồn kho (Số lượng)", f"{int(tong_ton):,}")
k3.metric("💰 Giá trị tồn kho", f"{gia_tri_ton:,.0f} VNĐ")
k4.metric("🔴 Vật tư cần chú ý", f"{len(df[df['Ton_Kho'] <= 10]):,}")

st.markdown("---")

col_left, col_right = st.columns(2)
with col_left:
    if "Ton_Kho" in df.columns and "Ten_San_Pham" in df.columns:
        top_10 = df.nlargest(10, "Ton_Kho")
        fig_top10 = px.bar(top_10, x="Ton_Kho", y="Ten_San_Pham", orientation="h",
                           title="Top 10 vật tư tồn kho nhiều nhất", text_auto=True,
                           color="Ton_Kho", color_continuous_scale="Blues")
        fig_top10.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_top10, use_container_width=True)

with col_right:
    st.write("📋 **Danh sách vật tư kho**")
    cols_to_show = [c for c in ["SKU", "Ten_San_Pham", "Ton_Kho", "Gia_Tri_Ton"] if c in df.columns]
    st.dataframe(df[cols_to_show].head(10), use_container_width=True)

# --- 7. TRỢ LÝ AI HỎI ĐÁP NỔI ---
with st.popover("💬 Bạn cần hỗ trợ?"):
    st.markdown("### 🤖 Trợ lý AI Kho Hàng")
    st.caption("Giải đáp thông tin dữ liệu kho 24/7")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    chat_box = st.container(height=300)
    with chat_box:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if prompt := st.chat_input("Nhập câu hỏi kho hàng..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with chat_box:
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("AI đang tra cứu dữ liệu..."):
                    time.sleep(0.3)
                    reply_msg = analyze_warehouse_data(prompt, st.session_state.df_data)

                def stream_response():
                    for word in reply_msg.split(" "):
                        yield word + " "
                        time.sleep(0.02)

                full_resp = st.write_stream(stream_response)
                st.session_state.messages.append({"role": "assistant", "content": full_resp})
