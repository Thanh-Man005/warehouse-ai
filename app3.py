import streamlit as st
import pandas as pd
import json
import os
import re
import io
import requests
from pathlib import Path

# ── Cấu hình trang ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Kho Hàng - Tự Động Định Tuyến",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS Tùy chỉnh ────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main .block-container { padding-top: 1.5rem; max-width: 1100px; }
    .stChatMessage { border-radius: 12px; }
    .badge-auto { background: #D1FAE5; color: #065F46; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }
    .badge-ai   { background: #FEF3C7; color: #92400E; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ── Đường dẫn lưu trữ dữ liệu bền vững ─────────────────────────────────────────
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
EXCEL_PATH  = DATA_DIR / "warehouse.xlsx"
CONFIG_PATH = DATA_DIR / "config.json"
CHAT_PATH   = DATA_DIR / "chat_history.json"

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 0 — HÀM LƯU / TẢI CẤU HÌNH VÀ LỊCH SỬ CHAT (PERSISTENCE)
# ════════════════════════════════════════════════════════════════════════════
def load_json_data(path: Path, default_val):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_val
    return default_val

def save_json_data(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Khởi tạo trạng thái ban đầu từ file đã lưu
saved_config = load_json_data(CONFIG_PATH, {
    "api_key": "",
    "data_source": "🌐 Link Google Trang tính",
    "gsheet_url": ""
})

if "api_key" not in st.session_state:
    st.session_state.api_key = saved_config.get("api_key", "")
if "gsheet_url" not in st.session_state:
    st.session_state.gsheet_url = saved_config.get("gsheet_url", "")
if "data_source" not in st.session_state:
    st.session_state.data_source = saved_config.get("data_source", "🌐 Link Google Trang tính")
if "messages" not in st.session_state:
    st.session_state.messages = load_json_data(CHAT_PATH, [])

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 1 — BỘ NHẬN DIỆN Ý ĐỊNH & ĐỊNH TUYẾN TỰ ĐỘNG (AUTO-ROUTER)
# ════════════════════════════════════════════════════════════════════════════
def auto_route_and_process(question: str, sheets_dict: dict[str, pd.DataFrame]):
    q_low = question.lower().strip()

    # Bắt buộc chuyển cho AI nếu hỏi nâng cao / danh sách / bảng
    if any(k in q_low for k in ["bảng", "lập bảng", "danh sách", "thống kê", "tại sao", "vì sao", "dự báo", "tư vấn", "lâu nhất", "tồn đọng", "nhiều nhất"]):
        return None, True 

    # 1. TRA CỨU HÀNG TỒN ÍT / SẮP HẾT (Xử lý nội bộ 0 Token)
    if any(k in q_low for k in ["sắp hết", "tồn ít", "cảnh báo", "hết hàng", "thiếu hàng"]):
        results = []
        for name, df in sheets_dict.items():
            stock_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["ton", "số lượng", "sl"])), None)
            name_col  = next((c for c in df.columns if any(x in str(c).lower() for x in ["tên", "vật tư", "mặt hàng"])), None)
            
            if stock_col and name_col:
                df_clean = df.dropna(subset=[stock_col]).copy()
                df_clean[stock_col] = pd.to_numeric(df_clean[stock_col], errors='coerce')
                low_df = df_clean[df_clean[stock_col] <= 20]
                
                if not low_df.empty:
                    items = [f"- **{row[name_col]}**: còn `{row[stock_col]}`" for _, row in low_df.head(10).iterrows()]
                    results.append(f"📌 **Tab [{name}] có {len(low_df)} mặt hàng tồn ít (<=20):**\n" + "\n".join(items))
        if results:
            return "⚡ **[Tự động xử lý - 0 Token]**\n\n" + "\n\n".join(results), False
        return "⚡ **[Tự động xử lý - 0 Token]**: Tất cả mặt hàng đều an toàn (tồn kho > 20).", False

    # 2. TÍNH TỔNG GIÁ TRỊ / TỔNG TIỀN
    elif any(k in q_low for k in ["tổng giá trị", "tổng tiền", "giá trị kho", "tổng vốn"]):
        total_val = 0
        details = []
        for name, df in sheets_dict.items():
            val_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["thành tiền", "giá trị", "tổng"])), None)
            if val_col:
                s = pd.to_numeric(df[val_col], errors='coerce').sum()
                if s > 0:
                    total_val += s
                    details.append(f"- Tab **{name}**: {s:,.0f} VNĐ")
        if details:
            msg = f"⚡ **[Tự động xử lý - 0 Token]**\n\n💰 **Tổng giá trị:** `{total_val:,.0f} VNĐ`\n\nChi tiết:\n" + "\n".join(details)
            return msg, False

    return None, True

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 2 — XỬ LÝ DỮ LIỆU & GỌI AI (CHUẨN TÊN MODEL CHÍNH THỨC)
# ════════════════════════════════════════════════════════════════════════════
def extract_gsheet_id(url: str) -> str:
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

