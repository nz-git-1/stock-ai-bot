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
                res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=35).json()
                if "candidates" in res:
                    return res['candidates'][0]['content']['parts'][0]['text'].strip()
                break
            except Exception:
                time.sleep(2)
    return "AI 분석 생성 실패"

def get_val(info, key, multiplier=1):
    try:
        val = info.get(key)
        if val is None or str(val).strip() == "":
            return "N/A"
        return round(float(val) * multiplier, 2)
    except:
        return "N/A"

def decode_html(res):
    for enc in ("euc-kr", "cp949", "utf-8"):
        try:
            return res.content.decode(enc)
        except:
            continue
    return res.text

# 범용 14일 RSI 계산 함수 (개별 종목 및 나스닥 지수 공용)
def get_rsi(symbol, rsi_period=14):
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="2mo")
        if hist.empty or len(hist) <= rsi_period:
            return None, None

        closes = [float(x) for x in hist['Close'].dropna().tolist()]
        if len(closes) <= rsi_period:
            return None, None

        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))

        if len(gains) < rsi_period:
            return None, None

        avg_gain = sum(gains[:rsi_period]) / rsi_period
        avg_loss = sum(losses[:rsi_period]) / rsi_period

        for i in range(rsi_period, len(gains)):
            avg_gain = (avg_gain * (rsi_period - 1) + gains[i]) / rsi_period
            avg_loss = (avg_loss * (rsi_period - 1) + losses[i]) / rsi_period

        if avg_loss == 0:
            rsi_val = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_val = 100.0 - (100.0 / (1.0 + rs))

        rsi_rounded = round(rsi_val, 2)
        if rsi_rounded >= 70:
            status = "과매수"
        elif rsi_rounded <= 30:
            status = "과매도"
        else:
            status = "중립"

        return rsi_rounded, status
    except:
        return None, None

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://finance.naver.com/'
}

# =====================================================================
# 2. 글로벌 금융 시장 시황 및 연준(Fed) 발언 수집
# =====================================================================
global_ai_analysis = ""
try:
    global_news_query = urllib.parse.quote("글로벌 증시 OR 미국 증시")
    global_news_url = f"https://news.google.com/rss/search?q={global_news_query}&hl=ko&gl=KR&ceid=KR:ko"

    res = requests.get(global_news_url, headers=headers, timeout=15)
    root = ET.fromstring(res.text)
    global_raw_titles = [item.find('title').text for item in root.findall('.//channel/item')[:4]]

    global_news_text = ""
    for t in global_raw_titles:
        clean_title = t.replace('&quot;', '"').replace('&amp;', '&')
        global_news_text += f"- {clean_title}\n"

    if not global_news_text.strip():
        global_news_text = "최근 글로벌 주요 뉴스 없음"

    fed_news_query = urllib.parse.quote("Kevin Warsh OR FOMC OR Federal Reserve speech")
    fed_news_url = f"https://news.google.com/rss/search?q={fed_news_query}&hl=en-US&gl=US&ceid=US:en"

    fed_res = requests.get(fed_news_url, headers=headers, timeout=15)
    fed_root = ET.fromstring(fed_res.text)
    fed_raw_titles = [item.find('title').text for item in fed_root.findall('.//channel/item')[:4]]

    fed_news_text = ""
    for t in fed_raw_titles:
        clean_title = t.replace('&quot;', '"').replace('&amp;', '&')
        fed_news_text += f"- {clean_title}\n"

    global_prompt = f"""당신은 수석 글로벌 거시경제 애널리스트입니다. 
현재 한국 시간은 {current_time}입니다.
아래의 최근 글로벌 핵심 뉴스와 연방준비제도(Fed) 관련 뉴스를 바탕으로 다음 3가지를 작성해 주세요.

[글로벌 증시 핵심 뉴스]
{global_news_text}

[연준(Fed) 및 FOMC 관련 최근 동향]
{fed_news_text}

[요청 사항]
1. 위 뉴스가 글로벌 금융 시장 및 국내 증시에 미칠 의미를 심도 있게 분석하고 투자 조언을 작성하세요.
2. 연준 의장(케빈 워시) 및 연은 총재들의 발언, 혹은 FOMC 회의 내용이 포함되어 있다면 그 숨은 의미(매파적/비둘기파적 스탠스)와 파급력을 집중 분석해 주세요.
3. {current_time}을 기준으로, '어제'와 '오늘' 발표된 한국 및 미국의 핵심 경제 지표(PPI, CPI 등)를 명시하고, 향후 1주일간 예정된 주요 경제 지표 일정(수출입동향, 기준금리 결정 등)을 일자별, 시간별로 상세히 요약하여 하단에 포함해 주세요.
* 주의: 마크다운 기호(*, **, #)는 절대 사용하지 말고 텍스트와 이모지만 사용하세요."""

    global_ai_analysis = ask_ai(global_prompt)
    if global_ai_analysis:
        global_ai_analysis = global_ai_analysis.replace('*', '').replace('#', '')
