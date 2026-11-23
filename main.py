import os
import requests
import yfinance as yf
import time
import urllib.parse
import xml.etree.ElementTree as ET
import re
import json
from datetime import datetime, timezone, timedelta

# =====================================================================
# 1. 초기 설정 (시간, 토큰, API 키)
# =====================================================================
kst = timezone(timedelta(hours=9))
current_time = datetime.now(kst).strftime("%Y년 %m월 %d일 %H시 %M분")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

try:
    with open("tickers.txt", "r") as f:
        raw_tickers = [line.strip().upper() for line in f if line.strip()]
        TICKERS = list(dict.fromkeys(raw_tickers))
except FileNotFoundError:
    TICKERS = ["005930.KS"]

if not TICKERS:
    TICKERS = ["005930.KS"]

valid_models = ["gemini-1.5-flash", "gemini-pro"]
try:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    list_res = requests.get(list_url, timeout=10).json()
    if "models" in list_res:
        valid_models = [m["name"].split("/")[-1] for m in list_res["models"] if "generateContent" in m.get("supportedGenerationMethods", [])]
except:
    pass

def ask_ai(prompt):
    for model_name in valid_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1}
        }
        for _ in range(2):
            try:
                res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=35).json()
                if "candidates" in res:
                    return res['candidates'][0]['content']['parts'][0]['text'].strip()
                break
            except Exception:
                time.sleep(2)
    return "AI 분석 생성 실패"

def get_val(info, key, multiplier=1):
    try:
        val = info.get(key)
        if val is None or str(val).strip() == "":
            return "N/A"
        return round(float(val) * multiplier, 2)
    except:
        return "N/A"

def decode_html(res):
    for enc in ("euc-kr", "cp949", "utf-8"):
        try:
            return res.content.decode(enc)
        except:
            continue
    return res.text

# 범용 14일 RSI 계산 함수 (개별 종목 및 나스닥 지수 공용)
def get_rsi(symbol, rsi_period=14):
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="2mo")
        if hist.empty or len(hist) <= rsi_period:
            return None, None

        closes = [float(x) for x in hist['Close'].dropna().tolist()]
        if len(closes) <= rsi_period:
            return None, None

        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))

        if len(gains) < rsi_period:
            return None, None

        avg_gain = sum(gains[:rsi_period]) / rsi_period
        avg_loss = sum(losses[:rsi_period]) / rsi_period

        for i in range(rsi_period, len(gains)):
            avg_gain = (avg_gain * (rsi_period - 1) + gains[i]) / rsi_period
            avg_loss = (avg_loss * (rsi_period - 1) + losses[i]) / rsi_period

        if avg_loss == 0:
            rsi_val = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_val = 100.0 - (100.0 / (1.0 + rs))

        rsi_rounded = round(rsi_val, 2)
        if rsi_rounded >= 70:
            status = "과매수"
        elif rsi_rounded <= 30:
            status = "과매도"
        else:
            status = "중립"

        return rsi_rounded, status
    except:
        return None, None

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://finance.naver.com/'
}

