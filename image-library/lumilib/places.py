"""離線地名：把 GPS 座標換成最近的城鎮名稱（中文優先），完全不需要連網。

資料來自 GeoNames（CC BY 4.0，https://www.geonames.org），精簡後內附在 lumilib/data/places.tsv.gz。
"""

from __future__ import annotations

import gzip
import sqlite3
import threading
from pathlib import Path

import numpy as np

from . import db

COUNTRY_ZH = {
    "TW": "台灣", "JP": "日本", "KR": "韓國", "CN": "中國", "HK": "香港", "MO": "澳門", "US": "美國", "GB": "英國",
    "FR": "法國", "DE": "德國", "IT": "義大利", "ES": "西班牙", "PT": "葡萄牙", "NL": "荷蘭", "BE": "比利時",
    "CH": "瑞士", "AT": "奧地利", "CZ": "捷克", "HU": "匈牙利", "PL": "波蘭", "GR": "希臘", "TR": "土耳其",
    "IS": "冰島", "NO": "挪威", "SE": "瑞典", "FI": "芬蘭", "DK": "丹麥", "IE": "愛爾蘭", "HR": "克羅埃西亞",
    "SI": "斯洛維尼亞", "RU": "俄羅斯", "TH": "泰國", "VN": "越南", "SG": "新加坡", "MY": "馬來西亞", "ID": "印尼",
    "PH": "菲律賓", "KH": "柬埔寨", "LA": "寮國", "MM": "緬甸", "IN": "印度", "NP": "尼泊爾", "LK": "斯里蘭卡",
    "MV": "馬爾地夫", "MN": "蒙古", "AE": "阿聯酋", "QA": "卡達", "JO": "約旦", "IL": "以色列", "EG": "埃及",
    "MA": "摩洛哥", "ZA": "南非", "KE": "肯亞", "TZ": "坦尚尼亞", "AU": "澳洲", "NZ": "紐西蘭", "CA": "加拿大",
    "MX": "墨西哥", "BR": "巴西", "AR": "阿根廷", "PE": "祕魯", "CL": "智利", "BO": "玻利維亞", "CU": "古巴",
    "GU": "關島", "PW": "帛琉", "FJ": "斐濟", "MP": "北馬里亞納群島",
}

# 常見簡體字：挑名字時優先選不含這些字的（偏向繁體）
_SIMPLIFIED = set("区县门东广汉湾台岛乡镇丰兰龙凤岭阳仑义兴宁贵辽苏闽赣鲁鄂湘粤琼渝陕园恒长马里乐泽桥")

_data: dict | None = None
_lock = threading.Lock()


def _zh_name(alternates: list[str]) -> str | None:
    cjk = [a for a in alternates if a and all("㐀" <= ch <= "鿿" or ch in "・" for ch in a)]
    if not cjk:
        return None
    cjk.sort(key=lambda a: (sum(ch in _SIMPLIFIED for ch in a), len(a)))
    return cjk[0]


DATA_DIR = Path(__file__).parent / "data"


def _load() -> dict:
    global _data
    with _lock:
        if _data is not None:
            return _data
        lats, lons, en, zh, cc = [], [], [], [], []
        with gzip.open(DATA_DIR / "places.tsv.gz", "rt", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) != 5:
                    continue
                lats.append(float(parts[0]))
                lons.append(float(parts[1]))
                en.append(parts[2])
                zh.append(parts[3] or None)
                cc.append(parts[4])
        countries = {}
        with gzip.open(DATA_DIR / "countries.tsv.gz", "rt", encoding="utf-8") as f:
            for line in f:
                code, _, name = line.rstrip("\n").partition("\t")
                countries[code] = name
        lat = np.radians(np.array(lats))
        lon = np.radians(np.array(lons))
        xyz = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=1).astype(np.float32)
        _data = {"xyz": xyz, "en": en, "zh": zh, "cc": cc, "country_en": countries}
        return _data


def available() -> bool:
    return (DATA_DIR / "places.tsv.gz").exists()


def lookup(points: list[tuple[float, float]]) -> list[dict]:
    """[(lat, lon)] → [{place, place_en, country, country_zh, country_en, km}]"""
    if not points:
        return []
    d = _load()
    lat = np.radians(np.array([p[0] for p in points]))
    lon = np.radians(np.array([p[1] for p in points]))
    q = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=1).astype(np.float32)
    out = []
    for i in range(0, len(q), 512):
        sims = q[i:i + 512] @ d["xyz"].T
        best = sims.argmax(axis=1)
        for j, k in enumerate(best):
            cc = d["cc"][k]
            km = float(np.degrees(np.arccos(np.clip(sims[j, k], -1, 1))) * 111.2)
            out.append({
                "place": d["zh"][k] or d["en"][k],
                "place_en": d["en"][k],
                "country": cc,
                "country_zh": COUNTRY_ZH.get(cc, d["country_en"].get(cc, cc)),
                "country_en": d["country_en"].get(cc, cc),
                "km": km,
            })
    return out


def geocode_images(conn: sqlite3.Connection, progress=None) -> int:
    """替有 GPS 但還沒有地名的照片補上地名。"""
    if not available():
        return 0
    rows = conn.execute(
        "SELECT id, lat, lon FROM images WHERE lat IS NOT NULL AND lon IS NOT NULL AND place IS NULL"
    ).fetchall()
    if not rows:
        return 0
    if progress:
        progress(f"換算地名：{len(rows)} 個位置")
    results = lookup([(r["lat"], r["lon"]) for r in rows])
    for row, res in zip(rows, results):
        far = res["km"] > 80  # 離最近城鎮太遠（海上、荒野）只標國家
        conn.execute(
            "UPDATE images SET place = ?, place_en = ?, country = ? WHERE id = ?",
            ("" if far else res["place"], "" if far else res["place_en"], res["country"], row["id"]),
        )
        db.refresh_search_text(conn, row["id"])
    conn.commit()
    return len(rows)


def country_names(cc: str | None) -> tuple[str, str]:
    if not cc:
        return "", ""
    zh = COUNTRY_ZH.get(cc)
    try:
        en = _load()["country_en"].get(cc, cc)
    except OSError:
        en = cc
    return zh or en, en
