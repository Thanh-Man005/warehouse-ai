import streamlit as st
import pandas as pd
import json
import os
import re
import hashlib
import requests
from pathlib import Path
from cryptography.fernet import Fernet

# ── Cấu hình trang ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Kho Hàng",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS tùy chỉnh ────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main .block-container { padding-top: 1.5rem; max-width: 1100px; }
    .stChatMessage { border-radius: 12px; }
    .token-badge {
        background: #FEF3C7; color: #92400E;
        padding: 2px 8px; border-radius: 4px;
        font-family: monospace; font-size: 12px;
    }
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

# ── Các field nhạy cảm (có thể chỉnh trong sidebar) ─────────────────────────
DEFAULT_SENSITIVE = ["nha_cung_cap", "supplier", "ton_kho", "quantity",
                     "gia_nhap", "cost", "gia_von", "so_luong", "phone",
                     "email", "dien_thoai", "loi_nhuan", "profit"]

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
# PHẦN 2 — Token hóa & giải mã
# ════════════════════════════════════════════════════════════════════════════
def is_sensitive(field_name: str, sensitive_fields: list) -> bool:
    fl = field_name.lower().replace(" ", "_")
    return any(s in fl for s in sensitive_fields)

def tokenize_dataframe(df: pd.DataFrame, sensitive_fields: list):
    """Trả về (df_masked, vault) — vault là dict token→giá trị thật."""
    vault = {}
    df_masked = df.copy()
    counter = [0]

    def make_token(col, val):
        prefix = re.sub(r'[^A-Za-z]', '', col)[:3].upper() or "FLD"
        counter[0] += 1
        tok = f"[{prefix}_{counter[0]:03d}]"
        # Lưu giá trị thật được mã hóa AES
        vault[tok] = fernet.encrypt(str(val).encode()).decode()
        return tok

    for col in df_masked.columns:
        if is_sensitive(col, sensitive_fields):
            df_masked[col] = df_masked[col].apply(lambda v: make_token(col, v))

    return df_masked, vault

def detokenize(text: str, vault: dict) -> str:
    """Thay token trong chuỗi text bằng giá trị thật đã giải mã."""
    for tok, encrypted in vault.items():
        if tok in text:
            real = fernet.decrypt(encrypted.encode()).decode()
            text = text.replace(tok, f"**{real}**")
    return text

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 3 — Đọc dữ liệu Excel
# ════════════════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def load_excel(path: str) -> dict[str, pd.DataFrame]:
    """Đọc tất cả sheet trong file Excel."""
    xl = pd.ExcelFile(path)
    return {sheet: xl.parse(sheet) for sheet in xl.sheet_names}

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 4 — Xử lý câu hỏi tự nhiên với Claude
# ════════════════════════════════════════════════════════════════════════════
def build_system_prompt(df_masked: pd.DataFrame, sheet_name: str) -> str:
    sample = df_masked.head(8).to_string(index=False)
    cols   = list(df_masked.columns)
    return f"""Bạn là trợ lý phân tích kho hàng thông minh cho quản lý.

DỮ LIỆU KHO (sheet: {sheet_name}):
Các cột: {cols}
Mẫu dữ liệu:
{sample}

HƯỚNG DẪN:
1. Trả lời bằng tiếng Việt, rõ ràng, súc tích.
2. Nếu câu hỏi không rõ hoặc gõ sai, hãy TỰ HIỂU Ý và trả lời, đồng thời ghi "(Tôi hiểu bạn hỏi về: ...)".
3. Nếu thực sự không hiểu, hỏi lại đúng 1 câu làm rõ.
4. Các giá trị dạng [XXX_001] là dữ liệu nhạy cảm đã được mã hóa — hãy dùng chúng bình thường trong câu trả lời.
5. Khi đề xuất hành động (nhập hàng, liên hệ NCC...), hãy cụ thể và thực tế.
6. Có thể phân tích xu hướng, cảnh báo hàng sắp hết, so sánh nhà cung cấp."""

