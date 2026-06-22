"""
寶塔線 + 資券協同選股掃描器
===========================
核心邏輯：
  1. 從 TWSE MI_MARGN 取得融資融券當日餘額（上市）
  2. 以「今日餘額 - 前日餘額」判斷資/券的增減方向
  3. 以 3T 寶塔線偵測「翻強」訊號（今日收盤 > 前3根最高收盤，且前一根為陰線）
  4. 依資券結構評分矩陣（資減券增100/資增券增75/資增券減40/資減券減20）給分
  5. 加入成交量、券資比加分
  6. 回傳前 2 名（最高分 + 次高分）

資料來源：
  TWSE MI_MARGN: https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&selectType=ALL
"""

import requests
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
from .yf_rate_limiter import fetch_stock_history
from .stock_data import get_yahoo_ticker

# 快取目錄 & 快取有效期（秒）
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
MARGIN_CACHE_FILE = CACHE_DIR / "margin_data_latest.json"
MARGIN_CACHE_TTL = 3600  # 1 小時（盤後資料一天只更新一次）


# ============================================================
# Section 1：融資融券資料獲取
# ============================================================

def fetch_twse_margin_data() -> Optional[Dict]:
    """
    從 TWSE MI_MARGN API 取得當日融資融券餘額。
    優先讀快取，超過 TTL 才重新抓取。

    Returns:
        {
            'date': 'YYYYMMDD',
            'stocks': {
                '2330': {
                    'name': '台積電',
                    'margin_buy': 買進張數,
                    'margin_sell': 賣出張數,
                    'margin_prev': 前日融資餘額(張),
                    'margin_today': 今日融資餘額(張),
                    'short_buy': 券買進張數,
                    'short_sell': 券賣出張數,
                    'short_prev': 前日融券餘額(張),
                    'short_today': 今日融券餘額(張),
                }
            }
        }
        或 None（失敗時）
    """
    # 檢查快取
    if MARGIN_CACHE_FILE.exists():
        try:
            with open(MARGIN_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if time.time() - cached.get("_fetched_at", 0) < MARGIN_CACHE_TTL:
                return cached
        except Exception:
            pass

    url = "https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&selectType=ALL"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        print("[chips_trend] 正在抓取 TWSE 融資融券資料...")
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        print(f"[chips_trend] TWSE MI_MARGN 抓取失敗: {e}")
        return None

    if raw.get("stat") != "OK":
        print(f"[chips_trend] API stat 異常: {raw.get('stat')}")
        return None

    tables = raw.get("tables", [])
    if len(tables) < 2:
        print("[chips_trend] 找不到融資融券匯總表（tables 數量不足）")
        return None

    # table[1] 為「融資融券彙總」，含 16 欄位：
    # [0]=代號, [1]=名稱,
    # 融資: [2]買進, [3]賣出, [4]現金償還, [5]前日餘額, [6]今日餘額, [7]次一日限額
    # 融券: [8]買進, [9]賣出, [10]現券償還, [11]前日餘額, [12]今日餘額, [13]次一日限額
    # [14]=資券互抵, [15]=註記
    table = tables[1]
    rows = table.get("data", [])
    date_str = raw.get("date", "")

    stocks = {}
    for row in rows:
        if not row or len(row) < 13:
            continue
        code = str(row[0]).strip()
        # 只保留 4 位純數字的上市股票代號（排除 ETF 後綴、上市後補碼等）
        if not (code.isdigit() and len(code) == 4):
            continue

        def to_int(s):
            try:
                return int(str(s).replace(",", "").strip())
            except Exception:
                return 0

        stocks[code] = {
            "name": str(row[1]).strip(),
            "margin_buy": to_int(row[2]),
            "margin_sell": to_int(row[3]),
            "margin_prev": to_int(row[5]),
            "margin_today": to_int(row[6]),
            "short_buy": to_int(row[8]),
            "short_sell": to_int(row[9]),
            "short_prev": to_int(row[11]),
            "short_today": to_int(row[12]),
        }

    result = {
        "date": date_str,
        "stocks": stocks,
        "_fetched_at": time.time(),
    }

    try:
        with open(MARGIN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except Exception as e:
        print(f"[chips_trend] 快取儲存失敗: {e}")

    print(f"[chips_trend] 成功解析 {len(stocks)} 筆融資融券資料（日期：{date_str}）")
    return result


# ============================================================
# Section 2：評分矩陣
# ============================================================

def compute_chip_score(
    margin_delta: int,   # 融資餘額變化（今日 - 前日，單位：張）
    short_delta: int,    # 融券餘額變化（今日 - 前日，單位：張）
    vol_ratio: float,    # 翻強當日成交量 / 5日均量
    short_ratio: float,  # 融券餘額 / 融資餘額（券資比）
) -> Tuple[int, str, str]:
    """
    計算籌碼評分。

    評分矩陣（依資減券增優先順序）：
      資減 + 券增 → 100（最高：黃金換手，空頭回補驅動）
      資增 + 券增 →  75（次高：熱錢湧入，爆發力強）
      資增 + 券減 →  40（中高：散戶抬轎）
      資減 + 券減 →  20（中低：多頭乏力）

    加分項目：
      翻強日成交量 > 5日均量 → +15
      券資比 > 20%           → +10

    Returns:
        (score, structure_label, rank_label)
    """
    is_margin_down = margin_delta < 0   # 融資減少
    is_short_up = short_delta > 0       # 融券增加

    # 基礎分
    if is_margin_down and is_short_up:
        base_score = 100
        structure = "資減券增"
        rank = "🥇 第1優先"
    elif not is_margin_down and is_short_up:
        base_score = 75
        structure = "資增券增"
        rank = "🥈 第2優先"
    elif not is_margin_down and not is_short_up:
        base_score = 40
        structure = "資增券減"
        rank = "第3優先"
    else:
        # is_margin_down and not is_short_up
        base_score = 20
        structure = "資減券減"
        rank = "第4優先"

    bonus = 0
    # 量能加分
    if vol_ratio >= 1.0:   # 翻強日量 >= 5日均量
        bonus += 15
    # 券資比加分
    if short_ratio >= 0.20:
        bonus += 10

    return base_score + bonus, structure, rank


# ============================================================
# Section 3：寶塔線 3T 翻強偵測
# ============================================================

def detect_tower_breakout_3t(hist: pd.DataFrame, periods: int = 3) -> Dict:
    """
    3T 寶塔線翻強偵測。

    算法（依截圖顯示「3T:翻強」定義）：
    逐根追蹤寶塔磚色（bull/bear），規則如下：
      - 若目前為「多頭（白磚）」：
          Close < 最近 periods 根的最低收盤 → 翻弱
      - 若目前為「空頭（黑磚）」：
          Close > 最近 periods 根的最高收盤 → 翻強

    使用滑動視窗（非整段趨勢最高/最低），計算較精確。

    「剛翻強」條件（今日發生）：
      - 昨日寶塔狀態為「空頭」
      - 今日寶塔狀態切換為「多頭」

    Args:
        hist: DataFrame，含 'Close' 欄位（日線）
        periods: 寶塔週期（預設 3T）

    Returns:
        {
            'just_turned_bull': bool,    # 今日剛翻強
            'is_bull': bool,             # 目前為多頭
            'tower_label': str,          # '翻強' / '持續多頭' / '空頭' / '翻弱'
            'breakout_price': float,     # 翻強突破的參考收盤價
            'days_since_turn': int,      # 翻強後幾日（0=今日剛翻）
        }
    """
    NOT_ENOUGH = {
        "just_turned_bull": False,
        "is_bull": False,
        "tower_label": "資料不足",
        "breakout_price": 0.0,
        "days_since_turn": -1,
    }

    if hist is None or hist.empty or len(hist) < periods + 2:
        return NOT_ENOUGH

    closes = hist["Close"].tolist()
    n = len(closes)

    # 初始化：以前幾根計算初始狀態
    # 取前 periods 根的 Close，若最後一根 > 前面最高 → 多頭，否則 → 空頭
    is_bull = closes[periods] > max(closes[:periods])

    states = [is_bull] * (periods + 1)  # 第 0..periods 根的狀態初始化

    breakout_price = closes[periods]
    days_since_turn = -1

    for i in range(periods + 1, n):
        prev_closes = closes[i - periods: i]  # 前 periods 根收盤
        curr_close = closes[i]

        if is_bull:
            # 多頭持續：Close < 近期最低 → 翻弱
            ref_low = min(prev_closes)
            if curr_close < ref_low:
                is_bull = False
                breakout_price = curr_close
                days_since_turn = 0
            elif days_since_turn >= 0:
                days_since_turn += 1
        else:
            # 空頭持續：Close > 近期最高 → 翻強
            ref_high = max(prev_closes)
            if curr_close > ref_high:
                is_bull = True
                breakout_price = curr_close
                days_since_turn = 0
            elif days_since_turn >= 0:
                days_since_turn += 1

        states.append(is_bull)

    # 判斷「剛翻強」：今日（最後一根）為多頭，且昨日為空頭
    today_is_bull = states[-1]
    yesterday_is_bull = states[-2] if len(states) >= 2 else today_is_bull
    just_turned_bull = today_is_bull and not yesterday_is_bull

    if just_turned_bull:
        tower_label = "🔴 翻強"
    elif today_is_bull:
        tower_label = "持續多頭"
        days_since_turn = days_since_turn if days_since_turn >= 0 else 0
    elif not today_is_bull and yesterday_is_bull:
        tower_label = "翻弱"
    else:
        tower_label = "空頭"

    return {
        "just_turned_bull": just_turned_bull,
        "is_bull": today_is_bull,
        "tower_label": tower_label,
        "breakout_price": round(float(breakout_price), 2),
        "days_since_turn": days_since_turn,
    }


# ============================================================
# Section 4：單一股票綜合分析
# ============================================================

def _analyze_single_stock(
    code: str,
    margin_info: Dict,
) -> Optional[Dict]:
    """
    對單一股票進行完整分析：
    1. 取歷史 K 線（yfinance）
    2. 偵測 3T 寶塔線翻強
    3. 計算資券評分
    4. 返回分析結果

    Args:
        code: 股票代號（4 碼）
        margin_info: 從 fetch_twse_margin_data 取得的該股融資融券資料

    Returns:
        分析結果 dict 或 None（不符合條件）
    """
    try:
        ticker_symbol = get_yahoo_ticker(code)
        hist = fetch_stock_history(code, ticker_symbol, period="3mo", interval="1d")

        if hist is None or hist.empty or len(hist) < 10:
            return None

        # 寶塔線偵測
        tower = detect_tower_breakout_3t(hist, periods=3)

        # 只留翻強或剛翻強（today_is_bull 條件可選擇放寬）
        if not tower["just_turned_bull"]:
            return None

        # 成交量指標
        today_vol = int(hist["Volume"].iloc[-1]) if not pd.isna(hist["Volume"].iloc[-1]) else 0
        avg_vol_5 = float(hist["Volume"].iloc[-6:-1].mean()) if len(hist) >= 6 else 0.0
        vol_ratio = today_vol / (avg_vol_5 + 1)

        # 資券數據
        margin_delta = margin_info["margin_today"] - margin_info["margin_prev"]
        short_delta = margin_info["short_today"] - margin_info["short_prev"]

        # 避免除以零
        short_ratio = (
            margin_info["short_today"] / margin_info["margin_today"]
            if margin_info["margin_today"] > 0
            else 0.0
        )

        score, structure, rank = compute_chip_score(
            margin_delta, short_delta, vol_ratio, short_ratio
        )

        # 計算今日漲跌
        current_price = float(hist["Close"].iloc[-1])
        prev_price = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current_price
        change_pct = ((current_price - prev_price) / prev_price * 100) if prev_price > 0 else 0.0

        return {
            "code": code,
            "name": margin_info["name"],
            "price": round(current_price, 2),
            "change_pct": round(change_pct, 2),
            "score": score,
            "structure": structure,
            "rank_label": rank,
            "tower_label": tower["tower_label"],
            "breakout_price": tower["breakout_price"],
            "vol_ratio": round(vol_ratio, 2),
            "margin_today": margin_info["margin_today"],
            "margin_delta": margin_delta,
            "short_today": margin_info["short_today"],
            "short_delta": short_delta,
            "short_ratio": round(short_ratio * 100, 1),  # 轉換成百分比
        }

    except Exception as e:
        print(f"[chips_trend] 分析 {code} 時發生錯誤: {e}")
        return None


# ============================================================
# Section 5：主掃描函數
# ============================================================

def scan_chips_trend_top2(top_n: int = 5) -> Dict:
    """
    掃描所有具融資融券資料的上市股票，
    找出「寶塔線 3T 翻強」且資券協同評分最高的前 top_n 名。

    Args:
        top_n: 回傳股票數量（預設 5）

    Returns:
        {
            'status': 'success' | 'error',
            'date': '資料日期',
            'results': [第1名, ..., 第N名],
            'total_scanned': 掃描股票數,
            'tower_hit': 翻強股票數,
        }
    """
    # Step 1：取得融資融券資料
    margin_data = fetch_twse_margin_data()
    if margin_data is None:
        return {
            "status": "error",
            "message": "無法取得融資融券資料，請稍後再試",
            "results": [],
        }

    stocks_margin = margin_data["stocks"]
    date_str = margin_data["date"]
    total_scanned = len(stocks_margin)

    # Step 2：對每支股票分析（過濾融資融券量太小的股票，避免冷門股干擾）
    MIN_MARGIN = 100    # 融資餘額至少 100 張
    MIN_SHORT = 10      # 融券餘額至少 10 張（避免幾乎沒有融券的股票）

    candidates = [
        code for code, info in stocks_margin.items()
        if info["margin_today"] >= MIN_MARGIN and info["short_today"] >= MIN_SHORT
    ]

    print(f"[chips_trend] 有效候選股票：{len(candidates)} 支（融資≥{MIN_MARGIN}張且融券≥{MIN_SHORT}張）")

    # Step 3：批次分析（使用 ThreadPoolExecutor 加速）
    from concurrent.futures import ThreadPoolExecutor

    results_raw = []

    def _worker(code):
        return _analyze_single_stock(code, stocks_margin[code])

    with ThreadPoolExecutor(max_workers=8) as executor:
        for res in executor.map(_worker, candidates):
            if res is not None:
                results_raw.append(res)

    tower_hit = len(results_raw)
    print(f"[chips_trend] 寶塔線翻強股票：{tower_hit} 支")

    # Step 4：按分數降序，取前 top_n 名
    results_raw.sort(key=lambda x: x["score"], reverse=True)
    top_results = results_raw[:top_n]

    # Step 5：補充排名標籤
    rank_labels = ["🏆 最高分", "🥈 次高分", "🥉 第3名"]
    for i, r in enumerate(top_results):
        r["top_rank"] = rank_labels[i] if i < len(rank_labels) else f"第{i+1}名"

    return {
        "status": "success",
        "date": date_str,
        "results": top_results,
        "total_scanned": total_scanned,
        "tower_hit": tower_hit,
        "candidates": len(candidates),
    }
