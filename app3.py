import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# --- 1. THIẾT LẬP TRANG ---
st.set_page_config(page_title="AI Kho Hàng - Dự Báo & Cảnh Báo", layout="wide", initial_sidebar_state="expanded")

# --- 2. DỮ LIỆU MẶC ĐỊNH & XỬ LÝ EXCEL ---
def get_default_df():
    return pd.DataFrame({
        "SKU": [f"SKU{i:03d}" for i in range(1, 21)],
        "Ten_San_Pham": [f"Sản phẩm {i}" for i in range(1, 21)],
        "Nhom_Hang": ["Đồ điện tử", "Thực phẩm", "Gia dụng", "Đồ điện tử", "Thực phẩm"] * 4,
        "Ton_Kho": [450, 400, 350, 320, 300, 280, 250, 210, 180, 150, 90, 80, 60, 40, 20, 8, 5, 4, 2, 0],
        "Nhap_Trong_Thang": [50] * 20,
        "Xuat_Trong_Thang": [120, 90, 80, 60, 50, 40, 30, 20, 15, 10, 5, 4, 3, 2, 1, 10, 8, 6, 4, 0],
        "Muc_Toi_Thieu": [10] * 20,
        "Gia_Tri_Ton": [1000000] * 20,
        "Khu_Vuc": ["Khu A", "Khu B", "Khu C", "Khu A", "Khu B"] * 4
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

        return df_clean.reset_index(drop=True) if not df_clean.empty else get_default_df()
    except Exception:
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
if "last_file_id" not in st.session_state:
    st.session_state.last_file_id = ""

# --- 3. ĐỘNG CƠ AI: TẠO BẢNG + DỰ BÁO + CẢNH BÁO ---
def analyze_warehouse_data_advanced(query: str, df: pd.DataFrame) -> str:
    q = query.lower().strip()
    if df.empty:
        return "⚠️ Dữ liệu kho đang rỗng. Vui lòng kiểm tra lại file tải lên."

    df_calc = df.copy()
    # Tốc độ xuất/ngày (30 ngày/tháng)
    df_calc["Xuat_Ngay"] = df_calc["Xuat_Trong_Thang"] / 30.0
    # Số ngày tồn kho còn lại (Days of Supply)
    df_calc["So_Ngay_Ton_Kho"] = np.where(
        df_calc["Xuat_Ngay"] > 0, 
        df_calc["Ton_Kho"] / df_calc["Xuat_Ngay"], 
        999
    )
    # Số lượng đề xuất nhập (Mục tiêu = 2 x Mức tối thiểu)
    df_calc["De_Xuat_Nhap"] = np.maximum(0, (df_calc["Muc_Toi_Thieu"] * 2) - df_calc["Ton_Kho"])

    # 1. TÍNH NĂNG CẢNH BÁO
    if any(k in q for k in ["cảnh báo", "canh bao", "nguy cơ", "cháy hàng", "tồn đọng", "dư thừa"]):
        canh_bao_do = df_calc[df_calc["Ton_Kho"] <= df_calc["Muc_Toi_Thieu"]]
        canh_bao_vang = df_calc[(df_calc["Ton_Kho"] > 300) & (df_calc["Xuat_Trong_Thang"] == 0)]
        
        res = "🚨 **HỆ THỐNG CẢNH BÁO KHO HÀNG TỰ ĐỘNG**\n\n"
        res += f"🔴 **Cảnh báo Đỏ (Cảnh báo cháy hàng / Dưới định mức - {len(canh_bao_do)} SKU):**\n"
        if not canh_bao_do.empty:
            res += "| Mã SKU | Tên Sản Phẩm | Tồn Hiện Tại | Ngưỡng Tối Thiểu | Đề Xuất Nhập Bổ Sung |\n"
            res += "| :--- | :--- | :---: | :---: | :---: |\n"
            for _, r in canh_bao_do.head(5).iterrows():
                res += f"| `{r['SKU']}` | {r['Ten_San_Pham']} | **{int(r['Ton_Kho']):,}** | {int(r['Muc_Toi_Thieu']):,} | ➕ **{int(r['De_Xuat_Nhap']):,}** |\n"
        else:
            res += "✅ Tất cả sản phẩm đều trên ngưỡng tối thiểu.\n"

        res += f"\n🟡 **Cảnh báo Vàng (Hàng tồn đọng / Không xuất bán - {len(canh_bao_vang)} SKU):**\n"
        if not canh_bao_vang.empty:
            res += "| Mã SKU | Tên Sản Phẩm | Tồn Kho Hiện Tại | Giá Trị Tồn Kho |\n"
            res += "| :--- | :--- | :---: | :---: |\n"
            for _, r in canh_bao_vang.head(5).iterrows():
                res += f"| `{r['SKU']}` | {r['Ten_San_Pham']} | {int(r['Ton_Kho']):,} | {r['Gia_Tri_Ton']:,.0f} VNĐ |\n"
        else:
            res += "✅ Không phát hiện hàng tồn đọng bất thường.\n"
        return res

    # 2. TÍNH NĂNG DỰ BÁO
    if any(k in q for k in ["dự báo", "du bao", "bao lâu", "ngày hết", "kế hoạch nhập"]):
        df_forecast = df_calc[df_calc["Xuat_Ngay"] > 0].sort_values("So_Ngay_Ton_Kho").head(7)
        
        res = "📈 **DỰ BÁO NGUY CƠ CẠN KHO & KẾ HOẠCH BỔ SUNG**\n\n"
        res += "| Mã SKU | Tên Sản Phẩm | Tồn Hiện Tại | Tốc Độ Xuất (SP/Ngày) | Dự Báo Cạn Kho | Đề Xuất Nhập Bù |\n"
        res += "| :--- | :--- | :---: | :---: | :---: | :---: |\n"
        for _, r in df_forecast.iterrows():
            days_str = "⚠️ Cạn kho ngay" if r['Ton_Kho'] <= 0 else f"⏳ **~{int(r['So_Ngay_Ton_Kho'])} ngày**"
            res += f"| `{r['SKU']}` | {r['Ten_San_Pham']} | {int(r['Ton_Kho']):,} | {r['Xuat_Ngay']:.1f} | {days_str} | 📦 **{int(r['De_Xuat_Nhap']):,}** |\n"
        return res

    # 3. TẠO BẢNG TỔNG QUAN
    if any(k in q for k in ["bảng", "tạo bảng", "danh sách", "chi tiết"]):
        res = "📋 **BẢNG BÁO CÁO TỔNG QUAN XUẤT - NHẬP - TỒN**\n\n"
        res += "| Mã SKU | Tên Sản Phẩm | Tồn Kho | Nhập Tháng | Xuất Tháng | Giá Trị Tồn |\n"
        res += "| :--- | :--- | :---: | :---: | :---: | :---: |\n"
        for _, r in df_calc.head(8).iterrows():
            res += f"| `{r['SKU']}` | {r['Ten_San_Pham']} | {int(r['Ton_Kho']):,} | {int(r['Nhap_Trong_Thang']):,} | {int(r['Xuat_Trong_Thang']):,} | {r['Gia_Tri_Ton']:,.0f} VNĐ |\n"
        return res

    return f"🤖 **Trợ lý AI Kho Hàng:** Đang quản lý **{len(df)}** mặt hàng.\n\nThử các câu lệnh:\n- *'Cho tôi xem cảnh báo kho'* (Phân tích nguy cơ hết hàng/tồn đọng)\n- *'Dự báo cạn kho'* (Dự báo số ngày cạn kho & đề xuất nhập)\n- *'Tạo bảng danh sách'* (Tự động xuất bảng tổng hợp)"

# --- 4. SIDEBAR CHỨA TRỢ LÝ AI & CÀI ĐẶT ---
with st.sidebar:
    st.header("🤖 Trợ Lý AI Kho Hàng")
    
    sidebar_chat = st.container(height=320)
    with sidebar_chat:
        if not st.session_state.messages:
            st.markdown("👋 *Tôi có thể giúp bạn **Dự báo nhu cầu**, **Cảnh báo hết hàng** và **Tạo bảng dữ liệu**.*")
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    with st.form("sidebar_chat_form", clear_on_submit=True):
        u_input = st.text_input("Hỏi AI...", placeholder="Ví dụ: Dự báo cạn kho...")
        if st.form_submit_button("Gửi câu hỏi", use_container_width=True) and u_input.strip():
            st.session_state.messages.append({"role": "user", "content": u_input})
            reply = analyze_warehouse_data_advanced(u_input, st.session_state.df_data)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()

    st.markdown("---")
    st.header("⚙️ Cấu hình & Dữ liệu")
    file_up = st.file_uploader("Tải file Excel/CSV kho", type=["xlsx", "xls", "csv"], key="sidebar_file_up")
    if file_up is not None:
        cur_id = f"{file_up.name}_{file_up.size}"
        if st.session_state.last_file_id != cur_id:
            st.session_state.df_data = process_excel_warehouse(file_up)
            st.session_state.last_file_id = cur_id
            st.success("Đã cập nhật dữ liệu thành công!")

# --- 5. TIÊU ĐỀ & POPUP AI ---
col_title, col_ai_top, col_user = st.columns([0.5, 0.25, 0.25])

with col_title:
    st.title("📦 AI Kho Hàng")

with col_ai_top:
    st.write("")
    with st.popover("💬 Trợ Lý AI (Cửa sổ)", use_container_width=True):
        st.markdown("### 🤖 Chat với AI Kho Hàng")
        top_chat = st.container(height=250)
        with top_chat:
            for m in st.session_state.messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])
        with st.form("top_chat_form", clear_on_submit=True):
            top_in = st.text_input("Hỏi AI...", placeholder="Cảnh báo kho...", label_visibility="collapsed")
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

