"""
backtest_mcpt.py — Monte Carlo Permutation Test (MCPT) 回測驗證工具
=======================================================================
驗證「外資 Z-Score 突買」策略是否具統計顯著性，
並與「KD 金叉」策略對照。

使用方式
--------
    python backtest_mcpt.py --code 2330 [--years 3] [--permutations 1000]
    python backtest_mcpt.py --scan-codes 2330,2454,2317

策略定義
--------
策略 A（主力）：外資 Z-Score 突買
    - 滾動 252 日均值 + 標準差
    - Z-Score ≥ 2.0 → 隔日開盤買入，持有 5 個交易日

策略 B（對照）：KD 金叉
    - K 線從下方穿越 D 線（K 前日 < D 前日，且當日 K > D）
    - 隔日開盤買入，持有 5 個交易日

MCPT 說明
---------
- 對「進場後的持有報酬」序列做排列（而非對進場訊號排列）
- IS: 前 2 年 / OOS: 後 1 年
- 排列次數：1000 次，計算 p-value（雙尾）

輸出
----
- 終端機：各策略績效摘要 + p-value
- 圖檔：mcpt_validation_result.png
"""

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

warnings.filterwarnings("ignore")

# ─── 常數 ──────────────────────────────────────────────────────────────────────
TRADING_DAYS  = 250        # 台股年均交易日
FEE_ONE_WAY   = 0.003      # 單邊手續費 0.3%
HOLD_DAYS     = 5          # 持有天數（交易日）
ZSCORE_WIN    = 252        # Z-Score 計算視窗（日）
ZSCORE_THRES  = 2.0        # Z-Score 進場門檻
N_PERMUTATIONS = 1000      # MCPT 排列次數
IS_YEARS      = 2          # 樣本內年數
OOS_YEARS     = 1          # 樣本外年數


# ─── 資料取得 ──────────────────────────────────────────────────────────────────

def fetch_ohlcv(code: str, years: int = 3) -> pd.DataFrame:
    """從 yfinance 取得台股 OHLCV（代號加 .TW）"""
    ticker = f"{code}.TW"
    period = f"{years}y"
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"yfinance 找不到 {ticker} 的資料，請確認代號。")
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    # 攤平 MultiIndex columns (yfinance 新版)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df


