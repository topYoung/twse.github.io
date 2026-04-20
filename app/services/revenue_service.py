"""
revenue_service.py

從公開資訊觀測站 (MOPS) 抓取台灣上市/上櫃公司每月營收，
計算月增率 (MOM) 與年增率 (YOY)，並提供帶快取的查詢介面。

資料來源：
  上市：https://mops.twse.com.tw/nas/t21/sii/t21sc03_{民國年}_{月}_0.html
  上櫃：https://mops.twse.com.tw/nas/t21/otc/t21sc03_{民國年}_{月}_0.html
"""

import requests
import pandas as pd
import threading
import time
import logging
from io import StringIO
from datetime import datetime, date
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 快取：TTL = 6 小時（月營收不需要高頻更新）
# ──────────────────────────────────────────────────────────────
_revenue_cache: Dict = {
    "data": None,        # {stock_code: {"mom": float|None, "yoy": float|None, "revenue": int|None}}
    "last_update": 0.0,
}
_cache_lock = threading.Lock()
_CACHE_TTL = 6 * 3600  # 6 小時


# ──────────────────────────────────────────────────────────────
# 輔助：民國年月計算
# ──────────────────────────────────────────────────────────────

def _get_latest_revenue_month() -> Tuple[int, int]:
    """
    回傳目前應查詢的「最新」月份（民國年, 月）。

    MOPS 月營收通常在每月 10 日前後公告。
    - 今日 > 10 日：使用上個月（例如 4/17 → 用 3 月資料）
    - 今日 <= 10 日：往前推兩個月（例如 4/8 → 用 2 月資料）
    這樣可以確保取到已公告的最新月份。
    """
    today = date.today()
    # 月初尚未公告，往前推一個月
    if today.day <= 10:
        # 前兩個月
        month = today.month - 2
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
    else:
        # 上個月
        month = today.month - 1
        year = today.year
        if month <= 0:
            month = 12
            year -= 1

    roc_year = year - 1911
    return roc_year, month


def _prev_month(roc_year: int, month: int) -> Tuple[int, int]:
    """回傳前一個月的 (民國年, 月)"""
    m = month - 1
    y = roc_year
    if m <= 0:
        m = 12
        y -= 1
    return y, m


def _same_month_last_year(roc_year: int, month: int) -> Tuple[int, int]:
    """回傳去年同月的 (民國年, 月)"""
    return roc_year - 1, month


# ──────────────────────────────────────────────────────────────
# 核心：從 MOPS 抓取單月所有股票的營收
# ──────────────────────────────────────────────────────────────

