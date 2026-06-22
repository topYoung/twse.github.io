"""
mcpt_service.py — 網頁版 MCPT 回測服務
=======================================
供 FastAPI endpoint 呼叫，回傳 JSON-serializable 結果（不使用 matplotlib）。

策略 A：外資 Z-Score 突買（主策略）
策略 B：KD 金叉（對照組）
IS / OOS 分割：IS 2 年 / OOS 1 年
MCPT：循環移位排列，計算 p-value（web 預設 500 次，約 10-20 秒完成）
"""

import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

TRADING_DAYS  = 250
FEE_ONE_WAY   = 0.003    # 單邊 0.3%
HOLD_DAYS     = 5        # 持有 5 個交易日
ZSCORE_WIN    = 252
ZSCORE_THRES  = 2.0
IS_YEARS      = 2
OOS_YEARS     = 1


# ─── 資料取得 ──────────────────────────────────────────────────────────────────

def _fetch_ohlcv(code: str, years: int) -> pd.DataFrame:
    ticker = f"{code}.TW"
    df = yf.download(ticker, period=f"{years}y", progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"yfinance 找不到 {ticker}，請確認股票代號。")
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df


def _fetch_foreign_net(code: str, years: int) -> pd.Series:
    """
    優先從本地 institutional_data 服務取得外資買賣超序列；
    若失敗（無資料或非台股）則用模擬資料。
    """
    try:
        from app.services.institutional_data import fetch_historical_data
        raw = fetch_historical_data("foreign", code, days=years * TRADING_DAYS + 60)
        if raw and len(raw) > 30:
            ser = pd.Series(
                {pd.Timestamp(r["date"]): float(r.get("net", r.get("foreignNet", 0)))
                 for r in raw if r.get("date")}
            ).sort_index()
            if len(ser) > 30:
                return ser
    except Exception:
        pass

    # fallback：用模擬正態分布（僅供測試）
    n = years * TRADING_DAYS
    idx = pd.bdate_range(end=pd.Timestamp.today(), periods=n)
    rng = np.random.default_rng(int(code) % 9999 if code.isdigit() else 42)
    return pd.Series(rng.normal(0, 5000, n), index=idx)


# ─── 策略訊號 ─────────────────────────────────────────────────────────────────

def _signals_foreign_zscore(foreign: pd.Series) -> pd.Series:
    roll_mean = foreign.rolling(ZSCORE_WIN).mean()
    roll_std  = foreign.rolling(ZSCORE_WIN).std()
    std_floor = (roll_mean.abs() * 0.30).clip(lower=10_000)
    eff_std   = roll_std.clip(lower=std_floor)
    z = (foreign - roll_mean) / eff_std
    return ((z >= ZSCORE_THRES) | (foreign >= 5000)).fillna(False)


def _signals_kd_cross(df: pd.DataFrame) -> pd.Series:
    low_min  = df["Low"].rolling(9).min()
    high_max = df["High"].rolling(9).max()
    denom    = (high_max - low_min).replace(0, np.nan)
    rsv      = (df["Close"] - low_min) / denom * 100
    K = rsv.ewm(com=2, adjust=False).mean()
    D = K.ewm(com=2, adjust=False).mean()
    return ((K.shift(1) < D.shift(1)) & (K > D)).fillna(False)


# ─── 報酬計算 ─────────────────────────────────────────────────────────────────

def _compute_trade_returns(signals: pd.Series, df: pd.DataFrame) -> np.ndarray:
    prices  = df["Close"].values
    idx     = df.index
    sig_idx = signals.reindex(idx, fill_value=False)

    rets = []
    in_trade_until = -1
    for i, is_sig in enumerate(sig_idx):
        if not is_sig or i <= in_trade_until:
            continue
        exit_i = min(i + HOLD_DAYS, len(prices) - 1)
        p_in, p_out = prices[i], prices[exit_i]
        if p_in <= 0:
            continue
        rets.append((p_out - p_in) / p_in - 2 * FEE_ONE_WAY)
        in_trade_until = exit_i
    return np.array(rets) if rets else np.array([0.0])


# ─── MCPT 核心 ────────────────────────────────────────────────────────────────

def _sharpe(r: np.ndarray) -> float:
    r = np.asarray(r)
    return float(r.mean() / r.std() * np.sqrt(len(r))) if r.std() > 0 else 0.0


def _run_mcpt(trade_returns: np.ndarray, n_perm: int) -> dict:
    if len(trade_returns) < 5:
        return {"obs_sharpe": 0.0, "p_value": 1.0, "perm_sharpes": [], "n_trades": len(trade_returns)}

    obs_sharpe = _sharpe(trade_returns)
    rng = np.random.default_rng(42)
    n = len(trade_returns)
    perm_sharpes = [_sharpe(np.roll(trade_returns, rng.integers(1, n))) for _ in range(n_perm)]
    perm_arr = np.array(perm_sharpes)

    return {
        "obs_sharpe":   round(float(obs_sharpe), 4),
        "p_value":      round(float((perm_arr >= obs_sharpe).mean()), 4),
        "perm_sharpes": perm_arr.tolist(),  # 前端用來畫直方圖
        "n_trades":     int(n),
    }


