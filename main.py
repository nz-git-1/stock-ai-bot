import os
import requests
import yfinance as yf
import time
from datetime import datetime, timezone, timedelta

# 1. 한국 시간 설정
kst = timezone(timedelta(hours=9))
current_time = datetime.now(kst).strftime("%Y년 %m월 %d일 %H시 %M분")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 2. 티커 파일 읽기
try:
    with open("tickers.txt", "r") as f:
        TICKERS = [line.strip().upper() for line in f if line.strip()]
except FileNotFoundError:
    TICKERS = ["AAPL"]

if not TICKERS:
    raise Exception("tickers.txt 파일이 비어있습니다. 종목을 입력해 주세요!")

# 3. AI 모델 자동 찾기
valid_models = ["gemini-1.5-flash", "gemini-pro"]
try:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    list_res = requests.get(list_url).json()
    if "models" in list_res:
        valid_models = [m["name"].split("/")[-1] for m in list_res["models"] if "generateContent" in m.get("supportedGenerationMethods", [])]
except:
    pass

# 4. 숫자 데이터 철벽 방어 함수
def get_val(info, key, multiplier=1):
    try:
        val = info.get(key)
        if val is None or str(val).strip() == "": return "N/A"
        return round(float(val) * multiplier, 2)
    except:
        return "N/A"

# 5. 종목별 분석 시작
for ticker in TICKERS:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get("shortName", ticker) if isinstance(info, dict) else ticker
        
        # 화폐 기호 처리
        currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") else "$"
        
        if isinstance(info, dict):
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
        
        prompt = f"""주식 데이터를 바탕으로 초보자에게 딱 2가지만 한국어로 설명하세요.
주의: 영어 절대 금지. 내가 입력한 지시문 반복 출력 절대 금지. 수치(PER 등) 반복 언급 금지. 결과만 출력할 것.

[종목: {name} ({ticker})]
{stock_data}

[출력 양식]
📊 현재 상태: (비싼지 싼지, 돈을 잘 버는지 비유를 들어 2줄 이내로 한국어로 요약)
💡 종합 의견: (매수할지 관망할지 2줄 이내로 한국어로 명확히 결론)
"""
        
        ai_analysis = ""
        for model_name in valid_models:
            ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1} # AI 헛소리 통제
            }
            res = requests.post(ai_url, headers={'Content-Type': 'application/json'}, json=payload)
            res_json = res.json()
            
            if "candidates" in res_json:
                ai_analysis = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                break 
            else:
                ai_analysis = f"AI 서버 에러 ({model_name}): {res.text}"
                
    except Exception as e:
        stock_data = "데이터 수집 오류 발생"
        ai_analysis = f"오류 원인: {e}"

    # 메시지 조립
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🤖 [AI 멘토 의견]\n{ai_analysis}"
    
    # ★ 텔레그램 글자 수 4,000자 초과 방어막 (이게 빠져서 그동안 에러가 났습니다!) ★
    if len(final_message) > 4000:
        final_message = final_message[:3900] + "\n\n(※ AI 분석이 너무 길어 일부 생략됨)"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    if t_res.status_code != 200:
        raise Exception(f"\n\n🚨 텔레그램 발송 실패 🚨\n종목명: {ticker}\n사유: {t_res.text}\n")
        
    time.sleep(5)
