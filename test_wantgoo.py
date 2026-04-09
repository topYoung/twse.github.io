import urllib.request
import ssl

url = "https://www.wantgoo.com/screener"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
}
context = ssl._create_unverified_context()
req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, context=context, timeout=10) as response:
        html = response.read().decode('utf-8')
        with open("wantgoo_screener.html", "w") as f:
            f.write(html)
        print("Success! Wrote to wantgoo_screener.html. Length:", len(html))
except Exception as e:
    print(f"Error fetching {url}: {e}")
