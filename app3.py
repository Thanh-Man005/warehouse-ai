import streamlit as st
import pandas as pd
import json
import os
import re
import io
import requests
import hashlib
import time
import unicodedata
import plotly.express as px
from pathlib import Path

# ── Cấu hình trang ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Kho Hàng - Quản Lý & Phân Tích",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="collapsed"
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

    /* Ghim ô hỏi đáp theo đáy màn hình; mặc định khi sidebar thu gọn. */
    div[data-testid="stChatInput"] {
        position: fixed !important;
        bottom: 1rem !important;
        left: max(1rem, calc((100vw - 1320px) / 2)) !important;
        right: max(1rem, calc((100vw - 1320px) / 2)) !important;
        width: auto !important;
        z-index: 9999 !important;
        background: var(--background-color);
        padding-top: 0.35rem;
        padding-bottom: 0.35rem;
        transition: left 180ms ease, right 180ms ease, width 180ms ease;
    }

    /* Sidebar mở: dịch ô chat sang phải và thu hẹp theo vùng nội dung còn lại. */
    .stApp:has([data-testid="stSidebar"][aria-expanded="true"]) div[data-testid="stChatInput"] {
        left: max(22rem, calc((100vw - 1320px) / 2 + 22rem)) !important;
        right: max(1rem, calc((100vw - 1320px) / 2)) !important;
    }

    @media (max-width: 700px) {
        div[data-testid="stChatInput"],
        .stApp:has([data-testid="stSidebar"][aria-expanded="true"]) div[data-testid="stChatInput"] {
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

if "gsheet_urls_input" not in st.session_state:
    saved_sheet_urls = saved_config.get("gsheet_urls", [])
    if isinstance(saved_sheet_urls, str):
        saved_sheet_urls = [line.strip() for line in saved_sheet_urls.splitlines() if line.strip()]
    if not saved_sheet_urls and st.session_state.gsheet_url:
        saved_sheet_urls = [st.session_state.gsheet_url]
    st.session_state.gsheet_urls_input = "\\n".join(
        url.strip() for url in saved_sheet_urls if isinstance(url, str) and url.strip()
    )

if "data_source" not in st.session_state:
    st.session_state.data_source = saved_config.get(
        "data_source", "🌐 Link Google Trang tính"
    )


def _norm(text) -> str:
    """Bỏ dấu + chữ thường để so khớp tên cột/từ khóa ổn định."""
    t = unicodedata.normalize("NFD", str(text))
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return t.replace("đ", "d").replace("Đ", "D").lower().strip()


def _find_sheet(sheets_dict: dict, name: str):
    """Tìm sheet theo tên (kể cả khi khóa có tiền tố 'file · sheet')."""
    for key, df in sheets_dict.items():
        if _norm(key).split("·")[-1].strip() == _norm(name):
            return df
    return None


def _col(df, *names):
    """Trả về tên cột thật khớp CHÍNH XÁC (không phân biệt dấu/hoa thường)."""
    lookup = {_norm(c): c for c in df.columns}
    for n in names:
        if _norm(n) in lookup:
            return lookup[_norm(n)]
    return None


def _cutoff(sheets_dict: dict):
    """Ngày chốt lấy từ sheet THIET_LAP (Ngay_mo_phong); hết ngày 23:59:59."""
    df = _find_sheet(sheets_dict, "THIET_LAP")
    if df is None:
        return None
    k, v = _col(df, "Tham_so"), _col(df, "Gia_tri")
    if not k or not v:
        return None
    row = df[df[k].astype(str).str.strip() == "Ngay_mo_phong"]
    if row.empty:
        return None
    val = row.iloc[0][v]
    try:
        if isinstance(val, (int, float)):
            val = pd.Timestamp("1899-12-30") + pd.to_timedelta(float(val), unit="D")
        return pd.Timestamp(val).normalize() + pd.Timedelta(hours=23, minutes=59, seconds=59)
    except Exception:
        return None


def _to_md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(x) for x in r.tolist()) + " |")
    return "\n".join(lines)


LOCATION_RE = re.compile(r"\b[A-Z]{2,4}-[A-Z]\d{1,3}-T\d+\b")
SKU_RE = re.compile(r"\bSP\d{3}\b", re.IGNORECASE)