def _fetch_mops_revenue(roc_year: int, month: int) -> Dict[str, int]:
    """
    從 MOPS 抓取指定年月的所有股票營收（上市 + 上櫃）。

    Returns:
        {stock_code: monthly_revenue_in_thousands}
        若抓取失敗回傳空 dict。
    """
    result: Dict[str, int] = {}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    # 上市 (sii) + 上櫃 (otc)
    markets = [("sii", "上市"), ("otc", "上櫃")]

    for market_code, market_name in markets:
        url = (
            f"https://mops.twse.com.tw/nas/t21/{market_code}/"
            f"t21sc03_{roc_year}_{month}_0.html"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.encoding = "big5"

            # 使用 StringIO 包裝，修復 FutureWarning
            dfs = pd.read_html(StringIO(resp.text), thousands=",")

            for df in dfs:
                # 尋找含有「公司代號」欄位的表格
                # 根據 MOPS 格式，欄名可能在第一列
                if df.shape[1] < 4:
                    continue

                # 嘗試找到正確的表格（含股票代號與營收）
                # MOPS 的欄位結構（pandas MultiIndex 後展平）：
                # 公司代號 | 公司名稱 | 當月營收 | 當月累計營收 | ...
                col_names = [str(c) for c in df.columns]
                header_row = None

                # 有時表頭在第 0 列的資料列中
                for idx, row in df.iterrows():
                    row_vals = [str(v) for v in row.values]
                    if any("公司代號" in v or "代號" in v for v in row_vals):
                        header_row = idx
                        break

                if header_row is not None:
                    # 重設表頭
                    df.columns = df.iloc[header_row].values
                    df = df.iloc[header_row + 1:].reset_index(drop=True)

                # 標準化欄名（找股票代號欄 & 當月營收欄）
                df.columns = [str(c).strip() for c in df.columns]

                code_col = None
                rev_col = None

                for c in df.columns:
                    c_clean = c.replace(" ", "").replace("\n", "")
                    if "公司代號" in c_clean or c_clean == "代號":
                        code_col = c
                    if "當月營收" in c_clean and rev_col is None:
                        rev_col = c

                if code_col is None or rev_col is None:
                    continue

                for _, row in df.iterrows():
                    code = str(row[code_col]).strip()
                    rev_raw = str(row[rev_col]).strip().replace(",", "")

                    # 過濾非代號列（例如 '合計' 或 NaN）
                    if not code.isdigit() or len(code) < 4:
                        continue

                    try:
                        revenue = int(float(rev_raw))
                        result[code] = revenue
                    except (ValueError, TypeError):
                        continue

        except Exception as e:
            logger.warning(f"[revenue_service] 抓取 {market_name} {roc_year}年{month}月 失敗: {e}")
            continue

    return result


# ──────────────────────────────────────────────────────────────
# 公開介面
# ──────────────────────────────────────────────────────────────

def build_revenue_map(force_refresh: bool = False) -> Dict[str, Dict]:
    """
    整合三個月份資料，計算每檔股票的 MOM / YOY，並快取結果。

    Returns:
        {
            "2330": {"mom": 25.3, "yoy": 42.1, "revenue": 280000000},
            "2454": {"mom": None, "yoy": 18.0, "revenue": 12000000},
            ...
        }
        mom/yoy 為 None 代表該月資料缺失，無法計算。
    """
    global _revenue_cache

    current_time = time.time()

    with _cache_lock:
        if (
            not force_refresh
            and _revenue_cache["data"] is not None
            and current_time - _revenue_cache["last_update"] < _CACHE_TTL
        ):
            return _revenue_cache["data"]

    logger.info("[revenue_service] 開始從 MOPS 抓取月營收資料...")

    # 決定最新月份
    cur_year, cur_month = _get_latest_revenue_month()
    prev_year, prev_month = _prev_month(cur_year, cur_month)
    ly_year, ly_month = _same_month_last_year(cur_year, cur_month)

    logger.info(
        f"[revenue_service] 抓取月份：最新={cur_year}年{cur_month}月 "
        f"上月={prev_year}年{prev_month}月 "
        f"去年同月={ly_year}年{ly_month}月"
    )

    # 抓取三個月份
    cur_data = _fetch_mops_revenue(cur_year, cur_month)
    prev_data = _fetch_mops_revenue(prev_year, prev_month)
    ly_data = _fetch_mops_revenue(ly_year, ly_month)

    logger.info(
        f"[revenue_service] 抓取完成：最新={len(cur_data)}筆 "
        f"上月={len(prev_data)}筆 去年同月={len(ly_data)}筆"
    )

    # 計算 MOM / YOY
    revenue_map: Dict[str, Dict] = {}
    all_codes = set(cur_data.keys()) | set(prev_data.keys())

    for code in all_codes:
        cur_rev = cur_data.get(code)
        prev_rev = prev_data.get(code)
        ly_rev = ly_data.get(code)

        mom: Optional[float] = None
        yoy: Optional[float] = None

        if cur_rev is not None and prev_rev and prev_rev > 0:
            mom = round((cur_rev / prev_rev - 1) * 100, 2)

        if cur_rev is not None and ly_rev and ly_rev > 0:
            yoy = round((cur_rev / ly_rev - 1) * 100, 2)

        revenue_map[code] = {
            "mom": mom,
            "yoy": yoy,
            "revenue": cur_rev,
        }

    with _cache_lock:
        _revenue_cache["data"] = revenue_map
        _revenue_cache["last_update"] = current_time

    logger.info(f"[revenue_service] 快取更新完成，共 {len(revenue_map)} 檔股票")
    return revenue_map


def get_revenue_map(force_refresh: bool = False) -> Dict[str, Dict]:
    """對外公開的快取查詢入口（與 build_revenue_map 相同）"""
    return build_revenue_map(force_refresh)


def get_stock_revenue(stock_code: str) -> Dict:
    """
    查詢單一股票的 MOM/YOY 數據。

    Returns:
        {"mom": float|None, "yoy": float|None, "revenue": int|None}
        若股票代號不在資料中，回傳全為 None 的 dict。
    """
    revenue_map = get_revenue_map()
    return revenue_map.get(stock_code, {"mom": None, "yoy": None, "revenue": None})
