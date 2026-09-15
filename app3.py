import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="AI Kho Hàng", layout="wide")

# --- 1. KHỞI TẠO BỘ NHỚ LƯU TRỮ (SESSION STATE) ---
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "df_data" not in st.session_state:
    st.session_state.df_data = None

# --- 2. NÚT BÁNH RĂNG CÀI ĐẶT (POPOVER) ---
# Nút bánh răng nằm gọn ở góc trên bên phải thanh bên
with st.sidebar:
    with st.popover("⚙️ Cài đặt & Dữ liệu", use_container_width=True):
        st.subheader("🛠️ Cấu hình hệ thống")
        
        # Nhập API Key (Chỉ lưu khi người dùng nhập/sửa)
        input_key = st.text_input(
            "🔑 Nhập API Key", 
            value=st.session_state.api_key, 
            type="password",
            help="API Key sẽ được giữ nguyên cho đến khi bạn thay đổi."
        )
        if input_key != st.session_state.api_key:
            st.session_state.api_key = input_key
            st.success("Đã cập nhật API Key!")

        st.markdown("---")
        st.subheader("📁 Tải tài liệu kho")
        
        # Upload file (Chỉ ghi đè dữ liệu khi có file mới)
        uploaded_file = st.file_uploader("Tải file Excel/CSV mới", type=["xlsx", "xls", "csv"])
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    st.session_state.df_data = pd.read_csv(uploaded_file)
                else:
                    st.session_state.df_data = pd.read_excel(uploaded_file)
                st.success("Đã tải và lưu dữ liệu mới!")
            except Exception as e:
                st.error("Lỗi đọc file Excel/CSV.")

    # Hiển thị trạng thái nhỏ bên ngoài để người dùng biết
    if st.session_state.api_key:
        st.caption("✅ Đã kết nối API")
    if st.session_state.df_data is not None:
        st.caption("✅ Đã có dữ liệu từ file upload")

# --- 3. GIAO DIỆN CHÍNH (TABS) ---
tab_dashboard, tab_chat = st.tabs(["📊 Dashboard Tổng Quan", "🤖 Hỏi đáp với AI"])

# Lấy dữ liệu hiện tại từ Session State, nếu chưa có thì dùng dữ liệu mẫu
if st.session_state.df_data is not None:
    df = st.session_state.df_data
else:
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
    df = pd.DataFrame(data)

if "Gia_Tri_Ton" not in df.columns and "Ton_Kho" in df and "Gia_Nhap" in df:
    df["Gia_Tri_Ton"] = df["Ton_Kho"] * df["Gia_Nhap"]

# --- TAB 1: DASHBOARD ---
with tab_dashboard:
    st.title("📦 Dashboard Tổng Quan Kho")
    
    st.subheader("📊 Chỉ số KPI chính")
    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

    tong_sku = df["SKU"].nunique() if "SKU" in df else len(df)
    tong_ton = df["Ton_Kho"].sum() if "Ton_Kho" in df else 0
    nhap_thang = df["Nhap_Thang"].sum() if "Nhap_Thang" in df else 0
    xuat_thang = df["Xuat_Thang"].sum() if "Xuat_Thang" in df else 0
    sku_canh_bao = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]]["SKU"].count() if ("Muc_Toi_Thieu" in df and "Ton_Kho" in df) else 0
    gia_tri_ton = df["Gia_Tri_Ton"].sum() if "Gia_Tri_Ton" in df else 0

    kpi1.metric("📦 Tổng SKU", f"{tong_sku:,}")
    kpi2.metric("📊 Tổng tồn kho", f"{tong_ton:,}")
    kpi3.metric("⬆️ Nhập trong tháng", f"{nhap_thang:,}")
    kpi4.metric("⬇️ Xuất trong tháng", f"{xuat_thang:,}")
    kpi5.metric("🔴 SKU dưới tối thiểu", f"{sku_canh_bao:,}")
    kpi6.metric("💰 Giá trị tồn kho", f"{gia_tri_ton:,.0f} VNĐ")

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        if "Ton_Kho" in df and "Ten_San_Pham" in df:
            top_10 = df.nlargest(10, "Ton_Kho")
            fig_top10 = px.bar(top_10, x="Ton_Kho", y="Ten_San_Pham", orientation="h",
                               title="Top 10 sản phẩm tồn nhiều nhất", text_auto=True,
                               color="Ton_Kho", color_continuous_scale="Blues")
            fig_top10.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_top10, use_container_width=True)

        if "Nhom_Hang" in df and "Ton_Kho" in df:
            by_cat = df.groupby("Nhom_Hang")["Ton_Kho"].sum().reset_index()
            fig_cat = px.pie(by_cat, values="Ton_Kho", names="Nhom_Hang", title="Phân bố tồn kho theo nhóm hàng", hole=0.4)
            st.plotly_chart(fig_cat, use_container_width=True)

    with col2:
        if "Muc_Toi_Thieu" in df and "Ton_Kho" in df:
            sap_het = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]].sort_values("Ton_Kho")
            st.write("⚠️ **Top sản phẩm sắp hết (Dưới mức tối thiểu)**")
            st.dataframe(sap_het[["SKU", "Ten_San_Pham", "Ton_Kho", "Muc_Toi_Thieu"]], use_container_width=True)

        if "Khu_Vuc" in df and "Ton_Kho" in df:
            by_warehouse = df.groupby("Khu_Vuc")["Ton_Kho"].sum().reset_index()
            fig_wh = px.bar(by_warehouse, x="Khu_Vuc", y="Ton_Kho", title="Tồn kho theo từng khu vực/kho",
                            color="Khu_Vuc", text_auto=True)
            st.plotly_chart(fig_wh, use_container_width=True)

# --- TAB 2: CHAT AI ---
with tab_chat:
    st.title("🤖 Trợ lý AI Quản Lý Kho")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Hỏi AI về dữ liệu kho..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            if not st.session_state.api_key:
                response = "⚠️ Vui lòng ấn vào nút **⚙️ Cài đặt & Dữ liệu** để nhập API Key trước khi hỏi AI."
            else:
                response = f"🤖 AI đang sử dụng API Key đã lưu để phân tích câu hỏi: '{prompt}'."
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
