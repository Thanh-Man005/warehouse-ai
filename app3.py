import streamlit as st
import pandas as pd
import json
import os
import re
import io
import hashlib
import requests
from pathlib import Path
from cryptography.fernet import Fernet

# ── Cấu hình trang ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Kho Hàng - Đọc Toàn Bộ File",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS tùy chỉnh ────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main .block-container { padding-top: 1.5rem; max-width: 1100px; }
    .stChatMessage { border-radius: 12px; }
    .secure-badge {
        background: #D1FAE5; color: #065F46;
        padding: 3px 10px; border-radius: 20px;
        font-size: 12px; font-weight: 600;
    }
    .warning-badge {
        background: #FEE2E2; color: #991B1B;
        padding: 3px 10px; border-radius: 20px;
        font-size: 12px; font-weight: 600;
    }
    div[data-testid="stExpander"] { border: 1px solid #E5E7EB; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Đường dẫn lưu file ───────────────────────────────────────────────────────
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
EXCEL_PATH = DATA_DIR / "warehouse.xlsx"
KEY_PATH   = DATA_DIR / ".secret.key"

DEFAULT_SENSITIVE = ["nha_cung_cap", "supplier", "ton_kho", "quantity",
                     "gia_nhap", "cost", "gia_von", "so_luong", "phone",
                     "email", "dien_thoai", "loi_nhuan", "profit", "thanh_tien"]

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 1 — Quản lý khóa mã hóa
# ════════════════════════════════════════════════════════════════════════════
def load_or_create_key() -> Fernet:
    if KEY_PATH.exists():
        key = KEY_PATH.read_bytes()
    else:
        key = Fernet.generate_key()
        KEY_PATH.write_bytes(key)
    return Fernet(key)

fernet = load_or_create_key()

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 2 — Mã hóa & Giải mã toàn bộ các Sheet
# ════════════════════════════════════════════════════════════════════════════
def is_sensitive(field_name: str, sensitive_fields: list) -> bool:
    fl = str(field_name).lower().replace(" ", "_")
    return any(s in fl for s in sensitive_fields)

def tokenize_all_sheets(sheets_dict: dict[str, pd.DataFrame], sensitive_fields: list):
    """Mã hóa tất cả các sheet, trả về (dict_sheets_masked, vault_tong)."""
    vault = {}
    masked_sheets = {}
    counter = [0]

    for sheet_name, df in sheets_dict.items():
        df_masked = df.copy()
        for col in df_masked.columns:
            if is_sensitive(col, sensitive_fields):
                def make_token(val, col_name=col):
                    if pd.isna(val) or str(val).strip() == "":
                        return val
                    prefix = re.sub(r'[^A-Za-z]', '', str(col_name))[:3].upper() or "FLD"
                    counter[0] += 1
                    tok = f"[{prefix}_{counter[0]:03d}]"
                    vault[tok] = fernet.encrypt(str(val).encode()).decode()
                    return tok
                df_masked[col] = df_masked[col].apply(make_token)
        masked_sheets[sheet_name] = df_masked

    return masked_sheets, vault

def detokenize(text: str, vault: dict) -> str:
    for tok, encrypted in vault.items():
        if tok in text:
            real = fernet.decrypt(encrypted.encode()).decode()
            text = text.replace(tok, f"**{real}**")
    return text

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 3 — Đọc toàn bộ các Tab từ Google Sheets / Excel
# ════════════════════════════════════════════════════════════════════════════
def extract_gsheet_id(url: str) -> str:
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

@st.cache_data(show_spinner=False, ttl=60)
def load_all_sheets_from_gsheet(url: str) -> dict[str, pd.DataFrame]:
    sheet_id = extract_gsheet_id(url)
    if not sheet_id:
        raise ValueError("Link Google Sheet không hợp lệ!")
    # Tải dưới dạng file Excel .xlsx để lấy ĐỦ TẤT CẢ CÁC TAB
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    resp = requests.get(export_url)
    if resp.status_code != 200:
        raise Exception("Không thể tải Google Sheet. Vui lòng kiểm tra quyền Chia sẻ!")
    
    xl = pd.ExcelFile(io.BytesIO(resp.content))
    return {sheet: xl.parse(sheet) for sheet in xl.sheet_names}

@st.cache_data(show_spinner=False)
def load_all_sheets_from_file(path: str) -> dict[str, pd.DataFrame]:
    xl = pd.ExcelFile(path)
    return {sheet: xl.parse(sheet) for sheet in xl.sheet_names}

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 4 — Ghép dữ liệu toàn bộ các Sheet gửi AI
# ════════════════════════════════════════════════════════════════════════════
def build_system_prompt(sheets_dict: dict[str, pd.DataFrame]) -> str:
    prompt_data = []
    for sheet_name, df in sheets_dict.items():
        # Lấy tối đa 30 dòng dữ liệu mỗi sheet để tối ưu tốc độ & token
        sample = df.dropna(how="all").head(30).to_string(index=False)
        prompt_data.append(f"=== TAB/SHEET: [{sheet_name}] ===\nCác cột: {list(df.columns)}\nDữ liệu mẫu:\n{sample}\n")
    
    full_context = "\n".join(prompt_data)
    
    return f"""Bạn là chuyên gia phân tích kho hàng thông minh. Bạn có quyền truy cập TOÀN BỘ CÁC TAB/SHEET trong trang tính.

DỮ LIỆU TẤT CẢ CÁC TAB TRONG KHO:
{full_context}

HƯỚNG DẪN TRẢ LỜI:
1. Bạn có thể tự do liên kết thông tin giữa các Tab (ví dụ: đối chiếu tab 'Tong hop' với tab 'Nhap'/'Xuat').
2. Trả lời bằng tiếng Việt ngắn gọn, rõ ràng, đưa ra con số cụ thể.
3. Các mã dạng [XXX_001] là dữ liệu nhạy cảm đã mã hóa, hãy giữ nguyên token này trong suy luận.
4. Nếu phát hiện bất thường (ví dụ: lệch tồn kho, hàng xuất nhiều nhưng kho sắp hết), hãy chủ động cảnh báo."""

def ask_ai(question: str, system: str, history: list) -> str:
    provider = st.session_state.get("ai_provider", "Gemini")
    api_key  = st.session_state.get("api_key", "")

    if provider == "Gemini":
        contents = []
        for m in history:
            contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]})
        contents.append({"role": "user", "parts": [{"text": f"{system}\n\nCÂU HỎI CỦA NGUỜI DÙNG: {question}"}]})
        body = {"contents": contents, "generationConfig": {"maxOutputTokens": 2000}}
        gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        resp = requests.post(gemini_url, params={"key": api_key}, json=body)
        if resp.status_code != 200:
            raise Exception(f"Gemini lỗi {resp.status_code}: {resp.text[:300]}")
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    elif provider == "Claude (Anthropic)":
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        messages = history + [{"role": "user", "content": question}]
        body = {"model": "claude-sonnet-4-20250514", "max_tokens": 2000, "system": system, "messages": messages}
        resp = requests.post(url, headers=headers, json=body)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    elif provider == "OpenAI (ChatGPT)":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": question}]
        body = {"model": "gpt-4o-mini", "max_tokens": 2000, "messages": messages}
        resp = requests.post(url, headers=headers, json=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 5 — SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ Cài đặt")

    provider = st.selectbox(
        "🤖 Chọn AI",
        ["Gemini", "Claude (Anthropic)", "OpenAI (ChatGPT)"],
        index=0
    )
    st.session_state.ai_provider = provider

    api_key_input = st.text_input("🔑 API Key", type="password", value=st.session_state.get("api_key", ""))
    if api_key_input:
        st.session_state.api_key = api_key_input

    st.divider()

    st.markdown("### 📂 Nguồn dữ liệu kho")
    data_source = st.radio("Hình thức:", ["🌐 Link Google Trang tính", "📁 Tải file Excel lên"])

    sheets_data = None

    if data_source == "🌐 Link Google Trang tính":
        gsheet_url = st.text_input("Dán link Google Sheet:", value=st.session_state.get("gsheet_url", ""))
        if gsheet_url:
            st.session_state.gsheet_url = gsheet_url
            try:
                sheets_data = load_all_sheets_from_gsheet(gsheet_url)
                st.success(f"✅ Đã đọc thành công **{len(sheets_data)} tab**!")
            except Exception as e:
                st.error("❌ Lỗi đọc file: Kiểm tra lại quyền 'Bất kỳ ai có link đều xem được'")
    else:
        uploaded = st.file_uploader("Tải file Excel (.xlsx)", type=["xlsx", "xls"])
        if uploaded:
            EXCEL_PATH.write_bytes(uploaded.read())
            st.cache_data.clear()
            sheets_data = load_all_sheets_from_file(str(EXCEL_PATH))
        elif EXCEL_PATH.exists():
            sheets_data = load_all_sheets_from_file(str(EXCEL_PATH))

    st.divider()
    security_on = st.toggle("Bật mã hóa bảo mật", value=True)
    sensitive_input = st.text_area("Cột nhạy cảm:", value="\n".join(DEFAULT_SENSITIVE), height=100)
    sensitive_fields = [s.strip() for s in sensitive_input.split("\n") if s.strip()]

    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.vault = {}
        st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 6 — GIAO DIỆN CHÍNH
# ════════════════════════════════════════════════════════════════════════════
st.markdown("# 🏭 AI Quản Lý Toàn Bộ File Kho Hàng")

if not sheets_data:
    st.info("👈 Vui lòng dán **Link Google Trang tính** hoặc tải file Excel ở cột Cài đặt để bắt đầu.")
    st.stop()

if not st.session_state.get("api_key"):
    st.warning("👈 Vui lòng nhập API Key ở sidebar bên trái.")
    st.stop()

# Hiển thị các Tab hiện có
sheet_names = list(sheets_data.keys())
cols = st.columns(min(len(sheet_names), 5))
for i, name in enumerate(sheet_names[:5]):
    with cols[i]:
        st.metric(f"Tab {i+1}", name, delta=f"{len(sheets_data[name])} dòng")

st.divider()

tab_data, tab_chat = st.tabs(["📊 Xem các Tab dữ liệu", "💬 Hỏi AI (Đọc toàn bộ File)"])

with tab_data:
    selected_tab_view = st.selectbox("🔍 Chọn Tab muốn xem:", sheet_names)
    st.dataframe(sheets_data[selected_tab_view], use_container_width=True, height=400)

with tab_chat:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    st.info(f"💡 AI đang sẵn sàng phân tích **đầy đủ {len(sheet_names)} Tab**: `{', '.join(sheet_names)}`")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.text_area("Nhập câu hỏi (AI sẽ tổng hợp từ tất cả các Tab):", height=90, placeholder="VD: Hãy đối chiếu dữ liệu tồn kho ở tab Tong hop và lịch sử nhập ở tab Nhap...")

    if st.button("🚀 Gửi câu hỏi cho AI", type="primary"):
        if question:
            with st.chat_message("user"):
                st.markdown(question)
            st.session_state.messages.append({"role": "user", "content": question})

            with st.spinner("🔄 AI đang đọc toàn bộ file và tổng hợp câu trả lời..."):
                if security_on:
                    masked_sheets, vault = tokenize_all_sheets(sheets_data, sensitive_fields)
                else:
                    masked_sheets = sheets_data
                    vault = {}

                system = build_system_prompt(masked_sheets)
                history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]

                try:
                    ai_response = ask_ai(question, system, history)
                    final_response = detokenize(ai_response, vault) if security_on else ai_response

                    with st.chat_message("assistant"):
                        st.markdown(final_response)

                    st.session_state.messages.append({"role": "assistant", "content": final_response})
                except Exception as e:
                    st.error(f"❌ Lỗi: {str(e)}")
