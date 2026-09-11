import os
import requests
import yfinance as yf
import time
import urllib.parse
import xml.etree.ElementTree as ET
import re
import json
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
        raw_tickers = [line.strip().upper() for line in f if line.strip()]
        TICKERS = list(dict.fromkeys(raw_tickers))
except FileNotFoundError:
    TICKERS = ["005930.KS"]

if not TICKERS:
    TICKERS = ["005930.KS"]

valid_models = ["gemini-1.5-flash", "gemini-pro"]
try:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    list_res = requests.get(list_url, timeout=10).json()
    if "models" in list_res:
        valid_models = [m["name"].split("/")[-1] for m in list_res["models"] if "generateContent" in m.get("supportedGenerationMethods", [])]
except:
    pass

def ask_ai(prompt):
    for model_name in valid_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1}
        }
        for _ in range(2):
            try:
                res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=20).json()
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

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

# =====================================================================
# 2. 글로벌 금융 시장 시황 선행 수집 및 분석 (경제 일정 포함)
# =====================================================================
global_ai_analysis = ""
try:
    global_news_query = urllib.parse.quote("글로벌 증시 OR 미국 증시")
    global_news_url = f"https://news.google.com/rss/search?q={global_news_query}&hl=ko&gl=KR&ceid=KR:ko"
    
    res = requests.get(global_news_url, headers=headers, timeout=15)
    root = ET.fromstring(res.text)
    global_raw_titles = [item.find('title').text for item in root.findall('.//channel/item')[:5]]
    
    global_news_text = ""
    for t in global_raw_titles:
        clean_title = t.replace('&quot;', '"').replace('&amp;', '&')
        global_news_text += f"- {clean_title}\n"
        
    if not global_news_text.strip():
        global_news_text = "최근 글로벌 주요 뉴스 없음"

    # ★ 프롬프트 고도화: 현재 날짜 주입 및 경제 캘린더 요약 지시
    global_prompt = f"""당신은 수석 글로벌 거시경제 애널리스트입니다. 
현재 한국 시간은 {current_time}입니다.
아래의 최근 글로벌 핵심 뉴스와 당신의 지식을 바탕으로 다음 2가지를 작성해 주세요.

[글로벌 핵심 뉴스]
{global_news_text}

[요청 사항]
1. 위 뉴스가 글로벌 금융 시장 및 국내 증시에 미칠 의미를 심도 있게 분석하고 투자 조언을 작성하세요.
2. {current_time}을 기준으로, '어제'와 '오늘' 발표된 한국 및 미국의 핵심 경제 지표(예: PPI, CPI 등 발표 결과)를 명시해 주세요. 
3. 추가로 향후 1주일간 예정된 한국과 미국의 주요 경제 지표 발표 일정(예: 수출입동향, 금리 결정 등)을 일자별, 시간별로 상세히 요약하여 하단에 포함해 주세요.
* 주의: 마크다운 기호(*, **, #)는 절대 사용하지 말고 텍스트와 이모지만 사용하세요."""
    
    global_ai_analysis = ask_ai(global_prompt)
    if global_ai_analysis: 
        global_ai_analysis = global_ai_analysis.replace('*', '').replace('#', '')
except Exception as e:
    global_ai_analysis = f"글로벌 시황 데이터 수집 지연으로 인한 생략"

