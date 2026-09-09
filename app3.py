import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Tổng quan kho", layout="wide")
st.title("📦 Dashboard Tổng Quan Kho")

# 1. Dữ liệu mẫu
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
df["Gia_Tri_Ton"] = df["Ton_Kho"] * df["Gia_Nhap"]

# 2. HIỂN THỊ KPI (6 THÔNG SỐ)
st.subheader("📊 Chỉ số KPI chính")
kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

tong_sku = df["SKU"].nunique()
tong_ton = df["Ton_Kho"].sum()
nhap_thang = df["Nhap_Thang"].sum()
xuat_thang = df["Xuat_Thang"].sum()
sku_canh_bao = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]]["SKU"].count()
gia_tri_ton = df["Gia_Tri_Ton"].sum()

kpi1.metric("📦 Tổng SKU", f"{tong_sku:,}")
kpi2.metric("📊 Tổng tồn kho", f"{tong_ton:,}")
kpi3.metric("⬆️ Nhập trong tháng", f"{nhap_thang:,}")
kpi4.metric("⬇️ Xuất trong tháng", f"{xuat_thang:,}")
kpi5.metric("🔴 SKU dưới tối thiểu", f"{sku_canh_bao:,}")
kpi6.metric("💰 Giá trị tồn kho", f"{gia_tri_ton:,.0f} VNĐ")

st.markdown("---")

# 3. CÁC BIỂU ĐỒ BÊN DƯỚI
col1, col2 = st.columns(2)

with col1:
    top_10 = df.nlargest(10, "Ton_Kho")
    fig_top10 = px.bar(top_10, x="Ton_Kho", y="Ten_San_Pham", orientation="h",
                       title="Top 10 sản phẩm tồn nhiều nhất", text_auto=True,
                       color="Ton_Kho", color_continuous_scale="Blues")
    fig_top10.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_top10, use_container_width=True)

    by_cat = df.groupby("Nhom_Hang")["Ton_Kho"].sum().reset_index()
    fig_cat = px.pie(by_cat, values="Ton_Kho", names="Nhom_Hang", title="Phân bố tồn kho theo nhóm hàng", hole=0.4)
    st.plotly_chart(fig_cat, use_container_width=True)

with col2:
    sap_het = df[df["Ton_Kho"] <= df["Muc_Toi_Thieu"]].sort_values("Ton_Kho")
    st.write("⚠️ **Top sản phẩm sắp hết (Dưới mức tối thiểu)**")
    st.dataframe(sap_het[["SKU", "Ten_San_Pham", "Ton_Kho", "Muc_Toi_Thieu"]], use_container_width=True)

    by_warehouse = df.groupby("Khu_Vuc")["Ton_Kho"].sum().reset_index()
    fig_wh = px.bar(by_warehouse, x="Khu_Vuc", y="Ton_Kho", title="Tồn kho theo từng khu vực/kho",
                    color="Khu_Vuc", text_auto=True)
    st.plotly_chart(fig_wh, use_container_width=True)

st.subheader("📈 Biểu đồ Nhập/Xuất theo thời gian")
time_data = pd.DataFrame({
    "Ngay": pd.date_range(start="2026-09-01", periods=10),
    "Nhap": [100, 150, 80, 200, 120, 90, 300, 110, 50, 180],
    "Xuat": [80, 120, 100, 160, 110, 80, 250, 90, 70, 150]
})
fig_time = px.line(time_data, x="Ngay", y=["Nhap", "Xuat"], labels={"value": "Số lượng", "variable": "Loại giao dịch"})
st.plotly_chart(fig_time, use_container_width=True)
