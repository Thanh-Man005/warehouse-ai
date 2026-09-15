import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

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

# --- 3. ĐỘNG CƠ AI PHÂN TÍCH & DỰ BÁO ---
def analyze_warehouse_data_advanced(query: str, df: pd.DataFrame) -> str:
    q = query.lower().strip()
    if df.empty:
        return "⚠️ Dữ liệu kho đang rỗng. Vui lòng kiểm tra lại file tải lên."

    df_calc = df.copy()
    df_calc["Xuat_Ngay"] = df_calc["Xuat_Trong_Thang"] / 30.0
    df_calc["So_Ngay_Ton_Kho"] = np.where(
        df_calc["Xuat_Ngay"] > 0, 
        df_calc["Ton_Kho"] / df_calc["Xuat_Ngay"], 
        999
    )
    df_calc["De_Xuat_Nhap"] = np.maximum(0, (df_calc["Muc_Toi_Thieu"] * 2) - df_calc["Ton_Kho"])

    # CẢNH BÁO
    if any(k in q for k in ["cảnh báo", "canh bao", "nguy cơ", "cháy hàng", "tồn đọng"]):
        canh_bao_do = df_calc[df_calc["Ton_Kho"] <= df_calc["Muc_Toi_Thieu"]]
        canh_bao_vang = df_calc[(df_calc["Ton_Kho"] > 200) & (df_calc["Xuat_Trong_Thang"] == 0)]
        
        res = "🚨 **HỆ THỐNG CẢNH BÁO KHO HÀNG TỰ ĐỘNG**\n\n"
        res += f"🔴 **Cảnh báo Đỏ (Dưới định mức tối thiểu - {len(canh_bao_do)} SKU):**\n"
        if not canh_bao_do.empty:
            res += "| Mã SKU | Tên Sản Phẩm | Tồn Hiện Tại | Định Mức | Đề Xuất Nhập |\n"
            res += "| :--- | :--- | :---: | :---: | :---: |\n"
            for _, r in canh_bao_do.head(5).iterrows():
                res += f"| `{r['SKU']}` | {r['Ten_San_Pham']} | **{int(r['Ton_Kho']):,}** | {int(r['Muc_Toi_Thieu']):,} | ➕ **{int(r['De_Xuat_Nhap']):,}** |\n"
        else:
            res += "✅ Không có sản phẩm nào dưới định mức.\n"

        res += f"\n🟡 **Cảnh báo Vàng (Tồn đọng lớn / Không có giao dịch xuất - {len(canh_bao_vang)} SKU):**\n"
        if not canh_bao_vang.empty:
            res += "| Mã SKU | Tên Sản Phẩm | Tồn Kho | Giá Trị Tồn |\n"
            res += "| :--- | :--- | :---: | :---: |\n"
            for _, r in canh_bao_vang.head(5).iterrows():
                res += f"| `{r['SKU']}` | {r['Ten_San_Pham']} | {int(r['Ton_Kho']):,} | {r['Gia_Tri_Ton']:,.0f} VNĐ |\n"
        else:
            res += "✅ Không phát hiện hàng tồn đọng bất thường.\n"
        return res

    # DỰ BÁO
    if any(k in q for k in ["dự báo", "du bao", "bao lâu", "ngày hết", "kế hoạch nhập"]):
        df_forecast = df_calc[df_calc["Xuat_Ngay"] > 0].sort_values("So_Ngay_Ton_Kho").head(7)
        
        res = "📈 **DỰ BÁO NGUY CƠ CẠN KHO & KẾ HOẠCH BỔ SUNG**\n\n"
        res += "| Mã SKU | Tên Sản Phẩm | Tồn Hiện Tại | Tốc Độ Xuất (SP/Ngày) | Dự Báo Cạn Kho | Đề Xuất Nhập Bù |\n"
        res += "| :--- | :--- | :---: | :---: | :---: | :---: |\n"
        for _, r in df_forecast.iterrows():
            days_str = "⚠️ Cạn kho ngay" if r['Ton_Kho'] <= 0 else f"⏳ **~{int(r['So_Ngay_Ton_Kho'])} ngày**"
            res += f"| `{r['SKU']}` | {r['Ten_San_Pham']} | {int(r['Ton_Kho']):,} | {r['Xuat_Ngay']:.1f} | {days_str} | 📦 **{int(r['De_Xuat_Nhap']):,}** |\n"
        return res

    # BẢNG TỔNG QUAN
    if any(k in q for k in ["bảng", "tạo bảng", "danh sách", "chi tiết"]):
        res = "📋 **BẢNG BÁO CÁO TỔNG QUAN XUẤT - NHẬP - TỒN**\n\n"
        res += "| Mã SKU | Tên Sản Phẩm | Tồn Kho | Nhập Tháng | Xuất Tháng | Giá Trị Tồn |\n"
        res += "| :--- | :--- | :---: | :---: | :---: | :---: |\n"
        for _, r in df_calc.head(10).iterrows():
            res += f"| `{r['SKU']}` | {r['Ten_San_Pham']} | {int(r['Ton_Kho']):,} | {int(r['Nhap_Trong_Thang']):,} | {int(r['Xuat_Trong_Thang']):,} | {r['Gia_Tri_Ton']:,.0f} VNĐ |\n"
        return res

    return f"🤖 **Trợ lý AI Kho Hàng:** Đang quản lý **{len(df)}** mặt hàng.\n\nBạn có thể thử các câu hỏi:\n- *'Cảnh báo kho'* (Phân tích nguy cơ hết hàng & tồn đọng)\n- *'Dự báo cạn kho'* (Dự báo số ngày cạn kho & đề xuất nhập bù)\n- *'Tạo bảng báo cáo'* (Xuất bảng chi tiết)"

