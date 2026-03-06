import asyncio
from app.services.stock_data import get_filtered_stocks, get_stock_history, get_stocks_realtime
from app.services.macd_scanner import get_macd_breakout_stocks
import pandas as pd

async def main():
    stock_codes = [s['code'] for s in get_filtered_stocks()[:10]]
    print(stock_codes)
    for code in stock_codes:
        res = get_stock_history(code, interval='1d')
        if not res or 'candlestick' not in res or not res['candlestick']:
            print(f"{code} no history")
            continue
        data = []
        for item in res['candlestick']:
            try:
                data.append({
                    'Date': pd.to_datetime(item['time']),
                    'Open': float(item['open']),
                    'High': float(item['high']),
                    'Low': float(item['low']),
                    'Close': float(item['close'])
                })
            except Exception:
                pass
        if len(data) < 35:
            print(f"{code} too few history points: {len(data)}")
            continue
            
        df = pd.DataFrame(data)
        df.set_index('Date', inplace=True)
        close_series = df['Close']
        fast = 12
        slow = 26
        signal = 9
        
        ema_fast = close_series.ewm(span=fast, adjust=False).mean()
        ema_slow = close_series.ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        hist = dif - dea
        
        hist_latest = hist.iloc[-1]
        hist_prev = hist.iloc[-2]
        close_latest = close_series.iloc[-1]
        
        print(f"[{code}] {res['info']['name']}")
        print(f"  Hist={hist_latest:.2f}, Prev={hist_prev:.2f}")
        is_green_shrinking = (hist_latest < 0) and (hist_latest > hist_prev) 
        is_just_red = (hist_prev <= 0) and (hist_latest > 0)
        is_converging = abs(hist_latest) / close_latest < 0.05
        is_dif_near_zero = abs(dif.iloc[-1]) / close_latest < 0.2
        print(f"  GreenShrinking={is_green_shrinking}, JustRed={is_just_red}, Converging={is_converging}, NearZero={is_dif_near_zero}")

if __name__ == "__main__":
    asyncio.run(main())
