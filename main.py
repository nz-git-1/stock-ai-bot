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

# 2. tickers.txt 파일에서 종목 읽어오기
try:
    with open("tickers.txt", "r") as f:
        TICKERS = [line.strip().upper() for line in f if line.strip()]
except FileNotFoundError:
    TICKERS = ["AAPL"]

# 3. 구글 AI 모델 시도 순서 (가장 빠르고 똑똑한 최신 모델부터 시도)
BEST_MODELS = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]

# 4. 종목별 개별 분석 시작
for ticker in TICKERS:
    try:
        # 야후 파이낸스 데이터 가져오기
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get("shortName", ticker)
        
        # ETF와 일반 주식의 가격 표시 방식이 달라 모두 탐색하도록 보완
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice") or "N/A"
        
        per = round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A"
        f_per = round(info.get("forwardPE", 0), 2) if info.get("forwardPE") else "N/A"
        pbr = round(info.get("priceToBook", 0), 2) if info.get("priceToBook") else "N/A"
        roe = round(info.get("returnOnEquity", 0) * 100, 2) if info.get("returnOnEquity") else "N/A"
        debt = round(info.get("debtToEquity", 0), 2) if info.get("debtToEquity") else "N/A"
        div = round(info.get("dividendYield", 0) * 100, 2) if info.get("dividendYield") else "0"
        
        stock_data = f"현재가: ${price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        prompt = f"""
        너는 주식 초보자를 위한 친절한 주식 멘토야. 
        반드시 100% '한국어'로만 대답하고, 복잡한 표나 영어는 빼고 스마트폰에서 읽기 쉽게 작성해.

        아래 {name}({ticker})의 [주식 지표]를 보고 분석해줘:
        1. 📊 현재 상태: 이 주식이 현재 비싼지 싼지, 돈을 잘 버는지, 빚(부채)이나 배당은 어떤지 일상적인 비유로 1~2줄로 아주 쉽게 설명해. ETF의 경우 지표가 없으면 생략하고 특징만 설명해.
        2. 💡 종합 의견: 지금 사야 할지, 관망할지 전체적인 투자 의견을 3줄 이내로 명확히 요약해.

        [주식 지표]
        {stock_data}
        """
        
        # 5. AI 분석 요청 (성공할 때까지 모델 변경하며 시도)
        ai_analysis = ""
        for model in BEST_MODELS:
            ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(ai_url, headers={'Content-Type': 'application/json'}, json=payload)
            res_json = res.json()
            
            if "candidates" in res_json:
                ai_analysis = res_json['candidates'][0]['content']['parts'][0]['text']
                break # 성공하면 즉시 종료하고 다음으로 넘어감
            else:
                ai_analysis = f"AI 서버 거절 사유 ({model}): {res.text}"
                
    except Exception as e:
        stock_data = "데이터를 불러오는 중 오류가 발생했습니다."
        ai_analysis = f"오류 원인: {e}"

    # 6. 최종 메시지 조립
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🤖 [AI 멘토 의견]\n{ai_analysis}"
    
    # 텔레그램으로 전송
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    # ★ 구글 무료 API 속도 제한(1분 15회)에 걸리지 않도록 종목과 종목 사이 5초 휴식 ★
    time.sleep(5)
