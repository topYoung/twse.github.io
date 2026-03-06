"""
全域 Yahoo Finance 速率限制器

所有需要呼叫 yfinance 的模組都應透過此模組來控制請求頻率，
避免同時發送過多請求觸發 Yahoo Finance 的 Rate Limit (429 Too Many Requests)。
"""
import threading
import time
import yfinance as yf
import pandas as pd


class YahooRateLimiter:
    """
    Token Bucket 速率限制器。
    控制每秒最多發出的 Yahoo Finance 請求數量。
    """

    def __init__(self, max_per_second: float = 5.0):
        """
        Args:
            max_per_second: 每秒允許的最大請求數（預設 5 次/秒）
        """
        self._lock = threading.Lock()
        self._min_interval = 1.0 / max_per_second
        self._last_request_time = 0.0

    def wait(self):
        """呼叫前等待，確保不超過速率上限"""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                sleep_time = self._min_interval - elapsed
                time.sleep(sleep_time)
            self._last_request_time = time.monotonic()


# 全域單例 — 整個應用程式共用同一個限制器
_limiter = YahooRateLimiter(max_per_second=5.0)


def fetch_stock_history(stock_code: str, ticker_symbol: str, period: str = "3mo",
                        interval: str = "1d", max_retries: int = 2) -> pd.DataFrame:
    """
    透過速率限制器安全地取得股票歷史資料。

    Args:
        stock_code: 原始股票代碼（僅用於 log）
        ticker_symbol: Yahoo Finance ticker (如 '2330.TW')
        period: 取得期間 (如 '3mo', '1y')
        interval: K 棒間隔 (如 '1d', '1wk')
        max_retries: 最大重試次數

    Returns:
        pd.DataFrame: 歷史資料，失敗時回傳空 DataFrame
    """
    for attempt in range(max_retries + 1):
        try:
            _limiter.wait()
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period=period, interval=interval)
            if not df.empty:
                # 統一移除時區資訊
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                return df
        except Exception as e:
            error_msg = str(e)
            if "Rate limited" in error_msg or "Too Many Requests" in error_msg:
                # 被限流時加長等待
                wait_time = 2.0 * (attempt + 1)
                time.sleep(wait_time)
            elif attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))
            else:
                # 最後一次嘗試也失敗
                pass

    return pd.DataFrame()
