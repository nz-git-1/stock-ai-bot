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
    TICKERS = ["005930.KS"]

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

# AI 만능 호출 함수 (번역 및 리포트 작성용)
def ask_ai(prompt):
    for model_name in valid_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2} 
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

def get_val(info, key, multiplier=1):
    try:
        val = info.get(key)
        if val is None or str(val).strip() == "": return "N/A"
        return round(float(val) * multiplier, 2)
    except:
        return "N/A"

for ticker in TICKERS:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info if stock.info else {}
        currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") else "$"
        
        # 1. 깃허브 차단 방지 및 이름 한글화 (AI 번역 활용)
        base_name = info.get("shortName", ticker)
        korean_name = base_name
        if ticker.endswith(".KS") or ticker.endswith(".KQ"):
            name_prompt = f"주식 종목코드 '{ticker}'의 한국 공식 상장명을 알려줘. 부가 설명 없이 오직 이름만 한 단어로 말해. (예: 삼성전자)"
            ai_name = ask_ai(name_prompt)
            if ai_name and "실패" not in ai_name and len(ai_name) < 15:
                korean_name = ai_name

        # 2. 정확한 현재가 추출 (.info 오류 회피)
        try:
            hist = stock.history(period="1d")
            if not hist.empty:
                price = round(hist['Close'].iloc[-1], 2)
            else:
                price = info.get("currentPrice", "N/A")
        except Exception:
            price = "N/A"

        # 3. 핵심 지표 자체 연산 및 추출
        eps = info.get("trailingEps")
        per = info.get("trailingPE")
        if per is None and price != "N/A" and eps and float(eps) > 0:
            per = round(float(price) / float(eps), 2)
        per = per if per is not None else "N/A"

        bv = info.get("bookValue")
        pbr = info.get("priceToBook")
        if pbr is None and price != "N/A" and bv and float(bv) > 0:
            pbr = round(float(price) / float(bv), 2)
        pbr = pbr if pbr is not None else "N/A"
        
        f_per = get_val(info, "forwardPE")
        roe = get_val(info, "returnOnEquity", 100)
        debt = get_val(info, "debtToEquity")
        div = get_val(info, "dividendYield", 100)

        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"

        # 4. 차단 없는 야후 뉴스 수집 및 AI 자동 번역
        news_text = ""
        try:
            raw_news = stock.news
            if raw_news:
                raw_titles = [n['title'] for n in raw_news[:3] if 'title' in n]
                if raw_titles:
                    raw_joined = "\n".join(raw_titles)
                    trans_prompt = f"다음 주식 관련 영어 뉴스 제목들을 한국어로 자연스럽게 번역해줘. 부가 설명 없이 번역된 텍스트만 리스트 형태로 한 줄씩 출력해:\n{raw_joined}"
                    translated = ask_ai(trans_prompt)
                    trans_titles = [t.strip("-* ") for t in translated.split('\n') if t.strip()]
                    
                    for i, orig_title in enumerate(raw_titles):
                        if i < len(trans_titles):
                            news_text += f"- {trans_titles[i]}\n"
                        else:
                            news_text += f"- {orig_title}\n"
        except Exception:
            pass
            
        if not news_text.strip():
            news_text = "최신 주요 뉴스 없음"

        # 5. AI 리포트 생성
        prompt = f"""당신은 기관 투자자를 담당하는 수석 주식 애널리스트입니다.
아래 데이터를 바탕으로 심층 분석 리포트를 작성하십시오.

[데이터]
종목: {korean_name} ({ticker})
{stock_data}

[최신 주요 뉴스]
{news_text}

[출력 양식]
📰 최신 이슈 및 단기 모멘텀: (작성)
🏰 비즈니스 해자 및 펀더멘털: (작성)
📊 밸류에이션 및 실적 진단: (작성)
🌐 매크로 환경 및 섹터 전망: (작성)
🎯 지지선 대응 및 투자 전략: (작성)"""
        
        ai_analysis = ask_ai(prompt)

    except Exception as e:
        korean_name = ticker
        stock_data = "데이터 수집 오류 발생"
        news_text = "뉴스 데이터 수집 실패"
        ai_analysis = f"오류 원인: {e}"

    # 최종 텔레그램 메시지 발송
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{korean_name} ({ticker})] 핵심 지표\n{stock_data}\n\n🗞️ [최신 주요 뉴스]\n{news_text}\n\n🏛️ [기관 심층 분석 리포트]\n{ai_analysis}"

    if len(final_message) > 4000:
        final_message = final_message[:3900] + "\n\n(※ 내용 초과로 일부 요약됨)"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    if t_res.status_code != 200:
        raise Exception(f"\n\n🚨 텔레그램 발송 실패 🚨\n종목명: {ticker}\n사유: {t_res.text}\n")
        
    time.sleep(2)
