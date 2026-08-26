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
        # ★ 안정성 강화: 네이버 금융 파싱 (한국 주식 전용)
        # =====================================================================
        if is_korean:
            code = ticker.split('.')[0]
            nv_url = f"https://finance.naver.com/item/main.naver?code={code}"
            
            try:
                nv_res = requests.get(nv_url, headers=headers, timeout=10)
                html_text = nv_res.text
                
                # 한글 종목명 추출을 더 튼튼하게 변경
                name_match = re.search(r'<title>(.*?)\s*:\s*네이버', html_text)
                if name_match: 
                    display_name = name_match.group(1).strip()
                else:
                    # 타이틀 태그 실패 시 본문 h2 태그에서 추출 시도
                    name_match_alt = re.search(r'<h2><a href="#" onclick="clickcr.*?>(.*?)</a></h2>', html_text)
                    if name_match_alt:
                        display_name = name_match_alt.group(1).strip()
                
                # 정확한 현재가 추출
                price_match = re.search(r'<dd>현재가\s+([0-9,]+)', html_text)
                if price_match: price = price_match.group(1).replace(',', '')
                
                # 지표 추출
                per_match = re.search(r'id="_per">([0-9.]+)</em>', html_text)
                if per_match: per = per_match.group(1)
                
                pbr_match = re.search(r'id="_pbr">([0-9.]+)</em>', html_text)
                if pbr_match: pbr = pbr_match.group(1)
                
                div_match = re.search(r'id="_dvr">([0-9.]+)</em>', html_text)
                if div_match: div = div_match.group(1)
                
            except Exception as e:
                print(f"네이버 금융 파싱 실패: {e}")

            # ★ 핵심 로직: 구글 뉴스 검색 시 'when:1d'를 추가하여 무조건 24시간 이내 최신 뉴스만 수집
            news_query = urllib.parse.quote(f"{display_name} when:1d")
            news_url = f"https://news.google.com/rss/search?q={news_query}&hl=ko&gl=KR&ceid=KR:ko"
            
            try:
                res = requests.get(news_url, headers=headers, timeout=10)
                root = ET.fromstring(res.text)
                news_titles = [item.find('title').text for item in root.findall('.//channel/item')[:3]]
            except:
                pass
                
        # =====================================================================
        # 미국 및 글로벌 주식 로직
        # =====================================================================
        else:
            stock = yf.Ticker(ticker)
            info = stock.info if stock.info else {}
            
            display_name = info.get("shortName", ticker)
            price = info.get("currentPrice", "N/A")
            per = get_val(info, "trailingPE")
            f_per = get_val(info, "forwardPE")
            pbr = get_val(info, "priceToBook")
            roe = get_val(info, "returnOnEquity", 100)
            debt = get_val(info, "debtToEquity")
            div = get_val(info, "dividendYield", 100)
            
            # 글로벌 주식 뉴스 검색에도 'when:1d'를 추가하여 최신성 보장
            news_query = urllib.parse.quote(f"{ticker} stock when:1d")
            news_url = f"https://news.google.com/rss/search?q={news_query}&hl=en-US&gl=US&ceid=US:en"
            
            try:
                res = requests.get(news_url, headers=headers, timeout=10)
                root = ET.fromstring(res.text)
                raw_titles = [item.find('title').text for item in root.findall('.//channel/item')[:3]]
                
                if raw_titles:
                    raw_text = "\n".join(raw_titles)
                    trans_prompt = f"미국 주식 영어 뉴스 제목들을 한국어로 자연스럽게 번역해줘. 번역된 텍스트만 한 줄씩 출력해:\n{raw_text}"
                    translated = ask_ai(trans_prompt)
                    news_titles = [t.strip("-* ") for t in translated.split('\n') if t.strip()]
            except:
                pass

        # 뉴스 텍스트 조립
        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        news_text = ""
        for t in news_titles:
            clean_title = t.replace('&quot;', '"').replace('&amp;', '&')
            news_text += f"- {clean_title}\n"
        
        if not news_text.strip():
            news_text = "최근 24시간 이내 주요 뉴스 없음"

        # =====================================================================
        # AI 리포트 생성 및 마크다운 완벽 제거
        # =====================================================================
        prompt = f"""당신은 수석 주식 애널리스트입니다. 
아래 데이터를 바탕으로 리포트를 작성하되, 마크다운 기호(*, **, #)를 절대 사용하지 마세요.

[데이터]
종목: {display_name}
{stock_data}
최신 주요 뉴스:
{news_text}

[출력 양식]
(이모지와 텍스트만 사용하여 아래 항목을 작성)
📰 최신 이슈 및 단기 모멘텀
🏰 비즈니스 해자 및 펀더멘털
📊 밸류에이션 및 실적 진단
🎯 지지선 대응 및 투자 전략"""
        
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
