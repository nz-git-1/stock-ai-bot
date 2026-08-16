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
        # 불필요한 대기 시간을 줄여 속도를 높입니다.
        for _ in range(2):
            try:
                res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=10).json()
                if "candidates" in res:
                    return res['candidates'][0]['content']['parts'][0]['text'].strip()
                break 
            except Exception:
                time.sleep(1)
    return ""

for ticker in TICKERS:
    try:
        info = None
        for _ in range(2):
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                if info: break
            except Exception:
                time.sleep(1)
        
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
        
        # ★ 질문을 단 1번만 던지도록 통합 (속도 2배 향상) 및 톤(Tone) 전문가 수준으로 상향 ★
        prompt = f"""당신은 여의도 최고 수준의 시니어 주식 애널리스트입니다.
제공된 데이터를 바탕으로 기관 투자자 수준의 전문적이고 객관적인 '주식 분석 리포트'를 딱 2줄로 작성하십시오.

[절대 규칙]
1. '용돈', '저금통' 같은 유치한 비유를 절대 금지합니다. 펀더멘털, 밸류에이션 매력도, 하방 경직성, 현금흐름 창출 능력, 인컴 수익 등 전문적인 금융 용어만 사용하십시오.
2. 분석 과정이나 영어를 출력하지 마십시오.
3. 반드시 아래 [출력 양식]의 기호와 텍스트로 시작하는 두 줄만 출력하십시오.

[데이터]
{name} ({ticker})
{stock_data}

[출력 양식]
📊 펀더멘털 분석: (기업 가치 및 재무 상태에 대한 전문적인 요약 1줄)
💡 투자의견 및 전략: (매수/보유/관망 등의 투자의견과 핵심 전략 요약 1줄)"""
        
        ai_raw_text = ask_ai(prompt)
        
        # 핀셋 추출 (기존의 완벽한 기능 유지)
        final_status = "📊 펀더멘털 분석: (데이터 요약 실패)"
        final_opinion = "💡 투자의견 및 전략: (의견 요약 실패)"
        
        for line in ai_raw_text.split('\n'):
            line = line.strip()
            if line.startswith('📊'):
                final_status = line
            elif line.startswith('💡'):
                final_opinion = line
                
        ai_analysis = f"{final_status}\n{final_opinion}"

    except Exception as e:
        stock_data = "데이터 수집 오류 발생"
        ai_analysis = f"오류 원인: {e}"

    # 이름도 AI 멘토에서 [전문가 리포트]로 변경
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🤖 [전문가 리포트]\n{ai_analysis}"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    if t_res.status_code != 200:
        raise Exception(f"\n\n🚨 텔레그램 발송 실패 🚨\n종목명: {ticker}\n사유: {t_res.text}\n")
        
    # 대기 시간을 5초에서 2초로 대폭 단축
    time.sleep(2)