# =====================================================================
# 3. 개별 종목 데이터 수집, 리포트 생성 및 발송
# =====================================================================
for ticker in TICKERS:
    try:
        is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")
        currency = "₩" if is_korean else "$"
        
        display_name = ticker
        price = per = f_per = pbr = roe = debt = div = "N/A"
        raw_price_num = None

        try:
            stock = yf.Ticker(ticker)
            info = stock.info if stock.info else {}
            
            if is_korean:
                code = ticker.split('.')[0]
                try:
                    nv_url = f"https://finance.naver.com/item/main.naver?code={code}"
                    html_res = requests.get(nv_url, headers=headers, timeout=5)
                    name_m = re.search(r'<title>(.*?)\s*:\s*네이버', html_res.text)
                    if name_m: display_name = name_m.group(1).strip()
                except:
                    pass
            else:
                display_name = info.get("shortName", ticker)

            # 5일치 데이터를 기반으로 가장 최근 가격 확보
            hist = stock.history(period="5d")
            if not hist.empty:
                raw_price_num = float(hist['Close'].iloc[-1])
            else:
                raw_price_num = info.get("currentPrice") or stock.fast_info.get("lastPrice")
            
            if raw_price_num:
                price = f"{int(raw_price_num):,}" if is_korean else f"{float(raw_price_num):,.2f}"
            
            per = get_val(info, "trailingPE")
            f_per = get_val(info, "forwardPE")
            pbr = get_val(info, "priceToBook")
            roe = get_val(info, "returnOnEquity", 100)
            debt = get_val(info, "debtToEquity")
            div = get_val(info, "dividendYield", 100)
        except Exception as e:
            pass

        if div != "N/A" and isinstance(div, (int, float)) and div > 20:
            div = "N/A (데이터 오류)"

        news_titles = []
        if is_korean:
            news_query = urllib.parse.quote(f"{display_name}")
            news_url = f"https://news.google.com/rss/search?q={news_query}&hl=ko&gl=KR&ceid=KR:ko"
        else:
            news_query = urllib.parse.quote(f"{ticker} stock")
            news_url = f"https://news.google.com/rss/search?q={news_query}&hl=en-US&gl=US&ceid=US:en"
            
        try:
            res = requests.get(news_url, headers=headers, timeout=15)
            root = ET.fromstring(res.text)
            raw_titles = [item.find('title').text for item in root.findall('.//channel/item')[:3]]
            
            if is_korean:
                news_titles = raw_titles
            else:
                if raw_titles:
                    raw_joined = "\n".join(raw_titles)
                    trans_prompt = f"다음 영어 기사 제목들을 번역해 줘. 부연 설명이나 원래 영어 문장은 절대 쓰지 말고, 번역된 한국어 문장만 정확히 한 줄에 하나씩 출력해.\n\n제목들:\n{raw_joined}"
                    translated = ask_ai(trans_prompt)
                    
                    for line in translated.split('\n'):
                        clean_line = re.sub(r'^(?:\d+\.|\-|\*|headline\s*\d*:?|draft.*?|translation.*?|refined.*?|output.*?|input.*?|task.*?)\s*', '', line, flags=re.IGNORECASE).strip('"-*[], ')
                        if not clean_line: continue
                        
                        if re.search(r'[가-힣]', clean_line) and not re.search(r'^(input|task|constraint|format|analysis)', clean_line, re.IGNORECASE):
                            news_titles.append(clean_line)
        except:
            pass

        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%"
        
        news_text = ""
        for t in news_titles[:3]:
            clean_title = t.replace('&quot;', '"').replace('&amp;', '&')
            news_text += f"- {clean_title}\n"
        if not news_text.strip():
            news_text = "최근 가용한 주요 뉴스 없음"

        prompt = f"""당신은 기관 투자자를 담당하는 수석 주식 애널리스트입니다.
아래 데이터를 바탕으로 펀더멘털 및 매크로 분석이 포함된 전문적인 리포트를 작성하되, 마크다운 기호(*, **, #)를 절대 사용하지 마세요.

[데이터]
종목: {display_name}
{stock_data}
최신 주요 뉴스:
{news_text}

[출력 양식 및 규칙]
1. (이모지와 텍스트만 사용하여 아래 항목을 작성할 것)
📰 최신 이슈 및 단기 모멘텀
🏰 비즈니스 해자 및 펀더멘털 분석
📊 밸류에이션 및 실적 진단
🎯 매크로 환경 및 투자 전략
🤖 AI 종합 평가 스코어 (반드시 1~6단계 중 하나로 명시, 예: 4단계)
2. 가짜 뉴스를 지어내지 마세요. 주어진 팩트만 사용하세요."""
        
        ai_analysis = ask_ai(prompt)
        if ai_analysis: ai_analysis = ai_analysis.replace('*', '').replace('#', '')

    except Exception as e:
        display_name = ticker
        stock_data = "데이터 수집 오류 방지 (다음 종목 진행)"
        news_text = "뉴스 데이터 수집 지연"
        ai_analysis = f"내부 처리 지연으로 분석 생략"

    try:
        final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{display_name} ({ticker})] 핵심 지표\n{stock_data}\n\n🗞️ [최신 주요 뉴스]\n{news_text}\n\n🏛️ [기관 심층 분석 리포트]\n{ai_analysis}"
        if len(final_message) > 4000: final_message = final_message[:3900] + "\n\n(※ 내용 초과로 일부 요약됨)"
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": final_message}, timeout=15)
    except Exception as e:
        print(f"텔레그램 발송 실패 (종목: {ticker}): {e}")
        
    time.sleep(2)