# ─── 績效指標 ─────────────────────────────────────────────────────────────────

def _stats(trade_returns: np.ndarray) -> dict:
    r = trade_returns
    if len(r) == 0:
        return {}
    cum = float((1 + r).prod() - 1)
    cum_arr = np.cumprod(1 + r)
    peak = np.maximum.accumulate(cum_arr)
    dd = (cum_arr - peak) / peak
    return {
        "n_trades": int(len(r)),
        "win_rate": round(float((r > 0).mean() * 100), 1),
        "avg_ret":  round(float(r.mean() * 100), 2),
        "cum_ret":  round(cum * 100, 2),
        "max_dd":   round(float(dd.min() * 100), 2),
        "sharpe":   round(_sharpe(r), 2),
    }


# ─── IS / OOS 分割 ────────────────────────────────────────────────────────────

def _split(df: pd.DataFrame, foreign: pd.Series):
    oos_days = OOS_YEARS  * TRADING_DAYS
    is_days  = IS_YEARS   * TRADING_DAYS
    total    = len(df)
    need     = is_days + oos_days
    if total < need:
        raise ValueError(
            f"資料不足：需要 {need} 個交易日，目前只有 {total} 日。"
            f"請增加歷史年數（years >= {int(need/TRADING_DAYS)+1}）。"
        )
    df_is  = df.iloc[-(is_days + oos_days):-(oos_days)]
    df_oos = df.iloc[-(oos_days):]

    def _align(ser, ref):
        return ser.reindex(ref.index).ffill().fillna(0)

    return df_is, df_oos, _align(foreign, df_is), _align(foreign, df_oos)


# ─── 主要入口 ─────────────────────────────────────────────────────────────────

def run_mcpt_web(code: str, years: int = 3, n_perm: int = 500) -> dict:
    """
    執行 MCPT 回測，回傳 JSON-serializable 結果。

    Returns:
        {
          "code": str,
          "is_period": {"start": str, "end": str},
          "oos_period": {"start": str, "end": str},
          "data_source": "live" | "simulated",
          "strategies": {
            "foreign_zscore": {
              "is":  {"stats": {...}, "mcpt": {...}},
              "oos": {"stats": {...}, "mcpt": {...}}
            },
            "kd_cross": { ... }
          }
        }
    """
    df      = _fetch_ohlcv(code, years)
    foreign, data_source = _get_foreign_with_source(code, years)
    df_is, df_oos, for_is, for_oos = _split(df, foreign)

    results = {
        "code":        code,
        "is_period":   {"start": str(df_is.index[0].date()),  "end": str(df_is.index[-1].date())},
        "oos_period":  {"start": str(df_oos.index[0].date()), "end": str(df_oos.index[-1].date())},
        "data_source": data_source,
        "n_perm":      n_perm,
        "strategies":  {},
    }

    configs = [
        ("foreign_zscore", _signals_foreign_zscore, for_is, for_oos, df_is, df_oos),
        ("kd_cross",       _signals_kd_cross,       df_is,  df_oos,  df_is, df_oos),
    ]

    for key, sig_fn, is_data, oos_data, is_df, oos_df in configs:
        strategy_result = {}
        for period, data, price_df in [("is", is_data, is_df), ("oos", oos_data, oos_df)]:
            sig  = sig_fn(data)
            rets = _compute_trade_returns(sig, price_df)
            strategy_result[period] = {
                "stats": _stats(rets),
                "mcpt":  _run_mcpt(rets, n_perm),
            }
        results["strategies"][key] = strategy_result

    return results


def _get_foreign_with_source(code: str, years: int):
    """回傳 (series, 'live'|'simulated')"""
    try:
        from app.services.institutional_data import fetch_historical_data
        raw = fetch_historical_data("foreign", code, days=years * TRADING_DAYS + 60)
        if raw and len(raw) > 30:
            ser = pd.Series(
                {pd.Timestamp(r["date"]): float(r.get("net", r.get("foreignNet", 0)))
                 for r in raw if r.get("date")}
            ).sort_index()
            if len(ser) > 30:
                return ser, "live"
    except Exception:
        pass

    n = years * TRADING_DAYS
    idx = pd.bdate_range(end=pd.Timestamp.today(), periods=n)
    rng = np.random.default_rng(int(code) % 9999 if code.isdigit() else 42)
    return pd.Series(rng.normal(0, 5000, n), index=idx), "simulated"
