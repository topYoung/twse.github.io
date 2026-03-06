import requests

def test_api():
    try:
        r = requests.get('http://127.0.0.1:8000/api/macd-breakout-stocks')
        print(f"Status Code: {r.status_code}")
        data = r.json()
        print(f"Items returned: {len(data)}")
        if len(data) > 0:
            print(f"First item: {data[0]}")
    except Exception as e:
        print(f"Error test api: {e}")

if __name__ == "__main__":
    test_api()
