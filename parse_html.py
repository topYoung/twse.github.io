from bs4 import BeautifulSoup
import re
import json

with open("wantgoo_screener.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
scripts = soup.find_all("script")

for i, script in enumerate(scripts):
    text = script.string
    if text and ("api" in text.lower() or "screener" in text.lower() or "window." in text):
        print(f"--- Script {i} ---")
        lines = text.strip().split("\n")
        # print first few lines of script
        print("\n".join(lines[:10]))
        if len(lines) > 10:
            print("...")
            print("\n".join(lines[-3:]))
