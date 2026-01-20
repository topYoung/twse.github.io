from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.services.stock_data import get_market_index, get_filtered_stocks, get_stock_history

app = FastAPI()

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
