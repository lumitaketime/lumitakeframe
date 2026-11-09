"""星等、顏色標籤、拒絕與關鍵字：只存在圖庫資料庫裡，不會寫入硬碟上的任何檔案。

- 星等：1–5，-1 代表拒絕（檢視器按 X），0 或空白代表清除。
- 顏色標籤：紅、黃、綠、藍、紫。掃描時從照片檔案內的中繼資料讀取（例如其他軟體寫入的 Label），
  各語系的寫法都會換成同一個標準名稱。
"""

from __future__ import annotations

import json
import sqlite3

from . import db

# 顏色標籤：標準名稱 → 各語系軟體可能寫入的文字
LABELS = {
    "red": ["Red", "紅色", "红色", "レッド", "Rot", "Rouge", "Rojo", "Rosso"],
    "yellow": ["Yellow", "黃色", "黄色", "イエロー", "Gelb", "Jaune", "Amarillo", "Giallo"],
    "green": ["Green", "綠色", "绿色", "グリーン", "Grün", "Vert", "Verde"],
    "blue": ["Blue", "藍色", "蓝色", "ブルー", "Blau", "Bleu", "Azul", "Blu"],
    "purple": ["Purple", "紫色", "パープル", "Lila", "Violet", "Morado", "Viola"],
}
_LOOKUP = {name.lower(): key for key, names in LABELS.items() for name in names}


def normalize_label(text) -> str | None:
    if not text:
        return None
    return _LOOKUP.get(str(text).strip().lower())


def update(conn: sqlite3.Connection, image_id: int, rating=None, label=None, keywords=None) -> None:
    """更新圖庫裡的星等、顏色標籤、關鍵字（只改資料庫，不動檔案）。"""
    image = db.get_image(conn, image_id)
    if image is None:
        raise ValueError("找不到這個檔案")
    if label is not None and label != "" and label not in LABELS:
        raise ValueError("未知的顏色標籤")
    if rating is not None and not (-1 <= int(rating) <= 5):
        raise ValueError("星等必須是 -1（拒絕）到 5")

    updates, params = [], []
    if rating is not None:
        updates.append("rating = ?")
        params.append(int(rating) if int(rating) != 0 else None)
    if label is not None:
        updates.append("label = ?")
        params.append(label or None)
    if keywords is not None:
        clean = list(dict.fromkeys(k.strip() for k in keywords if k and k.strip()))
        updates += ["keywords = ?", "user_tags = ?"]
        params += [json.dumps(clean, ensure_ascii=False) if clean else None, json.dumps(clean, ensure_ascii=False)]
    if updates:
        conn.execute(f"UPDATE images SET {', '.join(updates)} WHERE id = ?", (*params, image_id))
        db.refresh_search_text(conn, image_id)
        conn.commit()
