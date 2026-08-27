import os
import requests
import yfinance as yf
import time
import urllib.parse
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timezone, timedelta

# =====================================================================
# 1. 초기 설정 (시간, 토큰, API 키)
# =====================================================================
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

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# =====================================================================
# 2. 개별 종목 분석 및 발송 루프
# =====================================================================
for ticker in TICKERS:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info if stock.info else {}
        
        is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")
        currency = "₩" if is_korean else "$"
        
        # 이름 정제
        raw_name = info.get("shortName", ticker)
        display_name = re.sub(r'\(.*?\)', '', raw_name).strip()

        # 가격 데이터 추출 (5일치 차트 활용)
        price = "N/A"
        raw_price_num = None
        try:
            hist = stock.history(period="5d")
            if not hist.empty:
                raw_price_num = float(hist['Close'].iloc[-1])
            else:
                raw_price_num = info.get("currentPrice") or stock.fast_info.get("lastPrice")
                
            if raw_price_num:
                price = f"{int(raw_price_num):,}" if is_korean else f"{float(raw_price_num):,.2f}"
        except Exception:
            pass

        # 지표 추출
        eps = info.get("trailingEps")
        per = info.get("trailingPE")
        if per is None and raw_price_num and eps and float(eps) > 0:
            try: per = round(float(raw_price_num) / float(eps), 2)
            except: pass
        per = get_val({"val": per}, "val") if per is not None else "N/A"

        bv = info.get("bookValue")
        pbr = info.get("priceToBook")
        if pbr is None and raw_price_num and bv and float(bv) > 0:
            try: pbr = round(float(raw_price_num) / float(bv), 2)
            except: pass
        pbr = get_val({"val": pbr}, "val") if pbr is not None else "N/A"
        
        f_per = get_val(info, "forwardPE")
        roe = get_val(info, "returnOnEquity", 100)
        debt = get_val(info, "debtToEquity")
        
        div = get_val(info, "dividendYield", 100)
        if div != "N/A" and isinstance(div, (int, float)) and div > 20:
            div = "N/A (야후 데이터 오류)"

        # 종목별 뉴스 수집
        news_titles = []
        if is_korean:
            news_query = urllib.parse.quote(f"{display_name} when:1d")
            news_url = f"https://news.google.com/rss/search?q={news_query}&hl=ko&gl=KR&ceid=KR:ko"
        else:
            news_query = urllib.parse.quote(f"{ticker} stock when:1d")
            news_url = f"https://news.google.com/rss/search?q={news_query}&hl=en-US&gl=US&ceid=US:en"
            
        try:
            res = requests.get(news_url, headers=headers, timeout=10)
            root = ET.fromstring(res.text)
            raw_titles = [item.find('title').text for item in root.findall('.//channel/item')[:3]]
            
            if is_korean:
                news_titles = raw_titles
            else:
                if raw_titles:
                    raw_text = "\n".join(raw_titles)
                    trans_prompt = f"다음 미국 주식 영어 뉴스 제목들을 한국어로 번역해줘. 텍스트만 한 줄씩 출력해:\n{raw_text}"
                    translated = ask_ai(trans_prompt)
                    news_titles = [t.strip("-* ") for t in translated.split('\n') if t.strip()]
        except:
            pass

        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        news_text = ""
        for t in news_titles:
            clean_title = t.replace('&quot;', '"').replace('&amp;', '&')
            news_text += f"- {clean_title}\n"
        if not news_text.strip():
            news_text = "최근 24시간 이내 주요 뉴스 없음"

        # AI 개별 종목 리포트 생성
        prompt = f"""당신은 기관 투자자를 담당하는 수석 주식 애널리스트입니다.
아래 데이터를 바탕으로 리포트를 작성하되, 마크다운 기호(*, **, #)를 절대 사용하지 마세요.

[데이터]
종목: {display_name}
{stock_data}
최신 주요 뉴스:
{news_text}

[출력 양식 및 규칙]
1. (이모지와 텍스트만 사용하여 아래 4가지 항목을 작성할 것)
📰 최신 이슈 및 단기 모멘텀
🏰 비즈니스 해자 및 펀더멘털
📊 밸류에이션 및 실적 진단
🎯 지지선 대응 및 투자 전략
2. 가짜 뉴스를 지어내지 마세요."""
        
        ai_analysis = ask_ai(prompt)
        if ai_analysis: ai_analysis = ai_analysis.replace('*', '').replace('#', '')

    except Exception as e:
        display_name = ticker
        stock_data = "데이터 수집 오류 발생"
        news_text = "뉴스 데이터 수집 실패"
        ai_analysis = f"오류 원인: {e}"

    # 개별 종목 텔레그램 메시지 발송
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{display_name} ({ticker})] 핵심 지표\n{stock_data}\n\n🗞️ [최신 주요 뉴스]\n{news_text}\n\n🏛️ [기관 심층 분석 리포트]\n{ai_analysis}"
    if len(final_message) > 4000: final_message = final_message[:3900] + "\n\n(※ 내용 초과로 일부 요약됨)"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    time.sleep(2)

# =====================================================================
# 3. 맨 마지막: 글로벌 금융 시장 시황 뉴스 검색 및 AI 조언 발송
# =====================================================================
try:
    global_news_query = urllib.parse.quote("글로벌 금융 시장 증시 when:1d")
    global_news_url = f"https://news.google.com/rss/search?q={global_news_query}&hl=ko&gl=KR&ceid=KR:ko"
    
    res = requests.get(global_news_url, headers=headers, timeout=10)
    root = ET.fromstring(res.text)
    global_raw_titles = [item.find('title').text for item in root.findall('.//channel/item')[:5]]
    
    global_news_text = ""
    for t in global_raw_titles:
        clean_title = t.replace('&quot;', '"').replace('&amp;', '&')
        global_news_text += f"- {clean_title}\n"
        
    if not global_news_text.strip():
        global_news_text = "최근 24시간 이내 글로벌 주요 뉴스 없음"

    global_prompt = f"""당신은 수석 글로벌 거시경제 애널리스트입니다. 
다음은 오늘 전 세계 금융 시장과 증시에 영향을 줄 수 있는 최신 뉴스 헤드라인입니다. 

[글로벌 핵심 뉴스]
{global_news_text}

이 뉴스들이 글로벌 금융 시장 및 국내 증시에 미칠 의미를 심도 있게 분석하고, 오늘 시장에 임하는 투자자를 위한 조언과 코멘트를 작성해 주세요. 마크다운 기호(*, **, #)는 절대 사용하지 말고 텍스트와 이모지만 사용하세요."""
    
    global_ai_analysis = ask_ai(global_prompt)
    if global_ai_analysis: global_ai_analysis = global_ai_analysis.replace('*', '').replace('#', '')
    
    # 글로벌 시황 텔레그램 메시지 발송
    global_message = f"🌍 [글로벌 마감 시황 및 투자 조언]\n\n{global_ai_analysis}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": global_message})

except Exception as e:
    print(f"글로벌 마감 시황 전송 중 오류 발생: {e}")
