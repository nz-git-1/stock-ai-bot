import os
import requests
import yfinance as yf

# 1. 비밀 금고에서 암호 꺼내기
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 2. 분석할 주식 티커
TICKERS = ["AAPL", "NVDA", "TSLA"]

def get_stock_data():
    data_summary = ""
    for ticker in TICKERS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            name = info.get("shortName", ticker)
            price = info.get("currentPrice", 0)
            per = round(info.get("trailingPE", 0), 2)
            f_per = round(info.get("forwardPE", 0), 2)
            pbr = round(info.get("priceToBook", 0), 2)
            roe = round(info.get("returnOnEquity", 0) * 100, 2)
            
            data_summary += f"- {name}({ticker}): 현재가 ${price}, PER {per}, Forward PER {f_per}, PBR {pbr}, ROE {roe}%\n"
        except:
            data_summary += f"- {ticker}: 데이터 불러오기 실패\n"
    return data_summary

raw_data = get_stock_data()
prompt = f"""
아래는 오늘자 미국 주식의 주요 지표입니다. 
이 지표들을 바탕으로 일반 투자자 관점에서 각 주식의 현재 밸류에이션 상태(비싼지, 싼지)와 수익성을 분석하고, 
전체적인 투자 의견을 3~4줄로 아주 쉽고 명확하게 요약해 주세요.

[주식 지표]
{raw_data}
"""

# 3. 내 API 키로 사용 가능한 구글 AI 모델 '자동 검색' (에러 완벽 차단)
model_name = "gemini-pro" # 기본값
try:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    list_res = requests.get(list_url).json()
    if "models" in list_res:
        for m in list_res["models"]:
            # 글을 생성할 수 있는 AI 모델 중 첫 번째 것을 자동으로 선택
            if "generateContent" in m.get("supportedGenerationMethods", []):
                model_name = m["name"].split("/")[-1]
                break
except Exception:
    pass

# 4. 자동으로 찾은 AI 모델을 사용해 분석 요청
ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
headers = {'Content-Type': 'application/json'}
payload = {
    "contents": [{"parts": [{"text": prompt}]}]
}

try:
    res = requests.post(ai_url, headers=headers, json=payload)
    res_json = res.json()
    
    # 정상적으로 분석을 받아온 경우
    if "candidates" in res_json:
        ai_analysis = res_json['candidates'][0]['content']['parts'][0]['text']
    # 구글 서버가 에러를 뱉은 경우
    else:
        ai_analysis = f"AI 서버 거절 사유 (자동 적용된 모델: {model_name}): {res.text}"
        
except Exception as e:
    ai_analysis = f"통신 오류 발생: {e}"

# 5. 텔레그램으로 전송
final_message = f"📊 [오늘의 주식 지표]\n{raw_data}\n\n🤖 [AI 분석 의견]\n{ai_analysis}"
url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
