import os
import requests
import yfinance as yf
import time
import urllib.parse
import xml.etree.ElementTree as ET
import re
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
        is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")
        currency = "₩" if is_korean else "$"
        
        display_name = ticker
        price = "N/A"
        per = "N/A"
        pbr = "N/A"
        f_per = "N/A"
        roe = "N/A"
        debt = "N/A"
        div = "N/A"
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        news_titles = []

        # =====================================================================
        # ★ 차단 돌파 및 정확도 100%: 구글 파이낸스 한국어 강제 요청 로직
        # =====================================================================
        if is_korean:
            code = ticker.split('.')[0]
            market = "KRX" if ticker.endswith(".KS") else "KOSDAQ"
            
            # 구글 파이낸스에 ?hl=ko 를 붙여서 무조건 한국어로 응답받게 설정합니다.
            gf_url = f"https://www.google.com/finance/quote/{code}:{market}?hl=ko"
            
            try:
                gf_res = requests.get(gf_url, headers=headers, timeout=10)
                html_text = gf_res.text
                
                # 1. 완벽한 한글 이름 추출 (<title> 태그 활용)
                name_match = re.search(r'<title>([^<]+)\s+주가', html_text)
                if name_match: 
                    display_name = name_match.group(1).strip()
                else:
                    # 실패 시 AI에게 직접 이름을 물어보는 2차 안전장치
                    ai_name = ask_ai(f"종목코드 '{ticker}'의 한국 공식 상장명을 부가 설명 없이 한 단어로만 대답해줘.")
                    if ai_name and len(ai_name) < 15: display_name = ai_name.strip()
                
                # 2. 야후의 비정상 주가를 덮어쓰는 100% 정확한 현재가 추출 (숨겨진 속성값 활용)
                price_match = re.search(r'data-last-price="([0-9.]+)"', html_text)
                if price_match: 
                    # 75000.0 같은 숫자를 75,000 형태로 예쁘게 변환
                    price = f"{int(float(price_match.group(1))):,}"
                    
            except Exception as e:
                print(f"구글 파이낸스 데이터 추출 실패: {e}")

            # 3. 완벽한 한글 이름으로 '최근 24시간 이내(when:1d)' 뉴스 검색
            news_query = urllib.parse.quote(f"{display_name} when:1d")
            news_url = f"https://news.google.com/rss/search?q={news_query}&hl=ko&gl=KR&ceid=KR:ko"
            
            try:
                res = requests.get(news_url, headers=headers, timeout=10)
                root = ET.fromstring(res.text)
                news_titles = [item.find('title').text for item in root.findall('.//channel/item')[:3]]
            except:
                pass
                
            # 야후 파이낸스에서 PER, PBR 등 기타 재무 지표만 조용히 가져옵니다.
            stock = yf.Ticker(ticker)
            info = stock.info if stock.info else {}
            per = get_val(info, "trailingPE")
            f_per = get_val(info, "forwardPE")
            pbr = get_val(info, "priceToBook")
            roe = get_val(info, "returnOnEquity", 100)
            debt = get_val(info, "debtToEquity")
            div = get_val(info, "dividendYield", 100)

        # =====================================================================
        # 미국 및 글로벌 주식 로직
        # =====================================================================
        else:
            stock = yf.Ticker(ticker)
            info = stock.info if stock.info else {}
            
            display_name = info.get("shortName", ticker)
            raw_price = info.get("currentPrice", "N/A")
            if raw_price != "N/A":
                price = f"{raw_price:,.2f}"
            per = get_val(info, "trailingPE")
            f_per = get_val(info, "forwardPE")
            pbr = get_val(info, "priceToBook")
            roe = get_val(info, "returnOnEquity", 100)
            debt = get_val(info, "debtToEquity")
            div = get_val(info, "dividendYield", 100)
            
            news_query = urllib.parse.quote(f"{ticker} stock when:1d")
            news_url = f"https://news.google.com/rss/search?q={news_query}&hl=en-US&gl=US&ceid=US:en"
            
            try:
                res = requests.get(news_url, headers=headers, timeout=10)
                root = ET.fromstring(res.text)
                raw_titles = [item.find('title').text for item in root.findall('.//channel/item')[:3]]
                
                if raw_titles:
                    raw_text = "\n".join(raw_titles)
                    trans_prompt = f"다음 미국 주식 뉴스 제목들을 한국어로 번역해줘. 텍스트만 한 줄씩 출력해:\n{raw_text}"
                    translated = ask_ai(trans_prompt)
                    news_titles = [t.strip("-* ") for t in translated.split('\n') if t.strip()]
            except:
                pass

        # 뉴스 및 지표 텍스트 조립
        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        news_text = ""
        for t in news_titles:
            clean_title = t.replace('&quot;', '"').replace('&amp;', '&')
            news_text += f"- {clean_title}\n"
        
        if not news_text.strip():
            news_text = "최근 24시간 이내 주요 뉴스 없음"

        # =====================================================================
        # AI 리포트 생성 (가짜 뉴스 방지 지시어 추가)
        # =====================================================================
        prompt = f"""당신은 기관 투자자를 담당하는 수석 주식 애널리스트입니다. 
아래 데이터를 바탕으로 리포트를 작성하되, 마크다운 기호(*, **, #)를 절대 사용하지 마세요.

[데이터]
종목: {display_name}
{stock_data}
최신 주요 뉴스:
{news_text}

[출력 양식 및 필수 주의사항]
1. (이모지와 텍스트만 사용하여 아래 4가지 항목을 작성할 것)
📰 최신 이슈 및 단기 모멘텀
🏰 비즈니스 해자 및 펀더멘털
📊 밸류에이션 및 실적 진단
🎯 지지선 대응 및 투자 전략
2. 만약 '최신 주요 뉴스'가 '없음'이라면, 절대 과거의 가짜 급락/급등 사례를 지어내지 마세요. 주어진 현재가와 펀더멘털 지표만을 바탕으로 객관적으로 분석하세요."""
        
        ai_analysis = ask_ai(prompt)
        
        if ai_analysis:
            ai_analysis = ai_analysis.replace('*', '').replace('#', '')

    except Exception as e:
        display_name = ticker
        stock_data = "데이터 수집 오류 발생"
        news_text = "뉴스 데이터 수집 실패"
        ai_analysis = f"오류 원인: {e}"

    # 최종 텔레그램 메시지 발송
    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{display_name} ({ticker})] 핵심 지표\n{stock_data}\n\n🗞️ [최신 주요 뉴스]\n{news_text}\n\n🏛️ [기관 심층 분석 리포트]\n{ai_analysis}"

    if len(final_message) > 4000:
        final_message = final_message[:3900] + "\n\n(※ 내용 초과로 일부 요약됨)"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    if t_res.status_code != 200:
        raise Exception(f"\n\n🚨 텔레그램 발송 실패 🚨\n종목명: {ticker}\n사유: {t_res.text}\n")
        
    time.sleep(2)
