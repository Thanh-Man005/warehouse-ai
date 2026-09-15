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

# --- 4. HÀM PHÂN TÍCH DỮ LIỆU KHO CHO AI ---
def analyze_warehouse_data(query: str, df: pd.DataFrame) -> str:
    q = query.lower()
    
    # Hỏi về mặt hàng tồn kho cao nhất
    if any(k in q for k in ["cao nhất", "nhiều nhất", "lớn nhất", "max"]):
        if "Ton_Kho" in df.columns and "Ten_San_Pham" in df.columns:
            top_item = df.nlargest(1, "Ton_Kho").iloc[0]
            sku = top_item.get("SKU", "N/A")
            name = top_item["Ten_San_Pham"]
            qty = top_item["Ton_Kho"]
            cat = top_item.get("Nhom_Hang", "N/A")
            loc = top_item.get("Khu_Vuc", "N/A")
            return (
                f"📦 **Mặt hàng tồn kho cao nhất hiện tại:**\n\n"
                f"- **Tên sản phẩm:** {name} (Mã SKU: `{sku}`)\n"
                f"- **Nhóm hàng:** {cat} | **Vị trí:** {loc}\n"
                f"- **Số lượng tồn kho:** **{qty:,}** đơn vị.\n\n"
                f"💡 **Đề xuất:** Mặt hàng này có lượng tồn dư dả, **hiện chưa cần nhập thêm**. "
                f"Nên đẩy mạnh bán hàng/khuyến mãi để giải phóng bớt mặt bằng kho."
            )

    # Hỏi về sản phẩm sắp hết / cần nhập thêm
    if any(k in q for k in ["sắp hết", "thấp nhất", "bổ sung", "cảnh báo", "tối thiểu", "hết hàng", "cần nhập"]):
        if "Ton_Kho" in df.columns and "Muc_Toi_Thieu" in df.columns:
            low_stock = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]].sort_values("Ton_Kho")
            if len(low_stock) > 0:
                res = f"⚠️ **Có {len(low_stock)} sản phẩm đang ở dưới mức tối thiểu cần bổ sung ngay:**\n\n"
                for _, row in low_stock.head(5).iterrows():
                    res += f"- **{row['Ten_San_Pham']}** (`{row['SKU']}`): Tồn **{row['Ton_Kho']}** (Tối thiểu: {row['Muc_Toi_Thieu']})\n"
                res += "\n📌 **Khuyến nghị:** Cần lập đơn nhập hàng bổ sung ngay."
                return res
            else:
                return "✅ Tất cả các mặt hàng hiện tại đều ở mức tồn kho an toàn."

    # Hỏi về tổng quan kho
    if any(k in q for k in ["tổng tồn", "tổng số", "tổng giá trị", "bao nhiêu sku"]):
        tong_sku = len(df)
        tong_ton = df["Ton_Kho"].sum() if "Ton_Kho" in df.columns else 0
        gia_tri = df["Gia_Tri_Ton"].sum() if "Gia_Tri_Ton" in df.columns else 0
        return (
            f"📊 **Báo cáo tổng quan kho hàng:**\n\n"
            f"- **Tổng số SKU:** {tong_sku:,} mặt hàng\n"
            f"- **Tổng số lượng tồn kho:** {tong_ton:,} sản phẩm\n"
            f"- **Tổng giá trị vốn tồn kho:** {gia_tri:,.0f} VNĐ"
        )

    # Phản hồi mặc định
    top_3 = df.nlargest(3, "Ton_Kho")[["Ten_San_Pham", "Ton_Kho"]].to_dict('records')
    top_str = ", ".join([f"{item['Ten_San_Pham']} ({item['Ton_Kho']} sp)" for item in top_3])
    return (
        f"🤖 **Thông tin kho hàng hiện tại:**\n\n"
        f"- Top 3 sản phẩm tồn nhiều nhất: **{top_str}**.\n"
        f"- Số mặt hàng cần nhập thêm: **{len(df[df['Ton_Kho'] <= df['Muc_Toi_Thieu']])}** sản phẩm.\n"
        f"Bạn có thể đặt câu hỏi như: *'tồn kho cao nhất'*, *'sản phẩm sắp hết'*, hoặc *'tổng giá trị kho'*."
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
        uploaded_file = st.file_uploader("Tải file Excel/CSV", type=["xlsx", "xls", "csv"])
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_new = pd.read_csv(uploaded_file)
                else:
                    df_new = pd.read_excel(uploaded_file)
                if "Gia_Tri_Ton" not in df_new.columns and "Ton_Kho" in df_new.columns and "Gia_Nhap" in df_new.columns:
                    df_new["Gia_Tri_Ton"] = df_new["Ton_Kho"] * df_new["Gia_Nhap"]
                st.session_state.df_data = df_new
                st.success("Tải dữ liệu thành công!")
            except Exception:
                st.error("Không thể đọc file.")

# --- 6. KHU VỰC DASHBOARD METRICS & CHARTS ---
df = st.session_state.df_data

st.subheader("📊 Chỉ số KPI chính")
k1, k2, k3, k4, k5, k6 = st.columns(6)

tong_sku = df["SKU"].nunique() if "SKU" in df.columns else len(df)
tong_ton = df["Ton_Kho"].sum() if "Ton_Kho" in df.columns else 0
nhap_thang = df["Nhap_Thang"].sum() if "Nhap_Thang" in df.columns else 0
xuat_thang = df["Xuat_Thang"].sum() if "Xuat_Thang" in df.columns else 0
sku_canh_bao = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]]["SKU"].count() if ("Muc_Toi_Thieu" in df.columns and "Ton_Kho" in df.columns) else 0
gia_tri_ton = df["Gia_Tri_Ton"].sum() if "Gia_Tri_Ton" in df.columns else 0

