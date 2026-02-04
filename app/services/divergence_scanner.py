
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
from .institutional_data import fetch_historical_data, INVESTOR_NAMES
from .stock_data import get_stock_history
from .categories import STOCK_SUB_CATEGORIES
import twstock

def get_divergence_stocks(days: int = 5, min_net_buy: int = 100, max_price_change: float = 0.0, require_lower_shadow: bool = False) -> List[Dict]:
    """
    Find stocks where Major Investors are buying (Net Buy > 0) 
    but Price is falling (Change < 0) over the specified period.

    Args:
        days: Analysis period in days (default 5).
        min_net_buy: Minimum net buy volume (sheets) by institutions (default 100).
        max_price_change: Max price change percentage allow (default 0.0, i.e., must be falling).

    Returns:
        List of matching stocks sorted by Net Buy volume.
    """
    
    # 1. Fetch Aggregated Institutional Data
    investors = ['foreign', 'trust', 'dealer']
    stock_stats = {} # {code: {total_net: 0, details: {}, name: ''}}

    print(f"[Divergence] Scanning match for {days} days, Min Buy: {min_net_buy}, Max Change: {max_price_change}%")

    for inv in investors:
        # Fetch slightly more days to ensure we cover holidays/weekends overlap if needed,
        # but fetch_historical_data handles dates reasonably well.
        # We fetch exactly 'days' worth of recent data ideally.
        # However, fetch_historical_data takes 'days' as calendar lookback usually? 
        # distinct look at fetch_historical_data implementation:
        # It calculates start_date = now - days. So '5' means last 5 calendar days.
        # We might want 'trading days'. For now use larger calendar window e.g. days * 1.5
        
        data_map = fetch_historical_data(inv, days=int(days * 2)) 
        
        if not data_map:
            continue
            
        # Filter dates to keep only the actual latest 'days' trading days if map has more
        sorted_dates = sorted(data_map.keys(), reverse=True)[:days]
        
        for date_str in sorted_dates:
            stocks = data_map[date_str]
            for s in stocks:
                code = s['stock_code']
                net = s['net']
                
                if code not in stock_stats:
                    stock_stats[code] = {
                        'code': code,
                        'name': s['stock_name'],
                        'total_net': 0,
                        'details': {'foreign': 0, 'trust': 0, 'dealer': 0}
                    }
                
                stock_stats[code]['total_net'] += net
                stock_stats[code]['details'][inv] += net

    # 2. Filter Candidates (Inst Net Buy > threshold)
    candidates = []
    for code, stats in stock_stats.items():
        # Convert min_net_buy (sheets) to shares (raw data is usually shares? No wait, check parser)
        # In institutional_data.py, it parses '1,234' into int. 
        # Usually TWSE API returns shares. So 1000 shares = 1 sheet.
        # But 'min_net_buy' argument implies "Sheets" usually in UI?
        # Let's standardize: Input arg is 'Sheets', Data is 'Shares'.
        # Threshold = min_net_buy * 1000
        
        if stats['total_net'] >= (min_net_buy * 1000):
            candidates.append(stats)
            
    print(f"[Divergence] Found {len(candidates)} candidates with Net Buy > {min_net_buy} sheets")
    
    # 3. Check Price Change for Candidates
    results = []
    
    def check_price_divergence(stock_info):
        code = stock_info['code']
        # Fetch history for trend (allow slightly longer to find start point)
        # interval '1d', period '1mo' is safe.
        hist_data = get_stock_history(code, interval='1d')
        
        candles = hist_data.get('candlestick', [])
        if not candles or len(candles) < 2:
            return None
            
        # We need change over the last 'days'. 
        # Take last candle (today/yesterday) vs candle 'days' ago.
        # If fewer candles than days, take first available.
        
        # Verify if we have enough data
        idx_end = -1
        idx_start = -1 - min(len(candles) - 1, days)
        
        end_price = candles[idx_end]['close']
        start_price = candles[idx_start]['close'] # This is 'close' of N days ago? 
        # Actually divergence usually means: Cumulative Net Buy is Positive, BUT Price Trend is Down.
        # Price Change = (End - Start) / Start
        
        price_change_pct = ((end_price - start_price) / start_price) * 100
        
        price_change_pct = ((end_price - start_price) / start_price) * 100
        
        # Check Lower Shadow (Optional)
        has_lower_shadow = False
        if require_lower_shadow:
            last_candle = candles[idx_end]
            c_open = last_candle['open']
            c_close = last_candle['close']
            c_low = last_candle['low']
            c_high = last_candle['high'] # for reference if needed
            
            body = abs(c_open - c_close)
            lower_shadow = min(c_open, c_close) - c_low
            
            # Condition: Lower shadow is significant
            # 1. Shadow length > 0.5 * Body length (Visible tail relative to body)
            # 2. OR if body is very small (Doji), Shadow > 0.2% of price
            
            is_significant_shadow = False
            
            if body > 0:
                 if lower_shadow >= body * 0.5:
                     is_significant_shadow = True
            
            # For Doji or small body, checking ratio is better
            if lower_shadow / end_price >= 0.002: # 0.2% lower shadow
                is_significant_shadow = True
                
            if not is_significant_shadow:
                return None # Skip if required but not found
            
            has_lower_shadow = True

        if price_change_pct <= max_price_change:
            # Match!
            stock_info['price'] = round(end_price, 2)
            stock_info['price_change_pct'] = round(price_change_pct, 2)            
            # Add category
            cat = '其他'
            if code in STOCK_SUB_CATEGORIES:
                cat = STOCK_SUB_CATEGORIES[code]
            elif code in twstock.codes:
                if twstock.codes[code].group:
                    cat = twstock.codes[code].group.replace('業', '')
            stock_info['category'] = cat
            stock_info['has_lower_shadow'] = has_lower_shadow
            
            return stock_info
        return None

    # Use ThreadPool for price checks
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(check_price_divergence, cand) for cand in candidates]
        for f in futures:
            res = f.result()
            if res:
                results.append(res)

    # 4. Sort by Total Net Buy (Descending)
    results.sort(key=lambda x: x['total_net'], reverse=True)
    
    print(f"[Divergence] Returning {len(results)} matches")
    return results
