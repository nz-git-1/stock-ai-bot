import os
import requests
import yfinance as yf
import google.generativeai as genai

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

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
이 지표들을 바탕으로 일반 투자자 관점에서 각 주식의 현재 밸류에이션 상태(비싼지, 싼지)와 수익성을 분석하고, 전체적인 투자 의견을 3~4줄로 아주 쉽고 명확하게 요약해 주세요.

[주식 지표]
{raw_data}
"""

response = model.generate_content(prompt)
ai_analysis = response.text

final_message = f"📊 [오늘의 주식 지표]\n{raw_data}\n\n🤖 [AI 분석 의견]\n{ai_analysis}"
url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
