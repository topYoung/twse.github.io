import requests
import json
import time

try:
    print("Fetching TWSE T86...")
    twse_url = "https://www.twse.com.tw/rwd/zh/fund/T86?selectType=ALLBUT0999&response=json"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(twse_url, headers=headers)
    data = res.json()
    if 'data' in data:
        print(f"TWSE Date: {data.get('date', 'Unknown')}")
        print(f"TWSE Header length: {len(data['fields'])}")
        print(f"TWSE Row count: {len(data['data'])}")
        print(f"TWSE Example row: {data['data'][0]}")
    else:
        print("TWSE format changed or failed:", data.keys())
except Exception as e:
    print("TWSE Error:", e)

print("\n----------------\n")
try:
    print("Fetching TPEx 3itrade_hedge...")
    tpex_url = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D"
    res = requests.get(tpex_url, headers=headers)
    data = res.json()
    if 'aaData' in data:
        print(f"TPEx Date: {data.get('reportDate', 'Unknown')}")
        print(f"TPEx Row count: {len(data['aaData'])}")
        print(f"TPEx Example row: {data['aaData'][0]}")
    else:
        print("TPEx format changed or failed:", data.keys())
except Exception as e:
    print("TPEx Error:", e)