k1.metric("📦 Tổng SKU", f"{tong_sku:,}")
k2.metric("📊 Tổng tồn kho", f"{tong_ton:,}")
k3.metric("⬆️ Nhập trong tháng", f"{nhap_thang:,}")
k4.metric("⬇️ Xuất trong tháng", f"{xuat_thang:,}")
k5.metric("🔴 SKU dưới tối thiểu", f"{sku_canh_bao:,}")
k6.metric("💰 Giá trị tồn kho", f"{gia_tri_ton:,.0f} VNĐ")

st.markdown("---")

col_left, col_right = st.columns(2)
with col_left:
    if "Ton_Kho" in df.columns and "Ten_San_Pham" in df.columns:
        top_10 = df.nlargest(10, "Ton_Kho")
        fig_top10 = px.bar(top_10, x="Ton_Kho", y="Ten_San_Pham", orientation="h",
                           title="Top 10 sản phẩm tồn nhiều nhất", text_auto=True,
                           color="Ton_Kho", color_continuous_scale="Blues")
        fig_top10.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_top10, use_container_width=True)

    if "Nhom_Hang" in df.columns and "Ton_Kho" in df.columns:
        by_cat = df.groupby("Nhom_Hang")["Ton_Kho"].sum().reset_index()
        fig_cat = px.pie(by_cat, values="Ton_Kho", names="Nhom_Hang", title="Phân bố tồn kho theo nhóm hàng", hole=0.4)
        st.plotly_chart(fig_cat, use_container_width=True)

with col_right:
    if "Muc_Toi_Thieu" in df.columns and "Ton_Kho" in df.columns:
        sap_het = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]].sort_values("Ton_Kho")
        st.write("⚠️ **Top sản phẩm sắp hết (Dưới mức tối thiểu)**")
        st.dataframe(sap_het[["SKU", "Ten_San_Pham", "Ton_Kho", "Muc_Toi_Thieu"]], use_container_width=True)

    if "Khu_Vuc" in df.columns and "Ton_Kho" in df.columns:
        by_warehouse = df.groupby("Khu_Vuc")["Ton_Kho"].sum().reset_index()
        fig_wh = px.bar(by_warehouse, x="Khu_Vuc", y="Ton_Kho", title="Tồn kho theo từng khu vực/kho",
                        color="Khu_Vuc", text_auto=True)
        st.plotly_chart(fig_wh, use_container_width=True)

# ---
