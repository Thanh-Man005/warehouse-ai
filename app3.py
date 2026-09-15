import streamlit as st
import pandas as pd
import plotly.express as px
import time

st.set_page_config(page_title="AI Kho Hàng", layout="wide", initial_sidebar_state="collapsed")

# --- 1. KHỞI TẠO SESSION STATE ---
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

# --- HÀM PHÂN TÍCH DỮ LIỆU KHO CHO AI ---
def analyze_warehouse_data(query: str, df: pd.DataFrame) -> str:
    q = query.lower()
    
    # 1. Hỏi về tồn kho cao nhất / sản phẩm tồn nhiều nhất
    if any(k in q for k in ["cao nhất", "nhiều nhất", "lớn nhất", "max"]):
        if "Ton_Kho" in df.columns and "Ten_San_Pham" in df.columns:
            top_item = df.nlargest(1, "Ton_Kho").iloc[0]
            sku = top_item.get("SKU", "N/A")
            name = top_item["Ten_San_Pham"]
            qty = top_item["Ton_Kho"]
            cat = top_item.get("Nhom_Hang", "N/A")
            loc = top_item.get("Khu_Vuc", "N/A")
            return (
                f"📦 **Mặt hàng tồn kho cao nhất:**\n"
                f"- **Tên sản phẩm:** {name} (Mã SKU: `{sku}`)\n"
                f"- **Nhóm hàng:** {cat} | **Vị trí:** {loc}\n"
                f"- **Số lượng tồn kho:** **{qty:,}** đơn vị.\n\n"
                f"💡 **Khuyến nghị:** Mặt hàng này có tồn kho dư dả, hiện **chưa cần nhập thêm**. "
                f"Nên cân nhắc các chương trình khuyến mãi/kích cầu xuất hàng để tối ưu chi phí lưu kho."
            )

    # 2. Hỏi về sắp hết / cần bổ sung / cảnh báo tồn kho thấp
    if any(k in q for k in ["sắp hết", "thấp nhất", "bổ sung", "cảnh báo", "tối thiểu", "hết hàng", "cần nhập"]):
        if "Ton_Kho" in df.columns and "Muc_Toi_Thieu" in df.columns:
            low_stock = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]].sort_values("Ton_Kho")
            if len(low_stock) > 0:
                result_text = f"⚠️ **Có {len(low_stock)} sản phẩm đang ở dưới mức tối thiểu cần bổ sung ngay:**\n"
                for idx, row in low_stock.head(5).iterrows():
                    result_text += f"- **{row['Ten_San_Pham']}** (`{row['SKU']}`): Tồn kho **{row['Ton_Kho']}** (Định mức min: {row['Muc_Toi_Thieu']})\n"
                result_text += "\n📌 **Đề xuất:** Cần lập đơn nhập hàng bổ sung gấp cho các mặt hàng trên."
                return result_text
            else:
                return "✅ Tất cả các mặt hàng hiện tại đều ở mức an toàn (trên định mức tối thiểu)."

    # 3. Hỏi về tổng quan / tổng tồn kho
    if any(k in q for k in ["tổng tồn", "tổng số", "tổng giá trị", "bao nhiêu sku"]):
        tong_sku = len(df)
        tong_ton = df["Ton_Kho"].sum() if "Ton_Kho" in df.columns else 0
        gia_tri = df["Gia_Tri_Ton"].sum() if "Gia_Tri_Ton" in df.columns else 0
        return (
            f"📊 **Báo cáo tổng quan kho hàng:**\n"
            f"- **Tổng số mặt hàng (SKU):** {tong_sku:,} mặt hàng\n"
            f"- **Tổng số lượng tồn kho:** {tong_ton:,} sản phẩm\n"
            f"- **Tổng giá trị vốn tồn kho:** {gia_tri:,.0f} VNĐ"
        )

    # 4. Trả lời mặc định dựa trên dữ liệu tổng hợp
    top_3 = df.nlargest(3, "Ton_Kho")[["Ten_San_Pham", "Ton_Kho"]].to_dict('records')
    top_str = ", ".join([f"{item['Ten_San_Pham']} ({item['Ton_Kho']} sp)" for item in top_3])
    return (
        f"🤖 **Thông tin kho hàng liên quan đến câu hỏi '{query}':**\n\n"
        f"- Top 3 sản phẩm tồn kho cao nhất hiện tại là: **{top_str}**.\n"
        f"- Hiện có **{len(df[df['Ton_Kho'] <= df['Muc_Toi_Thieu']])}** mặt hàng cần nhập bổ sung.\n"
        f"Bạn có thể hỏi chi tiết như: *'sản phẩm nào sắp hết'*, *'tồn kho cao nhất'*, hoặc *'tổng giá trị tồn kho'*."
    )

# --- 2. CSS CỐ ĐỊNH NÚT AI Ở GÓC DƯỚI BÊN PHẢI ---
css_code = """
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
