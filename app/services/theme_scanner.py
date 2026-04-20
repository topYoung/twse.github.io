"""
主題選股掃描器 (Thematic Stock Scanner)
針對三大主題：矽光子CPO設備支援、液冷散熱零組件、邊緣AI自動化
套用10項技術/籌碼/基本面條件進行評分，特別標注「起漲訊號」與「星級雙重確認」。
"""

import pandas as pd
import threading
import time
import math
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import twstock

from app.services.categories import (
    THEME_SILICON_PHOTONICS, THEME_LIQUID_COOLING, THEME_EDGE_AI,
    STOCK_THEME_MAP, THEME_LABELS, ALL_THEME_STOCKS
)
from app.services.stock_data import get_yahoo_ticker
from app.services.yf_rate_limiter import fetch_stock_history
from app.services.indicators import compute_kd, compute_rsi, compute_macd, compute_macd_with_trend, detect_kd_golden_cross
from app.services.macd_scanner import is_after_consolidation
from app.services.institutional_data import get_5day_institutional_data

# ─────────────────────────────────────────────
# 快取設定
# ─────────────────────────────────────────────
_cache: Dict[str, Any] = {"data": None, "last_update": 0}
_cache_lock = threading.Lock()


def _safe(v, decimals: int = 2):
    """安全四捨五入，若為 None / NaN / Inf 則回傳 None"""
    if v is None:
        return None
    try:
        f = float(v)
        if not math.isfinite(f):
            return None
        return round(f, decimals)
    except Exception:
        return None


