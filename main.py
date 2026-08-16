import os
import requests
import yfinance as yf

# 1. 비밀 금고에서 암호 꺼내기
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 2. 분석할 주식 티커 (여기에 원하시는 종목 영문 이름을 넣으시면 됩니다)
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

# ★ 여기가 핵심! 초보자 맞춤형 + 100% 한글 강제 명령서 ★
prompt = f"""
너는 주식을 처음 시작하는 왕초보에게 친절하게 설명해주는 주식 전문가야. 
반드시 처음부터 끝까지 '한국어(Korean)'로만 대답해. 절대 영어를 쓰지 마.
복잡한 표나 어려운 전문 용어는 빼고, 스마트폰으로 읽기 편하게 작성해줘.

아래 [주식 지표]를 보고 다음 순서대로 분석해줘:
1. 종목별 상태: 각 주식이 현재 '비싼 편인지/싼 편인지', '돈을 잘 벌고 있는지' 초보자도 이해하기 쉬운 일상적인 비유나 쉬운 말로 1~2줄씩 설명해.
2. 종합 요약: 그래서 이 주식들을 지금 사야 할지, 관망해야 할지 전체적인 투자 의견을 3줄 이내로 아주 명확하게 요약해.

[주식 지표]
{raw_data}
"""

headers = {'Content-Type': 'application/json'}
payload = {"contents": [{"parts": [{"text": prompt}]}]}
ai_analysis = "사용 가능한 모델을 찾지 못했습니다."

try:
    # 3. 구글에 있는 '모든 AI 모델' 목록 가져오기
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    list_res = requests.get(list_url).json()
    
    valid_models = []
    if "models" in list_res:
        for m in list_res["models"]:
            if "generateContent" in m.get("supportedGenerationMethods", []):
                valid_models.append(m["name"].split("/")[-1])
    
    # 4. 목록의 모델들을 하나씩 찔러보며 성공할 때까지 무한 도전
    for model_name in valid_models:
        ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        res = requests.post(ai_url, headers=headers, json=payload)
        res_json = res.json()
        
        # 분석 결과를 제대로 뱉어내면 즉시 채택하고 루프 종료!
        if "candidates" in res_json:
            ai_analysis = f"(사용된 모델: {model_name})\n\n" + res_json['candidates'][0]['content']['parts'][0]['text']
            break 
        else:
            ai_analysis = f"마지막 시도 모델({model_name}) 거절 사유: {res.text}"
            
except Exception as e:
    ai_analysis = f"통신 오류 발생: {e}"

# 5. 텔레그램으로 전송
final_message = f"📊 [오늘의 주식 지표]\n{raw_data}\n\n🤖 [AI 분석 의견]\n{ai_analysis}"
url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