# --- 6. KPI DASHBOARD ---
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

# --- 7. CHARTS & TABLES ---
col_left, col_right = st.columns(2)

with col_left:
    if not df.empty:
        top10 = df.nlargest(10, "Ton_Kho")
        fig_top10 = px.bar(top10, x="Ton_Kho", y="Ten_San_Pham", orientation="h",
                           title="Top 10 sản phẩm tồn nhiều nhất", text_auto=True,
                           color="Ton_Kho", color_continuous_scale="Blues")
        fig_top10.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_top10, use_container_width=True)

    if "Nhom_Hang" in df.columns and not df.empty:
        df_nhom = df.groupby("Nhom_Hang")["Ton_Kho"].sum().reset_index()
        fig_pie = px.pie(df_nhom, values="Ton_Kho", names="Nhom_Hang", 
                         title="Phân bổ tồn kho theo nhóm hàng", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

with col_right:
    st.subheader("⚠️ Top sản phẩm sắp hết (Dưới mức tối thiểu)")
    df_low = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]].copy()
    if df_low.empty:
        df_low = df.nsmallest(5, "Ton_Kho").copy()
    
    df_low_display = df_low.head(10)[["SKU", "Ten_San_Pham", "Ton_Kho", "Muc_Toi_Thieu"]].copy()
    df_low_display.columns = ["Mã SKU", "Tên Sản Phẩm", "Tồn Kho", "Tối Thiểu"]
    df_low_display["Tồn Kho"] = df_low_display["Tồn Kho"].astype(int)
    df_low_display["Tối Thiểu"] = df_low_display["Tối Thiểu"].astype(int)

    st.dataframe(df_low_display, use_container_width=True, hide_index=True)

    if "Khu_Vuc" in df.columns and not df.empty:
        df_khu = df.groupby("Khu_Vuc")["Ton_Kho"].sum().reset_index()
        fig_khu = px.bar(df_khu, x="Khu_Vuc", y="Ton_Kho", color="Khu_Vuc",
                         title="Tồn kho theo từng khu vực/kho", text_auto=True)
        st.plotly_chart(fig_khu, use_container_width=True)
