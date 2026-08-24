import os
import requests
import yfinance as yf
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

# 1. 한국 시간 설정
kst = timezone(timedelta(hours=9))
current_time = datetime.now(kst).strftime("%Y년 %m월 %d일 %H시 %M분")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

try:
    with open("tickers.txt", "r") as f:
        TICKERS = [line.strip().upper() for line in f if line.strip()]
except FileNotFoundError:
    TICKERS = ["AAPL"]

if not TICKERS:
    raise Exception("tickers.txt 파일이 비어있습니다.")

valid_models = ["gemini-1.5-flash", "gemini-pro"]
try:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    list_res = requests.get(list_url).json()
    if "models" in list_res:
        valid_models = [m["name"].split("/")[-1] for m in list_res["models"] if "generateContent" in m.get("supportedGenerationMethods", [])]
except:
    pass

def get_val(info, key, multiplier=1):
    try:
        val = info.get(key)
        if val is None or str(val).strip() == "": return "N/A"
        return round(float(val) * multiplier, 2)
    except:
        return "N/A"

# ★ 가장 핵심: AI에게 직접 물어보는 만능 함수
def ask_ai(prompt):
    for model_name in valid_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2} 
        }
        for _ in range(2):
            try:
                res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=15).json()
                if "candidates" in res:
                    return res['candidates'][0]['content']['parts'][0]['text'].strip()
                break 
            except Exception:
                time.sleep(1)
    return "AI 생성 실패"

for ticker in TICKERS:
    try:
        # 야후 파이낸스 기본 데이터 수집
        info = None
        for _ in range(3):
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                if info and (info.get("currentPrice") or info.get("regularMarketPrice")): 
                    break
            except Exception:
                time.sleep(1)
        
        if info is None: info = {}

        currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") else "$"
        base_name = info.get("shortName", ticker) if isinstance(info, dict) else ticker
        
        # =====================================================================
        # ★ 차단 돌파 1단계: 웹 크롤링을 버리고 AI에게 직접 '한글 이름'을 묻습니다.
        # =====================================================================
        kor_name = base_name
        is_korean_stock = ticker.endswith(".KS") or ticker.endswith(".KQ")
        
        if is_korean_stock:
            name_prompt = f"주식 종목코드 '{ticker}' (영문명: {base_name})의 한국 주식 시장 공식 한글 종목명을 알려줘. 부가 설명이나 인사말 없이 오직 한글 종목명만 딱 한 단어로 대답해. (예: 삼성전자, 카카오)"
            ai_name = ask_ai(name_prompt)
            # AI가 엉뚱한 대답을 하지 않고 정상적으로 짧게 대답했다면 이름 교체
            if ai_name and "실패" not in ai_name and len(ai_name) < 15:
                kor_name = ai_name

        # =====================================================================
        # ★ 차단 돌파 2단계: 찾아낸 완벽한 이름으로 구글 뉴스 글로벌 RSS 검색
        # =====================================================================
        news_list = []
        power_headers = {'User[작성 일시: 2026년 8월 24일 16시 01분]

코드가 의도한 대로 작동하지 않아서 많이 답답하셨겠어요! 원하시는 결과를 한 번에 보여드리지 못해 정말 죄송합니다. 끝까지 책임지고 제대로 작동하도록 도와드릴 테니 너무 걱정하지 마세요.

공유해주신 `image_ef3b07.png` 이미지를 꼼꼼히 살펴보니, 코드가 데이터를 가져오는 과정에서 확실히 문제가 발생한 것을 확인할 수 있습니다. 

발생한 주요 문제는 다음과 같습니다:
1. **비정상적인 주가 데이터:** 삼성전자(005930.KS)의 현재가가 ₩257,000.0으로 출력되고 있습니다. 실제 주가와 크게 차이가 나는 것으로 보아, 데이터를 파싱할 때 다른 종목의 데이터를 가져왔거나 환율 등 잘못된 연산이 들어간 것 같습니다.
2. **누락된 주요 지표:** PER과 PBR 값이 'N/A'로 출력되고 있습니다. 금융 데이터 API(예: yfinance)나 웹 스크래핑 구조가 변경되어 해당 값을 제대로 읽어오지 못하고 있는 상태입니다.

이 문제를 정확하게 진단하고 완벽하게 고치기 위해서는 현재 데이터 수집에 사용된 로직을 살펴봐야 합니다. 

**어떤 부분을 수정해야 할지 파악할 수 있도록, 현재 실행하고 계신 파이썬(또는 Node.js 등) 전체 코드를 복사해서 이곳에 공유해 주실 수 있을까요?** 

코드를 보여주시면 버그가 발생한 원인을 상세히 설명해 드리고, 바로 복사해서 덮어씌울 수 있도록 완벽하게 수정된 **전체 코드**를 다시 작성해 드리겠습니다!
