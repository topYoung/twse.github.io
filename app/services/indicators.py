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





