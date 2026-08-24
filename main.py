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

for ticker in TICKERS:
    try:
        # 변수 초기화
        name = ticker
        price = per = f_per = pbr = roe = debt = div = "N/A"
        currency = "$"
        news_list = []
        news_text = ""
        
        # 깃허브 차단 방지를 위한 모바일 기기 위장 헤더
        power_headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36',
            'Accept': 'application/json, text/plain, */*'
        }

        # =====================================================================
        # ★ 분기 1: 한국 주식 (.KS, .KQ) - 야후를 버리고 네이버 모바일 API 직결 ★
        # =====================================================================
        if ticker.endswith(".KS") or ticker.endswith(".KQ"):
            currency = "₩"
            korean_code = ticker.split('.')[0]
            
            # 1. 핵심 지표 및 정확한 한글 이름 추출 (네이버 모바일 Integration API)
            try:
                info_url = f"https://m.stock.naver.com/api/stock/{korean_code}/integration"
                res = requests.get(info_url, headers=power_headers, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    name = data.get('stockName', ticker)
                    price = data.get('closePrice', "N/A")
                    per = data.get('per', "N/A")
                    f_per = data.get('cnsPer', "N/A")
                    pbr = data.get('pbr', "N/A")
                    roe = data.get('roe', "N/A")
                    div = data.get('dividendYield', "N/A")
            except Exception as e:
                print(f"한국 주식 지표 수집 에러 ({ticker}): {e}")
            
            # 2. 고품질 증권 뉴스 추출 (네이버 모바일 증권 뉴스 API)
            try:
                news_url = f"https://m.stock.naver.com/api/news/stock/{korean_code}?pageSize=3"
                res = requests.get(news_url, headers=power_headers, timeout=10)
                if res.status_code == 200:
                    news_data = res.json()
                    for item in news_data:
                        # HTML 엔티티 제거 후 깔끔하게 저장
                        clean_title = item.get('tit', '').replace('&quot;', '"').replace('&amp;', '&')
                        news_list.append({"title": clean_title})
            except Exception as e:
                print(f"한국 주식 뉴스 수집 에러 ({ticker}): {e}")

        # =====================================================================
        # ★ 분기 2: 미국 및 글로벌 주식 - 야후 파이낸스 + 구글 뉴스 + AI 번역 ★
        # =====================================================================
        else:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info or {}
                name = info.get("shortName", ticker)
                price = info.get("currentPrice") or info.get("regularMarketPrice") or "N/A"
                per = info.get("trailingPE", "N/A")
                f_per = info.get("forwardPE", "N/A")
                pbr = info.get("priceToBook", "N/A")
                roe = info.get("returnOnEquity", "N/A")
                if roe != "N/A" and isinstance(roe, (int, float)): roe = round(roe * 100, 2)
                debt = info.get("debtToEquity", "N/A")
                div = info.get("dividendYield", "N/A")
                if div != "N/A" and isinstance(div, (int, float)): div = round(div * 100, 2)
            except Exception:
                pass
            
            try:
                encoded_query = urllib.parse.quote(f"{ticker} stock")
                url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
                res = requests.get(url, headers=power_headers, timeout=10)
                root = ET.fromstring(res.text)
                raw_titles = [item.find('title').text for item in root.findall('.//channel/item')[:3]]
                
                if raw_titles:
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
                print(f"글로벌 주식 뉴스 수집 에러 ({ticker}): {e}")

        # =====================================================================
        # 메세지 조립 및 AI 리포트 생성 로직
        # =====================================================================
        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
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
종목: {name} ({ticker})
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

    final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{name} ({ticker})] 핵심 지표\n{stock_data}\n\n🗞️ [최신 주요 뉴스]\n{news_text}\n\n🏛️ [기관 심층 분석 리포트]\n{ai_analysis}"

    if len(final_message) > 4000:
        final_message = final_message[:3900] + "\n\n(※ 내용 초과로 일부 요약됨)"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    t_res = requests.post(url, data={"chat_id": CHAT_ID, "text": final_message})
    
    if t_res.status_code != 200:
        raise Exception(f"\n\n🚨 텔레그램 발송 실패 🚨\n종목명: {ticker}\n사유: {t_res.text}\n")
        
    time.sleep(2)
