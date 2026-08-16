import os
import requests
import yfinance as yf
import time
from datetime import datetime, timezone, timedelta

# 1. 잘 작동하는 기본 세팅 유지
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

# ★ 새로 추가한 핵심 기능: AI에게 질문하는 전용 함수 ★
def ask_ai(prompt):
    for model_name in valid_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1}}
        res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload).json()
        if "candidates" in res:
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
    return "AI 분석 실패"

# 2. 종목별 데이터 수집 및 분석 시작
for ticker in TICKERS:
    try:
        # 데이터 수집 (안전하게 3회 재시도 로직 유지)
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
        
        # ---------------------------------------------------------
        # ★ 선생님 아이디어 적용: 1단계 (자유롭게 분석하기) ★
        prompt1 = f"Analyze the stock/ETF {name} ({ticker}) based on this data: {stock_data}. What is its fundamental status and investment outlook?"
        raw_analysis = ask_ai(prompt1)
        
        time.sleep(2) # 구글 API 제한 안 걸리게 2초 휴식
        
        # ★ 선생님 아이디어 적용: 2단계 (중복 숫자 빼고 100% 한글 번역) ★
        prompt2 = f"""다음 원본 분석글을 '100% 한국어'로만 번역 및 요약해.

[절대 규칙]
1. 이미 데이터는 화면에 보여주므로, 번역할 때 숫자(PER 수치, 주가 등)나 영어 단어는 싹 다 빼고 자연스러운 비유로 바꿔라.
2. 불필요한 인사말, 너의 생각, 체크리스트는 절대 적지 마라.
3. 딱 아래 양식대로 2줄만 출력해라.

[원본 분석글]
{raw_analysis}

[출력 양식]
📊 현재 상태: (수치 없이 가치와 수익성을 한국어로 요약)
💡 종합 의견: (매수/관망 등 결론을 한국어로 요약)"""
        
        ai_analysis = ask_ai(prompt2)
        # ---------------------------------------------------------

    except Exception as e:
        stock_data = "데이터 수집 오류 발생"
        ai_analysis = f"오류 원인: {e}"

    # 잘 작동하는 메시지 전송 로직 유지
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🤖 [AI 멘토 의견]\n{ai_analysis}"
    
    if len(final_message) > 4000:
        final_message = final_message[:3900] + "\n\n(※ AI 분석이 너무 길어 일부 생략됨)"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    if t_res.status_code != 200:
        raise Exception(f"\n\n🚨 텔레그램 발송 실패 🚨\n종목명: {ticker}\n사유: {t_res.text}\n")
        
    time.sleep(5)