except Exception:
    global_ai_analysis = "글로벌 시황 데이터 수집 지연으로 인한 생략"

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
                    html_decoded = decode_html(html_res)
                    name_m = re.search(r'<title>(.*?)\s*:\s*네이버', html_decoded)
                    if name_m:
                        display_name = name_m.group(1).strip()
                except:
                    pass
            else:
                display_name = info.get("shortName", ticker)

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
        except Exception:
            pass

        if div != "N/A" and isinstance(div, (int, float)) and div > 20:
            div = "N/A (데이터 오류)"

        stock_rsi, stock_rsi_status = get_rsi(ticker, 14)
        rsi_str = f"{stock_rsi:.2f}점 ({stock_rsi_status})" if stock_rsi is not None else "N/A"

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
                        if not clean_line:
                            continue

                        if re.search(r'[가-힣]', clean_line) and not re.search(r'^(input|task|constraint|format|analysis)', clean_line, re.IGNORECASE):
                            news_titles.append(clean_line)
        except:
            pass

        stock_data = f"현재가: {currency}{price}\nPER: {per} (내년 예상: {f_per})\nPBR: {pbr}\nROE: {roe}%\n부채비율: {debt}%\n배당수익률: {div}%\nRSI(14일): {rsi_str}"

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
        if ai_analysis:
            ai_analysis = ai_analysis.replace('*', '').replace('#', '')

    except Exception:
        display_name = ticker
        stock_data = "데이터 수집 오류 방지 (다음 종목 진행)"
        news_text = "뉴스 데이터 수집 지연"
        ai_analysis = "내부 처리 지연으로 분석 생략"

    try:
        final_message = f"⏰ [작성 일시: {current_time}]\n\n🔎 [{display_name} ({ticker})] 핵심 지표\n{stock_data}\n\n🗞️ [최신 주요 뉴스]\n{news_text}\n\n🏛️ [기관 심층 분석 리포트]\n{ai_analysis}"
        if len(final_message) > 4000:
            final_message = final_message[:3900] + "\n\n(※ 내용 초과로 일부 요약됨)"

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": final_message}, timeout=15)
    except Exception:
        pass

    time.sleep(2)

# =====================================================================
# 4. 환율, 주요 자산 및 변동성/RSI 데이터 수집
# =====================================================================
def get_macro_data(symbol, multiply=1):
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="5d")
        if len(hist) >= 2:
            prev_close = hist['Close'].iloc[-2] * multiply
            current = hist['Close'].iloc[-1] * multiply
        else:
            current = t.fast_info.get("lastPrice", 0) * multiply
            prev_close = t.fast_info.get("previousClose", current) * multiply
            if current == 0:
                return None, None, None

        change = current - prev_close
        change_pct = (change / prev_close) * 100 if prev_close > 0 else 0
        return current, change, change_pct
    except:
        return None, None, None

