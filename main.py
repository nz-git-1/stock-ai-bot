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

for ticker in TICKERS:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get("shortName", ticker)
        
        # ★ 화폐 기호 자동 설정: 한국 주식(.KS, .KQ)은 ₩, 나머지는 $ ★
        currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") else "$"
        
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice") or "N/A"
        per = round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A"
        f_per = round(info.get("forwardPE", 0), 2) if info.get("forwardPE") else "N/A"
        pbr = round(info.get("priceToBook", 0), 2) if info.get("priceToBook") else "N/A"
        roe = round(info.get("returnOnEquity", 0) * 100, 2) if info.get("returnOnEquity") else "N/A"
        debt = round(info.get("debtToEquity", 0), 2) if info.get("debtToEquity") else "N/A"
        div = round(info.get("dividendYield", 0) * 100, 2) if info.get("dividendYield") else "0"
        
        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        # ★ AI 강력 통제 프롬프트: 영어 금지, 중복 멘트 금지 ★
        prompt = f"""
[절대 규칙]
1. 무조건 100% '한국어'로만 출력할 것 (영어 단어 사용 최소화).
2. 내가 내린 지시사항(Role, Task 등)을 앵무새처럼 답변에 적지 말 것. 바로 분석 내용만 출력할 것.
3. 쓸데없는 서론이나 인사말은 생략하고 핵심만 간결하게 작성할 것.

아래 {name}({ticker})의 [주식 지표]를 바탕으로 다음 2가지만 작성하세요:

1. 📊 현재 상태 (1~2줄): 
- 일반 주식: 지표를 보고 비싼지 싼지, 돈은 잘 버는지 초보자 눈높이에서 비유를 들어 설명.
- ETF/커버드콜: 빈 지표는 무시하고, 추종하는 '기초 자산(본주/지수)'을 파악해 향후 전망과 장단점(배당, 위험성 등)을 설명.

2. 💡 종합 의견 (3줄 이내): 
- 지금 사야 할지, 관망해야 할지 명확한 액션 플랜 제시.

[주식 지표]
{stock_data}
"""
        
        ai_analysis = ""
        for model_name in valid_models:
            ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(ai_url, headers={'Content-Type': 'application/json'}, json=payload)
            res_json = res.json()
            
            if "candidates" in res_json:
                ai_analysis = res_json['candidates'][0]['content']['parts'][0]['text']
                # AI가 가끔 불필요하게 덧붙이는 앞뒤 공백 제거
                ai_analysis = ai_analysis.strip()
                break 
            else:
                ai_analysis = f"AI 서버 거절 사유 ({model_name}): {res.text}"
                
    except Exception as e:
        stock_data = "데이터를 불러오는 중 오류가 발생했습니다."
        ai_analysis = f"오류 원인: {e}"

    # 최종 메시지 조립
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🤖 [AI 멘토 의견]\n{ai_analysis}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    time.sleep(5)
