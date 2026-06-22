"""
BSR 分點掃描器
從 TWSE 買賣日報表 (https://bsr.twse.com.tw/bshtm/) 抓取各券商分點對特定股票的當日買賣明細。

CAPTCHA 處理：使用 pytesseract OCR，失敗時自動重試（最多 5 次）。
快取策略：每支股票每日快取，避免重複解 CAPTCHA。
"""

import io
import time
import threading
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://bsr.twse.com.tw/bshtm"
_SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BASE_URL}/bsMenu.aspx",
}

# ── 日期快取：{股票代號: {"date": "YYYYMMDD", "data": [...]}}
_bsr_cache: Dict[str, Dict] = {}
_bsr_cache_lock = threading.Lock()


# ─────────────────────────────────────────────
# CAPTCHA 解碼（pytesseract）
# ─────────────────────────────────────────────

def _solve_captcha(img_bytes: bytes) -> str:
    """
    使用 pytesseract 辨識 BSR CAPTCHA（5 字元英數）。
    預處理：灰階 → 放大 → 二值化，提升 OCR 準確率。
    """
    try:
        import pytesseract
        from PIL import Image, ImageFilter, ImageEnhance

        img = Image.open(io.BytesIO(img_bytes)).convert("L")  # 灰階
        img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)
        img = img.filter(ImageFilter.SHARPEN)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        # 二值化：高於 140 設白，以下設黑
        img = img.point(lambda p: 255 if p > 140 else 0, "1")

        text = pytesseract.image_to_string(
            img,
            config="--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        )
        result = "".join(c for c in text.upper() if c.isalnum())[:5]
        return result
    except Exception as e:
        logger.warning(f"CAPTCHA OCR 失敗: {e}")
        return ""


# ─────────────────────────────────────────────
# 核心資料抓取
# ─────────────────────────────────────────────

def _fetch_bsr_raw(stock_code: str, max_retries: int = 5) -> Optional[List[Dict]]:
    """
    抓取指定股票的 BSR 分點資料（含 CAPTCHA 重試）。

    Returns:
        券商清單，每筆包含：
        {
            'broker_id': 券商代號,
            'broker_name': 券商名稱,
            'buy_shares': 買進張數,
            'buy_amount': 買進金額,
            'sell_shares': 賣出張數,
            'sell_amount': 賣出金額,
            'net_shares': 買賣超張數
        }
        失敗時回傳 None。
    """
    for attempt in range(max_retries):
        try:
            session = requests.Session()
            session.headers.update(_SESSION_HEADERS)

            # Step 1: GET 頁面，取得 VIEWSTATE + CAPTCHA URL
            r = session.get(f"{BASE_URL}/bsMenu.aspx", timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            form_data = {
                inp["name"]: inp.get("value", "")
                for inp in soup.find_all("input", type="hidden")
                if inp.get("name")
            }

            img_tag = soup.find("img", src=lambda s: s and "CaptchaImage.aspx" in s)
            if not img_tag:
                logger.warning(f"[{stock_code}] 找不到 CAPTCHA 圖片，重試 {attempt+1}/{max_retries}")
                time.sleep(1)
                continue

            captcha_url = f"{BASE_URL}/{img_tag['src']}"

            # Step 2: 下載 CAPTCHA 圖片並 OCR
            img_resp = session.get(captcha_url, timeout=10)
            captcha_text = _solve_captcha(img_resp.content)

            if len(captcha_text) < 4:
                logger.warning(f"[{stock_code}] CAPTCHA OCR 結果過短: '{captcha_text}'，重試")
                time.sleep(0.5)
                continue

            # Step 3: POST 表單
            form_data.update({
                "RadioButton_Normal": "RadioButton_Normal",
                "TextBox_Stkno": stock_code,
                "CaptchaControl1": captcha_text,
                "btnOK": "查詢",
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "__LASTFOCUS": "",
            })

            post_r = session.post(f"{BASE_URL}/bsMenu.aspx", data=form_data, timeout=15)
            post_soup = BeautifulSoup(post_r.text, "html.parser")

            bscontent_link = post_soup.find("a", href=lambda h: h and "bsContent" in h)
            if not bscontent_link:
                logger.warning(f"[{stock_code}] CAPTCHA 錯誤 ('{captcha_text}')，重試 {attempt+1}/{max_retries}")
                time.sleep(1)
                continue

            # Step 4: GET 分點資料
            data_r = session.get(
                f"{BASE_URL}/bsContent.aspx",
                params={"StkNo": stock_code},
                timeout=15,
            )
            data_r.encoding = "utf-8"

            rows = []
            for line in data_r.text.splitlines():
                cols = [c.strip() for c in line.split(",")]
                # 有效行：至少 6 欄，第 1 欄為數字代號
                if len(cols) >= 6 and cols[0].isdigit():
                    try:
                        buy_shares  = int(cols[2].replace(",", "")) if cols[2].replace(",", "").isdigit() else 0
                        buy_amount  = int(cols[3].replace(",", "")) if cols[3].replace(",", "").isdigit() else 0
                        sell_shares = int(cols[4].replace(",", "")) if cols[4].replace(",", "").isdigit() else 0
                        sell_amount = int(cols[5].replace(",", "")) if cols[5].replace(",", "").isdigit() else 0
                        rows.append({
                            "broker_id":    cols[0],
                            "broker_name":  cols[1],
                            "buy_shares":   buy_shares  // 1000,   # 股 → 張
                            "buy_amount":   buy_amount,
                            "sell_shares":  sell_shares // 1000,
                            "sell_amount":  sell_amount,
                            "net_shares":   (buy_shares - sell_shares) // 1000,
                        })
                    except (ValueError, IndexError):
                        continue

            logger.info(f"[{stock_code}] BSR 成功取得 {len(rows)} 筆分點資料")
            return rows

        except requests.exceptions.RequestException as e:
            logger.warning(f"[{stock_code}] 網路錯誤: {e}，重試 {attempt+1}/{max_retries}")
            time.sleep(2)
        except Exception as e:
            logger.error(f"[{stock_code}] 未預期錯誤: {e}")
            return None

    logger.error(f"[{stock_code}] BSR 查詢失敗，已重試 {max_retries} 次")
    return None


# ─────────────────────────────────────────────
# 公開 API（帶快取）
# ─────────────────────────────────────────────

def get_bsr_data(stock_code: str, force_refresh: bool = False) -> Dict:
    """
    取得指定股票的分點資料（當日快取）。

    Returns:
        {
            'stock_code': str,
            'date': 'YYYYMMDD',
            'brokers': [...],           # 全部分點清單
            'top_buyers': [...],        # 買超前 10 分點
            'concentration': float,     # 前 3 大買方佔總買量 %
            'total_buy': int,           # 合計買超張數
            'total_sell': int,
        }
    """
    today_str = date.today().strftime("%Y%m%d")

    with _bsr_cache_lock:
        cached = _bsr_cache.get(stock_code)
        if not force_refresh and cached and cached.get("date") == today_str:
            return cached["data"]

    raw = _fetch_bsr_raw(stock_code)
    if raw is None:
        return {"error": "BSR 查詢失敗，請稍後重試", "stock_code": stock_code}

    if not raw:
        return {"stock_code": stock_code, "date": today_str, "brokers": [],
                "top_buyers": [], "concentration": 0.0, "total_buy": 0, "total_sell": 0,
                "note": "無分點資料（非交易日或代號不存在）"}

    # 排序：依買超量由大到小
    raw.sort(key=lambda x: x["net_shares"], reverse=True)

    top_buyers  = [b for b in raw if b["net_shares"] > 0][:10]
    total_buy   = sum(b["buy_shares"] for b in raw)
    total_sell  = sum(b["sell_shares"] for b in raw)

    # 前 3 大買方集中度（買入張數 / 全市場買入張數）
    top3_buy = sum(b["buy_shares"] for b in sorted(raw, key=lambda x: x["buy_shares"], reverse=True)[:3])
    concentration = round((top3_buy / total_buy * 100), 1) if total_buy > 0 else 0.0

    result = {
        "stock_code":    stock_code,
        "date":          today_str,
        "brokers":       raw,
        "top_buyers":    top_buyers,
        "concentration": concentration,
        "total_buy":     total_buy,
        "total_sell":    total_sell,
    }

    with _bsr_cache_lock:
        _bsr_cache[stock_code] = {"date": today_str, "data": result}

    return result


def scan_concentrated_buying(
    stock_codes: List[str],
    min_concentration: float = 50.0,
    min_net_buy: int = 200,
) -> List[Dict]:
    """
    批次掃描多支股票，找出前 3 大券商買入集中度高的股票。

    Args:
        stock_codes: 要掃描的股票代號清單
        min_concentration: 前 3 大買方集中度門檻 % (預設 50%)
        min_net_buy: 最低合計買超門檻（張，預設 200 張）

    Returns:
        符合條件的股票清單，依集中度由高到低排序
    """
    import twstock
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []

    def _fetch_one(code):
        data = get_bsr_data(code)
        if "error" in data or not data.get("top_buyers"):
            return None
        total_net = data["total_buy"] - data["total_sell"]
        if total_net < min_net_buy:
            return None
        if data["concentration"] < min_concentration:
            return None
        name = twstock.codes[code].name if code in twstock.codes else code
        return {
            "code":          code,
            "name":          name,
            "concentration": data["concentration"],
            "total_buy":     data["total_buy"],
            "total_sell":    data["total_sell"],
            "net_buy":       total_net,
            "top_buyer":     data["top_buyers"][0]["broker_name"] if data["top_buyers"] else "",
            "top_buyer_net": data["top_buyers"][0]["net_shares"] if data["top_buyers"] else 0,
        }

    with ThreadPoolExecutor(max_workers=3) as executor:  # 保守：避免 BSR 封鎖
        futures = {executor.submit(_fetch_one, code): code for code in stock_codes}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)

    results.sort(key=lambda x: x["concentration"], reverse=True)
    return results