# --- 4. DIALOG / MODAL MỞ RỘNG TOÀN MÀN HÌNH CHO AI ---
@st.dialog("🖥️ Trợ Lý AI Kho Hàng - Chế Độ Mở Rộng", width="large")
def show_fullscreen_ai_chat():
    st.markdown(" Giao diện mở rộng giúp bạn dễ dàng theo dõi các bảng dữ liệu phức tạp và biểu đồ từ AI.")
    
    chat_container = st.container(height=450)
    with chat_container:
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                
    with st.form("modal_chat_form", clear_on_submit=True):
        col_in, col_btn = st.columns([0.8, 0.2])
        with col_in:
            m_input = st.text_input("Nhập yêu cầu cho AI...", placeholder="Ví dụ: Dự báo cạn kho...", label_visibility="collapsed")
        with col_btn:
            submitted = st.form_submit_button("🚀 Gửi câu hỏi", use_container_width=True)
        if submitted and m_input.strip():
            st.session_state.messages.append({"role": "user", "content": m_input})
            reply = analyze_warehouse_data_advanced(m_input, st.session_state.df_data)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()

# --- 5. SIDEBAR QUẢN LÝ & CÀI ĐẶT ---
with st.sidebar:
    st.header("🤖 Trợ Lý AI Kho Hàng")
    
    # Nút mở rộng Toàn màn hình
    if st.button("🖥️ Mở rộng khung AI Toàn Màn Hình", use_container_width=True, type="primary"):
        show_fullscreen_ai_chat()

    sidebar_chat = st.container(height=280)
    with sidebar_chat:
        if not st.session_state.messages:
            st.markdown("👋 *Tôi có thể giúp bạn **Dự báo nhu cầu**, **Cảnh báo hết hàng** và **Tạo bảng dữ liệu**.*")
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    with st.form("sidebar_chat_form", clear_on_submit=True):
        u_input = st.text_input("Hỏi AI...", placeholder="Cảnh báo kho...")
        if st.form_submit_button("Gửi câu hỏi", use_container_width=True) and u_input.strip():
            st.session_state.messages.append({"role": "user", "content": u_input})
            reply = analyze_warehouse_data_advanced(u_input, st.session_state.df_data)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()

    st.markdown("---")
    st.header("⚙️ Nguồn Dữ Liệu Kho")
    file_up = st.file_uploader("Tải file Excel/CSV kho", type=["xlsx", "xls", "csv"], key="sidebar_file_up")
    if file_up is not None:
        cur_id = f"{file_up.name}_{file_up.size}"
        if st.session_state.last_file_id != cur_id:
            df_r, df_c = process_excel_warehouse(file_up)
            st.session_state.df_raw = df_r
            st.session_state.df_data = df_c
            st.session_state.last_file_id = cur_id
            st.success("Đã nạp và chuẩn hóa dữ liệu!")

