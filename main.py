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

# AI 만능 호출 함수 (리포트 작성 및 영문 뉴스 번역)
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
        # =====================================================================
        # ★ 안정성 1: 야후 파이낸스(yfinance)로 모든 종목 기초 데이터 100% 수집 ★
        # =====================================================================
        info = None
        for _ in range(3): # 재시도 횟수 증가
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                if info and (info.get("currentPrice") or info.get("regularMarketPrice")): 
                    break
            except Exception:
                time.sleep(1)
        
        if info is None: info = {}

        currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") else "$"
        name = info.get("shortName", ticker) if isinstance(info, dict) else ticker
        
        # 깃허브 차단 방지를 위한 일반 브라우저 위장 헤더
        power_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        news_list = []

        # =====================================================================
        # ★ 안정성 2: 네이버를 버리고 구글 기반 한글 이름 추출 및 뉴스 수집 ★
        # =====================================================================
        try:
            if ticker.endswith(".KS") or ticker.endswith(".KQ"):
                korean_code = ticker.split('.')[0]
                market = "KRX" if ticker.endswith(".KS") else "KOSDAQ"
                
                # 1. 구글 파이낸스에서 안전하게 한글 종목명 추출 (예: 삼성전자)
                gf_url = f"https://www.google.com/finance/quote/{korean_code}:{market}"
                try:
                    gf_res = requests.get(gf_url, headers=power_headers, timeout=10)
                    match = re.search(r'<title>(.*?)\s+주가', gf_res.text)
                    if match:
                        name = match.group(1).strip()
                except Exception:
                    pass
                
                # 2. 추출한 한글명으로 구글 뉴스(한국) RSS 검색
                encoded_query = urllib.parse.quote(name)
                url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
                
                res = requests.get(url, headers=power_headers, timeout=10)
                root = ET.fromstring(res.text)
                for item in root.findall('.//item')[:3]:
                    title = item.find('title').text.replace('&quot;', '"').replace('<b>', '').replace('</b>', '').replace('&apos;', "'").replace('&amp;', '&')
                    news_list.append({"title": title})
                    
            else:
                # 3. 미국 주식: 티커로 구글 뉴스(미국) 검색 후 AI 한국어 번역
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
            print(f"뉴스 수집 에러 ({ticker}): {e}")
            pass

        # =====================================================================
        # ★ 안정성 3: 누락된 지표(PER/PBR) 자체 계산 수식 적용 ★
        # =====================================================================
        if isinstance(info, dict) and info:
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
            
            # PER 수동 계산 (현재가 / EPS)
            per = info.get("trailingPE")
            eps = info.get("trailingEps")
            if per is None and price and eps and float(eps) > 0:
                try: per = round(float(price) / float(eps), 2)
                except: pass
            per = get_val({"val": per}, "val") if per is not None else "N/A"
            
            # PBR 수동 계산 (현재가 / 주당순자산)
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
        else:
            price = per = f_per = pbr = roe = debt = div = "N/A"
            
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
