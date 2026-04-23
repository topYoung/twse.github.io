"""
盤整偵測掃描器

偵測邏輯：
- 找出收盤價在 [5, 65] 個交易日內保持在 ±15% 箱型內的股票（「盤整中」）
- 或：箱型盤整 ≥5 日後，最近 1~2 天出現連漲突破的股票（「剛起漲」）
返回每支股票：盤整天數、箱型高低、近 5 日三大法人合計買賣超
"""

import pandas as pd
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from app.services.indicators import compute_kd
from app.services.institutional_data import get_5day_institutional_bulk


# ── 盤整偵測 ─────────────────────────────────────────────────────────────────

def detect_consolidation(
    df: pd.DataFrame,
    min_days: int = 15,
    max_days: int = 65,
    range_threshold: float = 0.08,
) -> Dict[str, Any]:
    """
    偵測最近一段時間是否有箱型盤整，並判斷目前狀態。

    嚴格條件：
    1. 箱型波動 ≤ range_threshold (8%)
    2. 盤整天數 ≥ min_days (15 天 = 約 3 週)
    3. 期間至少出現 3 次漲跌方向反轉（真正横盤，非單方向漂移）

    Returns:
        {
          'status': 'consolidating' | 'just_broke_out' | 'none',
          'consolidation_days': int,
          'box_high': float,
          'box_low':  float,
          'box_range_pct': float,      # (box_high-box_low)/box_low * 100
        }
    """
    none_result = {'status': 'none', 'consolidation_days': 0,
                   'box_high': 0, 'box_low': 0, 'box_range_pct': 0}

    if df is None or len(df) < min_days + 3:
        return none_result

    close = df['Close'].values
    n = len(close)

    # ── 判斷是否剛起漲 ──
    # 定義：最近 2 天皆收紅，且合計漲幅 ≥ 4%；或單日大漲 ≥ 5%
    just_broke = False
    if n >= 3:
        c1 = float(close[-3])   # 突破前一日
        c2 = float(close[-2])   # 突破第 1 日
        c3 = float(close[-1])   # 突破第 2 日（今天）
        up1 = c2 > c1
        up2 = c3 > c2
        gain_2d = (c3 - c1) / c1 * 100 if c1 > 0 else 0
        just_broke = (gain_2d >= 5.0) or (up1 and up2 and gain_2d >= 4.0)

    # ── 找盤整箱型 ──
    # 如果剛起漲，從倒數第 3 天往前找；否則從今天往前找
    search_end = n - 3 if just_broke else n - 1

    if search_end < min_days:
        return none_result

    box_indices: List[int] = []
    for i in range(search_end, max(search_end - max_days - 1, -1), -1):
        if i < 0:
            break
        price = float(close[i])
        prices_so_far = [float(close[j]) for j in box_indices] + [price]
        pmax, pmin = max(prices_so_far), min(prices_so_far)
        if pmin > 0 and (pmax - pmin) / pmin > range_threshold:
            break   # 超出範圍，不加入
        box_indices.append(i)

    days = len(box_indices)
    if days < min_days:
        return none_result

    # ── 條件 3：至少 3 次方向反轉（有漲有跌） ──
    # box_indices 是從新到舊，反轉為時間順序
    ordered_idx = list(reversed(box_indices))
    directions = [
        close[ordered_idx[i]] > close[ordered_idx[i - 1]]
        for i in range(1, len(ordered_idx))
    ]
    reversals = sum(
        1 for i in range(1, len(directions)) if directions[i] != directions[i - 1]
    )
    if reversals < 3:
        return none_result

    box_prices = [float(close[i]) for i in box_indices]
    box_high = max(box_prices)
    box_low  = min(box_prices)
    range_pct = round((box_high - box_low) / box_low * 100, 1) if box_low > 0 else 0.0

    # ── 條件 4：MACD 在盤整期間貼近 0 軸（DIF / Histogram 幅度小）──
    # 真正蓄勢橫盤時，DIF 和 DEA 都在 0 附近徘徊，絕對值遠小於股價
    # 盤整窗口內 DIF 最大絕對值 / 均價 < 5%，Histogram < 3%
    ref_price = float(sum(box_prices) / len(box_prices)) if box_prices else 1.0
    if ref_price > 0:
        close_s = pd.Series(close)
        ema12 = close_s.ewm(span=12, adjust=False).mean()
        ema26 = close_s.ewm(span=26, adjust=False).mean()
        dif_s = ema12 - ema26
        dea_s = dif_s.ewm(span=9, adjust=False).mean()
        hist_s = dif_s - dea_s

        # 只看盤整窗口（ordered_idx = 時間由舊到新）
        start_i = ordered_idx[0]
        end_i   = ordered_idx[-1] + 1
        box_dif  = dif_s.iloc[start_i: end_i]
        box_hist = hist_s.iloc[start_i: end_i]

        dif_max_ratio  = float(box_dif.abs().max())  / ref_price if len(box_dif)  > 0 else 0
        hist_max_ratio = float(box_hist.abs().max()) / ref_price if len(box_hist) > 0 else 0

        if dif_max_ratio > 0.05 or hist_max_ratio > 0.03:
            return none_result

    return {
        'status': 'just_broke_out' if just_broke else 'consolidating',
        'consolidation_days': days,
        'box_high': round(box_high, 2),
        'box_low':  round(box_low,  2),
        'box_range_pct': range_pct,
        '_box_start_idx': ordered_idx[0],   # 供 process_stock 做量縮檢查用
    }