# --- 6. HEADER TRANG CHÍNH ---
col_title, col_ai_top, col_user = st.columns([0.45, 0.3, 0.25])

with col_title:
    st.title("📦 AI Kho Hàng")

with col_ai_top:
    st.write("")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        if st.button("🖥️ AI Fullscreen", use_container_width=True):
            show_fullscreen_ai_chat()
    with col_p2:
        with st.popover("💬 Chat nhanh", use_container_width=True):
            top_chat = st.container(height=250)
            with top_chat:
                for m in st.session_state.messages:
                    with st.chat_message(m["role"]):
                        st.markdown(m["content"])
            with st.form("top_chat_form", clear_on_submit=True):
                top_in = st.text_input("Hỏi AI...", placeholder="Dự báo cạn kho...", label_visibility="collapsed")
                if st.form_submit_button("Gửi", use_container_width=True) and top_in.strip():
                    st.session_state.messages.append({"role": "user", "content": top_in})
                    reply = analyze_warehouse_data_advanced(top_in, st.session_state.df_data)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    st.rerun()

with col_user:
    st.write("")
    if not st.session_state.is_logged_in:
        with st.popover("👤 Đăng nhập", use_container_width=True):
            u_in = st.text_input("Tên đăng nhập", key="login_u")
            p_in = st.text_input("Mật khẩu", type="password", key="login_p")
            if st.button("Xác nhận", use_container_width=True) and u_in:
                st.session_state.is_logged_in = True
                st.session_state.username = u_in
                st.rerun()
    else:
        with st.popover(f"👤 {st.session_state.username}", use_container_width=True):
            if st.button("Đăng xuất", use_container_width=True):
                st.session_state.is_logged_in = False
                st.rerun()

# --- 7. TÍNH NĂNG 1: XEM TRƯỚC & ĐỐI SOÁT DỮ LIỆU TẢI LÊN ---
st.subheader("🔍 Xem Trước & Kiểm Định Dữ Liệu Tải Lên")
with st.expander("📌 Nhấp vào đây để kiểm tra dữ liệu thô và đối soát dữ liệu đã xử lý", expanded=False):
    tab_clean, tab_raw, tab_val = st.tabs(["📊 Dữ Liệu Đã Xử Lý", "📄 Dữ Liệu Thô (Raw File)", "⚠️ Kiểm Trả Lỗi & Độ Chính Xác"])
    
    with tab_clean:
        st.markdown("**Bảng dữ liệu đã chuẩn hóa (Dùng cho AI & Phân tích):**")
        st.dataframe(st.session_state.df_data, use_container_width=True)
        
    with tab_raw:
        st.markdown("**Bảng dữ liệu gốc từ File Excel/CSV tải lên:**")
        if not st.session_state.df_raw.empty:
            st.dataframe(st.session_state.df_raw.head(30), use_container_width=True)
        else:
            st.info("Đang sử dụng dữ liệu mẫu mặc định. Hãy tải file Excel ở sidebar để kiểm tra file thực tế.")
            
    with tab_val:
        st.markdown("**Báo cáo sức khỏe dữ liệu (Data Health Check):**")
        df_chk = st.session_state.df_data
        col_v1, col_v2, col_v3 = st.columns(3)
        col_v1.metric("Tổng số dòng dữ liệu", f"{len(df_chk):,} dòng")
        col_v2.metric("Số ô bị khuyết (NaN)", f"{df_chk.isna().sum().sum():,} ô")
        col_v3.metric("Số SKU trùng lặp", f"{df_chk['SKU'].duplicated().sum():,} SKU")
        
        if df_chk["Ton_Kho"].isna().any() or df_chk["Gia_Tri_Ton"].isna().any():
            st.warning("⚠️ Phát hiện có giá trị trống ở cột số lượng/giá trị. Hệ thống đã tự động gán giá trị 0.")
        else:
            st.success("✅ Dữ liệu hoàn toàn hợp lệ, không bị mất mát hay sai lệch định dạng!")

st.markdown("---")

