"""Định tuyến câu hỏi kho hàng và xử lý các truy vấn đơn giản không cần gọi AI."""

import pandas as pd


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
