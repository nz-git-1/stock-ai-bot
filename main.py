import os
import requests
import yfinance as yf
import time
from datetime import datetime, timezone, timedelta

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

if not TICKERS:
    raise Exception("tickers.txt 파일이 비어있습니다.")

valid_models = ["gemini-1.5-flash", "gemini-pro"]
try:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    list_res = requests.get(list_url).json()
    if "models" in list_res:
        valid_models = [m["name"].split("/")[-1] for m in list_res["models"] if "generateContent" in m.get("supportedGenerationMethods", [])]
except:
    pass

def get_val(info, key, multiplier=1):
    try:
        val = info.get(key)
        if val is None or str(val).strip() == "": return "N/A"
        return round(float(val) * multiplier, 2)
    except:
        return "N/A"

def ask_ai(prompt):
    for model_name in valid_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1}
        }
        for _ in range(3):
            try:
                # 서버 통신 대기 시간(timeout=15) 추가로 에러 방지
                res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=15).json()
                if "candidates" in res:
                    return res['candidates'][0]['content']['parts'][0]['text'].strip()
                break 
            except Exception:
                time.sleep(2)
    return ""

for ticker in TICKERS:
    try:
        info = None
        for _ in range(3):
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                if info: break
            except Exception:
                time.sleep(2)
        
        if info is None: info = {}

        name = info.get("shortName", ticker) if isinstance(info, dict) else ticker
        currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") else "$"
        
        if isinstance(info, dict) and info:
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
        
        # 1단계: 자유롭게 분석
        prompt1 = f"Analyze the stock/ETF {name} ({ticker}) based on this data: {stock_data}. What is its fundamental status and investment outlook?"
        raw_analysis = ask_ai(prompt1)
        
        time.sleep(2)
        
        # 2단계: 한국어 번역 요청
        prompt2 = f"""다음 원본 분석글을 바탕으로 숫자와 영어를 완전히 빼고 초보자가 이해하기 쉬운 한국어 비유를 써서 요약해.
반드시 아래 두 줄을 포함해서 작성해:
📊 현재 상태: (여기에 내용)
💡 종합 의견: (여기에 내용)

[원본 분석글]
{raw_analysis}"""
        
        ai_raw_text = ask_ai(prompt2)
        
        # ★★★ 이 부분이 핵심입니다: AI가 뱉어낸 텍스트에서 딱 두 줄만 핀셋으로 추출 ★★★
        final_status = "📊 현재 상태: (데이터 요약 실패)"
        final_opinion = "💡 종합 의견: (의견 요약 실패)"
        
        # AI가 영어로 뭐라고 떠들든, 무시하고 📊와 💡로 시작하는 줄만 찾습니다.
        for line in ai_raw_text.split('\n'):
            line = line.strip()
            if line.startswith('📊'):
                final_status = line
            elif line.startswith('💡'):
                final_opinion = line
                
        # 추출한 딱 2줄만 최종 결과로 씁니다.
        ai_analysis = f"{final_status}\n{final_opinion}"

    except Exception as e:
        stock_data = "데이터 수집 오류 발생"
        ai_analysis = f"오류 원인: {e}"

    # 최종 텔레그램 메시지 조립
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🤖 [AI 멘토 의견]\n{ai_analysis}"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    if t_res.status_code != 200:
        raise Exception(f"\n\n🚨 텔레그램 발송 실패 🚨\n종목명: {ticker}\n사유: {t_res.text}\n")
        
    time.sleep(5)
