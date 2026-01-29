import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def compute_kd(df: pd.DataFrame, period: int = 9, smooth_k: int = 3, smooth_d: int = 3) -> tuple[float | None, float | None]:
    """
    KD (Stochastic) using Taiwan common smoothing:
    RSV = (C - L_n) / (H_n - L_n) * 100
    K = EMA(RSV, alpha=1/3), D = EMA(K, alpha=1/3)  (equivalent to 2/3 carry + 1/3 new)
    """
    if df is None or df.empty or len(df) < period + 2:
        return None, None

    high_n = df["High"].rolling(window=period).max()
    low_n = df["Low"].rolling(window=period).min()
    denom = (high_n - low_n).replace(0, pd.NA)
    rsv = ((df["Close"] - low_n) / denom) * 100
    rsv = rsv.clip(lower=0, upper=100)

    # Smoothing (alpha=1/smooth)
    k = rsv.ewm(alpha=1 / smooth_k, adjust=False).mean()
    d = k.ewm(alpha=1 / smooth_d, adjust=False).mean()

    k_last = k.iloc[-1]
    d_last = d.iloc[-1]
    if pd.isna(k_last) or pd.isna(d_last):
        return None, None
    return float(k_last), float(d_last)


def compute_rsi(close: pd.Series, period: int = 14) -> float | None:
    if close is None or close.empty or len(close) < period + 2:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    last = rsi.iloc[-1]
    return None if pd.isna(last) else float(last)


def compute_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float | None, float | None, float | None]:
    if close is None or close.empty or len(close) < slow + signal:
        return None, None, None
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    dif = ema_fast - ema_slow
    dea = _ema(dif, signal)  # signal line
    hist = dif - dea
    dif_last, dea_last, hist_last = dif.iloc[-1], dea.iloc[-1], hist.iloc[-1]
    if pd.isna(dif_last) or pd.isna(dea_last) or pd.isna(hist_last):
        return None, None, None
    return float(dif_last), float(dea_last), float(hist_last)


def compute_bias(close: pd.Series, ma_period: int = 20) -> float | None:
    if close is None or close.empty or len(close) < ma_period + 2:
        return None
    ma = close.rolling(window=ma_period).mean()
    ma_last = ma.iloc[-1]
    if pd.isna(ma_last) or ma_last == 0:
        return None
    bias = (close.iloc[-1] - ma_last) / ma_last * 100
    return float(bias)


def compute_bollinger(close: pd.Series, period: int = 20, std_mult: float = 2.0) -> tuple[float | None, float | None, float | None, float | None]:
    if close is None or close.empty or len(close) < period + 2:
        return None, None, None, None
    mid = close.rolling(window=period).mean()
    std = close.rolling(window=period).std(ddof=0)
    mid_last = mid.iloc[-1]
    std_last = std.iloc[-1]
    if pd.isna(mid_last) or pd.isna(std_last) or mid_last == 0:
        return None, None, None, None
    upper = mid_last + std_mult * std_last
    lower = mid_last - std_mult * std_last
    width = (upper - lower) / mid_last  # relative band width
    return float(upper), float(mid_last), float(lower), float(width)


# ============================================================
# 多週期技術指標驗證（高優先級改進 3）
# ============================================================

def compute_multi_rsi(close: pd.Series) -> dict:
    """
    計算多週期 RSI（高優先級改進 3.1, 3.2）
    
    Returns:
        dict: {
            'rsi_6': float,
            'rsi_14': float,
            'rsi_20': float,
            'alignment': str  # '多頭排列', '空頭排列', '混亂'
        }
    """
    rsi_6 = compute_rsi(close, period=6)
    rsi_14 = compute_rsi(close, period=14)
    rsi_20 = compute_rsi(close, period=20)
    
    # 檢查多頭/空頭排列
    alignment = '混亂'
    if all([rsi_6, rsi_14, rsi_20]):
        if rsi_6 > rsi_14 > rsi_20:
            alignment = '多頭排列'
        elif rsi_6 < rsi_14 < rsi_20:
            alignment = '空頭排列'
    
    return {
        'rsi_6': rsi_6,
        'rsi_14': rsi_14,
        'rsi_20': rsi_20,
        'alignment': alignment
    }


def compute_macd_with_trend(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9, trend_periods: int = 5) -> dict:
    """
    計算 MACD 並提供趨勢分析（高優先級改進 3.3, 3.4）
    
    Args:
        close: 收盤價序列
        fast: 快線週期
        slow: 慢線週期
        signal: 訊號線週期
        trend_periods: 分析趨勢的週期數
    
    Returns:
        dict: {
            'dif': float,
            'dea': float,
            'hist': float,
            'hist_series': list,  # 最近 N 期柱狀圖
            'trend': str  # '擴張', '收斂', '震盪'
        }
    """
    if close is None or close.empty or len(close) < slow + signal + trend_periods:
        return {
            'dif': None,
            'dea': None,
            'hist': None,
            'hist_series': [],
            'trend': '未知'
        }
    
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    dif = ema_fast - ema_slow
    dea = _ema(dif, signal)
    hist = dif - dea
    
    # 取最近 N 期柱狀圖
    hist_recent = hist.tail(trend_periods)
    hist_list = hist_recent.tolist()
    
    # 判斷趨勢
    trend = '震盪'
    if len(hist_recent) >= trend_periods:
        # 檢查是否持續擴張（每期都大於前一期）
        is_expanding = all(hist_recent.iloc[i] < hist_recent.iloc[i+1] 
                          for i in range(len(hist_recent)-1))
        # 檢查是否持續收斂（每期都小於前一期）
        is_contracting = all(hist_recent.iloc[i] > hist_recent.iloc[i+1] 
                            for i in range(len(hist_recent)-1))
        
        if is_expanding:
            trend = '擴張'
        elif is_contracting:
            trend = '收斂'
    
    return {
        'dif': float(dif.iloc[-1]) if not pd.isna(dif.iloc[-1]) else None,
        'dea': float(dea.iloc[-1]) if not pd.isna(dea.iloc[-1]) else None,
        'hist': float(hist.iloc[-1]) if not pd.isna(hist.iloc[-1]) else None,
        'hist_series': [float(x) if not pd.isna(x) else None for x in hist_list],
        'trend': trend
    }









