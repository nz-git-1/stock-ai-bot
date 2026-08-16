import os
import requests
import yfinance as yf
import time
import json
from datetime import datetime, timezone, timedelta

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

def ask_ai(prompt, force_json=False):
    for model_name in valid_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        config = {"temperature": 0.1}
        if force_json:
            config["responseMimeType"] = "application/json"
            
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}
        res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload).json()
        if "candidates" in res:
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
    return ""

for ticker in TICKERS:
    try:
        info = None
        for _ in range(3):
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                if info: break
            except Exception:
                time.sleep(2)
        
        if info is None: info = {}

        name = info.get("shortName", ticker) if isinstance(info, dict) else ticker
        currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") else "$"
        
        if isinstance(info, dict) and info:
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice") or "N/A"
            per = get_val(info, "trailingPE")
            f_per = get_val(info, "forwardPE")
            pbr = get_val(info, "priceToBook")
            roe = get_val(info, "returnOnEquity", 100)
            debt = get_val(info, "debtToEquity")
            div = get_val(info, "dividendYield", 100)
        else:
            price = per = f_per = pbr = roe = debt = div = "N/A"
            
        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        prompt1 = f"Analyze the stock/ETF {name} ({ticker}) based on this data: {stock_data}. What is its fundamental status and investment outlook?"
        raw_analysis = ask_ai(prompt1, force_json=False)
        
        time.sleep(2)
        
        prompt2 = f"""다음 원본 분석글을 읽고, 숫자와 영어를 모두 뺀 뒤 100% 한국어 비유로만 요약해.

[원본 분석글]
{raw_analysis}

반드시 아래 JSON 데이터 형식으로만 값을 채워서 반환할 것:
{{
    "status": "현재 상태에 대한 한국어 비유 요약 1줄",
    "opinion": "종합 의견(매수/관망 등)에 대한 한국어 요약 1줄"
}}"""
        
        ai_raw_json = ask_ai(prompt2, force_json=True)
        
        try:
            clean_json = ai_raw_json.replace('```json', '').replace('```', '').strip()
            data = json.loads(clean_json)
            ai_analysis = f"📊 현재 상태: {data.get('status', '요약 불가')}\n💡 종합 의견: {data.get('opinion', '의견 없음')}"
        except Exception:
            ai_analysis = "AI 요약 실패 (데이터 변환 오류)"

    except Exception as e:
        stock_data = "데이터 수집 오류 발생"
        ai_analysis = f"오류 원인: {e}"

    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🤖 [AI 멘토 의견]\n{ai_analysis}"
    
    if len(final_message) > 4000:
        final_message = final_message[:3900] + "\n\n(※ AI 분석이 너무 길어 일부 생략됨)"

    # 바로 이 부분이 오타가 나 있었습니다!
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    if t_res.status_code != 200:
        raise Exception(f"\n\n🚨 텔레그램 발송 실패 🚨\n종목명: {ticker}\n사유: {t_res.text}\n")
        
    time.sleep(5)