def auto_route_and_process(question: str, sheets_dict: dict):
    q_low = question.lower().strip()
    q_up = question.upper()

    # 0a. Tồn theo vị trí kệ: tính trực tiếp từ sổ BIEN_DONG (không để AI đoán)
    loc_match = LOCATION_RE.search(q_up)
    ledger = _find_sheet(sheets_dict, "BIEN_DONG")
    asks_contents = any(k in q_low for k in ["sku", "lượng hàng", "chứa", "đang có", "hàng nào", "tồn", "có gì", "bao nhiêu"])
    asks_movement = any(k in q_low for k in ["chuyển", "lúc nào", "khi nào", "điều chuyển", "từ kệ", "sang"])
    if loc_match and ledger is not None and asks_contents and not asks_movement and len(set(LOCATION_RE.findall(q_up))) == 1:
        c_pos, c_sku, c_qty = _col(ledger, "Vi_tri"), _col(ledger, "Ma_SKU"), _col(ledger, "SL_cong_tru")
        c_lot, c_st, c_ts = _col(ledger, "Ma_lo"), _col(ledger, "Trang_thai_hang"), _col(ledger, "Thoi_diem")
        if all([c_pos, c_sku, c_qty, c_lot, c_st]):
            loc = loc_match.group(0)
            led = ledger.copy()
            cut = _cutoff(sheets_dict)
            if c_ts and cut is not None:
                led[c_ts] = pd.to_datetime(led[c_ts], errors="coerce")
                led = led[led[c_ts] <= cut]
            led = led[led[c_pos].astype(str).str.strip().str.upper() == loc]
            led[c_qty] = pd.to_numeric(led[c_qty], errors="coerce").fillna(0)
            g = led.groupby([c_sku, c_lot, c_st], as_index=False)[c_qty].sum()
            g = g[g[c_qty] > 0].sort_values([c_sku, c_lot])
            names = _find_sheet(sheets_dict, "DM_SKU")
            if names is not None and _col(names, "Ma_SKU") and _col(names, "Ten_san_pham"):
                mp = dict(zip(names[_col(names, "Ma_SKU")], names[_col(names, "Ten_san_pham")]))
                g.insert(1, "Ten_san_pham", g[c_sku].map(mp))
            g = g.rename(columns={c_qty: "So_luong"})
            when = f" tại ngày chốt {cut:%d/%m/%Y}" if cut is not None else ""
            if g.empty:
                return f"⚡ **[Tính trực tiếp từ sổ BIEN_DONG]**\n\nVị trí **{loc}** hiện không có hàng{when}.", False
            return (
                f"⚡ **[Tính trực tiếp từ sổ BIEN_DONG]**\n\nVị trí **{loc}** có **{g[c_sku].nunique()} SKU**, "
                f"tổng **{int(g['So_luong'].sum())}** đơn vị{when}:\n\n" + _to_md_table(g)
            ), False

    # Nhóm câu hỏi bắt buộc gửi cho AI phân tích sâu hoặc vẽ biểu đồ
    if any(k in q_low for k in ["biểu đồ", "vẽ biểu đồ", "đồ thị", "vẽ đồ thị", "bảng", "lập bảng", "danh sách", "thống kê", "tại sao", "vì sao", "dự báo", "tư vấn", "lâu nhất", "tồn đọng", "nhiều nhất"]):
        return None, True

    # 1. Hàng dưới mức tồn an toàn / sắp hết (0 Token)
    if any(k in q_low for k in ["sắp hết", "tồn ít", "cảnh báo", "hết hàng", "thiếu hàng", "tồn an toàn", "dưới an toàn", "dưới mức"]):
        results = []
        for name, df in sheets_dict.items():
            c_safe = _col(df, "Ton_an_toan", "Tồn an toàn", "Mức tồn an toàn")
            c_stock = _col(df, "CO_THE_BAN", "Ton_kha_dung", "Tồn khả dụng", "Ton_kho", "Tồn kho", "Số lượng tồn", "So_luong_ton")
            c_name = _col(df, "Ten_san_pham", "Tên sản phẩm", "Tên hàng", "Tên vật tư", "Mặt hàng")
            c_code = _col(df, "Ma_SKU", "Mã SKU", "Mã hàng", "Mã")
            if c_safe and c_stock and (c_name or c_code):
                d = df.copy()
                d[c_safe] = pd.to_numeric(d[c_safe], errors="coerce")
                d[c_stock] = pd.to_numeric(d[c_stock], errors="coerce")
                low = d[d[c_stock] < d[c_safe]]
                show = [c for c in [c_code, c_name, c_stock, c_safe] if c]
                results.append(
                    f"📌 **Tab [{name}]: {len(low)} mặt hàng dưới mức tồn an toàn** "
                    f"(so sánh `{c_stock}` với `{c_safe}`):\n\n" + (_to_md_table(low[show]) if not low.empty else "_Không có._")
                )
        if results:
            return "⚡ **[Tự động xử lý - 0 Token]**\n\n" + "\n\n".join(results), False
        return None, True  # không có cột tồn an toàn → để AI đọc dữ liệu, không đoán ngưỡng

    # 2. Tính tổng giá trị kho (0 Token)
    elif any(k in q_low for k in ["tổng giá trị", "tổng tiền", "giá trị kho", "tổng vốn"]):
        total_val = 0
        details = []
        for name, df in sheets_dict.items():
            val_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["thành tiền", "giá trị", "tổng tiền"])), None)
            if val_col:
                s_ = pd.to_numeric(df[val_col], errors="coerce").sum()
                if s_ > 0:
                    total_val += s_
                    details.append(f"- Tab **{name}**: `{s_:,.0f} VNĐ`")
        if details:
            msg = f"⚡ **[Tự động xử lý - 0 Token]**\n\n💰 **Tổng giá trị kho:** `{total_val:,.0f} VNĐ`\n\nChi tiết từng tab:\n" + "\n".join(details)
            return msg, False

    # 3. Tồn của một mã SKU cụ thể (0 Token) — chỉ khi hỏi đúng mã, không liệt kê bừa
    elif any(k in q_low for k in ["còn chính xác bao nhiêu", "còn bao nhiêu", "số lượng còn", "số lượng trong kho"]):
        sku = SKU_RE.search(question)
        if sku:
            code = sku.group(0).upper()
            for name, df in sheets_dict.items():
                c_code, c_sell = _col(df, "Ma_SKU"), _col(df, "SELLABLE")
                if c_code and c_sell and _col(df, "CO_THE_BAN"):
                    row = df[df[c_code].astype(str).str.upper() == code]
                    if not row.empty:
                        r = row.iloc[0]
                        return (
                            f"⚡ **[Tự động tra cứu - 0 Token]**\n\n**{code}** còn **{r[c_sell]}** đơn vị bán được (SELLABLE, chưa trừ giữ hàng); "
                            f"có thể bán sau khi trừ giữ hàng: **{r[_col(df, 'CO_THE_BAN')]}** (tab `{name}`)."
                        ), False

    return None, True

# ════════════════════════════════════════════════════════════════════════════
# PHẦN 2 — XỬ LÝ DỮ LIỆU & GỌI AI GOOGLE
# ════════════════════════════════════════════════════════════════════════════
def extract_gsheet_id(url: str) -> str:
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