@st.cache_data(show_spinner=False, ttl=60)
def load_all_sheets_from_gsheet(url: str) -> dict[str, pd.DataFrame]:
    sheet_id = extract_gsheet_id(url)
    if not sheet_id: raise ValueError("Link không hợp lệ!")
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    resp = requests.get(export_url)
    if resp.status_code != 200: raise Exception("Lỗi tải trang tính")
    xl = pd.ExcelFile(io.BytesIO(resp.content))
    return {sheet: xl.parse(sheet) for sheet in xl.sheet_names}

@st.cache_data(show_spinner=False)
def load_all_sheets_from_file(path: str) -> dict[str, pd.DataFrame]:
    xl = pd.ExcelFile(path)
    return {sheet: xl.parse(sheet) for sheet in xl.sheet_names}

def ask_ai(question: str, sheets_dict: dict[str, pd.DataFrame]) -> str:
    api_key = st.session_state.get("api_key", "").strip()
    if not api_key:
        raise Exception("Vui lòng nhập API Key ở menu Cài đặt bên trái.")
    
    prompt_data = []
    for name, df in sheets_dict.items():
        df_clean = df.dropna(how="all")
        if not df_clean.empty:
            prompt_data.append(f"=== TAB [{name}] ===\n{df_clean.head(40).to_string(index=False)}")
            
    context = "\n\n".join(prompt_data)
    
    system = f"""Bạn là chuyên gia phân tích kho hàng. Dưới đây là dữ liệu từ file kho:

{context}

QUY TẮC BẮT BUỘC KHI TRẢ LỜI:
1. Bạn phải trả lời HOÀN CHỈNH, ĐẦY ĐỦ từ đầu đến cuối, tuyệt đối KHÔNG ĐƯỢC ngắt câu giữa chừng.
2. Trình bày thông tin rõ ràng dưới dạng BẢNG MARKDOWN chuẩn (nếu có danh sách mặt hàng, số lượng):
| STT | Mã VT | Tên Vật Tư | Số Lượng | Ghi Chú |
| --- | --- | --- | --- | --- |
3. Trả lời trực tiếp vào trọng tâm câu hỏi của người dùng."""

    body = {
        "contents": [{"role": "user", "parts": [{"text": f"{system}\n\nCÂU HỎI CỦA NGUỜI DÙNG: {question}"}]}],
        "generationConfig": {
            "maxOutputTokens": 8192,
            "temperature": 0.2
        }
    }

    # Tên các Model chính thức chuẩn 100% từ Google
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-2.0-flash"
    ]

    last_error = ""
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        try:
            resp = requests.post(url, params={"key": api_key}, json=body, timeout=30)
            if resp.status_code == 200:
                res_json = resp.json()
                candidates = res_json.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    text_parts = [p.get("text", "") for p in parts if "text" in p]
                    full_text = "".join(text_parts).strip()
                    if full_text:
                        return f"🤖 **[Phân tích bởi AI]**\n\n{full_text}"
            else:
                last_error = resp.text
        except Exception as e:
            last_error = str(e)

    raise Exception(f"Lỗi kết nối AI: {last_error[:200]}")

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 3 — GIAO DIỆN VÀ LUỒNG XỬ LÝ LƯU TRỮ CẤU HÌNH
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ Cài đặt")
    
    # 1. Tự động lưu API Key khi thay đổi
    api_key_input = st.text_input("🔑 API Key (Gemini)", type="password", value=st.session_state.api_key)
    if api_key_input != st.session_state.api_key:
        st.session_state.api_key = api_key_input
        saved_config["api_key"] = api_key_input
        save_json_data(CONFIG_PATH, saved_config)

    st.divider()
    st.markdown("### 📂 Nguồn dữ liệu kho")
    
    # 2. Tự động lưu Nguồn dữ liệu (Google Sheet hoặc Excel)
    data_source_idx = 0 if st.session_state.data_source == "🌐 Link Google Trang tính" else 1
    data_source = st.radio("Hình thức:", ["🌐 Link Google Trang tính", "📁 Tải file Excel lên"], index=data_source_idx)
    if data_source != st.session_state.data_source:
        st.session_state.data_source = data_source
        saved_config["data_source"] = data_source
        save_json_data(CONFIG_PATH, saved_config)

    sheets_data = None
    if data_source == "🌐 Link Google Trang tính":
        # 3. Tự động lưu Link Google Sheet
        gsheet_url_input = st.text_input("Dán link Google Sheet:", value=st.session_state.gsheet_url)
        if gsheet_url_input != st.session_state.gsheet_url:
            st.session_state.gsheet_url = gsheet_url_input
            saved_config["gsheet_url"] = gsheet_url_input
            save_json_data(CONFIG_PATH, saved_config)

        if st.session_state.gsheet_url:
            try:
                sheets_data = load_all_sheets_from_gsheet(st.session_state.gsheet_url)
                st.success(f"✅ Kết nối thành công {len(sheets_data)} tab!")
            except Exception:
                st.error("❌ Lỗi đọc Google Sheet!")
    else:
        uploaded = st.file_uploader("Tải file Excel", type=["xlsx", "xls"])
        if uploaded:
            EXCEL_PATH.write_bytes(uploaded.read())
            st.cache_data.clear()
            sheets_data = load_all_sheets_from_file(str(EXCEL_PATH))
            st.success("✅ Đã lưu file Excel mới!")
        elif EXCEL_PATH.exists():
            sheets_data = load_all_sheets_from_file(str(EXCEL_PATH))
            st.info("ℹ️ Đang sử dụng file Excel đã lưu sẵn.")

    st.divider()
    # Nút xóa lịch sử chat khi cần làm mới hoàn toàn
    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state.messages = []
        save_json_data(CHAT_PATH, [])
        st.rerun()

