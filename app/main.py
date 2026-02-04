from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.services.stock_data import get_market_index, get_filtered_stocks, get_stock_history, search_stock_code
from app.services.layout_analyzer import get_all_investors_summary, get_layout_stocks, get_multi_investor_layout, get_major_investors_layout
from app.services.breakout_scanner import get_breakout_stocks, get_rebound_stocks, get_downtrend_stocks
from app.services.dividend_scanner import get_high_dividend_stocks

app = FastAPI()
# Force server reload for stock_data updates

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('app/static/index.html')

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/market-index")
async def api_market_index():
    return get_market_index()

@app.get("/api/stocks")
async def api_stocks():
    # This might be slow, so usually we'd cache it or run it in background.
    # For this prototype, we call it directly.
    return get_filtered_stocks()

@app.get("/api/history/{stock_code}")
async def api_history(stock_code: str, interval: str = '1d'):
    return get_stock_history(stock_code, interval)

@app.get("/api/institutional-investors")
async def api_institutional_investors(days: int = 30):
    """
    取得三大法人摘要資訊
    
    Args:
        days: 統計天數（預設30天）
    """
    return get_all_investors_summary(days)

@app.get("/api/layout-stocks/major")
async def api_layout_major(days: int = 3, top_n: int = 50):
    """
    取得主力（三大法人合計）近期買超排行
    """
    return get_major_investors_layout(days, top_n)

@app.get("/api/layout-stocks/{investor_type}")
async def api_layout_stocks(investor_type: str, days: int = 90, min_score: float = 30.0, top_n: int = 50):
    """
    取得特定法人佈局的股票清單
    
    Args:
        investor_type: 'foreign'(外資), 'trust'(投信), 'dealer'(自營商)
        days: 分析期間天數（預設90天）
        min_score: 最低佈局評分（預設30分）
        top_n: 回傳前N檔股票（預設50檔）
    """
    valid_types = ['foreign', 'trust', 'dealer']
    if investor_type not in valid_types:
        return {"error": f"無效的法人類型，請使用: {', '.join(valid_types)}"}
    
    return get_layout_stocks(investor_type, days, min_score, top_n)


@app.get("/api/search")
async def api_search(query: str, limit: int = 10):
    """
    搜尋股票（支援模糊搜尋）
    
    Args:
        query: 搜尋關鍵字（代號或名稱）
        limit: 回傳結果數量上限
    """
    results = search_stock_code(query, limit)
    if results:
        return results
    return []

@app.get("/api/watchlist/check")
async def api_watchlist_check(codes: str):
    """
    批次查詢股票即時資料（用於監控清單）
    
    Args:
        codes: 逗號分隔的股票代號，例如 "2330,2454,2317"
    """
    from app.services.stock_data import get_stocks_realtime
    
    stock_codes = [code.strip() for code in codes.split(',') if code.strip()]
    
    if not stock_codes:
        return []
    
    return get_stocks_realtime(stock_codes)

@app.get("/api/breakout-stocks")
async def api_breakout_stocks():
    """
    Get potential breakout stocks (Consolidation + Spike)
    """
    return get_breakout_stocks()

@app.get("/api/rebound-stocks")
async def api_rebound_stocks():
    """
    Get low base rebound stocks
    """
    return get_rebound_stocks()

@app.get("/api/downtrend-stocks")
async def api_downtrend_stocks():
    """
    Get high level reversal stocks (Downtrend)
    """
    return get_downtrend_stocks()

@app.get("/api/layout-stocks/intersection/{mode}")
async def api_layout_intersection(mode: str, days: int = 90, min_score: float = 30.0, top_n: int = 50):
    """
    Get multi-investor layout stocks.
    mode: 'all-3' or 'any-2'
    """
    if mode not in ['all-3', 'any-2']:
        return {"error": "Invalid mode. Use 'all-3' or 'any-2'"}
        
    return get_multi_investor_layout(mode, days, min_score, top_n)

@app.get("/api/divergence-stocks")
async def api_divergence_stocks(days: int = 5, min_net_buy: int = 100, max_price_change: float = 1.0, require_lower_shadow: bool = False):
    """
    法人買超但股價下跌掃描 (Divergence Scanner)
    """
    try:
        from app.services.divergence_scanner import get_divergence_stocks
        results = get_divergence_stocks(days, min_net_buy, max_price_change, require_lower_shadow)
        return {"status": "success", "data": results}
    except Exception as e:
        print(f"Error in divergence scanner: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/high-dividend-stocks")
async def api_high_dividend_stocks(min_yield: float = 3.0, top_n: int = 50):
    """
    Get high dividend yield stocks.
    """
    return get_high_dividend_stocks(min_yield, top_n)

@app.get("/api/momentum-stocks")
async def api_momentum_stocks(min_days: int = 2):
    """
    Get consecutive rising stocks.
    Args:
        min_days: Minimum consecutive rising days (default 2)
    """
    from app.services.momentum_scanner import get_momentum_stocks
    return get_momentum_stocks(min_days)
