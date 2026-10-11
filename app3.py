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
    .main .block-container { padding-top: 1.25rem; max-width: 1320px; }
    .stChatMessage { border-radius: 12px; }
    div[data-testid="stMetric"] { background: #ffffff; border: 1px solid #e5edf6; border-radius: 14px; padding: 14px 16px; box-shadow: 0 3px 12px rgba(31, 75, 121, 0.055); }
    .warehouse-heading { display: flex; align-items: center; justify-content: space-between; margin: 0 0 1rem 0; padding: 0.15rem 0 0.4rem; }
    .warehouse-heading h2 { margin: 0.15rem 0 0.2rem; color: #12365c; font-size: 1.75rem; }
    .warehouse-heading p { margin: 0; color: #6b7d92; font-size: 0.95rem; }
    .warehouse-eyebrow { font-size: 0.68rem; letter-spacing: 0.12em; font-weight: 700; color: #3b82b8; }

    /* Ghim ô hỏi đáp theo đáy khung nhìn trình duyệt, không theo cuối lịch sử chat. */
    div[data-testid="stChatInput"] {
        position: fixed !important;
        bottom: 1rem !important;
        left: max(17rem, calc((100vw - 1100px) / 2 + 17rem)) !important;
        right: max(1rem, calc((100vw - 1100px) / 2 + 1rem)) !important;
        width: auto !important;
        z-index: 9999 !important;
        background: var(--background-color);
        padding-top: 0.35rem;
        padding-bottom: 0.35rem;
    }

    @media (max-width: 700px) {
        div[data-testid="stChatInput"] {
            left: 0.75rem !important;
            right: 0.75rem !important;
            bottom: 0.5rem !important;
        }
    }

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


def chat_path_for_user(username: str) -> Path:
    """Tệp hội thoại riêng cho từng tài khoản."""
    safe_username = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(username or "guest"))
    return DATA_DIR / f"chat_history_{safe_username}.json"

def normalize_chat_store(raw) -> dict:
    """Chuẩn hóa lịch sử mới và chuyển định dạng lịch sử cũ sang danh sách hội thoại."""
    if isinstance(raw, dict) and isinstance(raw.get("conversations"), list):
        conversations = raw["conversations"]
        active_id = raw.get("active_id")
    elif isinstance(raw, list) and raw:
        active_id = "legacy"
        first_question = next((str(m.get("content", "")) for m in raw if m.get("role") == "user"), "Cuộc trò chuyện cũ")
        conversations = [{
            "id": active_id,
            "title": first_question[:45] or "Cuộc trò chuyện cũ",
            "updated_at": "",
            "messages": raw,
        }]
    else:
        conversations, active_id = [], None

    if active_id not in [conv.get("id") for conv in conversations]:
        active_id = conversations[0].get("id") if conversations else None
    return {"active_id": active_id, "conversations": conversations}

def supabase_load_chat_store(username: str):
    """Đọc hội thoại từ Supabase; trả về None nếu tài khoản chưa có bản ghi."""
    url, _ = get_supabase_settings()
    response = requests.get(
        f"{url}/rest/v1/chat_history",
        headers=supabase_headers(),
        params={
            "select": "username,active_id,conversations,updated_at",
            "username": f"eq.{username}",
            "limit": "1",
        },
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError(f"Không đọc được lịch sử chat từ Supabase (HTTP {response.status_code}).")
    rows = response.json()
    if not rows:
        return None
    return normalize_chat_store({
        "active_id": rows[0].get("active_id"),
        "conversations": rows[0].get("conversations", []),
    })

def supabase_save_chat_store(username: str, store: dict):
    """Lưu toàn bộ danh sách hội thoại lên Supabase bằng upsert theo username."""
    url, _ = get_supabase_settings()
    response = requests.post(
        f"{url}/rest/v1/chat_history",
        headers={**supabase_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
        params={"on_conflict": "username"},
        json={
            "username": username,
            "active_id": store.get("active_id"),
            "conversations": store.get("conversations", []),
            "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Không lưu được lịch sử chat lên Supabase (HTTP {response.status_code}).")

def load_chat_store(username: str) -> dict:
    """Ưu tiên Supabase; nếu bảng chưa sẵn sàng thì dùng bản JSON dự phòng."""
    try:
        remote_store = supabase_load_chat_store(username)
        if remote_store is not None:
            st.session_state.chat_storage_warning = ""
            return remote_store

        # Nếu Supabase chưa có bản ghi, nhập lịch sử cục bộ cũ lên lần đầu.
        local_store = normalize_chat_store(load_json_data(chat_path_for_user(username), []))
        supabase_save_chat_store(username, local_store)
        st.session_state.chat_storage_warning = ""
        return local_store
    except Exception as exc:
        st.session_state.chat_storage_warning = (
            "Chưa lưu được lịch sử lâu dài trên Supabase. "
            "Ứng dụng tạm dùng tệp cục bộ; hãy tạo bảng chat_history theo hướng dẫn. "
            f"Chi tiết: {exc}"
        )
        return normalize_chat_store(load_json_data(chat_path_for_user(username), []))

def save_chat_history():
    """Đồng bộ tin nhắn hiện tại vào hội thoại đang mở và lưu lâu dài."""
    username = st.session_state.get("username", "")
    if not username:
        return
    conversations = st.session_state.get("conversations", [])
    active_id = st.session_state.get("active_conversation_id")
    for conv in conversations:
        if conv.get("id") == active_id:
            conv["messages"] = st.session_state.get("messages", [])
            if not conv.get("title") or conv.get("title") == "Cuộc trò chuyện mới":
                first_question = next((str(m.get("content", "")).strip() for m in conv["messages"] if m.get("role") == "user"), "")
                if first_question:
                    conv["title"] = first_question[:45] + ("…" if len(first_question) > 45 else "")
            conv["updated_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
            break
    store = {
        "active_id": active_id,
        "conversations": conversations,
    }
    # Luôn lưu bản dự phòng trước; sau đó đồng bộ Supabase.
    save_json_data(chat_path_for_user(username), store)
    try:
        supabase_save_chat_store(username, store)
        st.session_state.chat_storage_warning = ""
    except Exception as exc:
        st.session_state.chat_storage_warning = (
            "Lịch sử đang được lưu tạm trên máy chủ ứng dụng, chưa đồng bộ được Supabase. "
            f"Chi tiết: {exc}"
        )

def start_new_conversation():
    """Tạo một hội thoại trống và chuyển sang hội thoại đó."""
    import uuid
    conversation_id = uuid.uuid4().hex
    conversation = {
        "id": conversation_id,
        "title": "Cuộc trò chuyện mới",
        "updated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "messages": [],
    }
    st.session_state.conversations.insert(0, conversation)
    st.session_state.active_conversation_id = conversation_id
    st.session_state.messages = []
    st.session_state.chat_selector_id = conversation_id
    save_chat_history()

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

# Nạp kho hội thoại riêng cho tài khoản sau khi đăng nhập.
current_username = st.session_state.username
if st.session_state.get("chat_owner") != current_username:
    chat_store = load_chat_store(current_username)
    st.session_state.conversations = chat_store["conversations"]
    st.session_state.active_conversation_id = chat_store["active_id"]
    st.session_state.chat_owner = current_username
    active_conv = next((x for x in st.session_state.conversations if x.get("id") == st.session_state.active_conversation_id), None)
    st.session_state.messages = active_conv.get("messages", []) if active_conv else []
    st.session_state.chat_selector_id = st.session_state.active_conversation_id

# Luôn có một cuộc trò chuyện đang mở, nhưng chưa cần lưu cho đến khi có nội dung.
if not st.session_state.get("active_conversation_id"):
    start_new_conversation()

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


def load_all_sheets_from_uploaded_files(uploaded_files) -> tuple:
    """Đọc mọi sheet từ nhiều file Excel; giữ tên file trong khóa để không trùng sheet."""
    combined = {}
    errors = []
    for file_index, uploaded in enumerate(uploaded_files, start=1):
        filename = Path(str(uploaded.name)).name
        try:
            workbook = pd.ExcelFile(io.BytesIO(uploaded.getvalue()))
            for sheet_name in workbook.sheet_names:
                key = f"{filename} · {sheet_name}"
                if key in combined:
                    key = f"{filename} ({file_index}) · {sheet_name}"
                combined[key] = workbook.parse(sheet_name)
        except Exception as exc:
            errors.append(f"{filename}: {exc}")
    if not combined:
        details = "; ".join(errors) if errors else "Không tìm thấy sheet dữ liệu trong file."
        raise ValueError(details)
    return combined, errors


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

    # Đưa các lượt hội thoại gần nhất vào prompt để câu hỏi nối tiếp có ngữ cảnh.
    history_lines = []
    for item in (chat_history or [])[-16:]:
        role = "Người dùng" if item.get("role") == "user" else "Trợ lý"
        text_value = str(item.get("content", "")).strip()
        if text_value:
            history_lines.append(f"{role}: {text_value[:3500]}")
    history_context = "\n".join(history_lines)

    system_text = (
        "Bạn là chuyên gia phân tích kho hàng. Dữ liệu kho hàng bên dưới chỉ là dữ liệu hiện tại; "
        "lịch sử hội thoại được cung cấp để hiểu câu hỏi nối tiếp.\n\n"
        + context + "\n\n"
        "LỊCH SỬ HỘI THOẠI GẦN ĐÂY:\n" + (history_context or "(Chưa có lịch sử)") + "\n\n"
        "QUY TẮC BẮT BUỘC KHI TRẢ LỜI:\\n"
        "0. Với câu hỏi nối tiếp như 'các sản phẩm trên', chỉ xét đúng các sản phẩm trong câu trả lời trước liên quan; không mở rộng sang toàn bộ kho. Nếu thiếu dữ liệu, nói rõ, không đoán.\\n"
        "1. Ưu tiên câu trả lời NGẮN GỌN, trực tiếp: nêu kết quả chính ngay đầu; thường chỉ 1-3 câu, chỉ thêm bảng khi giúp đọc số liệu dễ hơn.\\n"
        "2. Với câu hỏi so sánh/xếp hạng, chỉ đưa tên/mã, số lượng và đơn vị cần thiết; nêu kết luận một lần. Không nhắc lại yêu cầu, không mô tả quy trình tra cứu, không lặp lại cùng số liệu ở nhiều đoạn, không thêm lời dẫn hoặc kết luận dài dòng.\\n"
        "3. Vẫn phải đủ thông tin để kiểm chứng: giữ nguyên tên/mã sản phẩm, số liệu và đơn vị; nếu so sánh nhiều sản phẩm thì dùng bảng gọn. Không bỏ các dữ kiện quan trọng chỉ để rút ngắn.\\n"
        "4. Nếu người dùng yêu cầu phân tích chi tiết, giải thích hoặc báo cáo đầy đủ thì mới trả lời dài hơn theo yêu cầu.\\n"
        "5. NẾU NGƯỜI DÙNG YÊU CẦU VẼ BIỂU ĐỒ: Viết mã Python vẽ biểu đồ bằng `plotly.express` (gán kết quả vào biến `fig`). Đặt mã trong khối ```python ... ```."
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
        uploaded_files = st.file_uploader(
            "Tải một hoặc nhiều file Excel",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="warehouse_excel_uploader",
            help="Có thể chọn nhiều file trong cùng một lần. Ứng dụng sẽ đọc tất cả sheet và ghi rõ tên file nguồn.",
        )
        if uploaded_files:
            try:
                sheets_data, upload_errors = load_all_sheets_from_uploaded_files(uploaded_files)
                # Giữ tương thích với cơ chế một file Excel đã lưu trước đây.
                if len(uploaded_files) == 1:
                    EXCEL_PATH.write_bytes(uploaded_files[0].getvalue())
                st.success(f"✅ Đã đọc {len(uploaded_files)} file Excel và {len(sheets_data)} sheet.")
                if upload_errors:
                    st.warning("Một số file chưa đọc được: " + " | ".join(upload_errors))
            except Exception as exc:
                st.error(f"❌ Không đọc được file Excel: {exc}")
        elif EXCEL_PATH.exists():
            sheets_data = load_all_sheets_from_file(str(EXCEL_PATH))
            st.info(f"ℹ️ Đang sử dụng file Excel đã lưu sẵn ({len(sheets_data)} sheet). Tải file lên để thay dữ liệu đang dùng.")

    st.divider()
    st.markdown("### 💬 Hội thoại")
    if st.session_state.get("chat_storage_warning"):
        st.warning(st.session_state.chat_storage_warning)
    if st.button("＋ Chat mới", key="start_new_chat", use_container_width=True):
        start_new_conversation()
        st.rerun()

    conversations = st.session_state.get("conversations", [])
    if conversations:
        conversation_labels = {
            conv["id"]: (conv.get("title") or "Cuộc trò chuyện mới")
            for conv in conversations
        }
        conversation_ids = [conv["id"] for conv in conversations]
        active_id = st.session_state.get("active_conversation_id")
        selected_index = conversation_ids.index(active_id) if active_id in conversation_ids else 0
        selected_conversation_id = st.selectbox(
            "Mở hội thoại cũ",
            options=conversation_ids,
            index=selected_index,
            format_func=lambda value: conversation_labels.get(value, "Cuộc trò chuyện"),
            key="chat_selector_id",
            label_visibility="collapsed",
        )
        if selected_conversation_id != active_id:
            st.session_state.active_conversation_id = selected_conversation_id
            selected_conv = next((conv for conv in conversations if conv.get("id") == selected_conversation_id), None)
            st.session_state.messages = selected_conv.get("messages", []) if selected_conv else []
            st.rerun()
    else:
        st.caption("Chưa có cuộc trò chuyện nào.")


def _find_column(df, groups):
    """Tìm cột theo tên thực tế; chỉ dùng khi tên cột khớp các từ khóa rõ ràng."""
    for group in groups:
        for col in df.columns:
            normalized = str(col).strip().lower()
            if all(term in normalized for term in group):
                return col
    return None


def _find_stock_column(df):
    """Ưu tiên tồn cuối kỳ/tồn hiện tại, không nhầm với tồn đầu kỳ hoặc tồn tối thiểu."""
    prioritized = [
        ["tồn cuối kỳ"], ["tồn cuối kì"], ["số lượng tồn cuối kỳ"],
        ["số lượng tồn hiện tại"], ["tồn kho hiện tại"], ["tồn hiện tại"],
        ["số lượng tồn"], ["tồn kho"], ["stock"],
    ]
    for group in prioritized:
        col = _find_column(df, [group])
        if col is not None:
            normalized = str(col).strip().lower()
            if any(term in normalized for term in ["tối thiểu", "đầu kỳ", "đầu kì", "minimum", "opening"]):
                continue
            return col

    # Chấp nhận tên cột tồn tổng quát, nhưng loại các cột nhập/xuất và ngưỡng.
    for col in df.columns:
        normalized = str(col).strip().lower()
        has_stock_word = "tồn" in normalized or "ton" in normalized
        excluded = any(term in normalized for term in [
            "tối thiểu", "đầu kỳ", "đầu kì", "tổng nhập", "tổng xuất",
            "nhập", "xuất", "minimum", "opening", "min stock",
        ])
        if has_stock_word and not excluded:
            return col
    return None


def _find_min_stock_column(df):
    """Nhận diện cột tồn tối thiểu/ngưỡng tồn đã có trong bảng tính."""
    return _find_column(df, [
        ["tồn", "tối thiểu"], ["mức", "tồn", "tối thiểu"],
        ["ngưỡng", "tồn"], ["tồn", "min"], ["minimum", "stock"],
        ["min", "stock"], ["safety", "stock"],
    ])


def _numeric_column(series):
    """Chuyển cột số về numeric, chấp nhận số có dấu phẩy và khoảng trắng."""
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.replace(" ", "", regex=False),
        errors="coerce",
    )


def render_warehouse_dashboard(sheets_dict):
    """Dashboard kho kiểu tổng quan: chỉ hiển thị số liệu nhận diện được từ nguồn thật."""
    st.markdown(
        """
        <div class="warehouse-heading">
            <div>
                <div class="warehouse-eyebrow">WAREHOUSE OVERVIEW</div>
                <h2>📦 Tổng quan kho</h2>
                <p>Theo dõi tồn kho, luồng hàng và các mặt hàng cần chú ý.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    candidates = []
    for sheet_name, frame in sheets_dict.items():
        if frame is None or frame.dropna(how="all").empty:
            continue
        clean_frame = frame.dropna(how="all").copy()
        candidates.append(
            (sheet_name, clean_frame, _find_stock_column(clean_frame), _find_min_stock_column(clean_frame))
        )

    if not candidates:
        st.warning("Không có sheet nào chứa dữ liệu để hiển thị.")
        return

    stock_candidates = [item for item in candidates if item[2] is not None]
    if stock_candidates:
        preferred = next((item for item in stock_candidates if item[3] is not None), stock_candidates[0])
        source_names = [item[0] for item in stock_candidates]
        if len(source_names) > 1:
            selected_name = st.selectbox(
                "Nguồn dữ liệu tồn kho",
                source_names,
                index=source_names.index(preferred[0]),
                key="warehouse_dashboard_source_sheet",
            )
            selected = next(item for item in stock_candidates if item[0] == selected_name)
        else:
            selected = stock_candidates[0]
        selected_name, df, stock_col, min_stock_col = selected
    else:
        selected_name, df, stock_col, min_stock_col = candidates[0]
        st.info("Chưa nhận diện được cột tồn hiện tại. Các số liệu tồn kho sẽ không được tự suy ra từ cột nhập hoặc xuất.")

    category_col = _find_column(df, [
        ["loại hàng"], ["nhóm hàng"], ["danh mục"], ["category"], ["loại sản phẩm"],
    ])
    name_col = _find_column(df, [
        ["tên hàng"], ["tên sản phẩm"], ["tên vật tư"], ["mặt hàng"], ["name"], ["tên"],
    ])
    code_col = _find_column(df, [
        ["mã hàng"], ["mã sản phẩm"], ["mã vật tư"], ["mã sp"], ["code"], ["mã"],
    ])
    unit_col = _find_column(df, [["đơn vị"], ["unit"]])

    # Nhận diện các cột luân chuyển theo tên cột cụ thể; không lấy cột ngày/đơn giá làm số lượng.
    inbound_col = _find_column(df, [
        ["số lượng nhập"], ["lượng nhập"], ["sl nhập"], ["tổng nhập"], ["nhập kho"],
        ["inbound qty"], ["qty in"],
    ])
    outbound_col = _find_column(df, [
        ["số lượng xuất"], ["lượng xuất"], ["sl xuất"], ["tổng xuất"], ["xuất kho"],
        ["outbound qty"], ["qty out"],
    ])
    transfer_col = _find_column(df, [
        ["số lượng điều chuyển"], ["lượng điều chuyển"], ["sl điều chuyển"],
        ["điều chuyển"], ["transfer qty"],
    ])
    date_col = _find_column(df, [
        ["ngày chứng từ"], ["ngày giao dịch"], ["ngày nhập"], ["ngày xuất"], ["ngày"], ["date"],
    ])

    stock_values = _numeric_column(df[stock_col]).dropna() if stock_col is not None else pd.Series(dtype=float)
    units = []
    if unit_col is not None:
        units = sorted(
            df[unit_col].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist()
        )

    def total_for(column):
        if column is None:
            return None
        values = _numeric_column(df[column]).dropna()
        if values.empty:
            return None
        return float(values.sum())

    inbound_total = total_for(inbound_col)
    outbound_total = total_for(outbound_col)
    transfer_total = total_for(transfer_col)

    def show_number(value):
        if value is None:
            return "Chưa có dữ liệu"
        return f"{value:,.2f}".rstrip("0").rstrip(".")

    if stock_col is not None and not stock_values.empty:
        if len(units) > 1:
            stock_display = "Nhiều đơn vị"
        else:
            stock_display = show_number(float(stock_values.sum()))
            if len(units) == 1:
                stock_display += f" {units[0]}"
            elif unit_col is None:
                stock_display += " (chưa rõ ĐVT)"
    else:
        stock_display = "Chưa xác định"

    inbound_metric, outbound_metric, stock_metric, transfer_metric = st.columns(4)
    inbound_metric.metric("Nhập kho", show_number(inbound_total), icon="📥", border=True,
                          help=f"Cột nguồn: {inbound_col}" if inbound_col else "Chưa tìm thấy cột số lượng nhập trong bảng đang chọn.")
    outbound_metric.metric("Xuất kho", show_number(outbound_total), icon="📤", border=True,
                           help=f"Cột nguồn: {outbound_col}" if outbound_col else "Chưa tìm thấy cột số lượng xuất trong bảng đang chọn.")
    stock_metric.metric("Tồn kho", stock_display, icon="📦", border=True,
                        help=f"Nguồn: {selected_name} · Cột tồn: {stock_col or 'chưa nhận diện'}")
    transfer_metric.metric("Điều chuyển", show_number(transfer_total), icon="🔁", border=True,
                           help=f"Cột nguồn: {transfer_col}" if transfer_col else "Chưa tìm thấy cột số lượng điều chuyển trong bảng đang chọn.")

    st.caption(
        f"Nguồn dữ liệu: **{selected_name}**"
        + (f" · Tồn kho lấy từ cột **{stock_col}**" if stock_col is not None else "")
        + " · Các chỉ số không có cột tương ứng sẽ hiển thị “Chưa có dữ liệu”."
    )

    left_chart, right_chart = st.columns([1.35, 1])
    with left_chart:
        st.markdown("### 📊 Biểu đồ nhập – xuất kho")
        if inbound_col is not None and outbound_col is not None:
            chart_frame = df.copy()
            chart_frame["_Nhập kho"] = _numeric_column(chart_frame[inbound_col])
            chart_frame["_Xuất kho"] = _numeric_column(chart_frame[outbound_col])
            parsed_dates = pd.to_datetime(chart_frame[date_col], errors="coerce", dayfirst=True) if date_col is not None else pd.Series(pd.NaT, index=chart_frame.index)
            if date_col is not None and parsed_dates.notna().any():
                chart_frame["_Tháng"] = parsed_dates.dt.to_period("M").astype(str)
                grouped = chart_frame.groupby("_Tháng", dropna=True)[["_Nhập kho", "_Xuất kho"]].sum().reset_index()
                grouped = grouped.tail(12)
                plot_frame = grouped.melt(id_vars="_Tháng", var_name="Luồng hàng", value_name="Số lượng")
                fig_flow = px.bar(
                    plot_frame, x="_Tháng", y="Số lượng", color="Luồng hàng", barmode="group",
                    color_discrete_map={"_Nhập kho": "#1769aa", "_Xuất kho": "#f79432",
                                        "Nhập kho": "#1769aa", "Xuất kho": "#f79432"},
                )
                fig_flow.update_layout(xaxis_title="", yaxis_title="Số lượng", legend_title="", margin=dict(l=8, r=8, t=12, b=8), height=300)
                st.plotly_chart(fig_flow, use_container_width=True, config={"displayModeBar": False})
            else:
                if name_col is not None and code_col is not None:
                    chart_frame["_Mặt hàng"] = chart_frame[code_col].astype(str) + " — " + chart_frame[name_col].astype(str)
                elif name_col is not None:
                    chart_frame["_Mặt hàng"] = chart_frame[name_col].astype(str)
                elif code_col is not None:
                    chart_frame["_Mặt hàng"] = chart_frame[code_col].astype(str)
                else:
                    chart_frame["_Mặt hàng"] = chart_frame.index.astype(str)
                chart_frame["_Tổng luân chuyển"] = chart_frame["_Nhập kho"].fillna(0) + chart_frame["_Xuất kho"].fillna(0)
                plot_frame = chart_frame.dropna(subset=["_Tổng luân chuyển"]).nlargest(8, "_Tổng luân chuyển")
                plot_frame = plot_frame[["_Mặt hàng", "_Nhập kho", "_Xuất kho"]].melt(
                    id_vars="_Mặt hàng", var_name="Luồng hàng", value_name="Số lượng"
                )
                fig_flow = px.bar(
                    plot_frame, x="_Mặt hàng", y="Số lượng", color="Luồng hàng", barmode="group",
                    color_discrete_map={"_Nhập kho": "#1769aa", "_Xuất kho": "#f79432",
                                        "Nhập kho": "#1769aa", "Xuất kho": "#f79432"},
                )
                fig_flow.update_layout(xaxis_title="", yaxis_title="Số lượng", legend_title="", margin=dict(l=8, r=8, t=12, b=8), height=300)
                fig_flow.update_xaxes(tickangle=-20)
                st.plotly_chart(fig_flow, use_container_width=True, config={"displayModeBar": False})
        elif stock_col is not None and not stock_values.empty:
            top_stock = df.copy()
            top_stock["_Tồn thực tế"] = _numeric_column(top_stock[stock_col])
            if name_col is not None and code_col is not None:
                top_stock["_Mặt hàng"] = top_stock[code_col].astype(str) + " — " + top_stock[name_col].astype(str)
            elif name_col is not None:
                top_stock["_Mặt hàng"] = top_stock[name_col].astype(str)
            elif code_col is not None:
                top_stock["_Mặt hàng"] = top_stock[code_col].astype(str)
            else:
                top_stock["_Mặt hàng"] = top_stock.index.astype(str)
            top_stock = top_stock.dropna(subset=["_Tồn thực tế"]).nlargest(10, "_Tồn thực tế")
            fig_stock = px.bar(top_stock, x="_Mặt hàng", y="_Tồn thực tế", color_discrete_sequence=["#1769aa"])
            fig_stock.update_layout(xaxis_title="", yaxis_title=f"Số lượng ({units[0] if len(units) == 1 else 'đơn vị'})", margin=dict(l=8, r=8, t=12, b=8), height=300)
            fig_stock.update_xaxes(tickangle=-20)
            st.plotly_chart(fig_stock, use_container_width=True, config={"displayModeBar": False})
            st.caption("Chưa có đủ cột nhập và xuất; biểu đồ đang hiển thị 10 mặt hàng tồn nhiều nhất.")
        else:
            st.info("Chưa có cột số lượng nhập/xuất hoặc tồn kho đủ rõ để vẽ biểu đồ.")

    with right_chart:
        st.markdown("### 🧩 Cơ cấu tồn kho")
        if category_col is not None:
            composition = df.copy()
            if stock_col is not None and not stock_values.empty and len(units) <= 1:
                composition["_Giá trị biểu đồ"] = _numeric_column(composition[stock_col])
                composition_label = f"Theo số lượng tồn{f' ({units[0]})' if len(units) == 1 else ''}"
            else:
                composition["_Giá trị biểu đồ"] = 1
                composition_label = "Theo số mặt hàng"
            composition[category_col] = composition[category_col].fillna("Chưa phân loại").astype(str)
            composition = composition.groupby(category_col, dropna=False)["_Giá trị biểu đồ"].sum().reset_index()
            composition = composition[composition["_Giá trị biểu đồ"] > 0].nlargest(8, "_Giá trị biểu đồ")
            if not composition.empty:
                fig_mix = px.pie(
                    composition, names=category_col, values="_Giá trị biểu đồ", hole=0.58,
                    color_discrete_sequence=["#1769aa", "#2997e8", "#8bbbe6", "#f79432", "#b7cce0", "#5d8fc3"],
                )
                fig_mix.update_layout(
                    legend_title="", margin=dict(l=8, r=8, t=12, b=8), height=300,
                    annotations=[dict(text=f"{len(df):,}<br>mặt hàng", x=0.5, y=0.5, showarrow=False, font_size=15)],
                )
                st.plotly_chart(fig_mix, use_container_width=True, config={"displayModeBar": False})
                st.caption(composition_label)
            else:
                st.info("Chưa có dữ liệu nhóm hàng hợp lệ để thể hiện cơ cấu.")
        elif stock_col is not None and not stock_values.empty:
            status = pd.DataFrame({"Tồn": _numeric_column(df[stock_col])})
            if min_stock_col is not None:
                minimum = _numeric_column(df[min_stock_col])
                status["Trạng thái"] = "Còn hàng"
                status.loc[status["Tồn"] <= minimum, "Trạng thái"] = "Tồn thấp"
                status.loc[status["Tồn"] == 0, "Trạng thái"] = "Hết hàng"
                status.loc[status["Tồn"] < 0, "Trạng thái"] = "Tồn âm"
            else:
                status["Trạng thái"] = "Còn hàng"
                status.loc[status["Tồn"] == 0, "Trạng thái"] = "Hết hàng"
                status.loc[status["Tồn"] < 0, "Trạng thái"] = "Tồn âm"
            counts = status["Trạng thái"].value_counts().rename_axis("Trạng thái").reset_index(name="Số mặt hàng")
            fig_status = px.pie(counts, names="Trạng thái", values="Số mặt hàng", hole=0.58,
                                color_discrete_sequence=["#1769aa", "#2997e8", "#f79432", "#b7cce0"])
            fig_status.update_layout(legend_title="", margin=dict(l=8, r=8, t=12, b=8), height=300)
            st.plotly_chart(fig_status, use_container_width=True, config={"displayModeBar": False})
            st.caption("Chưa nhận diện được cột nhóm hàng; biểu đồ thể hiện tình trạng tồn.")
        else:
            st.info("Chưa có dữ liệu để phân loại cơ cấu tồn kho.")

    st.divider()
    title_col, all_col = st.columns([5, 1])
    with title_col:
        st.markdown("### 📋 Danh sách hàng hóa")
    with all_col:
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        st.caption("Mở bộ lọc bên dưới để xem tất cả")

    display_frame = df.copy()
    if stock_col is not None:
        display_frame["_Sắp xếp tồn"] = _numeric_column(display_frame[stock_col])
        display_frame = display_frame.sort_values("_Sắp xếp tồn", ascending=False, na_position="last")

    visible_cols = [col for col in [code_col, name_col, category_col, stock_col, unit_col] if col is not None]
    if min_stock_col is not None and min_stock_col not in visible_cols:
        visible_cols.append(min_stock_col)
    if not visible_cols:
        visible_cols = list(df.columns[:6])
    preview = display_frame[visible_cols].head(5).copy()
    if stock_col is not None:
        preview["Trạng thái"] = "Còn hàng"
        current_values = _numeric_column(preview[stock_col])
        preview.loc[current_values == 0, "Trạng thái"] = "Hết hàng"
        preview.loc[current_values < 0, "Trạng thái"] = "Tồn âm"
        if min_stock_col is not None:
            minimum_values = _numeric_column(preview[min_stock_col])
            low_mask = (current_values > 0) & minimum_values.notna() & (current_values <= minimum_values)
            preview.loc[low_mask, "Trạng thái"] = "Sắp hết"
        preview.loc[current_values.isna(), "Trạng thái"] = "Chưa xác định"
    st.dataframe(preview, use_container_width=True, hide_index=True, height=230)

    with st.expander("🔎 Tra cứu và lọc nâng cao", expanded=False):
        filter1, filter2, filter3 = st.columns([1.2, 1, 2])
        filtered = df.copy()
        with filter1:
            if category_col is not None:
                category_options = ["Tất cả"] + sorted(df[category_col].dropna().astype(str).unique().tolist())
                category_value = st.selectbox("Nhóm hàng", category_options, key="warehouse_category_filter")
                if category_value != "Tất cả":
                    filtered = filtered[filtered[category_col].astype(str) == category_value]
            else:
                st.caption("Nguồn này không có cột nhóm hàng.")
        with filter2:
            unit_options = ["Tất cả"] + units if units else ["Tất cả"]
            unit_value = st.selectbox("Đơn vị tính", unit_options, key="warehouse_unit_filter")
            if unit_col is not None and unit_value != "Tất cả":
                filtered = filtered[filtered[unit_col].astype(str).str.strip() == unit_value]
        with filter3:
            search_value = st.text_input("Tìm theo mã hoặc tên", key="warehouse_item_search", placeholder="Nhập mã hoặc tên hàng")
            if search_value.strip():
                searchable = [col for col in [code_col, name_col] if col is not None] or list(filtered.columns)
                mask = pd.Series(False, index=filtered.index)
                for col in searchable:
                    mask = mask | filtered[col].astype(str).str.contains(search_value.strip(), case=False, na=False, regex=False)
                filtered = filtered[mask]

        if stock_col is not None:
            filter_options = ["Tất cả", "Sắp hết / tồn thấp", "Hết hàng (0)", "Tồn âm", "Còn hàng"]
            stock_filter = st.selectbox("Tình trạng tồn", filter_options, key="warehouse_stock_filter")
            values = _numeric_column(filtered[stock_col])
            if stock_filter == "Sắp hết / tồn thấp":
                if min_stock_col is not None:
                    minimum = _numeric_column(filtered[min_stock_col])
                    filtered = filtered[(values > 0) & minimum.notna() & (values <= minimum)]
                else:
                    st.caption("Chưa có cột tồn tối thiểu trong sheet nên không thể tự xác định hàng sắp hết.")
                    filtered = filtered.iloc[0:0]
            elif stock_filter == "Hết hàng (0)":
                filtered = filtered[values == 0]
            elif stock_filter == "Tồn âm":
                filtered = filtered[values < 0]
            elif stock_filter == "Còn hàng":
                filtered = filtered[values > 0]

        st.caption(f"Kết quả: **{len(filtered):,}** mặt hàng")
        filter_cols = [col for col in [code_col, name_col, category_col, stock_col, min_stock_col, unit_col] if col is not None]
        st.dataframe(filtered[filter_cols] if filter_cols else filtered, use_container_width=True, hide_index=True, height=320)

    with st.expander("📂 Dữ liệu chi tiết theo file / sheet", expanded=False):
        detail_name = st.selectbox("Chọn file / sheet", list(sheets_dict.keys()), key="detail_sheet_selector")
        detail_df = sheets_dict[detail_name]
        st.dataframe(detail_df, use_container_width=True, hide_index=True, height=420)


# ── GIAO DIỆN BẢNG ĐIỀU KHIỂN CHÍNH ─────────────────────────────────────────
st.markdown("# 🏭 AI Quản Lý Kho Hàng")

if not sheets_data:
    st.info("👈 Vui lòng dán Link Google Sheet hoặc tải file Excel ở sidebar trái.")
    st.stop()

tab_data, tab_chat = st.tabs(["📊 Xem dữ liệu", "💬 Hỏi đáp Thông Minh"])

with tab_data:
    render_warehouse_dashboard(sheets_data)

with tab_chat:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): 
            if msg["role"] == "assistant":
                render_message_and_chart(msg["content"], sheets_data)
            else:
                st.markdown(msg["content"])

    # Ô nhập câu hỏi của Streamlit được ghim ở cuối vùng ứng dụng,
    # để người dùng có thể hỏi tiếp dù đang xem phần trên hay dưới của hội thoại.
    question = st.chat_input(
        "Gõ câu hỏi bất kỳ... (Enter để gửi)",
        key="chat_question_input",
    )

    if question and question.strip():
        question = question.strip()
        with st.chat_message("user"):
            st.markdown(question)

        st.session_state.messages.append({"role": "user", "content": question})
        save_chat_history()

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
            save_chat_history()
        st.rerun()