# =====================================================================
# 4. 환율 및 주요 자산 데이터 수집 (5일치 데이터 기반 에러율 최소화)
# =====================================================================
def get_macro_data(symbol, multiply=1):
    try:
        t = yf.Ticker(symbol)
        # 안정성을 위해 5일치 데이터를 불러와 가장 최근 2거래일의 데이터를 사용합니다.
        hist = t.history(period="5d")
        
        if len(hist) >= 2:
            prev_close = hist['Close'].iloc[-2] * multiply
            current = hist['Close'].iloc[-1] * multiply
        else:
            current = t.fast_info.get("lastPrice", 0) * multiply
            prev_close = t.fast_info.get("previousClose", current) * multiply
            if current == 0: return None, None, None
            
        change = current - prev_close
        change_pct = (change / prev_close) * 100 if prev_close > 0 else 0
        return current, change, change_pct
    except:
        return None, None, None

def get_kr_10y_bond():
    try:
        url = "https://finance.naver.com/marketindex/interestDailyQuote.naver?marketindexCd=IRR_GOVT10Y"
        res = requests.get(url, headers=headers, timeout=10)
        match = re.findall(r'<td class="num">([0-9.]+)</td>', res.text)
        if len(match) >= 4:
            current = float(match[0])
            prev = float(match[3])
            change = current - prev
            change_pct = (change / prev) * 100 if prev > 0 else 0
            return current, change, change_pct
    except:
        pass
    return None, None, None

def get_fear_and_greed():
    try:
        fg_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        fg_res = requests.get(fg_url, headers=headers, timeout=10)
        if fg_res.status_code == 200:
            data = fg_res.json()
            score = round(data['fear_and_greed']['score'])
            # 전일 종가(previous close) 확보하여 변동량 계산
            prev_score = round(data['fear_and_greed']['previous_close'])
            change = score - prev_score
            
            rating = data['fear_and_greed']['rating'].lower()
            rating_map = {
                "extreme fear": "극단적 공포",
                "fear": "공포",
                "neutral": "중립",
                "greed": "탐욕",
                "extreme greed": "극단적 탐욕"
            }
            rating_kr = rating_map.get(rating, rating)
            return score, change, rating_kr
    except:
        pass
    return None, None, None

# 증시 지수
snp_c, snp_d, snp_p = get_macro_data("^GSPC")
nasdaq_c, nasdaq_d, nasdaq_p = get_macro_data("^IXIC")
kospi_c, kospi_d, kospi_p = get_macro_data("^KS11")
kosdaq_c, kosdaq_d, kosdaq_p = get_macro_data("^KQ11")

# 금리
us10y_c, us10y_d, us10y_p = get_macro_data("^TNX")
kr10y_c, kr10y_d, kr10y_p = get_kr_10y_bond()

# 환율 및 원자재, 변동성
usd_c, usd_d, usd_p = get_macro_data("USDKRW=X")
jpy_c, jpy_d, jpy_p = get_macro_data("JPYKRW=X", 100)
btc_c, btc_d, btc_p = get_macro_data("BTC-USD")
gold_c, gold_d, gold_p = get_macro_data("GC=F")
wti_c, wti_d, wti_p = get_macro_data("CL=F")
vkospi_c, vkospi_d, vkospi_p = get_macro_data("^VKOSPI")
vix_c, vix_d, vix_p = get_macro_data("^VIX")
fg_score, fg_change, fg_rating = get_fear_and_greed()

