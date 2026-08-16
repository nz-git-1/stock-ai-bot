import os
import requests
import yfinance as yf
import time
from datetime import datetime, timezone, timedelta

# 1. 한국 시간 설정
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
            "generationConfig": {"temperature": 0.2} # 사실 기반을 위해 낮은 온도 유지
        }
        for _ in range(2):
            try:
                res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=15).json()
                if "candidates" in res:
                    return res['candidates'][0]['content']['parts'][0]['text'].strip()
                break 
            except Exception:
                time.sleep(1)
    return "AI 분석 생성 실패"

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
            
            # 배당수익률 자체 검증 로직 유지
            div = "N/A"
            try:
                div_rate = info.get("dividendRate")
                if div_rate and isinstance(price, (int, float)) and price > 0:
                    div = round((div_rate / price) * 100, 2)
                else:
                    temp_div = get_val(info, "dividendYield", 100)
                    if isinstance(temp_div, (int, float)) and temp_div > 20 and "ETF" not in info.get("quoteType", ""):
                        div = "N/A (야후 데이터 오류)"
                    else:
                        div = temp_div
            except:
                pass
        else:
            price = per = f_per = pbr = roe = debt = div = "N/A"
            
        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        # ★ 수정된 프롬프트: 모든 수치, 데이터, 예측을 최신 팩트 기반으로 강력히 교차 검증할 것을 지시 ★
        prompt = f"""당신은 기관 투자자를 담당하는 수석 주식 애널리스트입니다.
제공된 실시간 재무 데이터와 현시점 기준 가장 정확한 글로벌 거시경제(매크로) 팩트만을 엄격하게 종합하여 깊이 있는 분석 리포트를 작성하십시오.

[절대 분석 지침 - 100% 팩트 기반]
1. 배당수익률뿐만 아니라 PER, PBR, 현재가, 내년 예상 PER 등 모든 수치와 시장 예측은 제공된 데이터와 당신이 알고 있는 최신 팩트만을 기반으로 교차 검증하여 분석하십시오.
2. 데이터에 비정상적인 수치나 상충되는 지표가 있다면 맹신하지 말고, 애널리스트의 시각에서 팩트 체크 후 논리적으로 지적하십시오.
3. 매크로 환경(미국 금리, 국채 금리, 연준 발언 등) 및 지지선 예측 등은 가상의 소설을 쓰지 말고, 현시점의 실제 시장 흐름과 논리적 근거에 기반하여 작성하십시오.
4. 100% 한국어 전문 금융 용어로 격식 있게 서술하십시오.
5. 아래 [출력 양식]의 3개 섹션 구분을 엄격히 준수하여 각 항목당 2~3문장으로 명확히 작성하십시오.

[데이터]
종목: {name} ({ticker})
{stock_data}

[출력 양식]
📊 밸류에이션 및 실적 진단:
(매출·이익 대비 주가 수준 팩트 체크 및 밸류에이션을 정당화하기 위해 요구되는 향후 실적 기준 제시)

🌐 매크로 환경 및 섹터 전망:
(미국 기준금리, 미 국채 10년물 금리 추이, 연준 통화정책 기조 등 실제 현시점의 정책 변수가 미치는 영향 분석)

🎯 지지선 대응 및 투자 전략:
(현재가 기준 현실적인 1차·2차 분할 매수 지지선 수치 제시, 지지선 이탈 시 리스크 관리 시그널 및 명확한 투자 포지션 제안)"""
        
        ai_analysis = ask_ai(prompt)

    except Exception as e:
        stock_data = "데이터 수집 오류 발생"
        ai_analysis = f"오류 원인: {e}"

    # 최종 메시지 조립
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🏛️ [기관 심층 분석 리포트]\n{ai_analysis}"

    if len(final_message) > 4000:
        final_message = final_message[:3900] + "\n\n(※ 내용 초과로 일부 요약됨)"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    if t_res.status_code != 200:
        raise Exception(f"\n\n🚨 텔레그램 발송 실패 🚨\n종목명: {ticker}\n사유: {t_res.text}\n")
        
    time.sleep(2)