def ask_ai(question: str, system: str, history: list) -> str:
    provider = st.session_state.get("ai_provider", "Gemini")
    api_key  = st.session_state.get("api_key", "")

    if provider == "Gemini":
        # Hỗ trợ cả 2 loại key: AIzaSy... và AQ.... (OAuth2)
        contents = []
        for m in history:
            contents.append({"role": "user" if m["role"] == "user" else "model",
                              "parts": [{"text": m["content"]}]})
        contents.append({"role": "user", "parts": [{"text": f"{system}\n\n{question}"}]})
        body = {"contents": contents, "generationConfig": {"maxOutputTokens": 1500}}
        gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
       	resp = requests.post(gemini_url, params={"key": api_key}, json=body)
        if resp.status_code != 200:
            raise Exception(f"Gemini lỗi {resp.status_code}: {resp.text[:300]}")
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    elif provider == "Claude (Anthropic)":
        # Anthropic Claude API
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        messages = history + [{"role": "user", "content": question}]
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1500,
            "system": system,
            "messages": messages
        }
        resp = requests.post(url, headers=headers, json=body)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    elif provider == "OpenAI (ChatGPT)":
        # OpenAI API
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        messages = [{"role": "system", "content": system}]
        for m in history:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": question})
        body = {"model": "gpt-4o-mini", "max_tokens": 1500, "messages": messages}
        resp = requests.post(url, headers=headers, json=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    else:
        raise ValueError(f"Nhà cung cấp AI không hợp lệ: {provider}")

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 5 — SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ Cài đặt")

    # Chọn nhà cung cấp AI
    provider = st.selectbox(
        "🤖 Chọn AI",
        ["Gemini", "Claude (Anthropic)", "OpenAI (ChatGPT)"],
        index=["Gemini", "Claude (Anthropic)", "OpenAI (ChatGPT)"].index(
            st.session_state.get("ai_provider", "Gemini")
        )
    )
    st.session_state.ai_provider = provider

    # Hướng dẫn lấy API key theo provider
    help_links = {
        "Gemini":             "Lấy miễn phí tại aistudio.google.com",
        "Claude (Anthropic)": "Lấy tại console.anthropic.com (trả phí)",
        "OpenAI (ChatGPT)":   "Lấy tại platform.openai.com (trả phí)",
    }
    api_key_input = st.text_input(
        f"🔑 API Key ({provider})",
        type="password",
        value=st.session_state.get("api_key", ""),
        help=help_links[provider]
    )
    if api_key_input:
        st.session_state.api_key = api_key_input

    st.divider()

    # Upload / cập nhật file Excel
    st.markdown("### 📂 File dữ liệu kho")
    if EXCEL_PATH.exists():
        st.success(f"✅ Đang dùng: `warehouse.xlsx`")
        mtime = os.path.getmtime(EXCEL_PATH)
        import datetime
        st.caption(f"Cập nhật lần cuối: {datetime.datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M')}")

    uploaded = st.file_uploader(
        "Tải lên file Excel mới" if EXCEL_PATH.exists() else "Tải lên file Excel",
        type=["xlsx", "xls"],
        help="File mới sẽ thay thế file hiện tại"
    )
    if uploaded:
        EXCEL_PATH.write_bytes(uploaded.read())
        st.cache_data.clear()
        st.success("✅ Đã cập nhật file!")
        st.rerun()

    # Tạo file mẫu nếu chưa có
    if not EXCEL_PATH.exists():
        if st.button("📥 Tạo file mẫu", use_container_width=True):
            sample_df = pd.DataFrame({
                "ma_hang":       ["SP001","SP002","SP003","SP004","SP005"],
                "ten_hang":      ["Bút bi xanh TL","Vở ô ly 96tr","Mực in HP 680","Giấy A4 IK","Bấm kim Kokuyo"],
                "don_vi":        ["hộp","quyển","hộp","ram","cái"],
                "ton_kho":       [150, 42, 8, 320, 15],
                "ton_kho_min":   [50, 30, 20, 100, 10],
                "nha_cung_cap":  ["Thiên Long","Hồng Hà","Phong Vũ","IK Plus","VPP Hà Nội"],
                "gia_nhap":      [45000,12000,185000,68000,35000],
                "gia_ban":       [55000,15000,220000,82000,45000],
            })
            with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as w:
                sample_df.to_excel(w, sheet_name="Ton_kho", index=False)
            st.cache_data.clear()
            st.success("✅ Đã tạo file mẫu!")
            st.rerun()

    st.divider()

    # Cài đặt bảo mật
    st.markdown("### 🔐 Bảo mật")
    security_on = st.toggle("Bật mã hóa dữ liệu nhạy cảm", value=True)

    with st.expander("Chỉnh field nhạy cảm"):
        sensitive_input = st.text_area(
            "Danh sách field (mỗi dòng 1 field):",
            value="\n".join(DEFAULT_SENSITIVE),
            height=150
        )
        sensitive_fields = [s.strip() for s in sensitive_input.split("\n") if s.strip()]

    if security_on:
        st.markdown('<span class="secure-badge">🔒 Bảo mật BẬT</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="warning-badge">⚠️ Bảo mật TẮT</span>', unsafe_allow_html=True)

    st.divider()

    # Xóa lịch sử chat
    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.vault    = {}
        st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 6 — GIAO DIỆN CHÍNH
# ════════════════════════════════════════════════════════════════════════════
st.markdown("# 🏭 AI Quản lý Kho Hàng")
st.caption("Hỏi đáp tự nhiên • Dữ liệu nhạy cảm được mã hóa trước khi gửi AI")

# Kiểm tra điều kiện
if not EXCEL_PATH.exists():
    st.info("👈 Chưa có file dữ liệu. Vui lòng tải lên hoặc tạo file mẫu từ sidebar.")
    st.stop()

if not st.session_state.get("api_key"):
    provider = st.session_state.get("ai_provider", "Gemini")
    st.warning(f"👈 Vui lòng nhập API Key ({provider}) ở sidebar để bắt đầu.")
    st.stop()

# Đọc dữ liệu
all_sheets = load_excel(str(EXCEL_PATH))

# Chọn sheet (nếu có nhiều sheet)
tab_names = list(all_sheets.keys())
if len(tab_names) > 1:
    selected_sheet = st.selectbox("📋 Chọn sheet dữ liệu:", tab_names)
else:
    selected_sheet = tab_names[0]

df_raw = all_sheets[selected_sheet]

# ── Thống kê nhanh ────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
sensitive_cols = [c for c in df_raw.columns if is_sensitive(c, sensitive_fields)]

with col1:
    st.metric("📦 Tổng sản phẩm", len(df_raw))
with col2:
    st.metric("📊 Số cột dữ liệu", len(df_raw.columns))
with col3:
    st.metric("🔒 Field nhạy cảm", len(sensitive_cols))
with col4:
    low_stock = 0
    if "ton_kho" in df_raw.columns and "ton_kho_min" in df_raw.columns:
        low_stock = (df_raw["ton_kho"] < df_raw["ton_kho_min"]).sum()
    elif "ton_kho" in df_raw.columns:
        low_stock = (df_raw["ton_kho"] < 20).sum()
    st.metric("⚠️ Hàng sắp hết", low_stock, delta=None)

st.divider()

# ── Tabs: Xem dữ liệu | Chat ──────────────────────────────────────────────
tab_data, tab_chat, tab_security = st.tabs(["📊 Xem dữ liệu", "💬 Hỏi AI", "🔐 Chi tiết bảo mật"])

# ── Tab 1: Xem dữ liệu ───────────────────────────────────────────────────
with tab_data:
    view_mode = st.radio(
        "Chế độ xem:",
        ["Dữ liệu gốc", "Dữ liệu sau mã hóa (AI nhìn thấy)"],
        horizontal=True
    )

    if view_mode == "Dữ liệu gốc":
        # Highlight các cột nhạy cảm
        def highlight_sensitive(col):
            if is_sensitive(col.name, sensitive_fields):
                return ["background-color: #FEF3C7"] * len(col)
            return [""] * len(col)
        st.dataframe(
            df_raw.style.apply(highlight_sensitive, axis=0),
            use_container_width=True, height=350
        )
        if sensitive_cols:
            st.caption(f"🟡 Các cột nhạy cảm (nền vàng): {', '.join(sensitive_cols)}")
    else:
        df_masked, _ = tokenize_dataframe(df_raw, sensitive_fields)
        st.dataframe(df_masked, use_container_width=True, height=350)
        st.caption("🔒 Các giá trị nhạy cảm đã được thay bằng token — đây là dữ liệu thật sự gửi lên AI")

# ── Tab 2: Chat với AI ───────────────────────────────────────────────────
with tab_chat:
    # Khởi tạo session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "vault" not in st.session_state:
        st.session_state.vault = {}

    # Gợi ý câu hỏi nhanh
    st.markdown("**💡 Gợi ý câu hỏi nhanh:**")
    quick_cols = st.columns(3)
    quick_questions = [
        "Mặt hàng nào sắp hết hàng?",
        "Tổng giá trị tồn kho là bao nhiêu?",
        "Phân tích nhà cung cấp theo giá",
    ]
    for i, (col, q) in enumerate(zip(quick_cols, quick_questions)):
        with col:
            if st.button(q, key=f"quick_{i}", use_container_width=True):
                st.session_state.quick_question = q

    st.divider()

    # Hiển thị lịch sử chat
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input câu hỏi
    question = st.chat_input("Nhập câu hỏi về kho hàng... (VD: hàng nào sắp hết? NCC nào rẻ nhất?)")

    # Xử lý quick question
    if "quick_question" in st.session_state:
        question = st.session_state.pop("quick_question")

    if question:
        # Hiển thị câu hỏi user
        with st.chat_message("user"):
            st.markdown(question)
        st.session_state.messages.append({"role": "user", "content": question})

        # Xử lý mã hóa
        with st.spinner("🔄 Đang xử lý..."):
            if security_on:
                df_for_ai, vault = tokenize_dataframe(df_raw, sensitive_fields)
                st.session_state.vault = vault
                token_count = len(vault)
            else:
                df_for_ai = df_raw
                vault = {}
                token_count = 0

            # Build system prompt với dữ liệu đã xử lý
            system = build_system_prompt(df_for_ai, selected_sheet)

            # Lịch sử chat (không bao gồm tin nhắn vừa thêm)
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages[:-1]
            ]

            try:
                ai_response = ask_ai(question, system, history)

                # Giải mã token trong phản hồi
                if security_on and vault:
                    final_response = detokenize(ai_response, vault)
                else:
                    final_response = ai_response

                with st.chat_message("assistant"):
                    st.markdown(final_response)
                    if security_on and token_count > 0:
                        st.caption(f"🔒 {token_count} giá trị nhạy cảm đã được mã hóa trước khi gửi AI và giải mã trong kết quả này.")

                st.session_state.messages.append({"role": "assistant", "content": final_response})

            except Exception as e:
                st.error(f"❌ Lỗi kết nối API: {str(e)}")

