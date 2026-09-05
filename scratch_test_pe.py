import requests
import json

def test_twse_pe():
    url = "https://www.twse.com.tw/exchangeReport/BWIBBU_d?response=json"
    res = requests.get(url, timeout=10)
    data = res.json()
    print("TWSE fields:", data.get('fields'))
    print("TWSE first row:", data.get('data')[0] if data.get('data') else "No data")

def test_tpex_pe():
    url = "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php?l=zh-tw&o=json"
    res = requests.get(url, timeout=10)
    data = res.json()
    print("TPEx first row:", data.get('aaData')[0] if data.get('aaData') else "No data")

test_twse_pe()
test_tpex_pe()