# ── 主掃描函式 ────────────────────────────────────────────────────────────────

def get_consolidation_stocks(tech_only: bool = True) -> List[Dict[str, Any]]:
    """
    掃描全市場（或科技股），回傳盤整中 / 剛起漲的股票清單。
    每支股票包含：盤整天數、箱型高低、近 5 日三大法人合計買賣超。
    """
    from app.services.categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES, DELISTED_STOCKS
    import twstock
    import yfinance as yf
    from app.services.stock_data import get_yahoo_ticker
    from app.services.yf_rate_limiter import fetch_stock_history

    # ── 1. 股票清單 ──
    # TECH_STOCKS 已涵蓋所有電子科技業；tech_only 時不加 STOCK_SUB_CATEGORIES.keys()
    # 因為 MANUAL_SUB_CATEGORIES 內含金融/航運/鋼鐵等非科技股
    if tech_only:
        all_codes = list(set(TECH_STOCKS))
    else:
        keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
        all_codes = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    stock_codes = [s for s in all_codes if s not in DELISTED_STOCKS]

    # 建立名稱對照
    stock_info_map = {}
    for code in stock_codes:
        name = twstock.codes[code].name if code in twstock.codes else code
        stock_info_map[code] = {'name': name}

    # ── 2. 下載歷史價格（6 個月，涵蓋最長盤整期）──
    def fetch_history(code: str):
        try:
            ticker = get_yahoo_ticker(code)
            df = fetch_stock_history(code, ticker, period="6mo", interval="1d")
            if not df.empty and len(df) > 30:
                return code, df
        except Exception:
            pass
        return code, None

    history_data: Dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for code, df in executor.map(lambda c: fetch_history(c), stock_codes):
            if df is not None:
                history_data[code] = df

    # ── 3. 一次性取得 5 日法人籌碼 ──
    inst5_map = get_5day_institutional_bulk()

    # ── 4. 逐支分析 ──
    def process_stock(code: str, df: pd.DataFrame) -> Dict[str, Any]:
        try:
            if df is None or df.empty or 'Close' not in df.columns or len(df) < 8:
                return None

            result = detect_consolidation(df)
            if result['status'] == 'none':
                return None

            close   = df['Close']
            c_now   = float(close.iloc[-1])
            c_prev  = float(close.iloc[-2]) if len(close) > 1 else c_now
            change  = round((c_now - c_prev) / c_prev * 100, 2) if c_prev > 0 else 0.0

            vol = int(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0
            if vol < 200_000:       # 最低流動性門檻：200 張
                return None

            # ── 條件 4：量縮確認盤整 ──
            # 盤整期平均量 < 整段期間均量 × 1.5（量縮代表真正蓄勢，非爆量下跌後橫盤）
            if 'Volume' in df.columns:
                box_start = result.get('_box_start_idx', len(df) - result['consolidation_days'] - 1)
                vol_box = float(df['Volume'].iloc[box_start:].mean())
                vol_all = float(df['Volume'].mean())
                if vol_all > 0 and vol_box > vol_all * 1.5:
                    return None   # 盤整期量太大，可能是套牢盤而非蓄勢

            # MACD（供前端顯示）
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            dif   = ema12 - ema26
            dea   = dif.ewm(span=9, adjust=False).mean()
            hist  = dif - dea

            # KD
            _, d_val = compute_kd(df)

            # 5 日三大法人（股 → 張，前端顯示用）
            inst5 = inst5_map.get(code, {})

            return {
                'code': code,
                'name': stock_info_map[code]['name'],
                'price': round(c_now, 2),
                'change_percent': change,
                'volume': vol,
                # 盤整資訊
                'status': result['status'],
                'consolidation_days': result['consolidation_days'],
                'box_high': result['box_high'],
                'box_low': result['box_low'],
                'box_range_pct': result['box_range_pct'],
                # 技術指標
                'macd': {
                    'dif':  round(float(dif.iloc[-1]),  2),
                    'dea':  round(float(dea.iloc[-1]),  2),
                    'hist': round(float(hist.iloc[-1]), 2),
                },
                'kd_d_value': round(float(d_val), 1) if d_val is not None else None,
                # 近 5 日三大法人（單位：股）
                'inst_5d': {
                    'foreign': int(inst5.get('foreign', 0)),
                    'trust':   int(inst5.get('trust',   0)),
                    'dealer':  int(inst5.get('dealer',  0)),
                    'total':   int(inst5.get('total',   0)),
                },
            }
        except Exception:
            return None

    results: List[Dict] = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for r in executor.map(lambda item: process_stock(*item), history_data.items()):
            if r:
                results.append(r)

    # 排序：先顯示「剛起漲」，再顯示「盤整中」；各自按盤整天數降序
    results.sort(key=lambda x: (
        0 if x['status'] == 'just_broke_out' else 1,
        -x['consolidation_days'],
    ))
    return results