st.markdown("# 🏭 AI Quản Lý Kho Hàng")

if not sheets_data:
    st.info("👈 Vui lòng dán Link Google Sheet hoặc tải file Excel ở sidebar trái.")
    st.stop()

tab_data, tab_chat = st.tabs(["📊 Xem dữ liệu", "💬 Hỏi đáp Thông Minh"])

with tab_data:
    selected_tab = st.selectbox("Chọn Tab:", list(sheets_data.keys()))
    st.dataframe(sheets_data[selected_tab], use_container_width=True, height=400)

with tab_chat:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): 
            st.markdown(msg["content"])

    question = st.text_area("Gõ câu hỏi bất kỳ...", height=90, placeholder="VD: Các mặt hàng xuất nhiều nhất đạt được trong 1 tháng")

    if st.button("🚀 Gửi câu hỏi", type="primary"):
        if question:
            with st.chat_message("user"): 
                st.markdown(question)
            
            st.session_state.messages.append({"role": "user", "content": question})
            save_json_data(CHAT_PATH, st.session_state.messages)

            with st.spinner("🔄 AI đang phân tích dữ liệu kho..."):
                local_answer, need_ai = auto_route_and_process(question, sheets_data)

                if not need_ai:
                    final_ans = local_answer
                else:
                    try:
                        final_ans = ask_ai(question, sheets_data)
                    except Exception as e:
                        final_ans = f"❌ Lỗi: {str(e)}"

                with st.chat_message("assistant"):
                    st.markdown(final_ans)
                
                st.session_state.messages.append({"role": "assistant", "content": final_ans})
                save_json_data(CHAT_PATH, st.session_state.messages)
