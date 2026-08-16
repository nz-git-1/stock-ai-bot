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

# 3. 구글 AI 서버와 '직접' 다이렉트 통신 (버그 우회)
ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
headers = {'Content-Type': 'application/json'}
payload = {
    "contents": [{"parts": [{"text": prompt}]}]
}

try:
    res = requests.post(ai_url, headers=headers, json=payload)
    res_json = res.json()
    ai_analysis = res_json['candidates'][0]['content']['parts'][0]['text']
except Exception as e:
    ai_analysis = f"AI 분석을 받아오지 못했습니다. 오류: {e}"

# 4. 텔레그램으로 전송
final_message = f"📊 [오늘의 주식 지표]\n{raw_data}\n\n🤖 [AI 분석 의견]\n{ai_analysis}"
url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
if res.status_code != 200:
    print(f"텔레그램 전송 실패! 상세 에러: {res.text}")
    raise Exception("텔레그램 아이디나 토큰이 잘못되었습니다.")