def normalize_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Cột ngày bị lưu dạng số serial Excel (vd 46285.375, định dạng General) → datetime thật."""
    keys = ("han_su_dung", "hsd", "han_dung", "expiry", "ngay", "thoi_gian", "thoi_diem", "bat_dau", "ket_thuc", "luc")
    for c in df.columns:
        if not any(k in _norm(c) for k in keys):
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            vals = df[c].dropna()
            if len(vals) and vals.between(30000, 80000).all():
                df[c] = pd.Timestamp("1899-12-30") + pd.to_timedelta(df[c], unit="D")
    return df


def smart_parse_sheet(xl: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    """Tự động tìm dòng tiêu đề thật sự (bỏ qua các dòng mô tả ở đầu sheet) và làm sạch bảng."""
    raw = xl.parse(sheet_name, header=None)
    if raw.empty:
        return pd.DataFrame()

    best_row = 0
    best_score = -1
    max_scan = min(15, len(raw))

    for i in range(max_scan):
        row = raw.iloc[i]
        non_null = row.dropna()
        if len(non_null) < 2:
            continue
        str_count = sum(1 for v in non_null if isinstance(v, str) and v.strip() != "")
        score = str_count * 2 + len(non_null)
        if score > best_score:
            best_score = score
            best_row = i

    df = xl.parse(sheet_name, header=best_row)
    df = df.dropna(how="all")
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed:")]
    return normalize_date_columns(df.reset_index(drop=True))


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
    return {sheet: smart_parse_sheet(xl, sheet) for sheet in xl.sheet_names}


def load_all_sheets_from_multiple_gsheets(urls: list) -> tuple:
    """Gộp sheet từ nhiều link Google Sheets; báo lỗi riêng từng link."""
    combined = {}
    errors = []
    for index, url in enumerate(urls, start=1):
        sheet_id = extract_gsheet_id(url)
        if not sheet_id:
            errors.append(f"Link {index}: URL không đúng định dạng Google Sheets.")
            continue
        source_label = f"Google Sheet {index} ({sheet_id[:8]})"
        try:
            sheets = load_all_sheets_from_gsheet(url)
            for sheet_name, frame in sheets.items():
                key = f"{source_label} · {sheet_name}"
                if key in combined:
                    key = f"{source_label} · {sheet_name} ({index})"
                combined[key] = frame
        except Exception as exc:
            errors.append(f"Link {index} ({sheet_id[:8]}): {exc}")
    return combined, errors


@st.cache_data(show_spinner=False)
def load_all_sheets_from_file(path: str, mtime: float = 0) -> dict:
    xl = pd.ExcelFile(path)
    return {sheet: smart_parse_sheet(xl, sheet) for sheet in xl.sheet_names}


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
                combined[key] = smart_parse_sheet(workbook, sheet_name)
        except Exception as exc:
            errors.append(f"{filename}: {exc}")
    if not combined:
        details = "; ".join(errors) if errors else "Không tìm thấy sheet dữ liệu trong file."
        raise ValueError(details)
    return combined, errors


# Tab luôn được gửi (nhỏ, dùng cho hầu hết câu hỏi). Nếu file không có tab nào trong nhóm này
# (vd file kho kiểu khác), hệ thống giữ cách cũ: gửi mọi tab.
DEFAULT_CORE_TABS = {"dm_sku", "ton_sku", "ton_lo", "ton_vi_tri", "thiet_lap", "quy_tac", "dm_khu", "tong_quan"}
# Gợi ý: từ khóa trong câu hỏi (không dấu) → các tab nên gửi thêm.
DEFAULT_TAB_HINTS = [
    (("so0", "dap ung don", "du hang cho don"), ("don_ban", "dong_don_ban", "giu_hang", "nhiem_vu_pick", "xuat_giao", "trang_thai_don")),
    (("po0", "phieu nhap", "duyet"), ("don_mua_po", "phieu_nhap", "lich_xe_nhap", "putaway", "dm_nhan_vien")),
    (("khu vuc", "day nao", "tang nao", "nam o dau", "vi tri", "ke "), ("dm_vi_tri", "putaway")),
    (("xe ", "xe nhap", "eta", "ata", "cua nhap", "tai xe", "bien so"), ("lich_xe_nhap", "don_mua_po", "phieu_nhap")),
    (("nhap", "nhan hang", " po", "mua hang", "nha cung cap", "ncc", "dat hang", "tre hang"), ("don_mua_po", "phieu_nhap", "lich_xe_nhap", "dm_doi_tac")),
    (("putaway", "len ke", "cat hang"), ("putaway", "phieu_nhap")),
    (("don ban", "don hang", "giu hang", "phan bo", "khach", "giao hang", "trang thai don"), ("don_ban", "dong_don_ban", "giu_hang", "trang_thai_don", "xuat_giao")),
    (("pick", "lay hang", "nhat hang"), ("nhiem_vu_pick", "don_ban", "dong_don_ban")),
    (("xuat", "ban giao", "cogs", "gia von", "doanh thu", "van chuyen"), ("xuat_giao", "don_ban", "dong_don_ban")),
    (("qc", "loi ngoai quan", "hu hong", "cach ly", "hu hai"), ("kiem_tra_qc",)),
    (("tra hang", "hang tra", "return"), ("hang_tra",)),
    (("kiem ke", "chenh lech", "thuc dem"), ("kiem_ke",)),
    (("dieu chuyen", "chuyen ke", "chuyen vi tri"), ("dieu_chuyen",)),
    (("tieu huy", "cho huy", "huy hang"), ("tieu_huy",)),
    (("serial", "imei", "truy xuat"), ("dm_serial",)),
    (("nhan vien", "ca lam", "ca sang", "ca chieu", "nguoi "), ("dm_nhan_vien", "ca_lam")),
    (("lo ", " lo", "han su dung", "het han", "hsd", "ton lau", "fefo"), ("dm_lo",)),
    (("bien dong", "so cai", "lich su", "phat sinh", "ledger", "nhap xuat ton"), ("bien_dong",)),
    (("8 ngay", "lich 8"), ("lich_8_ngay",)),
]
# Tab KHÔNG bao giờ gửi cho AI: TEST_30 chứa đáp án mẫu → AI sẽ chép đáp án thay vì tính từ dữ liệu.
DEFAULT_EXCLUDE_TABS = {"test_30"}
_STOP = {"khong", "bao", "nhieu", "cac", "nao", "hom", "nay", "the", "trong", "cua", "nhung", "mat", "hang",
         "kho", "con", "cho", "tai", "hay", "voi", "gi", "co", "la", "va", "nhung", "duoc", "den", "tu"}


TAB_CONFIG_PATH = DATA_DIR / "tab_config.json"
AUTO_CORE_MAX_ROWS = 150
AUTO_CORE_NAME_HINTS = ("tong", "ton", "dm", "danh muc", "summary", "bao cao", "snapshot")


def _fold(text) -> str:
    """Bỏ dấu + chữ thường, KHÔNG cắt khoảng trắng (từ khóa như 'xe ' cần giữ khoảng trắng)."""
    t = unicodedata.normalize("NFD", str(text))
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return t.replace("đ", "d").replace("Đ", "D").lower()


def _tabkey(name) -> str:
    """Khóa so khớp tên tab: không dấu, chữ thường, khoảng trắng/gạch dưới coi như nhau."""
    return re.sub(r"[\s_]+", "_", _fold(name).strip())


def _sheet_base(key) -> str:
    return _tabkey(str(key).split("·")[-1])


def default_tab_config() -> dict:
    return {
        "core_tabs": sorted(t.upper() for t in DEFAULT_CORE_TABS),
        "exclude_tabs": sorted(t.upper() for t in DEFAULT_EXCLUDE_TABS),
        "tab_hints": [{"keywords": list(k), "tabs": list(t)} for k, t in DEFAULT_TAB_HINTS],
    }


def load_tab_config() -> dict:
    """Đọc data/tab_config.json; thiếu khóa nào thì dùng mặc định."""
    cfg = default_tab_config()
    saved = load_json_data(TAB_CONFIG_PATH, {})
    if isinstance(saved, dict):
        for k in cfg:
            if k in saved and isinstance(saved[k], list):
                cfg[k] = saved[k]
    return cfg


def effective_core_keys(sheets_dict: dict, cfg: dict) -> set:
    """Tab lõi thực tế: theo cấu hình nếu khớp ít nhất 1 tab; nếu không thì TỰ NHẬN DIỆN
    (tab nhỏ <=150 dòng hoặc tên có 'tổng hợp/tồn/danh mục...')."""
    excluded = {_tabkey(t) for t in cfg.get("exclude_tabs", [])}
    wanted = {_tabkey(t) for t in cfg.get("core_tabs", [])}
    core = {k for k in sheets_dict if _sheet_base(k) in wanted and _sheet_base(k) not in excluded}
    if core:
        return core
    for k, df in sheets_dict.items():
        if _sheet_base(k) in excluded:
            continue
        rows = len(df.dropna(how="all"))
        name = _sheet_base(k).replace("_", " ")
        if 0 < rows <= AUTO_CORE_MAX_ROWS or any(h in name for h in AUTO_CORE_NAME_HINTS):
            core.add(k)
    return core


_STOP = {"khong", "bao", "nhieu", "cac", "nao", "hom", "nay", "the", "trong", "cua", "nhung", "mat", "hang",
         "kho", "con", "cho", "tai", "hay", "voi", "gi", "co", "la", "va", "duoc", "den", "tu"}


def select_tabs(question: str, sheets_dict: dict, extra=None):
    """Chọn tab gửi cho AI. Lõi luôn gửi; khớp gợi ý/tên tab thì gửi thêm; không khớp gì thì
    gửi thêm mọi tab vừa (<=300 dòng) — 'không chắc thì gửi nhiều hơn'. Cấu hình đọc từ tab_config.json."""
    cfg = load_tab_config()
    excluded = {_tabkey(t) for t in cfg.get("exclude_tabs", [])}
    bases = {k: _sheet_base(k) for k in sheets_dict}
    allowed = [k for k in sheets_dict if bases[k] not in excluded]
    core = effective_core_keys(sheets_dict, cfg)
    if not core:
        return allowed, []
    q = " " + _fold(question) + " "
    chosen = set(core)
    matched = set()
    for h in cfg.get("tab_hints", []):
        try:
            kws = [_fold(x) for x in h.get("keywords", [])]
            tabs = {_tabkey(x) for x in h.get("tabs", [])}
        except Exception:
            continue
        if any(kw in q for kw in kws):
            matched |= {k for k, b in bases.items() if b in tabs}
    qtok = set(re.findall(r"[a-z0-9]{3,}", q)) - _STOP
    for k, b in bases.items():
        if k not in core and (set(re.findall(r"[a-z0-9]{3,}", b.replace("_", " "))) - _STOP) & qtok:
            matched.add(k)
    if matched:
        chosen |= matched
    else:
        chosen |= {k for k, df in sheets_dict.items() if len(df.dropna(how="all")) <= 300}
    chosen |= set(extra or [])
    selected = [k for k in allowed if k in chosen]
    omitted = [k for k in allowed if k not in chosen]
    return selected, omitted


def _log_ask(question, model, selected, omitted, retried):
    """Ghi log mỗi lượt hỏi AI để xem lại khi AI trả lời sai (tab nào đã được gửi)."""
    try:
        import datetime
        rec = {"time": datetime.datetime.now().isoformat(timespec="seconds"), "question": question, "model": model,
               "sent_tabs": selected, "omitted_tabs": omitted, "retried_with_extra_tabs": retried}
        with open(DATA_DIR / "ask_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


ENTITY_PATTERNS = {
    "Mã SKU": re.compile(r"\bSP\d{3}\b"),
    "Mã lô": re.compile(r"\bL\d{3}-\d{2}\b"),
    "Vị trí": re.compile(r"\b[A-Z]{2,4}-[A-Z]\d{1,3}-T\d+\b"),
}
FOLLOWUP_MARKERS = [
    "trên", "đó", "này", "kia", "vừa rồi", "vừa nêu", "vừa hỏi", "ở trên", "nói trên", "như trên",
    "những cái", "các mặt hàng đó", "chúng", "nó ", "thế còn", "còn lại", "ngoài ra", "tiếp theo",
    "so với", "trong số", "trong đó", "cũng vậy", "tương tự", "câu trước", "lúc nãy", "ban nãy",
]


def is_followup_question(question: str) -> bool:
    """Câu hỏi nối tiếp (cần lịch sử) hay câu hỏi độc lập (không cần)."""
    q = question.lower().strip()
    if any(m in q for m in FOLLOWUP_MARKERS):
        return True
    # Câu quá ngắn và không chứa mã cụ thể thường là hỏi tiếp ("còn kho đông?")
    has_code = any(p.search(question.upper()) for p in ENTITY_PATTERNS.values())
    return len(q.split()) <= 4 and not has_code


def extract_entities(answer: str) -> dict:
    """Lấy mã SKU / lô / vị trí xuất hiện trong câu trả lời, giữ thứ tự, không trùng."""
    found = {}
    for label, pat in ENTITY_PATTERNS.items():
        items = list(dict.fromkeys(pat.findall(answer.upper())))
        if items:
            found[label] = items
    return found


def build_history_context(question: str, chat_history, last_entities) -> str:
    """Chỉ đưa lịch sử khi là câu hỏi nối tiếp; câu hỏi độc lập luôn cho cùng một ngữ cảnh."""
    if not is_followup_question(question):
        return ""
    msgs = [m for m in (chat_history or []) if str(m.get("content", "")).strip() and not str(m.get("content", "")).startswith("❌")]
    users = [m for m in msgs if m.get("role") == "user"][-15:]          # 15 câu hỏi gần nhất
    answers = [m for m in msgs if m.get("role") != "user"][-2:]         # 2 câu trả lời gần nhất, rút gọn
    keep = {id(m) for m in users + answers}
    lines = []
    for m in msgs:
        if id(m) not in keep:
            continue
        if m.get("role") == "user":
            lines.append(f"Người dùng: {str(m['content']).strip()[:500]}")
        else:
            lines.append(f"Trợ lý: {str(m['content']).strip()[:700]}")
    if last_entities:
        ent = "; ".join(f"{k}: {', '.join(v)}" for k, v in last_entities.items())
        lines.append(f"[Các mã xuất hiện trong câu trả lời GẦN NHẤT — 'các sản phẩm trên' nghĩa là đúng các mã này] {ent}")
    return "\n".join(lines)


def ask_ai(question: str, sheets_dict: dict, chat_history=None, last_entities=None,
           extra_tabs=None, _retry=True) -> str:
    api_key = get_gemini_api_key()
    if not api_key:
        raise Exception(
            "🔑 Chưa cấu hình GEMINI_API_KEY trong "
            "Streamlit Cloud → Settings → Secrets."
        )
    
    # Tự động gửi ĐỦ 100% dòng cho các bảng danh mục/tổng hợp (<= 300 dòng)
    # Chỉ giới hạn các bảng giao dịch quá lớn (> 300 dòng) để tránh quá tải ngữ cảnh
    prompt_data = []
    selected, omitted = select_tabs(question, sheets_dict, extra_tabs)
    for name in selected:
        df = sheets_dict[name]
        df_clean = df.dropna(how="all")
        if not df_clean.empty:
            total_rows = len(df_clean)
            if total_rows <= 300:
                df_send = df_clean
                note = f"Đầy đủ {total_rows} dòng"
            else:
                df_send = df_clean.head(100)
                note = (f"CHỈ 100/{total_rows} dòng đầu — KHÔNG đủ để cộng tổng hay lọc; "
                        f"hãy ưu tiên các tab tổng hợp/snapshot, nếu buộc phải dùng tab này thì nói rõ dữ liệu bị cắt")
            df_send = df_send.copy()
            for _c in df_send.columns:
                if pd.api.types.is_datetime64_any_dtype(df_send[_c]):
                    df_send[_c] = df_send[_c].dt.strftime("%d/%m/%Y %H:%M").str.replace(" 00:00", "", regex=False)
            prompt_data.append(f"=== TAB [{name}] ({note}) ===\n" + df_send.to_string(index=False))
            
    if omitted:
        catalog = "\n".join(
            f"- [{n}]: {len(sheets_dict[n].dropna(how='all'))} dòng; cột: {', '.join(map(str, sheets_dict[n].columns))}"
            for n in omitted
        )
        prompt_data.append("=== CÁC TAB KHÔNG GỬI (chỉ có mục lục: tên, số dòng, cột) ===\n" + catalog)
    context = "\n\n".join(prompt_data)
    if omitted and _retry:
        rule7 = ("\n7. Nếu để trả lời cần dữ liệu từ tab trong mục 'CÁC TAB KHÔNG GỬI', hãy trả lời DUY NHẤT "
                 "một dòng: CẦN_TAB: TEN_TAB1, TEN_TAB2 (không viết gì thêm).")
    else:
        rule7 = "\n7. Không còn tab nào để yêu cầu thêm; nếu thiếu dữ liệu, nói rõ phần nào thiếu, không đoán."

    # Đưa các lượt hội thoại gần nhất vào prompt để câu hỏi nối tiếp có ngữ cảnh.
    history_context = build_history_context(question, chat_history, last_entities)

    system_text = (
        "Bạn là chuyên gia phân tích dữ liệu kho hàng. Dữ liệu bên dưới chỉ là dữ liệu hiện tại; "
        "lịch sử hội thoại được cung cấp để hiểu câu hỏi nối tiếp.\n\n"
        + context + "\n\n"
        "LỊCH SỬ HỘI THOẠI GẦN ĐÂY:\n" + (history_context or "(Không có — đây là câu hỏi độc lập, chỉ dùng dữ liệu bên trên)") + "\n\n"
        "QUY TẮC BẮT BUỘC KHI TRẢ LỜI:\n"
        "0. Với câu hỏi nối tiếp như 'các sản phẩm trên', chỉ xét đúng các sản phẩm trong câu trả lời trước liên quan; không mở rộng sang toàn bộ kho. Nếu thiếu dữ liệu, nói rõ, không đoán.\n"
        "1. QUY TẮC TRA CỨU SỐ LIỆU: Tự động xác định đúng bảng tổng hợp/tồn kho/danh mục phù hợp nhất trong dữ liệu được cung cấp (ví dụ các tab tồn kho theo mã hàng, danh mục sản phẩm...). Đọc đúng tên cột thực tế của file, đối chiếu chính xác từng hàng theo đúng mã/tên sản phẩm, tuyệt đối không lấy nhầm số liệu của dòng khác hoặc tự suy diễn.\n"
        "2. Ưu tiên câu trả lời NGẮN GỌN, trực tiếp: nêu kết quả chính ngay đầu; thường chỉ 1-3 câu, chỉ thêm bảng khi giúp đọc số liệu dễ hơn.\n"
        "3. Với câu hỏi so sánh/xếp hạng, chỉ đưa tên/mã, số lượng và đơn vị cần thiết; nêu kết luận một lần. Không nhắc lại yêu cầu, không mô tả quy trình tra cứu, không lặp lại cùng số liệu ở nhiều đoạn, không thêm lời dẫn hoặc kết luận dài dòng.\n"
        "4. Vẫn phải đủ thông tin để kiểm chứng: giữ nguyên tên/mã sản phẩm, số liệu và đơn vị; nếu so sánh nhiều sản phẩm thì dùng bảng gọn. Không bỏ các dữ kiện quan trọng chỉ để rút ngắn.\n"
        "5. Nếu người dùng yêu cầu phân tích chi tiết, giải thích hoặc báo cáo đầy đủ thì mới trả lời dài hơn theo yêu cầu.\n"
        "6. NẾU NGƯỜI DÙNG YÊU CẦU VẼ BIỂU ĐỒ: Viết mã Python vẽ biểu đồ bằng `plotly.express` (gán kết quả vào biến `fig`). Đặt mã trong khối ```python ... ```."
        + rule7
    )

    body = {
        "contents": [{"role": "user", "parts": [{"text": system_text + "\n\nCÂU HỎI CỦA NGƯỜI DÙNG: " + question}]}],
        "generationConfig": {
            "maxOutputTokens": 16384,
            "temperature": 0.0
        }
    }

    # Ưu tiên các model Flash/Pro tiêu chuẩn (tránh dùng bản lite dễ lệch cột khi đọc bảng lớn)
    preferred_models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro-latest",
    ]
    discovered_models = []
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        l_resp = requests.get(list_url, timeout=10)
        if l_resp.status_code == 200:
            m_list = l_resp.json().get("models", [])
            for m in m_list:
                m_name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                # Chỉ nhận model văn bản chuẩn; loại preview/computer-use/tts/image/exp...
                if "generateContent" in methods and re.fullmatch(r"gemini-\d+(\.\d+)?-(flash|pro)(-latest)?", m_name):
                    discovered_models.append(m_name)
    except Exception:
        pass

    candidate_models = list(dict.fromkeys(preferred_models + discovered_models))

    last_error = ""
    quota_error = ""
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        for attempt in range(2):  # thử lại 1 lần với lỗi tạm thời 5xx
            try:
                resp = requests.post(url, params={"key": api_key}, json=body, timeout=60)
            except Exception as e:
                last_error = f"[{model_name}]: {str(e)}"
                break
            if resp.status_code == 200:
                res_json = resp.json()
                candidates = res_json.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    full_text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
                    if full_text:
                        need = re.match(r"\s*CẦN_TAB\s*:\s*(.+)", full_text)
                        if need and _retry and omitted:
                            wanted = {_tabkey(w) for w in re.split(r"[,;]", need.group(1)) if w.strip()}
                            more = [k for k in omitted if _sheet_base(k) in wanted]
                            if more:  # AI báo thiếu tab → gửi lại đúng 1 lần kèm tab đó
                                _log_ask(question, model_name, selected, omitted, more)
                                return ask_ai(question, sheets_dict, chat_history, last_entities,
                                              extra_tabs=list(extra_tabs or []) + more, _retry=False)
                        if need:
                            full_text = "⚠️ AI báo thiếu dữ liệu (" + need.group(1).strip() + ") nên chưa thể trả lời chắc chắn."
                        _log_ask(question, model_name, selected, omitted, list(extra_tabs or []))
                        if candidates[0].get("finishReason") == "MAX_TOKENS":
                            full_text += "\n\n⚠️ _Câu trả lời bị cắt do giới hạn độ dài. Hãy hỏi hẹp hơn (theo nhóm hàng / theo kho) để xem đủ._"
                        return f"🤖 **[Phân tích bởi AI ({model_name}) · gửi {len(selected)}/{len(sheets_dict)} tab]**\n\n{full_text}"
                last_error = f"[{model_name}]: phản hồi rỗng"
                break
            try:
                err_msg = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                err_msg = resp.text
            if "api key not valid" in err_msg.lower() or "invalid authentication credentials" in err_msg.lower():
                raise Exception("🔑 **API Key không hợp lệ hoặc đã hết hạn!**\nVui lòng kiểm tra lại API Key.")
            if resp.status_code == 429 or "quota" in err_msg.lower():
                if not quota_error:
                    m = re.search(r"retry in ([0-9hms\.]+)", err_msg)
                    quota_error = m.group(1).rstrip(".") if m else "một lúc"
                last_error = f"[{model_name}]: hết hạn mức"
                break  # model này hết hạn mức → thử model khác
            last_error = f"[{model_name}]: {err_msg}"
            if resp.status_code >= 500 and attempt == 0:
                time.sleep(2)
                continue
            break

    if quota_error:
        raise Exception(
            "⏳ **Đã hết hạn mức gọi Gemini API (gói miễn phí).** Hãy thử lại sau khoảng "
            f"**{quota_error}**, hoặc bật thanh toán/đổi API key. Các câu hỏi tra cứu trực tiếp (tồn an toàn, tồn theo vị trí, tổng giá trị) vẫn chạy không cần AI."
        )
    raise Exception(f"Lỗi kết nối AI. Chi tiết: {last_error}")

def _clean_cell(x: str) -> str:
    return re.sub(r"[*`]|<br\s*/?>", lambda m: "\n" if m.group(0).startswith("<") else "", x).strip()


def _render_text_with_tables(text: str):
    """Bảng markdown → st.dataframe (hiện đủ mọi dòng, cuộn khi quá dài); phần còn lại → st.markdown."""
    lines = text.split("\n")
    buf, i = [], 0

    def flush():
        if buf and "".join(buf).strip():
            st.markdown("\n".join(buf))
        buf.clear()

    sep_re = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
    while i < len(lines):
        if lines[i].strip().startswith("|") and i + 1 < len(lines) and sep_re.match(lines[i + 1]):
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            try:
                split = lambda ln: [_clean_cell(c) for c in ln.strip().strip("|").split("|")]
                header = split(lines[i])
                rows = []
                for ln in lines[i + 2:j]:
                    cells = split(ln)
                    cells = (cells + [""] * len(header))[:len(header)]
                    rows.append(cells)
                df = pd.DataFrame(rows, columns=header)
                flush()
                height = min(38 + 35 * (len(df) + 1), 900)
                st.dataframe(df, use_container_width=True, hide_index=True, height=height)
            except Exception:
                buf.extend(lines[i:j])
            i = j
        else:
            buf.append(lines[i])
            i += 1
    flush()


# HÀM HIỂN THỊ: chỉ ẩn khối code vẽ biểu đồ; giữ nguyên mọi khối khác (bảng, mã...)
def render_message_and_chart(content: str, sheets_dict: dict):
    code_pattern = r"```(?:python|py)?\s*(.*?)\s*```"
    plot_blocks = []

    def _keep_or_extract(m):
        block = m.group(1)
        if any(kw in block for kw in ["plotly", "px.", "fig"]):
            plot_blocks.append(block)
            return ""
        return m.group(0)  # không phải code biểu đồ → giữ lại, không xóa mất nội dung

    clean_text = re.sub(code_pattern, _keep_or_extract, content, flags=re.DOTALL).strip()

    if clean_text:
        _render_text_with_tables(clean_text)

    for code_block in plot_blocks:
        try:
            local_vars = {"sheets_dict": sheets_dict, "pd": pd, "px": px}
            exec(code_block, globals(), local_vars)
            if "fig" in local_vars:
                st.plotly_chart(local_vars["fig"], use_container_width=True)
        except Exception as exc:
            st.caption(f"⚠️ Không vẽ được biểu đồ: {exc}")

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
        gsheet_urls_input = st.text_area(
            "Link Google Trang tính (mỗi link một dòng)",
            key="gsheet_urls_input",
            height=120,
            placeholder="https://docs.google.com/spreadsheets/d/…/edit\nhttps://docs.google.com/spreadsheets/d/…/edit",
            help="Dán một hoặc nhiều link Google Sheets, mỗi link trên một dòng. Mỗi bảng tính phải được chia sẻ quyền xem cho ứng dụng.",
        )
        gsheet_urls = list(dict.fromkeys(
            line.strip()
            for line in gsheet_urls_input.splitlines()
            if line.strip()
        ))

        # Lưu danh sách link mới; duy trì gsheet_url cũ để tương thích với cấu hình phiên bản trước.
        if saved_config.get("gsheet_urls") != gsheet_urls or saved_config.get("gsheet_url", "") != (gsheet_urls[0] if gsheet_urls else ""):
            saved_config["gsheet_urls"] = gsheet_urls
            saved_config["gsheet_url"] = gsheet_urls[0] if gsheet_urls else ""
            save_json_data(CONFIG_PATH, saved_config)
        st.session_state.gsheet_url = gsheet_urls[0] if gsheet_urls else ""

        if gsheet_urls:
            with st.spinner(f"Đang đọc {len(gsheet_urls)} link Google Sheets..."):
                sheets_data, gsheet_errors = load_all_sheets_from_multiple_gsheets(gsheet_urls)
            if sheets_data:
                st.success(f"✅ Đã đọc {len(gsheet_urls) - len(gsheet_errors)}/{len(gsheet_urls)} link và tải {len(sheets_data)} tab dữ liệu.")
            if gsheet_errors:
                st.warning("Một số link chưa đọc được:\n\n" + "\n".join(f"- {message}" for message in gsheet_errors))
            if not sheets_data and not gsheet_errors:
                st.warning("Các Google Sheets đã kết nối nhưng không có tab dữ liệu để hiển thị.")
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
            sheets_data = load_all_sheets_from_file(str(EXCEL_PATH), os.path.getmtime(EXCEL_PATH))
            st.info(f"ℹ️ Đang sử dụng file Excel đã lưu sẵn ({len(sheets_data)} sheet). Tải file lên để thay dữ liệu đang dùng.")

    if sheets_data:
        with st.expander("🧩 Cấu hình tab gửi cho AI", expanded=False):
            _cfg = load_tab_config()
            _keys = list(sheets_data.keys())
            _sig = hashlib.md5("|".join(_keys).encode("utf-8")).hexdigest()[:8]
            _wanted_core = {_tabkey(t) for t in _cfg.get("core_tabs", [])}
            _configured = any(_sheet_base(k) in _wanted_core for k in _keys)
            if not _configured:
                st.caption("Chưa có tab lõi nào khớp file này → đang TỰ NHẬN DIỆN (tab ≤150 dòng hoặc tên có \"tổng hợp / tồn / danh mục...\"). "
                           "Chọn tab lõi bên dưới rồi bấm Lưu để cố định.")
            _core_default = sorted(effective_core_keys(sheets_data, _cfg), key=_keys.index)
            _excl_wanted = {_tabkey(t) for t in _cfg.get("exclude_tabs", [])}
            _excl_default = [k for k in _keys if _sheet_base(k) in _excl_wanted]
            _core_sel = st.multiselect("Tab lõi (luôn gửi cho AI)", _keys, default=_core_default, key=f"tabcfg_core_{_sig}")
            _excl_sel = st.multiselect("Tab KHÔNG gửi (vd tab chứa đáp án mẫu)", _keys, default=_excl_default, key=f"tabcfg_excl_{_sig}")
            _hints_txt = st.text_area(
                "Gợi ý từ khóa → tab (JSON)",
                value=json.dumps(_cfg.get("tab_hints", []), ensure_ascii=False, indent=1),
                height=160, key=f"tabcfg_hints_{_sig}",
                help='Mỗi mục: {"keywords": ["xe nhập", "eta"], "tabs": ["LICH_XE_NHAP"]}. Câu hỏi chứa từ khóa thì gửi thêm các tab này.',
            )
            _c1, _c2 = st.columns(2)
            if _c1.button("💾 Lưu cấu hình", use_container_width=True, key=f"tabcfg_save_{_sig}"):
                try:
                    _hints = json.loads(_hints_txt or "[]")
                    assert isinstance(_hints, list) and all(isinstance(h, dict) for h in _hints)
                    save_json_data(TAB_CONFIG_PATH, {
                        "core_tabs": [k.split("·")[-1].strip() for k in _core_sel],
                        "exclude_tabs": [k.split("·")[-1].strip() for k in _excl_sel],
                        "tab_hints": _hints,
                    })
                    st.success("Đã lưu. Áp dụng từ câu hỏi tiếp theo.")
                except Exception as _exc:
                    st.error(f"JSON gợi ý không hợp lệ: {_exc}")
            if _c2.button("↩️ Về mặc định", use_container_width=True, key=f"tabcfg_reset_{_sig}"):
                try:
                    TAB_CONFIG_PATH.unlink(missing_ok=True)
                except Exception:
                    pass
                for _k in (f"tabcfg_core_{_sig}", f"tabcfg_excl_{_sig}", f"tabcfg_hints_{_sig}"):
                    st.session_state.pop(_k, None)
                st.rerun()

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
        ["số lượng tồn"], ["tồn kho"], ["stock"], ["sellable"], ["co_the_ban"],
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
    """Đọc số từ Excel/Sheets theo cả định dạng Việt Nam và quốc tế."""
    def parse_one(value):
        if pd.isna(value):
            return float("nan")
        text = str(value).strip().replace(" ", "")
        if not text or text.lower() in {"nan", "none", "nat", "-"}:
            return float("nan")

        if "," in text and "." in text:
            # Ký tự phân cách xuất hiện cuối cùng thường là dấu thập phân.
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+", text):
                text = text.replace(",", "")
            else:
                text = text.replace(",", ".")
        elif "." in text:
            # Ví dụ "1.250" thường là 1.250 đơn vị theo chuẩn quốc tế,
            # nhưng cũng là 1.250 (một nghìn hai trăm năm mươi) theo cách ghi VN.
            # Chỉ coi dấu chấm là phân cách hàng nghìn khi nhóm 3 chữ số lặp rõ ràng.
            if re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+", text):
                text = text.replace(".", "")

        try:
            return float(text)
        except (TypeError, ValueError):
            return float("nan")

    return pd.Series(series.map(parse_one), index=series.index, dtype="float64")

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
    preferred = (
        next((item for item in stock_candidates if item[3] is not None), stock_candidates[0])
        if stock_candidates else candidates[0]
    )
    source_names = [item[0] for item in candidates]
    if len(source_names) > 1:
        selected_name = st.selectbox(
            "Nguồn dữ liệu hiển thị (chọn sheet tồn kho hoặc sheet nhập/xuất)",
            source_names,
            index=source_names.index(preferred[0]),
            key="warehouse_dashboard_source_sheet",
        )
        selected = next(item for item in candidates if item[0] == selected_name)
    else:
        selected = candidates[0]
    selected_name, df, stock_col, min_stock_col = selected
    if stock_col is None:
        st.info("Sheet đang chọn không có cột tồn kho hiện tại; Dashboard sẽ ưu tiên hiển thị số liệu nhập/xuất nếu có.")

    category_col = _find_column(df, [
        ["loại hàng"], ["nhóm hàng"], ["nhom_hang"], ["nhom"], ["danh mục"], ["category"], ["loại sản phẩm"],
    ])
    name_col = _find_column(df, [
        ["tên hàng"], ["tên sản phẩm"], ["ten_san_pham"], ["tên vật tư"], ["mặt hàng"], ["name"], ["tên"],
    ])
    code_col = _find_column(df, [
        ["mã hàng"], ["mã sản phẩm"], ["ma_sku"], ["ma_lo"], ["mã vật tư"], ["mã sp"], ["code"], ["mã"],
    ])
    unit_col = _find_column(df, [["đơn vị"], ["don_vi"], ["unit"]])

    # Nhận diện các cột luân chuyển theo tên cột cụ thể; không lấy cột ngày/đơn giá làm số lượng.
    inbound_col = _find_column(df, [
        ["số lượng nhập"], ["lượng nhập"], ["sl nhập"], ["sl_nhap"], ["nhap_thuc"], ["tổng nhập"], ["nhập kho"],
        ["inbound qty"], ["qty in"],
    ])
    outbound_col = _find_column(df, [
        ["số lượng xuất"], ["lượng xuất"], ["sl xuất"], ["sl_xuat"], ["xuat_thuc"], ["tổng xuất"], ["xuất kho"],
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
            return "Chưa xác định"
        return f"{value:,.2f}".rstrip("0").rstrip(".")

    # Đếm phiên bằng mã phiếu/chứng từ/giao dịch, không nhầm tổng số lượng thành số phiên.
    document_col_groups = [
        ["mã phiếu"], ["số phiếu"], ["mã chứng từ"], ["số chứng từ"],
        ["mã giao dịch"], ["số giao dịch"], ["mã phiên"], ["mã đơn"],
        ["transaction id"], ["voucher no"], ["document no"], ["receipt no"],
    ]

    def count_sessions(direction):
        if direction == "in":
            movement_groups = [
                ["số lượng nhập"], ["lượng nhập"], ["sl nhập"], ["nhập kho"],
                ["inbound qty"], ["qty in"],
            ]
            direction_terms = ["nhập", "nhap", "inbound", "receipt"]
            opposite_terms = ["xuất", "xuat", "outbound", "shipment"]
        elif direction == "out":
            movement_groups = [
                ["số lượng xuất"], ["lượng xuất"], ["sl xuất"], ["xuất kho"],
                ["outbound qty"], ["qty out"],
            ]
            direction_terms = ["xuất", "xuat", "outbound", "shipment"]
            opposite_terms = ["nhập", "nhap", "inbound", "receipt"]
        else:
            movement_groups = [
                ["số lượng điều chuyển"], ["lượng điều chuyển"], ["sl điều chuyển"],
                ["transfer qty"],
            ]
            direction_terms = ["điều chuyển", "dieu chuyen", "transfer"]
            opposite_terms = []

        session_total = 0
        found = False
        for sheet_label, frame in sheets_dict.items():
            if frame is None or frame.dropna(how="all").empty:
                continue
            clean = frame.dropna(how="all").copy()
            label = str(sheet_label).lower()
            has_direction_name = any(term in label for term in direction_terms)
            has_opposite_name = any(term in label for term in opposite_terms)
            qty_col = _find_column(clean, movement_groups)

            # Chỉ đếm trong sheet có tên đúng luồng hoặc có cột số lượng đúng luồng.
            if has_opposite_name and not has_direction_name:
                continue
            if not has_direction_name and qty_col is None:
                continue

            doc_col = _find_column(clean, document_col_groups)
            if doc_col is None:
                continue

            session_rows = clean[doc_col].astype(str).str.strip()
            valid_mask = clean[doc_col].notna() & ~session_rows.str.lower().isin(["", "nan", "none", "nat"])
            if qty_col is not None:
                qty = _numeric_column(clean[qty_col])
                valid_mask = valid_mask & qty.notna() & (qty > 0)
            session_ids = session_rows[valid_mask].drop_duplicates()
            if not session_ids.empty:
                session_total += int(session_ids.nunique())
                found = True

        return session_total if found else None

    # Số sản phẩm được đếm theo mã duy nhất; nếu không có mã thì dùng tên duy nhất.
    if code_col is not None:
        product_values = df[code_col].astype(str).str.strip()
        product_count = int(product_values[
            df[code_col].notna() & ~product_values.str.lower().isin(["", "nan", "none", "nat"])
        ].nunique())
    elif name_col is not None:
        product_values = df[name_col].astype(str).str.strip()
        product_count = int(product_values[
            df[name_col].notna() & ~product_values.str.lower().isin(["", "nan", "none", "nat"])
        ].nunique())
    else:
        product_count = int(len(df))

    inbound_sessions = count_sessions("in")
    outbound_sessions = count_sessions("out")
    transfer_sessions = count_sessions("transfer")

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric(
        "Phiên nhập",
        show_number(inbound_sessions),
        icon="📥",
        border=True,
        help="Đếm mã phiếu/chứng từ nhập duy nhất trong dữ liệu giao dịch. Nếu chưa xác định được, cần có cột Mã phiếu hoặc Mã chứng từ.",
    )
    metric2.metric(
        "Phiên xuất",
        show_number(outbound_sessions),
        icon="📤",
        border=True,
        help="Đếm mã phiếu/chứng từ xuất duy nhất trong dữ liệu giao dịch. Nếu chưa xác định được, cần có cột Mã phiếu hoặc Mã chứng từ.",
    )
    metric3.metric(
        "Sản phẩm",
        f"{product_count:,}",
        icon="📦",
        border=True,
        help="Số mã sản phẩm duy nhất (hoặc tên sản phẩm duy nhất nếu bảng không có cột mã). Đây không phải tổng số lượng tồn.",
    )
    metric4.metric(
        "Phiên điều chuyển",
        show_number(transfer_sessions),
        icon="🔁",
        border=True,
        help="Đếm mã phiếu/chứng từ điều chuyển duy nhất nếu dữ liệu có thể nhận diện.",
    )
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
                    _prev = st.session_state.messages[:-1]
                    _last_ans = next((m["content"] for m in reversed(_prev)
                                      if m.get("role") != "user" and not str(m.get("content", "")).startswith("❌")), "")
                    final_ans = ask_ai(question, sheets_data, _prev, extract_entities(_last_ans))
                except Exception as e:
                    final_ans = f"❌ {str(e)}"

            with st.chat_message("assistant"):
                render_message_and_chart(final_ans, sheets_data)

            st.session_state.messages.append({"role": "assistant", "content": final_ans})
            save_chat_history()
        st.rerun()
