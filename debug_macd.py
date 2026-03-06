import asyncio
from app.services.stock_data import get_filtered_stocks, get_stock_history, get_stocks_realtime
import pandas as pd

async def main():
    res = get_stock_history('2330', interval='1d')
    if res and 'candlestick' in res:
        data = []
        for item in res['candlestick']:
            data.append({
                'Date': pd.to_datetime(item['time']),
                'Open': item['open'],
                'High': item['high'],
                'Low': item['low'],
                'Close': item['close']
            })
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
        hist_prev2 = hist.iloc[-3]
        
        dif_latest = dif.iloc[-1]
        dea_latest = dea.iloc[-1]
        close_latest = close_series.iloc[-1]
        
        print("2330 MACD:")
        print(f"Close: {close_latest}")
        print(f"DIF: {dif_latest}")
        print(f"DEA: {dea_latest}")
        print(f"Hist (latest, prev, prev2): {hist_latest}, {hist_prev}, {hist_prev2}")
        print(f"Converging ratio: {abs(hist_latest) / close_latest}")
        
    res2 = get_stock_history('2317', interval='1d')
    if res2 and 'candlestick' in res2:
        data = []
        for item in res2['candlestick']:
            data.append({
                'Date': pd.to_datetime(item['time']),
                'Open': item['open'],
                'High': item['high'],
                'Low': item['low'],
                'Close': item['close']
            })
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
        hist_prev2 = hist.iloc[-3]
        
        dif_latest = dif.iloc[-1]
        dea_latest = dea.iloc[-1]
        close_latest = close_series.iloc[-1]
        
        print("\n2317 MACD:")
        print(f"Close: {close_latest}")
        print(f"DIF: {dif_latest}")
        print(f"DEA: {dea_latest}")
        print(f"Hist (latest, prev, prev2): {hist_latest}, {hist_prev}, {hist_prev2}")
        print(f"Converging ratio: {abs(hist_latest) / close_latest}")

if __name__ == "__main__":
    asyncio.run(main())