def fetch_foreign_net(code: str, years: int = 3) -> pd.Series:
    """
    從本地 app 服務取得外資買賣超日序列。
    若取不到（無網路或非台股），則模擬正態分布資料（僅供測試）。
    回傳：index=日期, values=外資買賣超張數
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from app.services.institutional_data import fetch_historical_data
        raw = fetch_historical_data("foreign", code, days=years * TRADING_DAYS + 50)
        if raw and isinstance(raw, list) and len(raw) > 30:
            ser = pd.Series(
                {pd.Timestamp(r["date"]): float(r.get("net", r.get("foreignNet", 0)))
                 for r in raw if r.get("date")}
            ).sort_index()
            return ser
    except Exception:
        pass

    # ── fallback：模擬資料（僅用於離線測試）
    print(f"[警告] 無法取得 {code} 外資資料，使用模擬資料（測試用）")
    n = years * TRADING_DAYS
    idx = pd.bdate_range(end=pd.Timestamp.today(), periods=n)
    rng = np.random.default_rng(int(code) % 9999 if code.isdigit() else 42)
    return pd.Series(rng.normal(0, 5000, n), index=idx)


# ─── 策略訊號生成 ──────────────────────────────────────────────────────────────

def signals_foreign_zscore(foreign: pd.Series) -> pd.Series:
    """
    計算外資 Z-Score 訊號序列。
    回傳：boolean Series，True 表示當日觸發，對齊 foreign.index。
    """
    roll_mean = foreign.rolling(ZSCORE_WIN).mean()
    roll_std  = foreign.rolling(ZSCORE_WIN).std()

    # std floor：防止波動過小時 Z 值虛高
    std_floor = roll_mean.abs() * 0.30
    std_floor = std_floor.clip(lower=10_000)
    eff_std   = roll_std.clip(lower=std_floor)

    z = (foreign - roll_mean) / eff_std
    # 安全網：絕對值 >= 5000 張也算進場
    sig = (z >= ZSCORE_THRES) | (foreign >= 5000)
    return sig.fillna(False)


def signals_kd_cross(df: pd.DataFrame) -> pd.Series:
    """
    計算 KD 金叉訊號（9日隨機指標）。
    K 從下方穿越 D。
    """
    low_min  = df["Low"].rolling(9).min()
    high_max = df["High"].rolling(9).max()
    denom    = (high_max - low_min).replace(0, np.nan)
    rsv      = (df["Close"] - low_min) / denom * 100

    K = rsv.ewm(com=2, adjust=False).mean()
    D = K.ewm(com=2, adjust=False).mean()

    cross = (K.shift(1) < D.shift(1)) & (K > D)
    return cross.fillna(False)


# ─── 報酬計算 ──────────────────────────────────────────────────────────────────

def compute_trade_returns(signals: pd.Series, df: pd.DataFrame) -> np.ndarray:
    """
    根據訊號計算每筆交易的持有報酬（已扣費用）。

    進場：訊號當日 close 買入（簡化，不管隔日 open）
    出場：持有 HOLD_DAYS 個交易日後 close 賣出
    """
    prices  = df["Close"].values
    idx     = df.index
    sig_idx = signals.reindex(idx, fill_value=False)

    rets = []
    in_trade_until = -1

    for i, (dt, is_sig) in enumerate(zip(idx, sig_idx)):
        if not is_sig:
            continue
        if i <= in_trade_until:
            continue  # 前一筆未結束，跳過（不重疊）
        exit_i = min(i + HOLD_DAYS, len(prices) - 1)
        p_in   = prices[i]
        p_out  = prices[exit_i]
        if p_in <= 0:
            continue
        gross = (p_out - p_in) / p_in
        net   = gross - 2 * FEE_ONE_WAY  # 進出各一次
        rets.append(net)
        in_trade_until = exit_i

    return np.array(rets) if rets else np.array([0.0])


# ─── MCPT 核心 ─────────────────────────────────────────────────────────────────

def run_mcpt(trade_returns: np.ndarray, n_perm: int = N_PERMUTATIONS) -> dict:
    """
    對持有報酬序列做 MCPT（保留自相關性的排列）。

    做法：對整個報酬序列做循環移位排列（circular block permutation），
    計算每次的夏普比率，最後統計 p-value。
    """
    if len(trade_returns) < 5:
        return {"p_value": 1.0, "perm_sharpes": [], "obs_sharpe": 0.0}

    def sharpe(r):
        r = np.asarray(r)
        if r.std() == 0:
            return 0.0
        return r.mean() / r.std() * np.sqrt(len(r))

    obs_sharpe = sharpe(trade_returns)
    rng = np.random.default_rng(42)

    perm_sharpes = []
    n = len(trade_returns)
    for _ in range(n_perm):
        shift  = rng.integers(1, n)
        perm_r = np.roll(trade_returns, shift)
        perm_sharpes.append(sharpe(perm_r))

    perm_arr = np.array(perm_sharpes)
    p_val    = (perm_arr >= obs_sharpe).mean()

    return {
        "obs_sharpe":   float(obs_sharpe),
        "perm_sharpes": perm_arr.tolist(),
        "p_value":      float(p_val),
        "n_trades":     int(n),
    }


def strategy_stats(trade_returns: np.ndarray) -> dict:
    """計算常見績效指標"""
    r = trade_returns
    if len(r) == 0:
        return {}
    win_rate = float((r > 0).mean())
    avg_ret  = float(r.mean())
    max_dd   = float(_max_drawdown(r))
    sharpe   = float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if r.std() > 0 else 0.0
    return {
        "n_trades": len(r),
        "win_rate": round(win_rate * 100, 1),
        "avg_ret":  round(avg_ret * 100, 2),
        "sharpe":   round(sharpe, 2),
        "max_dd":   round(max_dd * 100, 2),
        "cum_ret":  round(float((1 + r).prod() - 1) * 100, 2),
    }


def _max_drawdown(rets: np.ndarray) -> float:
    cum = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    return float(dd.min()) if len(dd) > 0 else 0.0


# ─── IS / OOS 分割 ─────────────────────────────────────────────────────────────

def split_is_oos(df: pd.DataFrame, foreign: pd.Series):
    """
    依照 IS_YEARS + OOS_YEARS 切割。
    回傳：(df_is, df_oos, foreign_is, foreign_oos)
    """
    total_days = len(df)
    oos_days   = OOS_YEARS * TRADING_DAYS
    is_days    = IS_YEARS  * TRADING_DAYS

    if total_days < is_days + oos_days:
        raise ValueError(
            f"資料不足：需要 {is_days + oos_days} 個交易日，現有 {total_days} 日。"
            "請下載更長歷史（--years 增大）。"
        )

    df_is  = df.iloc[-(is_days + oos_days):-(oos_days)]
    df_oos = df.iloc[-(oos_days):]

    def _align(ser, ref_df):
        return ser.reindex(ref_df.index).ffill()

    return df_is, df_oos, _align(foreign, df_is), _align(foreign, df_oos)


# ─── 繪圖 ─────────────────────────────────────────────────────────────────────

def plot_results(code: str, results: dict, save_path: str = "mcpt_validation_result.png"):
    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor("#0d1117")
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35)
    text_color = "#c9d1d9"
    grid_color = "#30363d"

    strategies = [
        ("foreign_zscore", "外資 Z-Score 突買", "#f0883e"),
        ("kd_cross",       "KD 金叉",           "#58a6ff"),
    ]

    for col, (key, label, color) in enumerate(strategies):
        for period, row in [("is", 0), ("oos", 1)]:
            ax = fig.add_subplot(gs[row, col])
            period_label = "IS（樣本內）" if period == "is" else "OOS（樣本外）"
            ax.set_facecolor("#161b22")
            ax.tick_params(colors=text_color)
            for spine in ax.spines.values():
                spine.set_edgecolor(grid_color)
            ax.yaxis.label.set_color(text_color)
            ax.xaxis.label.set_color(text_color)
            ax.title.set_color(text_color)

            res = results.get(f"{key}_{period}")
            if not res:
                ax.text(0.5, 0.5, "無資料", ha="center", va="center",
                        transform=ax.transAxes, color=text_color)
                continue

            stats = res["stats"]
            mcpt  = res["mcpt"]

            # 排列分布
            perm = np.array(mcpt.get("perm_sharpes", []))
            obs  = mcpt.get("obs_sharpe", 0)
            p    = mcpt.get("p_value", 1.0)

            if len(perm) > 0:
                ax.hist(perm, bins=40, color=grid_color, edgecolor="none", alpha=0.7)
                ax.axvline(obs, color=color, linewidth=2, label=f"實際 Sharpe={obs:.2f}")
                ax.legend(fontsize=8, labelcolor=text_color, facecolor="#0d1117")

            sig_str = "✅ 顯著(p<0.05)" if p < 0.05 else "❌ 不顯著"
            ax.set_title(
                f"{label} {period_label}\n"
                f"p={p:.3f} {sig_str} | 勝率 {stats.get('win_rate', 0)}% | "
                f"夏普 {stats.get('sharpe', 0):.2f}",
                fontsize=8,
                color=text_color,
            )
            ax.set_xlabel("排列夏普比率", fontsize=7, color=text_color)
            ax.set_ylabel("次數", fontsize=7, color=text_color)

    # 綜合比較表格
    ax_tbl = fig.add_subplot(gs[:, 2])
    ax_tbl.set_facecolor("#161b22")
    ax_tbl.axis("off")
    ax_tbl.set_title(f"{code} 策略績效摘要", color=text_color, fontsize=11, fontweight="bold")

    col_labels = ["指標", "外資Z-Score IS", "外資Z-Score OOS", "KD金叉 IS", "KD金叉 OOS"]
    row_labels = ["交易次數", "勝率(%)", "平均報酬(%)", "累計報酬(%)", "最大回撤(%)", "夏普比率", "MCPT p值"]
    stat_keys  = ["n_trades", "win_rate", "avg_ret", "cum_ret", "max_dd", "sharpe"]
    p_keys     = ["foreign_zscore_is", "foreign_zscore_oos", "kd_cross_is", "kd_cross_oos"]

    table_data = []
    for sk in stat_keys:
        row = [sk]
        for pk in p_keys:
            res = results.get(pk, {})
            val = res.get("stats", {}).get(sk, "-")
            row.append(str(val))
        table_data.append(row)
    # p-value row
    prow = ["MCPT p值"]
    for pk in p_keys:
        res = results.get(pk, {})
        pv  = res.get("mcpt", {}).get("p_value", "-")
        prow.append(f"{pv:.3f}" if isinstance(pv, float) else str(pv))
    table_data.append(prow)

    tbl = ax_tbl.table(
        cellText=[[r[0]] + r[1:] for r in table_data],
        colLabels=col_labels,
        cellLoc="center",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.scale(1, 1.6)
    for (i, j), cell in tbl.get_celld().items():
        cell.set_facecolor("#1c2128" if i % 2 == 0 else "#161b22")
        cell.set_text_props(color=text_color)
        cell.set_edgecolor(grid_color)

    fig.suptitle(f"MCPT 回測驗證 — {code}", color=text_color, fontsize=14, fontweight="bold")
    plt.savefig(save_path, dpi=120, bbox_inches="tight", facecolor="#0d1117")
    print(f"\n圖表已儲存：{save_path}")


# ─── 主程式 ───────────────────────────────────────────────────────────────────

def run_backtest(code: str, years: int = 3, n_perm: int = N_PERMUTATIONS):
    print(f"\n{'='*60}")
    print(f"  MCPT 回測驗證：{code}  ({years} 年資料, {n_perm} 次排列)")
    print(f"{'='*60}")

    print(f"  下載 {code} OHLCV 資料…")
    df = fetch_ohlcv(code, years)
    print(f"  取得 {len(df)} 個交易日")

    print(f"  取得外資買賣超資料…")
    foreign = fetch_foreign_net(code, years)

    df_is, df_oos, for_is, for_oos = split_is_oos(df, foreign)
    print(f"  IS: {df_is.index[0].date()} ~ {df_is.index[-1].date()} ({len(df_is)} 日)")
    print(f"  OOS: {df_oos.index[0].date()} ~ {df_oos.index[-1].date()} ({len(df_oos)} 日)")

    results = {}
    configs = [
        ("foreign_zscore", signals_foreign_zscore, [for_is, for_oos]),
        ("kd_cross",       signals_kd_cross,       [df_is,  df_oos]),
    ]

    for key, sig_fn, data_pair in configs:
        for period, period_df, period_data in [
            ("is",  df_is,  data_pair[0]),
            ("oos", df_oos, data_pair[1]),
        ]:
            sig  = sig_fn(period_data)
            rets = compute_trade_returns(sig, period_df)
            mcpt = run_mcpt(rets, n_perm)
            stat = strategy_stats(rets)
            label = "外資Z-Score" if "foreign" in key else "KD金叉"
            period_label = "IS" if period == "is" else "OOS"
            print(
                f"  [{label} {period_label}] 交易 {stat.get('n_trades', 0)} 次 | "
                f"勝率 {stat.get('win_rate', 0)}% | 夏普 {stat.get('sharpe', 0):.2f} | "
                f"p={mcpt['p_value']:.3f}"
            )
            results[f"{key}_{period}"] = {"stats": stat, "mcpt": mcpt}

    out_path = f"mcpt_{code}.png"
    plot_results(code, results, save_path=out_path)
    return results


def main():
    parser = argparse.ArgumentParser(description="MCPT 回測驗證工具")
    parser.add_argument("--code",  default="2330", help="台股代號（預設 2330）")
    parser.add_argument("--years", type=int, default=3, help="歷史資料年數（預設 3）")
    parser.add_argument("--permutations", type=int, default=N_PERMUTATIONS, help=f"排列次數（預設 {N_PERMUTATIONS}）")
    parser.add_argument("--scan-codes", default="", help="批次驗證，逗號分隔，例如 2330,2454")
    args = parser.parse_args()

    codes = [c.strip() for c in args.scan_codes.split(",") if c.strip()] if args.scan_codes else [args.code]

    for code in codes:
        try:
            run_backtest(code, years=args.years, n_perm=args.permutations)
        except Exception as e:
            print(f"[{code}] 錯誤：{e}")

    print("\n完成。")


if __name__ == "__main__":
    main()