def _get_capital_b(ticker_symbol: str) -> Optional[float]:
    """
    取得股本（以億元計）。
    計算方式：sharesOutstanding（股數）× NT$10（面額）/ 1億。
    若取不到則回傳 None。
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker_symbol).fast_info
        shares = getattr(info, 'shares', None)
        if shares and shares > 0:
            return round(shares * 10 / 1e8, 2)
    except Exception:
        pass
    return None


def _calc_macd_series(close: pd.Series):
    """計算完整 MACD 序列，回傳 (dif, dea, hist) Series"""
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def _check_trend_radar_inline(df: pd.DataFrame, inst_data: Dict) -> bool:
    """
    在已有 df + inst_data 的情況下，直接判斷是否符合「動能趨勢雷達」條件
    （潛龍伏淵 or 乘風破浪），避免重複 API 呼叫。
    """
    try:
        from app.services.breakout_scanner import detect_lower_shadow_after_decline, analyze_volume_trend

        if df is None or len(df) < 60:
            return False

        today = df.iloc[-1]
        current_price = float(today['Close'])
        prev_close = float(df.iloc[-2]['Close'])

        today_vol = float(today["Volume"])
        avg_vol_5 = float(df.iloc[-6:-1]["Volume"].mean())
        if today_vol < 200_000 or avg_vol_5 < 100_000:
            return False
        vol_increase = today_vol > avg_vol_5

        k, d = compute_kd(df)
        rsi = compute_rsi(df["Close"], period=14)
        macd_trend = compute_macd_with_trend(df["Close"], trend_periods=3)

        ma5 = float(df['Close'].rolling(5).mean().iloc[-1])
        ma10 = float(df['Close'].rolling(10).mean().iloc[-1])
        ma20 = float(df['Close'].rolling(20).mean().iloc[-1])

        recent_60 = df['Close'].iloc[-60:]
        low_60, high_60 = float(recent_60.min()), float(recent_60.max())
        position_pct = (current_price - low_60) / (high_60 - low_60) if high_60 > low_60 else 0.5

        is_red_k = current_price >= float(today['Open'])
        lower_shadow_info = detect_lower_shadow_after_decline(df, decline_days=2, shadow_ratio=1.5)
        has_lower_shadow = lower_shadow_info.get('has_lower_shadow', 0) == 1

        # MACD 起動訊號
        hist_series = macd_trend.get('hist_series', [])
        macd_starting = False
        if len(hist_series) >= 2:
            h_latest = float(hist_series[-1] or 0)
            h_prev = float(hist_series[-2] or 0)
            if (h_prev <= 0 and h_latest > 0) or (h_latest < 0 and h_latest > h_prev):
                macd_starting = True

        inst_foreign = inst_data.get('foreign', 0)
        inst_trust = inst_data.get('trust', 0)
        inst_dealer = inst_data.get('dealer', 0)
        cond_sneaky_inst = (inst_foreign > 0 or inst_trust > 0 or inst_dealer > 0)

        # 潛龍伏淵
        consecutive_rise_days = 0
        for i in range(len(df) - 1, 0, -1):
            if float(df.iloc[i]['Close']) > float(df.iloc[i - 1]['Close']):
                consecutive_rise_days += 1
            else:
                break

        cond_level_safe = (position_pct <= 0.40
                           or (current_price >= ma20 and prev_close < ma20)
                           or (abs(current_price - ma20) / ma20 < 0.02))
        cond_not_overbought = consecutive_rise_days <= 3
        cond_macd_kd_rsi = (macd_starting
                            and d is not None and d <= 40
                            and rsi is not None and 40 <= rsi <= 75)
        cond_support = cond_sneaky_inst and vol_increase
        cond_k_shape = is_red_k or has_lower_shadow

        if cond_level_safe and cond_not_overbought and cond_macd_kd_rsi and cond_support and cond_k_shape:
            return True

        # 乘風破浪
        cond_ma_alignment = current_price > ma5 > ma10 > ma20
        cond_rsi_strong = rsi is not None and 55 <= rsi <= 75
        _, _, macd_hist_val = compute_macd(df["Close"])
        cond_macd_strong = (macd_trend.get('trend') == '擴張'
                            and macd_hist_val is not None and macd_hist_val > 0)
        vol_info = analyze_volume_trend(df, days=5)
        cond_healthy_vol = vol_info.get('is_healthy', False)
        inst_net = inst_data.get('total', 0)
        cond_momentum = (current_price > prev_close
                         and prev_close > float(df.iloc[-3]['Close'])) or inst_net > 200

        if cond_ma_alignment and cond_rsi_strong and cond_macd_strong and cond_healthy_vol and cond_momentum:
            return True

    except Exception:
        pass
    return False


def _eval_stock(code: str, df: pd.DataFrame, max_capital_b: float) -> Optional[Dict[str, Any]]:
    """評估單檔主題股票，回傳結果 dict 或 None（不符合基本門檻）"""
    try:
        if df is None or df.empty or len(df) < 35:
            return None
        if 'Close' not in df.columns or 'Volume' not in df.columns:
            return None

        close = df['Close']
        close_latest = float(close.iloc[-1])
        if close_latest <= 0:
            return None

        # 股票基本資訊
        name = twstock.codes[code].name if code in twstock.codes else code
        theme_key = STOCK_THEME_MAP.get(code, 'unknown')
        theme_label = THEME_LABELS.get(theme_key, theme_key)

        # ── 價格/量能基礎計算 ──────────────────────────────
        prev_close = float(close.iloc[-2])
        change_pct = (close_latest - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
        vol_today = float(df['Volume'].iloc[-1])
        vol_5d_avg = float(df['Volume'].iloc[-6:-1].mean()) if len(df) >= 6 else vol_today
        vol_ratio = vol_today / vol_5d_avg if vol_5d_avg > 0 else 1.0

        # 最低成交量門檻（100 張）
        if vol_today < 100_000:
            return None

        # ── MACD 全序列 ──────────────────────────────────
        dif_series, dea_series, hist_series = _calc_macd_series(close)
        hist_latest = float(hist_series.iloc[-1])
        hist_prev = float(hist_series.iloc[-2])
        dif_latest = float(dif_series.iloc[-1])

        # ── 均線 ─────────────────────────────────────────
        ma5 = float(close.rolling(5).mean().iloc[-1])
        ma10 = float(close.rolling(10).mean().iloc[-1])
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma60 = float(close.rolling(60).mean().iloc[-1]) if len(df) >= 60 else None

        # ── 法人 5 日資料 ─────────────────────────────────
        try:
            inst_5day = get_5day_institutional_data(code)
        except Exception:
            inst_5day = {
                'trust_days': 0, 'trust_increasing': False, 'trust_daily': [],
                'foreign_days': 0, 'foreign_increasing': False, 'foreign_daily': [],
            }

        # ── 法人最新單日資料（用於雷達條件）─────────────────
        from app.services.institutional_data import get_latest_institutional_data
        # 避免每股都呼叫一次，外部已批次取得後傳入；此處保留 fallback
        latest_inst = {}  # 由 get_theme_stocks 傳入覆蓋

        # ── 股本 ──────────────────────────────────────────
        ticker_symbol = get_yahoo_ticker(code)
        capital_b = _get_capital_b(ticker_symbol)

        # ─────────────────────────────────────────────────
        # 10 項條件評估
        # ─────────────────────────────────────────────────

        # C1：股本 ≤ max_capital_b 億
        c1_capital = (capital_b is not None and capital_b <= max_capital_b)

        # C2：法人5日買超 ≥ 3天，且持續放大
        c2_inst_5day = (
            (inst_5day['trust_days'] >= 3 and inst_5day['trust_increasing']) or
            (inst_5day['foreign_days'] >= 3 and inst_5day['foreign_increasing'])
        )

        # C3：MACD 金叉（剛翻紅 or 綠縮短）
        is_just_red = (hist_prev <= 0 and hist_latest > 0)
        is_green_shrinking = (hist_latest < 0 and hist_latest > hist_prev)
        is_converging = abs(hist_latest) / close_latest < 0.05
        is_dif_near_zero = abs(dif_latest) / close_latest < 0.2
        c3_macd_cross = (is_just_red or is_green_shrinking) and is_converging and is_dif_near_zero

        # C4：KD 中段金叉（40~60 區間穿越，最近5日）
        c4_kd_cross_mid = detect_kd_golden_cross(df, lookback=5, kd_min=40.0, kd_max=60.0)

        # C5：量能突破（今日 ≥ 5日均量 × 1.5）
        c5_volume = vol_ratio >= 1.5

        # C6：突破季線（近5日曾在 MA60 以下，現在在 MA60 以上），且短均線初步多頭
        c6_ma60_breakout = False
        if ma60 is not None:
            recent5_close = close.iloc[-6:-1]
            was_below_ma60 = any(float(p) < ma60 for p in recent5_close)
            now_above_ma60 = close_latest >= ma60
            short_ma_ok = ma5 > ma10
            c6_ma60_breakout = was_below_ma60 and now_above_ma60 and short_ma_ok

        # C7：營收成長（YOY > 0 AND MOM > 0）
        c7_revenue = False
        try:
            from app.services.revenue_service import get_stock_revenue
            rev = get_stock_revenue(code)
            if rev and rev.get('yoy') is not None and rev.get('mom') is not None:
                c7_revenue = rev['yoy'] > 0 and rev['mom'] > 0
        except Exception:
            c7_revenue = False  # 抓不到資料不扣分，標示未知

        # C8：動能趨勢雷達（潛龍伏淵 or 乘風破浪）
        # latest_inst 在 _eval_stock 簽名外傳入（見下方 wrapper）
        c8_trend_radar = False  # 由 wrapper 填入

        # C9：起漲訊號 = 盤整後MACD金叉 + KD D值 ≤ 55
        k_val, d_val = compute_kd(df)
        consolidation_ok = is_after_consolidation(close, hist_series, dif_series, close_latest, rt_change=change_pct)
        # D 值改回更嚴格的 40，或考慮 K 值穿越 D 時的斜率（上升狠度）
        c9_launch_signal = consolidation_ok and c3_macd_cross and (d_val is not None and d_val <= 40)

        # C10：星級雙重確認 = C9 + 量能突破 + 今日漲幅 ≥ 2%
        c10_star_confirmed = c9_launch_signal and c5_volume and change_pct >= 2.0

        # ─────────────────────────────────────────────────
        # 評分 & 徽章
        # ─────────────────────────────────────────────────
        conditions = {
            'capital_ok': c1_capital,
            'inst_5day': c2_inst_5day,
            'macd_cross': c3_macd_cross,
            'kd_cross_mid': c4_kd_cross_mid,
            'volume_ok': c5_volume,
            'ma60_breakout': c6_ma60_breakout,
            'revenue_growth': c7_revenue,
            'trend_radar': c8_trend_radar,   # 由 wrapper 更新
            'launch_signal': c9_launch_signal,
            'star_confirmed': c10_star_confirmed,
        }

        score = sum(1 for v in conditions.values() if v)

        badges = []
        if c10_star_confirmed:
            badges.append('🏆雙確認')
        if c9_launch_signal:
            badges.append('⭐起漲')
        if c8_trend_radar:
            badges.append('📡雷達')
        if c2_inst_5day:
            badges.append('💼法人')
        if c6_ma60_breakout:
            badges.append('📈季線突破')

        # RSI、KD 供前端顯示
        rsi_val = compute_rsi(close, 14)

        return {
            'code': code,
            'name': name,
            'theme': theme_key,
            'theme_label': theme_label,
            'price': _safe(close_latest),
            'change_percent': _safe(change_pct),
            'volume': int(vol_today),
            'vol_ratio': _safe(vol_ratio),
            'capital_b': capital_b,
            'score': score,
            'conditions': conditions,
            'badges': badges,
            'inst_detail': {
                'trust_days': inst_5day['trust_days'],
                'trust_increasing': inst_5day['trust_increasing'],
                'foreign_days': inst_5day['foreign_days'],
                'foreign_increasing': inst_5day['foreign_increasing'],
            },
            'indicators': {
                'rsi': _safe(rsi_val, 1),
                'kd_k': _safe(k_val, 1),
                'kd_d': _safe(d_val, 1),
                'macd_hist': _safe(hist_latest, 3),
                'macd_just_red': is_just_red,
                'ma5': _safe(ma5),
                'ma10': _safe(ma10),
                'ma20': _safe(ma20),
                'ma60': _safe(ma60) if ma60 else None,
            },
        }
    except Exception as e:
        return None


def get_theme_stocks(theme: Optional[str] = None, max_capital_b: float = 30.0,
                     min_score: int = 0, force_refresh: bool = False) -> Dict[str, Any]:
    """
    主函數：掃描主題股票並評分。

    Args:
        theme: 'silicon_photonics' | 'liquid_cooling' | 'edge_ai' | None/'all'（全部）
        max_capital_b: 股本上限（億元），預設 30
        min_score: 最低得分門檻（0~10），預設 0
        force_refresh: 強制忽略快取

    Returns:
        {
            "status": "success",
            "data": {
                "silicon_photonics": [...],
                "liquid_cooling": [...],
                "edge_ai": [...]
            },
            "params": {...},
            "last_update": float
        }
    """
    global _cache
    now = datetime.now()
    current_time = time.time()
    is_market_hours = (9 <= now.hour < 14) and now.weekday() < 5
    cache_duration = 300 if is_market_hours else 1800

    cache_key = f"{theme}_{max_capital_b}_{min_score}"

    with _cache_lock:
        if not force_refresh and _cache.get("data"):
            if (current_time - _cache.get("last_update", 0) < cache_duration
                    and _cache.get("cache_key") == cache_key):
                return _cache["data"]

    # 決定要掃描的股票清單
    theme_map = {
        'silicon_photonics': THEME_SILICON_PHOTONICS,
        'liquid_cooling': THEME_LIQUID_COOLING,
        'edge_ai': THEME_EDGE_AI,
    }
    if theme and theme in theme_map:
        codes_to_scan = theme_map[theme]
    else:
        codes_to_scan = ALL_THEME_STOCKS

    # ── 批次 fetch 歷史資料 ───────────────────────────────
    def fetch_one(code: str):
        try:
            ticker = get_yahoo_ticker(code)
            df = fetch_stock_history(code, ticker, period="3mo", interval="1d")
            if df is not None and not df.empty and len(df) > 35:
                return code, df
        except Exception:
            pass
        return code, None

    history_map: Dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for code, df in executor.map(fetch_one, codes_to_scan):
            if df is not None:
                history_map[code] = df

    # ── 取一次最新法人資料（避免重複呼叫）────────────────
    from app.services.institutional_data import get_latest_institutional_data
    latest_inst_map = {}
    try:
        latest_inst_map = get_latest_institutional_data()
    except Exception:
        pass

    # ── 評估每支股票 ──────────────────────────────────────
    results: List[Dict] = []

    def eval_wrapper(code: str) -> Optional[Dict]:
        df = history_map.get(code)
        if df is None:
            return None
        res = _eval_stock(code, df, max_capital_b)
        if res is None:
            return None

        # 補填 C8（動能趨勢雷達）— 傳入已有的 latest_inst_map
        inst_single = latest_inst_map.get(code, {})
        res['conditions']['trend_radar'] = _check_trend_radar_inline(df, inst_single)
        if res['conditions']['trend_radar'] and '📡雷達' not in res['badges']:
            res['badges'].insert(0 if '⭐起漲' not in res['badges'] else 1, '📡雷達')

        # 重新計算 score（C8 可能剛被更新）
        res['score'] = sum(1 for v in res['conditions'].values() if v)

        return res

    with ThreadPoolExecutor(max_workers=8) as executor:
        for res in executor.map(eval_wrapper, codes_to_scan):
            if res is not None and res['score'] >= min_score:
                results.append(res)

    # ── 分組 & 排序 ────────────────────────────────────────
    # 排序：雙確認 → 起漲 → score → 漲幅
    def sort_key(r):
        return (
            not r['conditions']['star_confirmed'],
            not r['conditions']['launch_signal'],
            -r['score'],
            -(r['change_percent'] or 0),
        )

    grouped: Dict[str, List] = {k: [] for k in theme_map}
    for r in results:
        t = r.get('theme', 'unknown')
        if t in grouped:
            grouped[t].append(r)
        # 若股票同時屬多主題（目前不重疊）就只放一個

    for t in grouped:
        grouped[t].sort(key=sort_key)

    output = {
        "status": "success",
        "data": grouped,
        "params": {
            "theme": theme or "all",
            "max_capital_b": max_capital_b,
            "min_score": min_score,
            "theme_labels": THEME_LABELS,
            "theme_descriptions": {
                "silicon_photonics": "矽光子(CPO)與先進封裝設備支援軍：精密光學檢測、光收發模組、先進封裝設備/材料周邊小廠",
                "liquid_cooling": "次世代液冷散熱零組件：快拆接頭(UQD)、特種閥門、液冷模組、CDU散熱分配裝置",
                "edge_ai": "邊緣AI與工廠自動化隱形冠軍：機器視覺AOI、工業機器人、邊緣運算、智慧製造",
            }
        },
        "last_update": current_time,
    }

    with _cache_lock:
        _cache["data"] = output
        _cache["last_update"] = current_time
        _cache["cache_key"] = cache_key

    return output
