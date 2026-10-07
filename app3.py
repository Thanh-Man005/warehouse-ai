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
# PHẦN 0 — HÀM LƯU / TẢI CẤU HÌNH VÀ LỊCH SỬ CHAT
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
# PHẦN 1 — BỘ NHẬN DIỆN Ý ĐỊNH & ĐỊNH TUYẾN TỰ ĐỘNG (0 TOKEN)
# ════════════════════════════════════════════════════════════════════════════
def auto_route_and_process(question: str, sheets_dict: dict[str, pd.DataFrame]):
    q_low = question.lower().strip()

    # Nhóm câu hỏi bắt buộc gửi cho AI phân tích sâu
    if any(k in q_low for k in ["bảng", "lập bảng", "danh sách", "thống kê", "tại sao", "vì sao", "dự báo", "tư vấn", "lâu nhất", "tồn đọng", "nhiều nhất"]):
        return None, True 

    # 1. Tra cứu tồn ít / sắp hết (0 Token)
    if any(k in q_low for k in ["sắp hết", "tồn ít", "cảnh báo", "hết hàng", "thiếu hàng"]):
        results = []
        for name, df in sheets_dict.items():
            stock_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["ton", "số lượng", "sl", "tồn kho"])), None)
            name_col  = next((c for c in df.columns if any(x in str(c).lower() for x in ["tên", "vật tư", "mặt hàng", "mã"])), None)
            
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

    # 2. Tính tổng giá trị kho (0 Token)
    elif any(k in q_low for k in ["tổng giá trị", "tổng tiền", "giá trị kho", "tổng vốn"]):
        total_val = 0
        details = []
        for name, df in sheets_dict.items():
            val_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["thành tiền", "giá trị", "tổng tiền"])), None)
            if val_col:
                s = pd.to_numeric(df[val_col], errors='coerce').sum()
                if s > 0:
                    total_val += s
                    details.append(f"- Tab **{name}**: `{s:,.0f} VNĐ`")
        if details:
            msg = f"⚡ **[Tự động xử lý - 0 Token]**\n\n💰 **Tổng giá trị kho:** `{total_val:,.0f} VNĐ`\n\nChi tiết từng tab:\n" + "\n".join(details)
            return msg, False

    # 3. Tra cứu tồn kho tổng quát (0 Token)
    elif any(k in q_low for k in ["còn chính xác bao nhiêu", "còn bao nhiêu", "số lượng còn", "số lượng trong kho"]):
        found_rows = []
        for name, df in sheets_dict.items():
            stock_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["ton", "số lượng", "sl", "tồn kho"])), None)
            name_col  = next((c for c in df.columns if any(x in str(c).lower() for x in ["tên", "vật tư", "mặt hàng", "mã sp", "mã"])), None)
            
            if stock_col and name_col:
                df_clean = df.dropna(subset=[stock_col, name_col]).copy()
                for _, row in df_clean.head(15).iterrows():
                    found_rows.append(f"- **{row[name_col]}** (Tab `{name}`): còn `{row[stock_col]}` đơn vị")
        
        if found_rows:
            return "⚡ **[Tự động tra cứu kho - 0 Token]**\n\n" + "\n".join(found_rows), False

    return None, True

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 2 — XỬ LÝ DỮ LIỆU & GỌI AI GOOGLE (CHỈ LẤY MODEL GEMINI)
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
        raise Exception("🔑 Chưa nhập API Key! Vui lòng dán API Key vào menu Cài đặt ở góc trái.")
    
    prompt_data = []
    for name, df in sheets_dict.items():
        df_clean = df.dropna(how="all")
        if not df_clean.empty:
            prompt_data.append(f"=== TAB [{name}] ===\n{df_clean.head(50).to_string(index=False)}")
            
    context = "\n\n".join(prompt_data)
    
    system = f"""Bạn là chuyên gia phân tích kho hàng. Dưới đây là dữ liệu từ file kho:

{context}

QUY TẮC BẮT BUỘC KHI TRẢ LỜI:
1. Trả lời HOÀN CHỈNH, ĐẦY ĐỦ từ đầu đến cuối.
2. Trình bày rõ ràng dưới dạng BẢNG MARKDOWN nếu có danh sách/số lượng:
| STT | Mã VT | Tên Vật Tư | Số Lượng | Ghi Chú |
| --- | --- | --- | --- | --- |
3. Trả lời trực tiếp vào trọng tâm câu hỏi."""

    body = {
        "contents": [{"role": "user", "parts": [{"text": f"{system}\n\nCÂU HỎI CỦA NGUỜI DÙNG: {question}"}]}],
        "generationConfig": {
            "maxOutputTokens": 8192,
            "temperature": 0.2
        }
    }

    # 1. Truy vấn Google API lấy danh sách Model (Chỉ lọc lấy model dạng gemini-*)
    gemini_models = []
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        res_list = requests.get(list_url, timeout=10)
        if res_list.status_code == 200:
            models_data = res_list.json().get("models", [])
            for m in models_data:
                m_name = m["name"].replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                # BẮT BUỘC CHỈ LẤY MODEL GEMINI VĂN BẢN
                if "generateContent" in methods and m_name.startswith("gemini"):
                    gemini_models.append(m_name)
        elif res_list.status_code in [400, 401, 403]:
            raise Exception("🔑 **API Key bị sai hoặc đã hết hạn!**\nVui lòng truy cập [Google AI Studio](https://aistudio.google.com/app/apikey) để tạo API Key mới và dán lại ở thanh bên trái.")
    except Exception as e:
        if "API Key" in str(e):
            raise e

    # Sắp xếp ưu tiên các model Gemini tiêu chuẩn
    if gemini_models:
        gemini_models.sort(key=lambda x: (
            0 if "2.5-flash" in x else (1 if "1.5-flash" in x else (2 if "2.0-flash" in x else 3))
        ))
    else:
        gemini_models = ["gemini-1.5-flash", "gemini-2.5-flash", "gemini-1.5-pro"]

    # 2. Thử từng Model Gemini
    last_error = ""
    for model_name in gemini_models:
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
                        return f"🤖 **[Phân tích bởi AI ({model_name})]**\n\n{full_text}"
            else:
                res_err = resp.json().get("error", {})
                err_msg = res_err.get("message", resp.text)
                if "invalid authentication credentials" in err_msg.lower():
                    raise Exception("🔑 **API Key không hợp lệ hoặc đã hết hạn!**\nVui lòng tạo API Key mới tại [Google AI Studio](https://aistudio.google.com/app/apikey) và dán lại ở ô Cài đặt bên trái.")
                last_error = f"[{model_name}]: {err_msg}"
        except Exception as e:
