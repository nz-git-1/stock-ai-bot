import os
import requests
import yfinance as yf
import time
import urllib.parse
import xml.etree.ElementTree as ET
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

# AI에게 질문을 보내고 답변을 받는 만능 함수 (이름 추출, 리포트, 번역에 모두 사용)
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
    return "AI 생성 실패"

for ticker in TICKERS:
    try:
        info = None
        for _ in range(3):
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                if info and (info.get("currentPrice") or info.get("regularMarketPrice")): 
                    break
            except Exception:
                time.sleep(1)
        
        if info is None: info = {}

        currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") else "$"
        base_name = info.get("shortName", ticker) if isinstance(info, dict) else ticker
        
        # =====================================================================
        # ★ 차단 돌파 1단계: AI에게 직접 '한글 이름'을 묻습니다.
        # =====================================================================
        kor_name = base_name
        is_korean_stock = ticker.endswith(".KS") or ticker.endswith(".KQ")
        
        if is_korean_stock:
            name_prompt = f"주식 종목코드 '{ticker}' (영문명: {base_name})의 한국 주식 시장 공식 한글 종목명을 알려줘. 부가 설명이나 인사말 없이 오직 한글 종목명만 딱 한 단어로 대답해. (예: 삼성전자, 카카오)"
            ai_name = ask_ai(name_prompt)
            if ai_name and "실패" not in ai_name and len(ai_name) < 15:
                kor_name = ai_name

        # =====================================================================
        # ★ 차단 돌파 2단계: 찾아낸 이름으로 구글 뉴스 검색 및 자동 번역
        # =====================================================================
        news_list = []
        power_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        
        try:
            encoded_query = urllib.parse.quote(kor_name if is_korean_stock else f"{ticker} stock")
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko" if is_korean_stock else f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
            
            res = requests.get(url, headers=power_headers, timeout=10)
            root = ET.fromstring(res.text)
            raw_titles = [item.find('title').text for item in root.findall('.//channel/item')[:3]]
            
            if raw_titles:
                if is_korean_stock:
                    for title in raw_titles:
                        clean_title = title.replace('&quot;', '"').replace('<b>', '').replace('</b>', '').replace('&apos;', "'").replace('&amp;', '&')
                        news_list.append({"title": clean_title})
                else:
                    # 미국 주식은 영어 뉴스를 모아서 AI에게 번역 요청
                    raw_text = "\n".join(raw_titles)
                    trans_prompt = f"다음 미국 주식 영어 뉴스 제목들을 한국어로 자연스럽게 번역해줘. 부가 설명이나 인사말 없이 번역된 텍스트만 한 줄씩 출력해:\n{raw_text}"
                    translated = ask_ai(trans_prompt)
                    trans_titles = [t.strip("-* ") for t in translated.split('\n') if t.strip()]
                    for i, original_title in enumerate(raw_titles):
                        if i < len(trans_titles):
                            news_list.append({"title": trans_titles[i]})
                        else:
                            news_list.append({"title": original_title})
        except Exception as e:
            print(f"뉴스 수집 에러 ({ticker}): {e}")
            pass

        # =====================================================================
        # ★ 차단 돌파 3단계: 야후가 누락한 지표 자체 계산 로직
        # =====================================================================
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        
        per = info.get("trailingPE")
        eps = info.get("trailingEps")
        if per is None and price and eps and float(eps) > 0:
            try: per = round(float(price) / float(eps), 2)
            except: pass
        per = get_val({"val": per}, "val") if per is not None else "N/A"
        
        pbr = info.get("priceToBook")
        bv = info.get("bookValue")
        if pbr is None and price and bv and float(bv) > 0:
            try: pbr = round(float(price) / float(bv), 2)
            except: pass
        pbr = get_val({"val": pbr}, "val") if pbr is not None else "N/A"
        
        f_per = get_val(info, "forwardPE")
        roe = get_val(info, "returnOnEquity", 100)
        debt = get_val(info, "debtToEquity")
        
        div = "N/A"
        try:
            div_rate = info.get("dividendRate")
            if div_rate and isinstance(price, (int, float)) and price > 0:
                div = round((div_rate / price) * 100, 2)
            else:
                temp_div = get_val(info, "dividendYield", 100)
                if isinstance(temp_div, (int, float)) and temp_div > 20 and "ETF" not in info.get("quoteType", ""):
                    div = "N/A (오류)"
                else:
                    div = temp_div
        except:
            pass
        
        price = get_val({"val": price}, "val") if price else "N/A"

        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        news_text = ""
        if news_list:
            for n in news_list[:3]:
                if n.get("title"):
                    news_text += f"- {n['title']}\n"
        if not news_text:
            news_text = "최신 주요 뉴스 없음"
        
        prompt = f"""당신은 기관 투자자를 담당하는 여의도 수석 주식 애널리스트입니다.
제공된 실시간 재무 데이터와 '최신 주요 뉴스'를 엄격하게 종합하여 심층 분석 리포트를 작성하십시오.

[절대 분석 지침 - 100% 팩트 기반]
1. 배당수익률, PER 등 수치와 시장 예측은 제공된 데이터와 최신 팩트를 기반으로 교차 검증하십시오.
2. [최신 주요 뉴스]에 제공된 이슈를 분석하여 '단기 모멘텀 및 최신 이슈'를 반드시 리포트에 반영하십시오.
3. 100% 한국어 전문 금융 용어로 격식 있게 서술하며, 인사말이나 불필요한 서론은 일절 배제하십시오.
4. 아래 [출력 양식]의 5개 항목을 빠짐없이 유지하여 작성하십시오.

[데이터]
종목: {kor_name} ({ticker})
{stock_data}

[최신 주요 뉴스]
{news_text}

[출력 양식]
📰 최신 이슈 및 단기 모멘텀:
(제공된 최신 뉴스를 바탕으로 현재 시장의 주목을 받는 이슈와 단기 주가 방향성 분석)

🏰 비즈니스 해자 및 펀더멘털:
(시장 점유율, 독점적 지위, 진입 장벽, 주요 사업부별 수익 구조 분석)

📊 밸류에이션 및 실적 진단:
(매출·이익 대비 현재 주가 수준, 밸류에이션 정당화 요건, 잉여현금흐름 평가)

🌐 매크로 환경 및 섹터 전망:
(미국 기준금리, 국채 금리 추이, 연준 정책 기조 등 거시경제 변수 영향)

🎯 지지선 대응 및 투자 전략:
(현재가 기준 현실적인 1차·2차 분할 매수 지지선, 리스크 관리 시그널 및 최종 투자 포지션 제안)"""
        
        ai_analysis = ask_ai(prompt)

    except Exception as e:
        stock_data = "데이터 수집 오류 발생"
        news_text = "뉴스 데이터 수집 실패"
        ai_analysis = f"오류 원인: {e}"

    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{kor_name} ({ticker})] 핵심 지표\n{stock_data}\n\n🗞️ [최신 주요 뉴스]\n{news_text}\n\n🏛️ [기관 심층 분석 리포트]\n{ai_analysis}"

    if len(final_message) > 4000:
        final_message = final_message[:3900] + "\n\n(※ 내용 초과로 일부 요약됨)"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    if t_res.status_code != 200:
        raise Exception(f"\n\n🚨 텔레그램 발송 실패 🚨\n종목명: {ticker}\n사유: {t_res.text}\n")
        
    time.sleep(2)