def get_vkospi():
    # 1순위: 네이버 금융 모바일 JSON API (가장 안정적)
    try:
        mobile_headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'Referer': 'https://m.stock.naver.com/'
        }
        api_url = "https://m.stock.naver.com/api/index/VPI200/basic"
        res = requests.get(api_url, headers=mobile_headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            close_str = str(data.get("closePrice", "")).replace(",", "").strip()
            if close_str:
                current = float(close_str)
                diff_str = str(data.get("compareToPreviousClosePrice", "0")).replace(",", "").strip()
                ratio_str = str(data.get("fluctuationsRatio", "0")).replace(",", "").strip()

                change = float(diff_str) if diff_str else 0.0
                change_pct = float(ratio_str) if ratio_str else 0.0

                # 하락 코드('5')인 경우 음수 부호 보정
                comp_info = data.get("compareToPreviousPrice", {})
                if isinstance(comp_info, dict) and str(comp_info.get("code")) == "5":
                    change = -abs(change)
                    change_pct = -abs(change_pct)

                return current, change, change_pct
    except Exception as e:
        print(f"V-KOSPI 모바일 API 조회 실패: {e}")

    # 2순위: 네이버 금융 PC 웹 스크래핑
    try:
        url = "https://finance.naver.com/sise/sise_index.naver?code=VPI200"
        res = requests.get(url, headers=headers, timeout=10)
        html = decode_html(res)

        now_m = re.search(r'id=["\']now_value["\'][^>]*>([0-9.,]+)', html)
        if now_m:
            current = float(now_m.group(1).replace(",", ""))
            change = 0.0
            change_pct = 0.0

            change_m = re.search(r'id=["\']change_value_and_rate["\'][^>]*>(.*?)</', html, flags=re.DOTALL)
            if change_m:
                c_raw = change_m.group(1)
                c_clean = re.sub(r'<[^>]+>', ' ', c_raw)
                nums = re.findall(r'([0-9.,]+)', c_clean)
                if len(nums) >= 2:
                    change = float(nums[0].replace(",", ""))
                    change_pct = float(nums[1].replace(",", ""))
                    is_down = ("하락" in c_raw) or ("minus" in c_raw.lower()) or ("nv01" in c_raw.lower())
                    if is_down:
                        change = -abs(change)
                        change_pct = -abs(change_pct)
            return current, change, change_pct
    except Exception as e:
        print(f"V-KOSPI PC 페이지 조회 실패: {e}")

    # 3순위: 야후 파이낸스 보조 백업
    return get_macro_data("^VKOSPI")

def get_kr_10y_bond():
    try:
        hist = yf.Ticker("KR10YT=RR").history(period="5d")
        if len(hist) >= 2:
            prev = hist['Close'].iloc[-2]
            curr = hist['Close'].iloc[-1]
            return curr, curr - prev, ((curr - prev) / prev) * 100 if prev > 0 else 0
    except:
        pass

    try:
        url = "https://finance.naver.com/marketindex/interestDailyQuote.naver?marketindexCd=IRR_GOVT10Y"
        res = requests.get(url, headers=headers, timeout=10)
        html = decode_html(res)
        match = re.findall(r'<td class="num">([0-9.]+)</td>', html)
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

snp_c, snp_d, snp_p = get_macro_data("^GSPC")
nasdaq_c, nasdaq_d, nasdaq_p = get_macro_data("^IXIC")
kospi_c, kospi_d, kospi_p = get_macro_data("^KS11")
kosdaq_c, kosdaq_d, kosdaq_p = get_macro_data("^KQ11")

us10y_c, us10y_d, us10y_p = get_macro_data("^TNX")
kr10y_c, kr10y_d, kr10y_p = get_kr_10y_bond()

usd_c, usd_d, usd_p = get_macro_data("USDKRW=X")
jpy_c, jpy_d, jpy_p = get_macro_data("JPYKRW=X", 100)
thb_c, thb_d, thb_p = get_macro_data("THBKRW=X")
btc_c, btc_d, btc_p = get_macro_data("BTC-USD")
gold_c, gold_d, gold_p = get_macro_data("GC=F")
wti_c, wti_d, wti_p = get_macro_data("CL=F")

vkospi_c, vkospi_d, vkospi_p = get_vkospi()
vix_c, vix_d, vix_p = get_macro_data("^VIX")
fg_score, fg_change, fg_rating = get_fear_and_greed()
nasdaq_rsi, nasdaq_rsi_status = get_rsi("^IXIC", 14)

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
macro_text += f"🇹🇭 바트/원: ₩{thb_c:,.2f} ({thb_d:+.2f} / {thb_p:+.2f}%)\n" if thb_c else "🇹🇭 바트/원: 정보 없음\n"
macro_text += f"비트코인: ${btc_c:,.2f} ({btc_d:+.2f} / {btc_p:+.2f}%)\n" if btc_c else "비트코인: 정보 없음\n"
macro_text += f"금(온스당): ${gold_c:,.2f} ({gold_d:+.2f} / {gold_p:+.2f}%)\n" if gold_c else "금: 정보 없음\n"
macro_text += f"WTI 원유: ${wti_c:,.2f} ({wti_d:+.2f} / {wti_p:+.2f}%)\n\n" if wti_c else "WTI 원유: 정보 없음\n\n"

macro_text += "📉 [변동성 및 투자 심리]\n"
macro_text += f"V-KOSPI(코스피 변동성): {vkospi_c:,.2f} ({vkospi_d:+.2f} / {vkospi_p:+.2f}%)\n" if vkospi_c else "V-KOSPI(코스피 변동성): 정보 없음\n"
macro_text += f"VIX(미국 공포지수): {vix_c:,.2f} ({vix_d:+.2f} / {vix_p:+.2f}%)\n" if vix_c else "VIX(공포지수): 정보 없음\n"
macro_text += f"CNN 공포·탐욕 지수: {fg_score}점 ({fg_change:+.0f} / {fg_rating})\n" if fg_score is not None else "CNN 공포·탐욕 지수: 정보 없음\n"
macro_text += f"나스닥 RSI(14일): {nasdaq_rsi:.2f}점 ({nasdaq_rsi_status})\n" if nasdaq_rsi is not None else "나스닥 RSI(14일): 정보 없음\n"

# =====================================================================
# 5. 맨 마지막: 글로벌 마감 시황 및 투자 조언 메시지 발송 (2분할 발송)
# =====================================================================
try:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    msg_1 = f"🌍 [글로벌 마감 시황 및 주요 경제 일정]\n\n{global_ai_analysis}"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg_1[:4000]}, timeout=15)

    time.sleep(2)

    msg_2 = f"📊 [주요 경제 및 금융 지표 종합]\n\n{macro_text}"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg_2[:4000]}, timeout=15)

except Exception:
    pass