# =====================================================================
# 2. 글로벌 금융 시장 시황 및 연준(Fed) 발언 수집
# =====================================================================
global_ai_analysis = ""
try:
    global_news_query = urllib.parse.quote("글로벌 증시 OR 미국 증시")
    global_news_url = f"https://news.google.com/rss/search?q={global_news_query}&hl=ko&gl=KR&ceid=KR:ko"

    res = requests.get(global_news_url, headers=headers, timeout=15)
    root = ET.fromstring(res.text)
    global_raw_titles = [item.find('title').text for item in root.findall('.//channel/item')[:4]]

    global_news_text = ""
    for t in global_raw_titles:
        clean_title = t.replace('&quot;', '"').replace('&amp;', '&')
        global_news_text += f"- {clean_title}\n"

    if not global_news_text.strip():
        global_news_text = "최근 글로벌 주요 뉴스 없음"

    fed_news_query = urllib.parse.quote("Kevin Warsh OR FOMC OR Federal Reserve speech")
    fed_news_url = f"https://news.google.com/rss/search?q={fed_news_query}&hl=en-US&gl=US&ceid=US:en"

    fed_res = requests.get(fed_news_url, headers=headers, timeout=15)
    fed_root = ET.fromstring(fed_res.text)
    fed_raw_titles = [item.find('title').text for item in fed_root.findall('.//channel/item')[:4]]

    fed_news_text = ""
    for t in fed_raw_titles:
        clean_title = t.replace('&quot;', '"').replace('&amp;', '&')
        fed_news_text += f"- {clean_title}\n"

    global_prompt = f"""당신은 수석 글로벌 거시경제 애널리스트입니다. 
현재 한국 시간은 {current_time}입니다.
아래의 최근 글로벌 핵심 뉴스와 연방준비제도(Fed) 관련 뉴스를 바탕으로 다음 3가지를 작성해 주세요.

[글로벌 증시 핵심 뉴스]
{global_news_text}

[연준(Fed) 및 FOMC 관련 최근 동향]
{fed_news_text}

[요청 사항]
1. 위 뉴스가 글로벌 금융 시장 및 국내 증시에 미칠 의미를 심도 있게 분석하고 투자 조언을 작성하세요.
2. 연준 의장(케빈 워시) 및 연은 총재들의 발언, 혹은 FOMC 회의 내용이 포함되어 있다면 그 숨은 의미(매파적/비둘기파적 스탠스)와 파급력을 집중 분석해 주세요.
3. {current_time}을 기준으로, '어제'와 '오늘' 발표된 한국 및 미국의 핵심 경제 지표(PPI, CPI 등)를 명시하고, 향후 1주일간 예정된 주요 경제 지표 일정(수출입동향, 기준금리 결정 등)을 일자별, 시간별로 상세히 요약하여 하단에 포함해 주세요.
* 주의: 마크다운 기호(*, **, #)는 절대 사용하지 말고 텍스트와 이모지만 사용하세요."""

    global_ai_analysis = ask_ai(global_prompt)
    if global_ai_analysis:
        global_ai_analysis = global_ai_analysis.replace('*', '').replace('#', '')
except Exception:
    global_ai_analysis = "글로벌 시황 데이터 수집 지연으로 인한 생략"

# =====================================================================
# 3. 개별 종목 데이터 수집, 리포트 생성 및 발송
# =====================================================================
for ticker in TICKERS:
    try:
        is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")
        currency = "₩" if is_korean else "$"

        display_name = ticker
        price = per = f_per = pbr = roe = debt = div = "N/A"
        raw_price_num = None

        try:
            stock = yf.Ticker(ticker)
            info = stock.info if stock.info else {}

            if is_korean:
                code = ticker.split('.')[0]
                try:
                    nv_url = f"https://finance.naver.com/item/main.naver?code={code}"
                    html_res = requests.get(nv_url, headers=headers, timeout=5)
                    html_decoded = decode_html(html_res)
                    name_m = re.search(r'<title>(.*?)\s*:\s*네이버', html_decoded)
                    if name_m:
                        display_name = name_m.group(1).strip()
                except:
                    pass
            else:
                display_name = info.get("shortName", ticker)

            hist = stock.history(period="5d")
            if not hist.empty:
                raw_price_num = float(hist['Close'].iloc[-1])
            else:
                raw_price_num = info.get("currentPrice") or stock.fast_info.get("lastPrice")

            if raw_price_num:
                price = f"{int(raw_price_num):,}" if is_korean else f"{float(raw_price_num):,.2f}"

            per = get_val(info, "trailingPE")
            f_per = get_val(info, "forwardPE")
            pbr = get_val(info, "priceToBook")
            roe = get_val(info, "returnOnEquity", 100)
            debt = get_val(info, "debt
