import requests

def test_api():
    try:
        r = requests.get('http://127.0.0.1:8000/api/macd-breakout-stocks')
        print(f"Status Code: {r.status_code}")
        data = r.json()
        print(f"Items returned: {len(data)}")
        for x in data[:3]:
            print(f"{x['code']} {x['name']} - {x['pattern']} - {x['macd']}")
    except Exception as e:
        print(f"Error test api: {e}")

if __name__ == "__main__":
    test_api()