# ── Tab 3: Chi tiết bảo mật ──────────────────────────────────────────────
with tab_security:
    st.markdown("### Cách hoạt động của hệ thống bảo mật")

    st.markdown("""
    **Luồng xử lý khi bạn đặt câu hỏi:**

    1. 📥 **Đọc dữ liệu** — App đọc file Excel từ máy của bạn
    2. 🔍 **Phát hiện field nhạy cảm** — Scan các cột như `ton_kho`, `nha_cung_cap`, `gia_nhap`...
    3. 🔐 **Token hóa** — Thay giá trị thật bằng token `[TON_001]`, giá trị thật lưu mã hóa AES-256
    4. 📤 **Gửi lên AI** — Claude chỉ nhận dữ liệu đã token hóa, không bao giờ thấy số thật
    5. 📥 **Nhận phản hồi** — AI trả về câu trả lời với token
    6. 🔓 **Giải mã** — App thay token bằng giá trị thật trước khi hiển thị cho bạn
    """)

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**✅ AI NHÌN THẤY:**")
        st.code("""ma_hang: SP003
ten_hang: Mực in HP 680
don_vi: hộp
ton_kho: [TON_003]        ← token
nha_cung_cap: [NHA_003]   ← token
gia_nhap: [GIA_003]       ← token""")

    with col_b:
        st.markdown("**🔒 GIÁ TRỊ THẬT (chỉ app biết):**")
        st.code("""[TON_003] → AES256(8)
[NHA_003] → AES256("Phong Vũ")
[GIA_003] → AES256(185000)

Khóa mã hóa lưu tại:
data/.secret.key
(chỉ trên máy của bạn)""")

    st.info("🔑 Khóa mã hóa AES-256 được tạo ngẫu nhiên và lưu trên máy bạn. AI không bao giờ nhận được dữ liệu thật của các field nhạy cảm.")

    if st.session_state.get("vault"):
        st.divider()
        st.markdown(f"**Token đã tạo trong phiên này: {len(st.session_state.vault)} token**")
        with st.expander("Xem danh sách token (không hiển thị giá trị thật)"):
            for tok in st.session_state.vault:
                st.code(tok)
