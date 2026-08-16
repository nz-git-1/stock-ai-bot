import os
import requests
import yfinance as yf
import time
from datetime import datetime, timezone, timedelta

# 1. 실행 시간 (한국 시간 KST 기준) 설정
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

valid_models = []
try:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    list_res = requests.get(list_url).json()
    if "models" in list_res:
        for m in list_res["models"]:
            if "generateContent" in m.get("supportedGenerationMethods", []):
                valid_models.append(m["name"].split("/")[-1])
except Exception:
    pass

if not valid_models:
    valid_models = ["gemini-1.5-flash", "gemini-pro"]

# ★ 엔비디아(NVDA) 누락 방지: 숫자가 비어있어도 절대 에러 안 나게 막아주는 함수 ★
def safe_round(val):
    try:
        if val is None or str(val).isalpha():
            return "N/A"
        return round(float(val), 2)
    except:
        return "N/A"

for ticker in TICKERS:
    try:
        print(f"--- {ticker} 분석 시작 ---")
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get("shortName", ticker) if isinstance(info, dict) else ticker
        
        currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") else "$"
        
        if isinstance(info, dict):
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice") or "N/A"
            per = safe_round(info.get("trailingPE"))
            f_per = safe_round(info.get("forwardPE"))
            pbr = safe_round(info.get("priceToBook"))
            roe = safe_round(info.get("returnOnEquity") * 100) if info.get("returnOnEquity") else "N/A"
            debt = safe_round(info.get("debtToEquity"))
            div = safe_round(info.get("dividendYield") * 100) if info.get("dividendYield") else "0"
        else:
            price = per = f_per = pbr = roe = debt = div = "N/A"
            
        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        # ★ 초강력 족쇄 프롬프트: 영어/수치 반복 완전 금지, 출력 양식 강제 ★
        prompt = f"""
너는 초보자를 위한 주식 분석가야. 아래 규칙을 어기면 시스템이 파괴되니 무조건 지켜.

[절대 규칙]
1. 답변은 처음부터 끝까지 무조건 100% '한국어'로만 출력해. 
2. 네가 받은 지시사항이나 영어 단어는 입 밖에도 꺼내지 마.
3. PER, PBR, 현재가 등의 수치는 이미 화면에 표시되므로, 답변에서 절대 숫자를 다시 언급하지 마. (예: "PER이 24라서" -> "버는 돈에 비해 주가가 비싸서"로 변경)
4. 오직 아래 [답변 양식]에 맞춰서 딱 2가지만 간결하게 출력해.

[답변 양식]
📊 현재 상태: (수치 언급 절대 금지! 현재 비싼지 싼지, 기업 상태나 기초자산이 튼튼한지 비유를 들어 1~2줄로 설명)
💡 종합 의견: (그래서 사라는 건지 말라는 건지 2줄 이내로 명확하게 결론)

[종목 정보]
이름: {name} ({ticker})
{stock_data}
"""
        
        ai_analysis = ""
        for model_name in valid_models:
            ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            # ★ AI의 창의성(헛소리)을 죽이고 정해진 대로만 말하게 하는 '온도(temperature)' 설정 추가 ★
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1} 
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

    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🤖 [AI 멘토 의견]\n{ai_analysis}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    # 텔레그램 전송 실패 시 강제로 에러 띄우기 (엔비디아 증발 원인 파악용)
    if t_res.status_code != 200:
        print(f"[{ticker}] 텔레그램 전송 실패: {t_res.text}")
        
    time.sleep(5)
