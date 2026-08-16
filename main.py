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

# 3. 내 API 키로 쓸 수 있는 AI 모델 '자동 검색' (에러 원천 차단)
valid_models = []
try:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    list_res = requests.get(list_url).json()
    if "models" in list_res:
        for m in list_res["models"]:
            # 텍스트를 생성할 수 있는 모델들만 싹 다 모아오기
            if "generateContent" in m.get("supportedGenerationMethods", []):
                valid_models.append(m["name"].split("/")[-1])
except Exception:
    pass

# 만약 구글이 목록을 안 주면 최후의 기본값 세팅
if not valid_models:
    valid_models = ["gemini-1.5-flash", "gemini-pro"]

# 4. 종목별 개별 분석 시작
for ticker in TICKERS:
    try:
        # 야후 파이낸스 데이터 가져오기
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get("shortName", ticker)
        
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice") or "N/A"
        per = round(info.get("trailingPE", 0), 2) if info.get("trailingPE") else "N/A"
        f_per = round(info.get("forwardPE", 0), 2) if info.get("forwardPE") else "N/A"
        pbr = round(info.get("priceToBook", 0), 2) if info.get("priceToBook") else "N/A"
        roe = round(info.get("returnOnEquity", 0) * 100, 2) if info.get("returnOnEquity") else "N/A"
        debt = round(info.get("debtToEquity", 0), 2) if info.get("debtToEquity") else "N/A"
        div = round(info.get("dividendYield", 0) * 100, 2) if info.get("dividendYield") else "0"
        
        stock_data = f"현재가: ${price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        # ETF/커버드콜 맞춤형 초지능 프롬프트
        prompt = f"""
        너는 주식 초보자를 위한 수석 투자 전략가야. 
        반드시 100% '한국어'로만 대답하고, 초보자가 스마트폰에서 읽기 편하게 작성해.

        아래 {name}({ticker})의 [주식 지표]를 보고 분석해줘.

        [핵심 분석 지시사항]
        1. 일반 주식일 경우: PER, PBR 등의 지표를 바탕으로 현재 가격이 비싼지 싼지, 돈을 잘 버는지 비유를 들어 쉽게 설명해.
        2. 🚨 ETF 또는 커버드콜 ETF일 경우 (매우 중요): 지표가 N/A로 나와도 당황하지 마. 대신 네 지식을 총동원해서 이 종목 이름({name})이 추종하는 '기초 자산(본주 또는 지수)'이 정확히 무엇인지 찾아내. 그리고 껍데기 지표 대신 그 **'기초 자산'의 향후 시장 전망과 미래 가치**를 중심으로 분석해줘. (만약 한국/미국 커버드콜 ETF라면, 현재 증시 상황에서 이 커버드콜 전략이 유리할지, 배당(분배금)의 장점과 원금 손실 위험성 등 주의할 점을 꼭 포함해줘.)
        3. 종합 의견: 그래서 지금 사야 할지, 관망해야 할지 3줄 이내로 명확한 액션 플랜을 제시해.

        [주식 지표]
        {stock_data}
        """
        
        # 5. 찾아낸 모든 AI 모델들을 성공할 때까지 하나씩 찔러보기
        ai_analysis = ""
        for model_name in valid_models:
            ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(ai_url, headers={'Content-Type': 'application/json'}, json=payload)
            res_json = res.json()
            
            if "candidates" in res_json:
                ai_analysis = res_json['candidates'][0]['content']['parts'][0]['text']
                break # ◀ 분석에 성공하면 뒤에 남은 모델들은 무시하고 즉시 다음 주식으로 넘어감
            else:
                ai_analysis = f"AI 서버 거절 사유 ({model_name}): {res.text}"
                
    except Exception as e:
        stock_data = "데이터를 불러오는 중 오류가 발생했습니다."
        ai_analysis = f"오류 원인: {e}"

    # 6. 최종 메시지 조립 및 텔레그램 발송
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🤖 [AI 멘토 의견]\n{ai_analysis}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    # 구글 서버 과부하 막기 (5초 대기)
    time.sleep(5)
