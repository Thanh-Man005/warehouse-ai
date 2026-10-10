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
from core.router import auto_route_and_process

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

# ── Kết nối Supabase (khóa chỉ được đọc từ Streamlit Secrets) ────────────────
def get_supabase_settings():
    try:
        url = str(st.secrets.get("SUPABASE_URL", "")).strip().rstrip("/")
        key = str(st.secrets.get("SUPABASE_KEY", "")).strip()
    except Exception:
        url, key = "", ""
    if not url or not key:
        raise RuntimeError(
            "Chưa cấu hình SUPABASE_URL và SUPABASE_KEY trong "
            "Streamlit Cloud → Settings → Secrets."
        )
    return url, key

def supabase_headers():
    _, key = get_supabase_settings()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def supabase_get_users():
    url, _ = get_supabase_settings()
    response = requests.get(
        f"{url}/rest/v1/app_users",
        headers=supabase_headers(),
        params={"select": "username,password_hash,role,fullname,created_at", "order": "created_at.asc"},
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError(f"Không đọc được danh sách tài khoản từ Supabase (HTTP {response.status_code}).")
    return response.json()

def supabase_insert_user(username, password_hash, role, fullname):
    url, _ = get_supabase_settings()
    response = requests.post(
        f"{url}/rest/v1/app_users",
        headers={**supabase_headers(), "Prefer": "return=representation"},
        json={
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "fullname": fullname or username,
        },
        timeout=15,
    )
    if not response.ok:
        if response.status_code == 409:
            raise ValueError("Tài khoản đã tồn tại!")
        raise RuntimeError(f"Không lưu được tài khoản vào Supabase (HTTP {response.status_code}).")
    return response.json()

def supabase_update_user(username, updates):
    """Cập nhật thông tin tài khoản theo username trong Supabase."""
    if not updates:
        raise ValueError("Chưa có thông tin nào cần cập nhật.")
    url, _ = get_supabase_settings()
    response = requests.patch(
        f"{url}/rest/v1/app_users",
        headers={**supabase_headers(), "Prefer": "return=representation"},
        params={"username": f"eq.{username}"},
        json=updates,
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError(f"Không cập nhật được tài khoản (HTTP {response.status_code}).")
    updated_rows = response.json()
    if not updated_rows:
        raise RuntimeError("Không tìm thấy tài khoản cần cập nhật.")
    return updated_rows[0]

# Chuyển tài khoản cũ sang Supabase nếu file users.json còn tồn tại.
# Nếu chưa có dữ liệu cũ và bảng trống, tạo tài khoản khởi tạo admin/admin123.
def init_users_data():
    rows = supabase_get_users()
    existing = {str(row.get("username", "")) for row in rows}
    legacy_users = load_json_data(USERS_PATH, {})

    if not rows and not legacy_users:
        legacy_users = {
            "admin": {
                "password": hash_password("admin123"),
                "role": "admin",
                "fullname": "Quản trị viên",
            }
        }

    for username, record in legacy_users.items():
        if username in existing:
            continue
        password_hash = record.get("password") or record.get("password_hash")
        if not password_hash:
            continue
        supabase_insert_user(
            username,
            password_hash,
            record.get("role", "user"),
            record.get("fullname", username),
        )
        existing.add(username)

    rows = supabase_get_users()
    return {
        row["username"]: {
            "password": row["password_hash"],
            "role": row.get("role", "user"),
            "fullname": row.get("fullname") or row["username"],
            "created_at": row.get("created_at", ""),
        }
        for row in rows
    }

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
                try:
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
                except Exception as e:
                    st.error(f"❌ Không thể kết nối cơ sở dữ liệu tài khoản: {e}")

if not st.session_state.logged_in:
    render_login_screen()
    st.stop()  # Dừng chương trình tại đây nếu chưa đăng nhập

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 1 — TẢI CẤU HÌNH VÀ BỘ NHẬN DIỆN Ý ĐỊNH (0 TOKEN)

# ════════════════════════════════════════════════════════════════════════════

saved_config = load_json_data(CONFIG_PATH, {
"data_source": "🌐 Link Google Trang tính",
"gsheet_url": ""
})


# Lấy Gemini API Key từ Streamlit Secrets, không nhập trực tiếp trong giao diện.
def get_gemini_api_key() -> str:
    try:
        return str(st.secrets.get("GEMINI_API_KEY", "")).strip()
    except Exception:
        return ""

# Xóa API Key cũ khỏi cấu hình nếu trước đây đã lưu trong config.json.
if "api_key" in saved_config:
    saved_config.pop("api_key", None)
    save_json_data(CONFIG_PATH, saved_config)

if "gsheet_url" not in st.session_state:
    st.session_state.gsheet_url = saved_config.get("gsheet_url", "")

if "data_source" not in st.session_state:
    st.session_state.data_source = saved_config.get(
        "data_source", "🌐 Link Google Trang tính"
    )

if "messages" not in st.session_state:
    st.session_state.messages = load_json_data(CHAT_PATH, [])


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


def ask_ai(question: str, sheets_dict: dict, chat_history=None) -> str:
    api_key = get_gemini_api_key()
    if not api_key:
        raise Exception(
            "🔑 Chưa cấu hình GEMINI_API_KEY trong "
            "Streamlit Cloud → Settings → Secrets."
        )
    
    prompt_data = []
    for name, df in sheets_dict.items():
        df_clean = df.dropna(how="all")
        if not df_clean.empty:
            prompt_data.append("=== TAB [" + str(name) + "] ===\n" + df_clean.head(50).to_string(index=False))
            
    context = "\n\n".join(prompt_data)
    
    # Chỉ gửi tối đa 10 tin nhắn gần nhất; giới hạn mỗi tin nhắn 2.000 ký tự.
    history_lines = []
    for msg in (chat_history or [])[-10:]:
        role = msg.get("role", "")
        if role not in ("user", "assistant"):
            continue
        text = str(msg.get("content", ""))[:2000]
        if text.strip():
            label = "Người dùng" if role == "user" else "Trợ lý"
            history_lines.append(f"{label}: {text}")
    history_text = "\\n".join(history_lines) if history_lines else "(Chưa có lịch sử hội thoại.)"

    system_text = (
        "Bạn là trợ lý phân tích kho hàng. Chỉ dùng dữ liệu được cung cấp; không suy đoán hoặc tự tạo số liệu.\n"
        "Trả lời ngắn gọn, trực tiếp, thường trong 1-3 câu.\n"
        "Nếu thiếu căn cứ, nói rõ: Chưa đủ dữ liệu để kết luận; nêu ngắn gọn dữ liệu còn thiếu.\n"
        "Nếu các nguồn hoặc dòng dữ liệu mâu thuẫn, chỉ ra giá trị và tab liên quan; không tự chọn một giá trị để kết luận.\n"
        "Phân biệt dữ liệu thiếu, giá trị 0 và giá trị không xác định. Không coi phần dữ liệu được cung cấp là toàn bộ nếu chưa chắc.\n"
        "Khi đủ dữ liệu, trả lời kết quả cùng căn cứ ngắn gọn. Chỉ dùng bảng khi người dùng yêu cầu hoặc cần thiết.\n"
        "Nếu được yêu cầu vẽ biểu đồ, dùng plotly.express và gán biểu đồ vào biến fig.\n"
        "Dùng lịch sử hội thoại để hiểu câu hỏi tiếp nối; không coi câu trả lời cũ của trợ lý là dữ liệu đã được xác minh. Dữ liệu kho hiện tại là căn cứ chính.\n\n"
        "LỊCH SỬ HỘI THOẠI GẦN ĐÂY (tối đa 10 tin nhắn, mỗi tin tối đa 2.000 ký tự):\n"
        + history_text + "\n\n"
        "DỮ LIỆU KHO HÀNG (tối đa 50 dòng mỗi tab):\n\n"
        + context
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

    # TÍNH NĂNG CHỈ DÀNH CHO ADMIN: CẤP TÀI KHOẢN + DANH SÁCH
    if st.session_state.user_role == "admin":
        with st.expander("➕ Cấp tài khoản mới"):
            new_user = st.text_input("Tên đăng nhập mới", key="new_user_supabase").strip()
            new_fullname = st.text_input("Họ tên", key="new_fullname_supabase").strip()
            new_pass = st.text_input("Mật khẩu mới", type="password", key="new_pass_supabase").strip()
            new_role = st.selectbox("Quyền", ["user", "admin"], key="new_role_supabase")

            if st.button("Tạo tài khoản", key="create_supabase_user"):
                if new_user and new_pass:
                    try:
                        users_data = init_users_data()
                        if new_user in users_data:
                            st.error("Tài khoản đã tồn tại!")
                        else:
                            supabase_insert_user(
                                new_user,
                                hash_password(new_pass),
                                new_role,
                                new_fullname or new_user,
                            )
                            st.success(f"Đã tạo tài khoản {new_user} thành công!")
                            st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Không thể tạo tài khoản: {e}")
                else:
                    st.warning("Vui lòng điền tên đăng nhập và mật khẩu!")

        with st.expander("📋 Danh sách tài khoản đã cấp", expanded=True):
            try:
                account_rows = supabase_get_users()
                if account_rows:
                    st.dataframe(
                        [
                            {
                                "Tên đăng nhập": row.get("username", ""),
                                "Họ tên": row.get("fullname") or row.get("username", ""),
                                "Quyền": row.get("role", "user"),
                                "Ngày tạo": row.get("created_at", ""),
                            }
                            for row in account_rows
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption(f"Tổng số tài khoản: {len(account_rows)}")
                else:
                    st.info("Chưa có tài khoản nào trong Supabase.")
            except Exception as e:
                st.error(f"Không tải được danh sách tài khoản: {e}")
        with st.expander("🛠️ Quản lý tài khoản", expanded=False):
            try:
                managed_users = supabase_get_users()
                if not managed_users:
                    st.info("Chưa có tài khoản để quản lý.")
                else:
                    user_options = [row.get("username", "") for row in managed_users]
                    selected_user = st.selectbox(
                        "Chọn tài khoản cần chỉnh sửa",
                        user_options,
                        key="manage_user_select",
                    )
                    selected_record = next(
                        (row for row in managed_users if row.get("username") == selected_user),
                        {},
                    )
                    with st.form("manage_account_form"):
                        edit_fullname = st.text_input(
                            "Họ tên",
                            value=selected_record.get("fullname") or selected_user,
                        ).strip()
                        edit_role = st.selectbox(
                            "Quyền tài khoản",
                            ["user", "admin"],
                            index=0 if selected_record.get("role", "user") == "user" else 1,
                        )
                        reset_password = st.text_input(
                            "Mật khẩu mới (để trống nếu không đổi)",
                            type="password",
                        ).strip()
                        save_account = st.form_submit_button(
                            "Lưu thay đổi", type="primary", use_container_width=True
                        )

                    if save_account:
                        current_role = selected_record.get("role", "user")
                        admin_count = sum(1 for row in managed_users if row.get("role") == "admin")
                        if selected_user == st.session_state.username and edit_role != "admin":
                            st.error("Không thể tự hạ quyền admin của tài khoản đang đăng nhập.")
                        elif current_role == "admin" and edit_role != "admin" and admin_count <= 1:
                            st.error("Không thể hạ quyền admin cuối cùng của hệ thống.")
                        elif reset_password and len(reset_password) < 6:
                            st.error("Mật khẩu mới phải có ít nhất 6 ký tự.")
                        else:
                            updates = {
                                "fullname": edit_fullname or selected_user,
                                "role": edit_role,
                            }
                            if reset_password:
                                updates["password_hash"] = hash_password(reset_password)
                            try:
                                supabase_update_user(selected_user, updates)
                                st.success(f"Đã cập nhật tài khoản {selected_user}.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Không thể cập nhật tài khoản: {e}")
            except Exception as e:
                st.error(f"Không tải được dữ liệu quản lý tài khoản: {e}")
        st.divider()


    st.markdown("## ⚙️ Cài đặt")

    if get_gemini_api_key():
        st.success("🔑 Gemini API Key đã được cấu hình.")
    else:
        st.warning("🔑 Chưa tìm thấy GEMINI_API_KEY trong Streamlit Secrets.")

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
                        final_ans = ask_ai(question, sheets_data, st.session_state.messages[:-1])
                    except Exception as e:
                        final_ans = f"❌ {str(e)}"

                with st.chat_message("assistant"):
                    render_message_and_chart(final_ans, sheets_data)
                
                st.session_state.messages.append({"role": "assistant", "content": final_ans})
                save_json_data(CHAT_PATH, st.session_state.messages)
