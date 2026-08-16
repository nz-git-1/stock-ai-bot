import os
import requests
import yfinance as yf
import time
from datetime import datetime, timezone, timedelta

# 1. 실행 시간 (한국 시간 KST 기준) 설정
kst = timezone(timedelta(hours=9))
current_time = datetime.now(kst).strftime("%Y년 %m월 %d일 %H시 %M분")

# 비밀 금고에서 암호 꺼내기
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 2. tickers.txt 파일에서 종목 목록 읽어오기
try:
    with open("tickers.txt", "r") as f:
        # 빈 줄은 무시하고 한 줄씩 읽어서 리스트로 만듦
        TICKERS = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    # 파일이 없을 경우 임시 기본값
    TICKERS = ["AAPL"]

# 3. 사용 가능한 구글 AI 모델 한 번만 찾기 (에러 방지용)
model_name = "gemini-pro"
try:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    list_res = requests.get(list_url).json()
    if "models" in list_res:
        for m in list_res["models"]:
            if "generateContent" in m.get("supportedGenerationMethods", []):
                model_name = m["name"].split("/")[-1]
                break
except Exception:
    pass

# 4. 종목 리스트를 하나씩 꺼내서 정밀 분석 후 '개별 발송'
for ticker in TICKERS:
    try:
        # 야후 파이낸스에서 실시간 데이터 가져오기 (부채비율, 배당수익률 추가)
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get("shortName", ticker)
        price = info.get("currentPrice", "N/A")
        
        per = round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A"
        f_per = round(info.get("forwardPE", 0), 2) if info.get("forwardPE") else "N/A"
        pbr = round(info.get("priceToBook", 0), 2) if info.get("priceToBook") else "N/A"
        roe = round(info.get("returnOnEquity", 0) * 100, 2) if info.get("returnOnEquity") else "N/A"
        debt = round(info.get("debtToEquity", 0), 2) if info.get("debtToEquity") else "N/A"
        div = round(info.get("dividendYield", 0) * 100, 2) if info.get("dividendYield") else "0"
        
        stock_data = f"현재가: ${price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        # 100% 한글, 초보자 맞춤형 명령서
        prompt = f"""
        너는 주식 초보자를 위한 친절한 주식 멘토야. 
        반드시 100% '한국어'로만 대답하고, 복잡한 표나 영어는 빼고 스마트폰에서 읽기 쉽게 작성해.

        아래 {name}({ticker})의 [주식 지표]를 보고 분석해줘:
        1. 📊 현재 상태: 이 주식이 현재 비싼지 싼지, 돈을 잘 버는지, 빚(부채)이나 배당은 어떤지 일상적인 비유로 1~2줄로 아주 쉽게 설명해.
        2. 💡 종합 의견: 지금 사야 할지, 관망할지 전체적인 투자 의견을 3줄 이내로 명확히 요약해.

        [주식 지표]
        {stock_data}
        """
        
        # AI 분석 요청
        ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(ai_url, headers={'Content-Type': 'application/json'}, json=payload)
        res_json = res.json()
        
        if "candidates" in res_json:
            ai_analysis = res_json['candidates'][0]['content']['parts'][0]['text']
        else:
            ai_analysis = "AI 분석을 받아오지 못했습니다."
            
    except Exception as e:
        stock_data = "데이터를 불러오는 중 오류가 발생했습니다."
        ai_analysis = f"오류 원인: {e}"

    # 5. 최종 메시지 조립 (첫 줄에 작성일시 고정)
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🤖 [AI 멘토 의견]\n{ai_analysis}"
    
    # 텔레그램으로 1종목씩 전송
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    # 텔레그램 스팸 차단을 막기 위해 한 종목 보내고 3초 휴식 (필수)
    time.sleep(3)