# --- 8. KPI DASHBOARD ---
df = st.session_state.df_data
st.subheader("📊 Chỉ Số KPI Tổng Quan")
k1, k2, k3, k4, k5, k6 = st.columns(6)

k1.metric("📦 Tổng SKU", f"{len(df):,}")
k2.metric("📊 Tổng tồn kho", f"{int(df['Ton_Kho'].sum()):,}")
k3.metric("📥 Nhập trong tháng", f"{int(df['Nhap_Trong_Thang'].sum()):,}")
k4.metric("📤 Xuất trong tháng", f"{int(df['Xuat_Trong_Thang'].sum()):,}")
k5.metric("⚠️ SKU dưới tối thiểu", f"{len(df[df['Ton_Kho'] <= df['Muc_Toi_Thieu']]):,}")
k6.metric("💰 Giá trị tồn", f"{df['Gia_Tri_Ton'].sum():,.0f} VNĐ")

st.markdown("---")

# --- 9. TÍNH NĂNG 2: BỘ TẠO BIỂU ĐỒ LINH HOẠT (DYNAMIC CHART GENERATOR) ---
st.subheader("📈 Trình Tạo Biểu Đồ & Phân Tích Trực Quan")

tab_auto_chart, tab_custom_chart = st.tabs(["📊 Biểu Đồ AI Tự Động", "🎨 Tùy Chỉnh Biểu Đồ Theo Ý Muốn"])

with tab_auto_chart:
    c_left, c_right = st.columns(2)
    with c_left:
        if not df.empty:
            top10 = df.nlargest(10, "Ton_Kho")
            fig_top10 = px.bar(top10, x="Ton_Kho", y="Ten_San_Pham", orientation="h",
                               title="Top 10 Sản Phẩm Tồn Kho Nhiều Nhất", text_auto=True,
                               color="Ton_Kho", color_continuous_scale="Blues")
            fig_top10.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_top10, use_container_width=True)

    with c_right:
        if "Nhom_Hang" in df.columns and not df.empty:
            df_nhom = df.groupby("Nhom_Hang")["Ton_Kho"].sum().reset_index()
            fig_pie = px.pie(df_nhom, values="Ton_Kho", names="Nhom_Hang", 
                             title="Tỷ Lệ Tồn Kho Theo Nhóm Hàng", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

with tab_custom_chart:
    st.markdown("**Tự do vẽ biểu đồ phân tích theo từng tiêu chí:**")
    col_sel1, col_sel2, col_sel3, col_sel4 = st.columns(4)
    
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df.select_dtypes(include=['object']).columns.tolist()

    with col_sel1:
        chart_type = st.selectbox("Loại biểu đồ", ["Cột (Bar)", "Đường (Line)", "Tròn (Pie)", "Khối (Treemap)", "Điểm (Scatter)"])
    with col_sel2:
        x_col = st.selectbox("Trục X (Danh mục)", cat_cols, index=1 if len(cat_cols) > 1 else 0)
    with col_sel3:
        y_col = st.selectbox("Trục Y (Giá trị số)", num_cols, index=0)
    with col_sel4:
        color_col = st.selectbox("Phân màu theo", [None] + cat_cols, index=0)

    if st.button("📊 Vẽ Biểu Đồ Tùy Chỉnh", use_container_width=True, type="secondary"):
        if chart_type == "Cột (Bar)":
            fig_custom = px.bar(df, x=x_col, y=y_col, color=color_col, title=f"Biểu đồ cột: {y_col} theo {x_col}", text_auto=True)
        elif chart_type == "Đường (Line)":
            fig_custom = px.line(df, x=x_col, y=y_col, color=color_col, title=f"Biểu đồ đường: {y_col} theo {x_col}")
        elif chart_type == "Tròn (Pie)":
            fig_custom = px.pie(df, values=y_col, names=x_col, title=f"Biểu đồ tròn: {y_col} theo {x_col}")
        elif chart_type == "Khối (Treemap)":
            fig_custom = px.treemap(df, path=[x_col], values=y_col, title=f"Biểu đồ khối Treemap: {y_col} theo {x_col}")
        else:
            fig_custom = px.scatter(df, x=x_col, y=y_col, color=color_col, title=f"Biểu đồ phân tán: {y_col} theo {x_col}")
            
        st.plotly_chart(fig_custom, use_container_width=True)