macro_text = ""
macro_text += "📈 [글로벌 및 국내 증시 지수]\n"
macro_text += f"🇺🇸 S&P 500: {snp_c:,.2f} ({snp_d:+.2f} / {snp_p:+.2f}%)\n" if snp_c else "🇺🇸 S&P 500: 정보 없음\n"
macro_text += f"🇺🇸 나스닥: {nasdaq_c:,.2f} ({nasdaq_d:+.2f} / {nasdaq_p:+.2f}%)\n" if nasdaq_c else "🇺🇸 나스닥: 정보 없음\n"
macro_text += f"🇰🇷 코스피: {kospi_c:,.2f} ({kospi_d:+.2f} / {kospi_p:+.2f}%)\n" if kospi_c else "🇰🇷 코스피: 정보 없음\n"
macro_text += f"🇰🇷 코스닥: {kosdaq_c:,.2f} ({kosdaq_d:+.2f} / {kosdaq_p:+.2f}%)\n\n" if kosdaq_c else "🇰🇷 코스닥: 정보 없음\n\n"

macro_text += "🏦 [양국 10년물 국채 금리]\n"
macro_text += f"🇺🇸 미국 10년물: {us10y_c:,.3f}% ({us10y_d:+.3f} / {us10y_p:+.2f}%)\n" if us10y_c else "🇺🇸 미국 10년물: 정보 없음\n"
macro_text += f"🇰🇷 한국 10년물: {kr10y_c:,.3f}% ({kr10y_d:+.3f} / {kr10y_p:+.2f}%)\n\n" if kr10y_c else "🇰🇷 한국 10년물: 정보 없음\n\n"

macro_text += "💵 [환율 및 암호화폐, 원자재]\n"
macro_text += f"달러/원: ₩{usd_c:,.2f} ({usd_d:+.2f} / {usd_p:+.2f}%)\n" if usd_c else "달러/원: 정보 없음\n"
macro_text += f"엔/원(100엔): ₩{jpy_c:,.2f} ({jpy_d:+.2f} / {jpy_p:+.2f}%)\n" if jpy_c else "엔/원: 정보 없음\n"
macro_text += f"비트코인: ${btc_c:,.2f} ({btc_d:+.2f} / {btc_p:+.2f}%)\n" if btc_c else "비트코인: 정보 없음\n"
macro_text += f"금(온스당): ${gold_c:,.2f} ({gold_d:+.2f} / {gold_p:+.2f}%)\n" if gold_c else "금: 정보 없음\n"
macro_text += f"WTI 원유: ${wti_c:,.2f} ({wti_d:+.2f} / {wti_p:+.2f}%)\n\n" if wti_c else "WTI 원유: 정보 없음\n\n"

macro_text += "📉 [변동성 및 투자 심리]\n"
macro_text += f"코스피 변동성(VKOSPI): {vkospi_c:,.2f} ({vkospi_d:+.2f} / {vkospi_p:+.2f}%)\n" if vkospi_c else "코스피 변동성: 정보 없음\n"
macro_text += f"VIX(미국 공포지수): {vix_c:,.2f} ({vix_d:+.2f} / {vix_p:+.2f}%)\n" if vix_c else "VIX(공포지수): 정보 없음\n"
macro_text += f"CNN 공포·탐욕 지수: {fg_score}점 ({fg_change:+.0f} / {fg_rating})\n" if fg_score is not None else "CNN 공포·탐욕 지수: 정보 없음\n"


# =====================================================================
# 5. 맨 마지막: 글로벌 마감 시황 및 투자 조언 메시지 발송 (2분할 발송)
# =====================================================================
try:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # 첫 번째 메시지 발송 (AI 분석 및 경제 캘린더 요약)
    msg_1 = f"🌍 [글로벌 마감 시황 및 주요 경제 일정]\n\n{global_ai_analysis}"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg_1[:4000]}, timeout=15)
    
    time.sleep(2)
    
    # 두 번째 메시지 발송 (거시 경제 지표 데이터 모음)
    msg_2 = f"📊 [주요 경제 및 금융 지표 종합]\n\n{macro_text}"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg_2[:4000]}, timeout=15)

except Exception as e:
    print(f"글로벌 마감 시황 전송 중 오류 발생: {e}")
