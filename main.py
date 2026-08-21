import os
import requests
import yfinance as yf
import time
import urllib.parse
import xml.etree.ElementTree as ET
import re  # ★ 텍스트 추출을 위한 정규표현식 라이브러리 추가
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
        info = None
        for _ in range(2):
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                if info: break
            except Exception:
                time.sleep(1)
        
        if info is None: info = {}

        # 기본 이름은 야후 데이터(예: SamsungElec)를 사용하지만, 아래에서 한글로 바꿉니다.
        name = info.get("shortName", ticker) if isinstance(info, dict) else ticker
        currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") else "$"
        
        # =====================================================================
        # ★ 완벽 해결: 네이버 금융에서 실제 '한글 이름'을 찾아 검색에 활용 ★
        # =====================================================================
        news_list = []
        try:
            if ticker.endswith(".KS") or ticker.endswith(".KQ"):
                korean_code = ticker.split('.')[0]
                
                # 1. 네이버 금융 페이지에 접속해서 실제 한글 이름 가져오기
                finance_url = f"https://finance.naver.com/item/main.naver?code={korean_code}"
                fin_res = requests.get(finance_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                
                # <title>삼성전자 : 네이버페이 증권</title> 에서 '삼성전자'만 빼옵니다.
                match = re.search(r'<title>(.*?)\s*:\s*네이버', fin_res.text)
                if match:
                    name = match.group(1).strip()  # 텔레그램 제목도 예쁜 '한글 이름'으로 교체!
                
                # 2. 찾은 정확한 한글 이름으로 네이버 뉴스 RSS 검색
                encoded_query = urllib.parse.quote(name)
                url = f"https://news.search.naver.com/news.naver?where=rss&query={encoded_query}"
                
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                root = ET.fromstring(res.text)
                for item in root.findall('.//item')[:3]:
                    title = item.find('title').text.replace('&quot;', '"').replace('<b>', '').replace('</b>', '').replace('&apos;', "'").replace('&amp;', '&')
                    news_list.append({"title": title})
            else:
                # 미국 및 글로벌 주식: 고유 티커명 그대로 구글 뉴스 검색
                encoded_query = urllib.parse.quote(f"{ticker} stock")
                url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
                
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                root = ET.fromstring(res.text)
                for item in root.findall('.//channel/item')[:3]:
                    title = item.find('title').text
                    news_list.append({"title": title})
        except Exception as e:
            print(f"뉴스 수집 에러 ({ticker}): {e}")
            pass
        # =====================================================================

        if isinstance(info, dict) and info:
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice") or "N/A"
            per = get_val(info, "trailingPE")
            f_per = get_val(info, "forwardPE")
            pbr = get_val(info, "priceToBook")
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
                        div = "N/A (야후 데이터 오류)"
                    else:
                        div = temp_div
            except:
                pass
        else:
            price = per = f_per = pbr = roe = debt = div = "N/A"
            
        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        news_text = ""
        if news_list:
            for n in news_list[:3]:
                title = n.get("title", "")
                if title:
                    news_text += f"- {title}\n"
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
