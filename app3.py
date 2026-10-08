import streamlit as st
import pandas as pd
import json
import os
import re
import io
import requests
import hashlib
import plotly.express as px
from pathlib import Path

# ── Cấu hình trang ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Kho Hàng - Quản Lý & Phân Tích",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS Tùy chỉnh ────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main .block-container { padding-top: 1.5rem; max-width: 1100px; }
    .stChatMessage { border-radius: 12px; }
    .login-box {
        max-width: 420px;
        margin: 50px auto;
        padding: 30px;
        background-color: #ffffff;
        border-radius: 15px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border: 1px solid #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)

# ── Đường dẫn lưu trữ dữ liệu bền vững ─────────────────────────────────────────
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
EXCEL_PATH  = DATA_DIR / "warehouse.xlsx"
CONFIG_PATH = DATA_DIR / "config.json"
CHAT_PATH   = DATA_DIR / "chat_history.json"
USERS_PATH  = DATA_DIR / "users.json"

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 0 — XỬ LÝ ĐĂNG NHẬP VÀ MÃ HÓA TÀI KHOẢN
# ════════════════════════════════════════════════════════════════════════════
def hash_password(password: str) -> str:
    """Mã hóa mật khẩu bằng SHA-256 để bảo mật"""
    return hashlib.sha256(password.encode()).hexdigest()

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

# Khởi tạo tài khoản mặc định nếu chưa có file users.json
def init_users_data():
    users = load_json_data(USERS_PATH, {})
    if not users:
        # Tạo tài khoản Admin mặc định: admin / admin123
        users = {
            "admin": {
                "password": hash_password("admin123"),
                "role": "admin",
                "fullname": "Quản trị viên"
            }
        }
        save_json_data(USERS_PATH, users)
    return users

# Khởi tạo trạng thái Session State
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = ""

# ── MÀN HÌNH ĐĂNG NHẬP ────────────────────────────────────────────────────────
def render_login_screen():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>🔐 ĐĂNG NHẬP HỆ THỐNG</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Hệ thống Quản lý Kho hàng AI nội bộ</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            username_input = st.text_input("👤 Tên tài khoản").strip()
            password_input = st.text_input("🔑 Mật khẩu", type="password").strip()
            submit_btn = st.form_submit_button("Đăng Nhập", type="primary", use_container_width=True)
            
            if submit_btn:
                users = init_users_data()
                if username_input in users:
                    hashed_pwd = hash_password(password_input)
                    if users[username_input]["password"] == hashed_pwd:
                        st.session_state.logged_in = True
                        st.session_state.username = username_input
                        st.session_state.user_role = users[username_input].get("role", "user")
                        st.success("✅ Đăng nhập thành công!")
                        st.rerun()
                    else:
                        st.error("❌ Sai mật khẩu!")
                else:
                    st.error("❌ Tài khoản không tồn tại!")

if not st.session_state.logged_in:
    render_login_screen()
    st.stop()  # Dừng chương trình tại đây nếu chưa đăng nhập

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 1 — TẢI CẤU HÌNH VÀ BỘ NHẬN DIỆN Ý ĐỊNH (0 TOKEN)
# ════════════════════════════════════════════════════════════════════════════
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

def auto_route_and_process(question: str, sheets_dict: dict):
    q_low = question.lower().strip()

    # Nhóm câu hỏi bắt buộc gửi cho AI phân tích sâu hoặc vẽ biểu đồ
    if any(k in q_low for k in ["biểu đồ", "vẽ biểu đồ", "đồ thị", "vẽ đồ thị", "bảng", "lập bảng", "danh sách", "thống kê", "tại sao", "vì sao", "dự báo", "tư vấn", "lâu nhất", "tồn đọng", "nhiều nhất"]):
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
# PHẦN 2 — XỬ LÝ DỮ LIỆU & GỌI AI GOOGLE
# ════════════════════════════════════════════════════════════════════════════
def extract_gsheet_id(url: str) -> str:
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

@st.cache_data(show_spinner=False, ttl=60)
def load_all_sheets_from_gsheet(url: str) -> dict:
    sheet_id = extract_gsheet_id(url)
    if not sheet_id:
        raise ValueError("Link không hợp lệ!")
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    resp = requests.get(export_url)
    if resp.status_code != 200:
        raise Exception("Lỗi tải trang tính")
    xl = pd.ExcelFile(io.BytesIO(resp.content))
    return {sheet: xl.parse(sheet) for sheet in xl.sheet_names}

@st.cache_data(show_spinner=False)
def load_all_sheets_from_file(path: str) -> dict:
    xl = pd.ExcelFile(path)
    return {sheet: xl.parse(sheet) for sheet in xl.sheet_names}

def ask_ai(question: str, sheets_dict: dict) -> str:
    api_key = st.session_state.get("api_key", "").strip()
    if not api_key:
        raise Exception("🔑 Chưa nhập API Key! Vui lòng dán API Key vào menu Cài đặt ở góc trái.")
    
    prompt_data = []
    for name, df in sheets_dict.items():
        df_clean = df.dropna(how="all")
        if not df_clean.empty:
            prompt_data.append("=== TAB [" + str(name) + "] ===\n" + df_clean.head(50).to_string(index=False))
            
    context = "\n\n".join(prompt_data)
    
    system_text = (
        "Bạn là chuyên gia phân tích kho hàng. Dưới đây là dữ liệu kho hàng hiện tại (tối đa 50 dòng):\n\n"
        + context + "\n\n"
        "QUY TẮC BẮT BUỘC KHI TRẢ LỜI:\n"
        "1. Trả lời HOÀN CHỈNH, ĐẦY ĐỦ từ đầu đến cuối.\n"
        "2. Trình bày rõ ràng dưới dạng BẢNG MARKDOWN nếu có danh sách/số lượng:\n"
        "| STT | Mã VT | Tên Vật Tư | Số Lượng | Ghi Chú |\n"
        "| --- | --- | --- | --- | --- |\n"
        "3. Trả lời trực tiếp vào trọng tâm câu hỏi.\n"
        "4. NẾU NGƯỜI DÙNG YÊU CẦU VẼ BIỂU ĐỒ: Viết mã Python vẽ biểu đồ bằng `plotly.express` (gán kết quả vào biến `fig`). Đặt mã trong khối ```python ... ```."
    )

    body = {
        "contents": [{"role": "user", "parts": [{"text": system_text + "\n\nCÂU HỎI CỦA NGƯỜI DÙNG: " + question}]}],
        "generationConfig": {
            "maxOutputTokens": 8192,
            "temperature": 0.2
        }
    }

    # TỰ ĐỘNG CẬP NHẬT danh sách model
    candidate_models = []
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        l_resp = requests.get(list_url, timeout=10)
        if l_resp.status_code == 200:
            m_list = l_resp.json().get("models", [])
            for m in m_list:
                m_name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods and m_name.startswith("gemini-"):
                    candidate_models.append(m_name)
    except Exception:
        pass

    if not candidate_models:
        candidate_models = ["gemini-1.5-flash-latest", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro-latest"]

    last_error = ""
    for model_name in candidate_models:
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
                if "invalid authentication credentials" in err_msg.lower() or "api key not valid" in err_msg.lower():
                    raise Exception("🔑 **API Key không hợp lệ hoặc đã hết hạn!**\nVui lòng kiểm tra lại API Key.")
                last_error = f"[{model_name}]: {err_msg}"
        except Exception as e:
            if "API Key" in str(e):
                raise e
            last_error = f"[{model_name}]: {str(e)}"

    raise Exception(f"Lỗi kết nối AI. Chi tiết: {last_error}")

# HÀM HIỂN THỊ: ẨN HOÀN TOÀN CODE PYTHON VÀ CHỈ VẼ BIỂU ĐỒ
def render_message_and_chart(content: str, sheets_dict: dict):
    code_pattern = r"```(?:python|py)?\s*(.*?)\s*```"
    code_matches = re.findall(code_pattern, content, re.DOTALL)
    clean_text = re.sub(code_pattern, "", content, flags=re.DOTALL).strip()
    
    if clean_text:
        st.markdown(clean_text)
        
    if code_matches:
        for code_block in code_matches:
            if any(kw in code_block for kw in ["plotly", "px", "fig"]):
                try:
                    local_vars = {"sheets_dict": sheets_dict, "pd": pd, "px": px}
                    exec(code_block, globals(), local_vars)
                    if "fig" in local_vars:
                        st.plotly_chart(local_vars["fig"], use_container_width=True)
                except Exception:
                    pass

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 3 — GIAO DIỆN CHÍNH & SIDEBAR QUẢN TRỊ
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # Thông tin tài khoản đăng nhập
    st.markdown(f"👤 Xin chào: **{st.session_state.username}** (`{st.session_state.user_role.upper()}`)")
    if st.button("🚪 Đăng xuất", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.user_role = ""
        st.rerun()

    st.divider()

    # TÍNH NĂNG CHỈ DÀNH CHO ADMIN: CẤP TÀI KHOẢN MỚI
    if st.session_state.user_role == "admin":
        with st.expander("➕ Cấp tài khoản mới"):
            new_user = st.text_input("Tên đăng nhập mới").strip()
            new_pass = st.text_input("Mật khẩu mới", type="password").strip()
            new_role = st.selectbox("Quyền", ["user", "admin"])
            
            if st.button("Tạo tài khoản"):
                if new_user and new_pass:
                    users_data = load_json_data(USERS_PATH, {})
                    if new_user in users_data:
                        st.error("Tài khoản đã tồn tại!")
                    else:
                        users_data[new_user] = {
                            "password": hash_password(new_pass),
                            "role": new_role,
                            "fullname": new_user
                        }
                        save_json_data(USERS_PATH, users_data)
                        st.success(f"✅ Đã tạo tài khoản `{new_user}` thành công!")
                else:
                    st.warning("Vui lòng điền đầy đủ thông tin!")
        st.divider()

    st.markdown("## ⚙️ Cài đặt")
    
    api_key_input = st.text_input("🔑 API Key (Gemini)", type="password", value=st.session_state.api_key)
    if api_key_input != st.session_state.api_key:
        st.session_state.api_key = api_key_input
        saved_config["api_key"] = api_key_input
        save_json_data(CONFIG_PATH, saved_config)

    st.divider()
    st.markdown("### 📂 Nguồn dữ liệu kho")
    
    data_source_idx = 0 if st.session_state.data_source == "🌐 Link Google Trang tính" else 1
    data_source = st.radio("Hình thức:", ["🌐 Link Google Trang tính", "📁 Tải file Excel lên"], index=data_source_idx)
    if data_source != st.session_state.data_source:
        st.session_state.data_source = data_source
        saved_config["data_source"] = data_source
        save_json_data(CONFIG_PATH, saved_config)

    sheets_data = None
    if data_source == "🌐 Link Google Trang tính":
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
    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state.messages = []
        save_json_data(CHAT_PATH, [])
        st.rerun()

# ── GIAO DIỆN BẢNG ĐIỀU KHIỂN CHÍNH ─────────────────────────────────────────
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
            if msg["role"] == "assistant":
                render_message_and_chart(msg["content"], sheets_data)
            else:
                st.markdown(msg["content"])

    question = st.text_area("Gõ câu hỏi bất kỳ...", height=90, placeholder="VD: Vẽ biểu đồ biến động tài chính theo ngày?")

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
                        final_ans = f"❌ {str(e)}"

                with st.chat_message("assistant"):
                    render_message_and_chart(final_ans, sheets_data)
                
                st.session_state.messages.append({"role": "assistant", "content": final_ans})
                save_json_data(CHAT_PATH, st.session_state.messages)
