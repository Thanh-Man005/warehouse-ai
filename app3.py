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

    with st.form("chat_question_form", clear_on_submit=True):
        question = st.text_area("Gõ câu hỏi bất kỳ...", height=90, placeholder="VD: Vẽ biểu đồ biến động tài chính theo ngày?")
        send_question = st.form_submit_button("🚀 Gửi câu hỏi", type="primary", use_container_width=True)

    if send_question and question.strip():
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
