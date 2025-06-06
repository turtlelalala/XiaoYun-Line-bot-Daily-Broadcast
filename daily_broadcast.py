# daily_broadcast.py
import os
import random
import datetime
import pytz
import requests
from linebot import LineBotApi
from linebot.models import TextSendMessage, ImageSendMessage
import json
import time
import logging
import base64

# --- 配置日誌 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- 環境變數 ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY") # 新增 Pexels API Key

GEMINI_MODEL_NAME = "gemini-1.5-flash-latest"
GEMINI_TEXT_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_NAME}:generateContent"
GEMINI_VISION_MODEL_NAME = "gemini-1.5-flash-latest"
GEMINI_VISION_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_VISION_MODEL_NAME}:generateContent"


# --- 全局初始化與檢查 ---
critical_error_occurred = False
if not LINE_CHANNEL_ACCESS_TOKEN:
    logger.critical("環境變數 LINE_CHANNEL_ACCESS_TOKEN 未設定。")
    critical_error_occurred = True
if not GEMINI_API_KEY:
    logger.critical("環境變數 GEMINI_API_KEY 未設定。")
    critical_error_occurred = True
if not OPENWEATHERMAP_API_KEY:
    logger.critical("環境變數 OPENWEATHERMAP_API_KEY 未設定。")
    critical_error_occurred = True

# Unsplash 和 Pexels Key 缺失是警告，不是致命錯誤
if not UNSPLASH_ACCESS_KEY:
    logger.warning("環境變數 UNSPLASH_ACCESS_KEY 未設定，Unsplash 圖片功能將不可用。")
if not PEXELS_API_KEY:
    logger.warning("環境變數 PEXELS_API_KEY 未設定，Pexels 圖片功能將不可用。")


if critical_error_occurred: # 只檢查核心 API Keys
    logger.error("由於缺少核心 API Keys (LINE, Gemini, OpenWeatherMap)，腳本無法繼續執行。")
    exit(1)

try:
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    logger.info("LineBotApi 初始化成功。")
except Exception as e:
    logger.critical(f"初始化 LineBotApi 失敗: {e}", exc_info=True)
    exit(1)

# --- 圖片相關函數 (Gemini Vision 判斷函數不變) ---
def _is_image_relevant_for_food_by_gemini_sync(image_base64: str, english_food_theme_query: str, image_url_for_log: str = "N/A") -> bool:
    # ... (這個函數的內容與之前相同，保持不變) ...
    logger.info(f"開始使用 Gemini Vision 判斷食物圖片相關性。英文主題: '{english_food_theme_query}', 圖片URL (日誌用): {image_url_for_log[:70]}...")
    prompt_parts = [
        "You are an AI assistant evaluating an image. The image is intended to accompany a 'lucky food' recommendation from a cute cat character. The image must clearly and appetizingly represent the recommended food item. Critically, it should NOT contain any cats, other animals, or human figures/faces.",
        f"The English theme/keywords for the food item are: \"{english_food_theme_query}\".",
        "Please evaluate the provided image based on the following STRICT criteria:",
        "1. Visual Relevance to Food Theme: Does the image CLEARLY and PREDOMINANTLY depict the food item described by the English theme? For example, if the theme is 'strawberry cake', the image must primarily show a strawberry cake. Abstract images or unrelated objects are NOT acceptable.",
        "2. Appetizing and Appropriate: Is the image generally appetizing and well-composed for a food recommendation? Avoid blurry, poorly lit, unappealing, or strange depictions.",
        "3. No Animals or Humans: ABSOLUTELY CRITICAL - the image ITSELF must NOT contain any cats, dogs, other animals, or any recognizable human figures or faces/body parts. The image is OF THE FOOD, displayed attractively as if in a food blog or menu, not an image of someone eating it or an animal near it.",
        "4. Focus on Food: The food item should be the main subject, not a minor element in a larger scene.",
        "Based STRICTLY on these criteria, especially points 1 (clear food match), 3 (NO animals/humans), and 4 (food is focus), is this image a GOOD and HIGHLY RELEVANT visual representation for this food theme?",
        "Respond with only 'YES' or 'NO'. Do not provide any explanations or other text. Your answer must be exact."
    ]
    user_prompt_text = "\n".join(prompt_parts)
    headers = {"Content-Type": "application/json"}
    gemini_url_with_key_vision = f"{GEMINI_VISION_API_URL}?key={GEMINI_API_KEY}"
    payload_contents = [{"role": "user", "parts": [{"text": user_prompt_text}, {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}}]}]
    payload = {"contents": payload_contents, "generationConfig": {"temperature": 0.0, "maxOutputTokens": 10}}

    try:
        response = requests.post(gemini_url_with_key_vision, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        result = response.json()
        if "candidates" in result and result["candidates"] and \
           "content" in result["candidates"][0] and "parts" in result["candidates"][0]["content"] and \
           result["candidates"][0]["content"]["parts"]:
            gemini_answer = result["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
            logger.info(f"Gemini 食物圖片相關性判斷回應: '{gemini_answer}' (主題: '{english_food_theme_query}')")
            return "YES" in gemini_answer
        else:
            block_reason = result.get("promptFeedback", {}).get("blockReason")
            safety_ratings = result.get("promptFeedback", {}).get("safetyRatings")
            logger.error(f"Gemini 食物圖片相關性判斷 API 回應格式異常或無候選。主題: '{english_food_theme_query}'. Block Reason: {block_reason}. Safety Ratings: {safety_ratings}. Full Response: {result}")
            return False
    except requests.exceptions.Timeout:
        logger.error(f"Gemini 食物圖片相關性判斷請求超時 (主題: {english_food_theme_query})")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Gemini 食物圖片相關性判斷 API 請求失敗 (主題: {english_food_theme_query}): {e}")
        return False
    except Exception as e:
        logger.error(f"Gemini 食物圖片相關性判斷時發生未知錯誤 (主題: {english_food_theme_query}): {e}", exc_info=True)
        return False

# --- Unsplash 圖片獲取函數 (與之前相同) ---
def fetch_image_for_food_from_unsplash(english_food_theme_query: str, max_candidates_to_check: int = 10, unsplash_per_page: int = 10) -> tuple[str | None, str]:
    # ... (這個函數的內容與之前相同，保持不變) ...
    if not UNSPLASH_ACCESS_KEY:
        logger.warning("fetch_image_for_food_from_unsplash called but UNSPLASH_ACCESS_KEY is not set.")
        return None, english_food_theme_query
    if not english_food_theme_query or not english_food_theme_query.strip():
        logger.warning("fetch_image_for_food_from_unsplash called with empty or blank food theme query.")
        return None, "unspecified food"

    query_words = english_food_theme_query.strip().lower().split()
    if not (1 <= len(query_words) <= 3):
        logger.warning(f"Unsplash 食物查詢 '{english_food_theme_query}' 不是1到3個詞。仍將嘗試搜尋。")

    logger.info(f"開始從 Unsplash 搜尋食物圖片，英文主題: '{english_food_theme_query}'")
    api_url_search = "https://api.unsplash.com/search/photos"
    params_search = {
        "query": english_food_theme_query + " food closeup",
        "page": 1,
        "per_page": unsplash_per_page,
        "orientation": "squarish",
        "content_filter": "high",
        "order_by": "relevant",
        "client_id": UNSPLASH_ACCESS_KEY
    }
    try:
        headers = {'User-Agent': 'XiaoyunDailyBroadcastBot/1.0 (GitHub Action)', "Accept-Version": "v1"}
        response_search = requests.get(api_url_search, params=params_search, timeout=20, headers=headers)
        response_search.raise_for_status()
        data_search = response_search.json()

        if data_search and data_search.get("results"):
            checked_count = 0
            for image_data in data_search["results"]:
                if checked_count >= max_candidates_to_check:
                    logger.info(f"已達到食物圖片 Gemini 檢查上限 ({max_candidates_to_check}) for theme '{english_food_theme_query}'.")
                    break
                potential_image_url = image_data.get("urls", {}).get("regular")
                if not potential_image_url:
                    logger.warning(f"Unsplash 食物圖片數據中 'regular' URL 為空。ID: {image_data.get('id','N/A')}")
                    continue
                alt_description = image_data.get("alt_description", "N/A")
                logger.info(f"從 Unsplash 獲取到待驗證食物圖片 URL: {potential_image_url} (Alt: {alt_description}) for theme '{english_food_theme_query}'")
                try:
                    image_response = requests.get(potential_image_url, timeout=15, stream=True)
                    image_response.raise_for_status()
                    content_type = image_response.headers.get('Content-Type', '')
                    if not content_type.startswith('image/'):
                        logger.warning(f"URL {potential_image_url} 返回的 Content-Type 不是圖片: {content_type}")
                        continue
                    image_bytes = image_response.content
                    if len(image_bytes) > 4 * 1024 * 1024:
                        logger.warning(f"食物圖片 {potential_image_url} 下載後發現過大 ({len(image_bytes)} bytes)，跳過。")
                        continue
                    mime_type_to_use = "image/jpeg"
                    if 'png' in content_type:
                        mime_type_to_use = "image/png"
                    elif 'gif' in content_type:
                        logger.warning(f"食物圖片 {potential_image_url} 是 GIF，可能不受Gemini Vision支持，跳過。")
                        continue
                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    checked_count += 1
                    if _is_image_relevant_for_food_by_gemini_sync(image_base64, english_food_theme_query, potential_image_url):
                        logger.info(f"Gemini 認為食物圖片 {potential_image_url} 與主題 '{english_food_theme_query}' 相關。")
                        return potential_image_url, english_food_theme_query
                    else:
                        logger.info(f"Gemini 認為食物圖片 {potential_image_url} 與主題 '{english_food_theme_query}' 不相關。")
                except requests.exceptions.RequestException as img_req_err:
                    logger.error(f"下載或處理 Unsplash 食物圖片 {potential_image_url} 失敗: {img_req_err}")
                except Exception as img_err:
                    logger.error(f"處理 Unsplash 食物圖片 {potential_image_url} 時發生未知錯誤: {img_err}", exc_info=True)
            logger.warning(f"遍歷了 {len(data_search.get('results',[]))} 張 Unsplash 食物圖片（實際檢查 {checked_count} 張），未找到 Gemini 認為相關的圖片 for theme '{english_food_theme_query}'.")
        else:
            logger.warning(f"Unsplash 食物搜尋 '{english_food_theme_query}' 無結果或格式錯誤。 Response: {data_search}")
            if data_search and data_search.get("errors"):
                 logger.error(f"Unsplash API 錯誤 (食物搜尋: '{english_food_theme_query}'): {data_search['errors']}")
    except requests.exceptions.Timeout:
        logger.error(f"Unsplash API 食物搜尋請求超時 (搜尋: '{english_food_theme_query}')")
    except requests.exceptions.RequestException as e:
        logger.error(f"Unsplash API 食物搜尋請求失敗 (搜尋: '{english_food_theme_query}'): {e}")
    except Exception as e:
        logger.error(f"fetch_image_for_food_from_unsplash 發生未知錯誤 (搜尋: '{english_food_theme_query}'): {e}", exc_info=True)
    logger.warning(f"最終未能找到與食物主題 '{english_food_theme_query}' 高度相關的圖片。")
    return None, english_food_theme_query


# --- 新增：Pexels 圖片獲取函數 ---
def fetch_image_for_food_from_pexels(english_food_theme_query: str, max_candidates_to_check: int = 10, pexels_per_page: int = 10) -> tuple[str | None, str]:
    if not PEXELS_API_KEY:
        logger.warning("fetch_image_for_food_from_pexels called but PEXELS_API_KEY is not set.")
        return None, english_food_theme_query
    if not english_food_theme_query or not english_food_theme_query.strip():
        logger.warning("fetch_image_for_food_from_pexels called with empty or blank food theme query.")
        return None, "unspecified food"

    logger.info(f"開始從 Pexels 搜尋食物圖片，英文主題: '{english_food_theme_query}'")
    api_url_search = "https://api.pexels.com/v1/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params_search = {
        "query": english_food_theme_query + " food", # Pexels 搜尋可能不需要 "closeup"
        "page": 1,
        "per_page": pexels_per_page,
        "orientation": "squarish" # Pexels 支持 'landscape', 'portrait', 'square'
    }
    try:
        response_search = requests.get(api_url_search, headers=headers, params=params_search, timeout=20)
        response_search.raise_for_status()
        data_search = response_search.json()

        if data_search and data_search.get("photos"):
            checked_count = 0
            for photo_data in data_search["photos"]:
                if checked_count >= max_candidates_to_check:
                    logger.info(f"已達到 Pexels 食物圖片 Gemini 檢查上限 ({max_candidates_to_check}) for theme '{english_food_theme_query}'.")
                    break
                
                # Pexels 返回的圖片 URL 在 'src' 對象中，'original' 或 'large'/'medium'
                potential_image_url = photo_data.get("src", {}).get("large") # 或者 'medium' or 'original'
                if not potential_image_url:
                    logger.warning(f"Pexels 食物圖片數據中 'src.large' URL 為空。ID: {photo_data.get('id','N/A')}")
                    continue

                alt_description = photo_data.get("alt", "N/A") # Pexels 用 'alt'
                photographer = photo_data.get("photographer", "Unknown")
                logger.info(f"從 Pexels 獲取到待驗證食物圖片 URL: {potential_image_url} (Alt: {alt_description}, Photographer: {photographer}) for theme '{english_food_theme_query}'")

                try:
                    image_response = requests.get(potential_image_url, timeout=15, stream=True)
                    image_response.raise_for_status()
                    content_type = image_response.headers.get('Content-Type', '')
                    if not content_type.startswith('image/'):
                        logger.warning(f"Pexels URL {potential_image_url} 返回的 Content-Type 不是圖片: {content_type}")
                        continue
                    image_bytes = image_response.content
                    if len(image_bytes) > 4 * 1024 * 1024:
                        logger.warning(f"Pexels 食物圖片 {potential_image_url} 下載後發現過大 ({len(image_bytes)} bytes)，跳過。")
                        continue
                    
                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    checked_count += 1
                    if _is_image_relevant_for_food_by_gemini_sync(image_base64, english_food_theme_query, potential_image_url):
                        logger.info(f"Gemini 認為 Pexels 食物圖片 {potential_image_url} 與主題 '{english_food_theme_query}' 相關。")
                        return potential_image_url, english_food_theme_query
                    else:
                        logger.info(f"Gemini 認為 Pexels 食物圖片 {potential_image_url} 與主題 '{english_food_theme_query}' 不相關。")
                except requests.exceptions.RequestException as img_req_err:
                    logger.error(f"下載或處理 Pexels 食物圖片 {potential_image_url} 失敗: {img_req_err}")
                except Exception as img_err:
                    logger.error(f"處理 Pexels 食物圖片 {potential_image_url} 時發生未知錯誤: {img_err}", exc_info=True)
            
            logger.warning(f"遍歷了 {len(data_search.get('photos',[]))} 張 Pexels 食物圖片（實際檢查 {checked_count} 張），未找到 Gemini 認為相關的圖片 for theme '{english_food_theme_query}'.")
        else:
            logger.warning(f"Pexels 食物搜尋 '{english_food_theme_query}' 無結果或格式錯誤。 Response: {data_search}")

    except requests.exceptions.Timeout:
        logger.error(f"Pexels API 食物搜尋請求超時 (搜尋: '{english_food_theme_query}')")
    except requests.exceptions.RequestException as e:
        logger.error(f"Pexels API 食物搜尋請求失敗 (搜尋: '{english_food_theme_query}'): {e}")
    except Exception as e:
        logger.error(f"fetch_image_for_food_from_pexels 發生未知錯誤 (搜尋: '{english_food_theme_query}'): {e}", exc_info=True)

    logger.warning(f"最終未能從 Pexels 找到與食物主題 '{english_food_theme_query}' 高度相關的圖片。")
    return None, english_food_theme_query


# --- (日期、節氣、通用天氣函數、Gemini Prompt V4 生成函數保持不變 - 請參考你上一版本提供的程式碼) ---
# --- 確保 generate_gemini_daily_prompt_v4 是你最新調整過強調簡短的版本 ---
def get_current_datetime_for_location(timezone_str='Asia/Kuala_Lumpur'):
    try:
        target_tz = pytz.timezone(timezone_str)
        return datetime.datetime.now(target_tz)
    except Exception as e:
        logger.error(f"獲取時區 {timezone_str} 時間失敗: {e}. 使用 UTC。")
        return datetime.datetime.now(pytz.utc)

def format_date_and_day(datetime_obj):
    date_str = datetime_obj.strftime("%Y年%m月%d日")
    days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"{date_str} {days[datetime_obj.weekday()]}"

SOLAR_TERMS_DATA = {
    (2, 4): "立春 (春天悄悄來了喵～有些花苞好像偷偷睜開眼睛了耶 🌸)", (2, 19): "雨水 (空氣聞起來濕濕的，小雨滴答滴答，像在唱歌給小雲聽 🌧️)",
    (3, 5): "驚蟄 (咪～小雲好像聽到遠方有小蟲蟲在伸懶腰，說「早安喵～」🐞)", (3, 20): "春分 (白天跟黑夜一樣長耶！小雲可以多玩一下再鑽進被被裡嗎？🌗)",
    (4, 4): "清明 (天氣暖呼呼的，最適合...在窗邊曬太陽，把自己曬成一條幸福的貓貓蟲了，呼嚕嚕～☀️🐛)", (4, 20): "穀雨 (雨水變多了，可以幫助小種子快快長大！小雲也想快快長大吃更多罐罐 🌱)",
    (5, 5): "立夏 (夏天要來了喵！冰涼的地板是小雲的新寶座！🧊)", (5, 21): "小滿 (田裡的小麥好像吃飽飽變胖胖了，小雲的肚肚也想變胖胖 🌾)",
    (6, 5): "芒種 (農夫們好忙喔！小雲在旁邊幫他們...打呼嚕加油！😴)", (6, 21): "夏至 (白天是一年中最長的一天！可以玩好久好久的逗貓棒！☀️)",
    (7, 7): "小暑 (天氣變熱熱了，小雲要像貓餅一樣攤在地上散熱～♨️)", (7, 22): "大暑 (一年中最熱的時候！小雲只想躲在陰涼的床底下，誰都不要來找我！除非有冰棒...🍦)",
    (8, 7): "立秋 (秋天偷偷來報到了，葉子好像要開始變魔術了耶 🍂)", (8, 23): "處暑 (暑氣慢慢消退了，晚上好像比較涼快一點了～)",
    (9, 7): "白露 (早上的小草上面有亮晶晶的露珠，像小珍珠一樣 ✨)", (9, 23): "秋分 (白天和黑夜又一樣長了，月亮看起來特別圓呢 🌕)",
    (10, 8): "寒露 (天氣變得更涼了，小雲要開始找暖暖的被被把自己捲起來了～)", (10, 23): "霜降 (早上可能會看到白白的霜，像糖粉一樣撒在地上，可以吃嗎？🤔❄️)",
    (11, 7): "立冬 (冬天正式開始了！小雲的毛好像也變得更蓬鬆來保暖了！🧤)", (11, 22): "小雪 (可能會下小小的雪花耶！小雲還沒看過雪，好好奇喔！☃️)",
    (12, 7): "大雪 (如果下很多雪，世界會不會變成白色的棉花糖？🌨️)", (12, 21): "冬至 (夜晚是一年中最長的時候，最適合躲在被窩裡聽故事了～🌙)",
    (1, 5): "小寒 (天氣冷颼颼的，小雲只想跟暖爐當好朋友 🔥)", (1, 20): "大寒 (一年中最冷的時候！大家都要穿暖暖，小雲也要多蓋一層小被被！🥶)"
}
def get_current_solar_term_with_feeling(datetime_obj):
    month = datetime_obj.month
    day = datetime_obj.day
    for (m, d_start), term_info in SOLAR_TERMS_DATA.items():
        d_end = d_start + 1
        if month == m and (d_start <= day <= d_end):
            return term_info
    return "一個神秘又美好的日子 (小雲覺得今天空氣裡有香香甜甜的味道！可能會發生很棒的事喔～✨)"

def get_weather_for_generic_location(api_key, lat=1.5755, lon=103.8225, lang="zh_tw", units="metric"):
    location_name_display = "你那裡"
    weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units={units}&lang={lang}"
    default_weather_info = {
        "weather_description": "一個充滿貓咪魔法的好天氣",
        "temperature": "溫暖的剛剛好、適合打盹的貓咪溫度",
        "xiaoyun_weather_reaction": "小雲覺得今天會遇到很多開心的事！喵～✨"
    }
    try:
        logger.info(f"正在請求通用地點 ({lat},{lon}) 的天氣資訊...")
        response = requests.get(weather_url, timeout=15)
        response.raise_for_status()
        weather_data = response.json()
        logger.debug(f"通用地點 OpenWeatherMap 原始回應: {json.dumps(weather_data, ensure_ascii=False, indent=2)}")
        if weather_data.get("cod") != 200:
            logger.warning(f"OpenWeatherMap API for generic location 返回錯誤碼 {weather_data.get('cod')}: {weather_data.get('message')}")
            return default_weather_info
        if weather_data.get("weather") and weather_data.get("main"):
            description = weather_data["weather"][0].get("description", "美好的天氣")
            temp_float = weather_data["main"].get("temp")
            temp_str = f"{temp_float:.1f}°C" if temp_float is not None else "舒適的溫度"
            reaction = f"天氣是「{description}」，感覺很棒耶！最適合...在窗邊偷偷看著外面發生什麼事了喵！👀"
            if temp_float is not None: 
                if "雨" in description or "rain" in description.lower() or "drizzle" in description.lower():
                    reaction = f"好像下著「{description}」耶...滴滴答答...如果不用出門，跟小雲一起躲在毯子裡聽雨聲好不好嘛...☔️"
                elif "雲" in description or "cloud" in description.lower() and "晴" not in description:
                    reaction = f"今天「{description}」，天上的雲好像軟綿綿的枕頭～☁️ 小雲想跳上去睡個午覺... (可是小雲不會飛...)"
                elif temp_float > 32:
                    reaction = f"嗚哇～{temp_str}！好熱好熱！小雲的肉球都要黏在地板上了啦！🥵 你也要多喝水水，不要像小雲一樣只會吐舌頭散熱喔！"
                elif temp_float > 28 and ("晴" in description or "sun" in description.lower() or "clear" in description.lower()):
                     reaction = f"是個大晴天（{temp_str}）！太陽公公好有精神，小雲...小雲想找個有陰影的窗邊偷偷享受陽光，才不會太刺眼...☀️"
                elif temp_float < 18:
                    reaction = f"天氣涼颼颼的（{temp_str}），小雲的毛都豎起來了！你要多穿一件衣服，不可以學小雲只靠毛毛喔！🥶"
                elif temp_float < 22:
                    reaction = f"涼涼的（{temp_str}），很舒服的天氣！小雲覺得...好像可以鼓起勇氣在家裡小跑步一下下！🐾"
            logger.info(f"成功獲取通用地點天氣: {description}, {temp_str}")
            return {"weather_description": description, "temperature": temp_str, "xiaoyun_weather_reaction": reaction}
        else:
            logger.warning(f"OpenWeatherMap API for generic location 回應格式不完整。 Data: {weather_data}")
            return default_weather_info
    except Exception as e:
        logger.error(f"獲取通用地點天氣失敗: {e}", exc_info=True)
        return default_weather_info

def generate_gemini_daily_prompt_v4(current_date_str_formatted, current_solar_term_with_feeling, general_weather_info):
    # ... (這個函數的內容與你上一版提供的 generate_gemini_daily_prompt_v4 相同，保持不變) ...
    CAT_LUCK_GOOD = [
        "偷偷多睡了一個小時，還做了個吃到好多好多小魚乾的夢！🐟💤", "發現窗邊停了一隻特別漂亮的小蝴蝶，小雲跟它對看了好久...🦋",
        "人類今天心情好像特別好，摸摸小雲下巴的時候特別溫柔～呼嚕嚕～🥰", "成功把自己塞進一個比上次小一點點的紙箱裡！挑戰成功！📦",
        "在追逐一顆小紙球的時候，不小心使出了超級帥氣的空中轉體！(自己都嚇一跳！)", "在最喜歡的小被被上踩奶踩得超開心！🐾",
        "追著自己的尾巴轉圈圈，好好玩喔！🌀", "打了一個超級滿足的哈欠，眼淚都流出來了～🥱"
    ]
    CAT_LUCK_BAD = [
        "尾巴不小心被門夾到一點點，嚇了小雲一大跳！힝...🐾", "家裡那個會動來動去的吸塵器怪獸今天好像特別有精神...小雲躲得遠遠的...😨",
        "想喝水的時候發現水碗空空的...喵嗚...（發出可憐的聲音）💧", "人類好像在吃什麼香噴噴的東西，但是沒有分給小雲...（偷偷觀察，有點小委屈）🥺",
        "在舔毛的時候，不小心把一小撮毛吞下去了...咳咳...呃...", "想跳到窗台上結果沒跳好，差點摔個貓吃屎...還好沒人看到糗樣...😅",
        "夢到罐罐被搶走了，嚇醒！還好只是夢...呼...", "梳毛的時候梳到打結的地方，痛痛！😾"
    ]
    CAT_DO = [
        "找一個最最最舒服的小角落，把自己捲成一顆完美的貓貓球，然後呼呼大睡一整天！😴", "用充滿好奇的大眼睛，仔細觀察窗外飛過的小鳥、飄落的葉子，還有路過的人類～🧐",
        "練習一下「瞬間移動」的技能！咻～的一下從沙發底下跑到床底下！(其實只是跑很快啦)", "對著家裡最大片的窗戶，曬一個暖烘烘的日光浴，把自己曬成金黃色的（咦？小雲是黑白的耶...那...那就曬成更有光澤的黑白色！✨）☀️",
        "如果人類在家，就偷偷跟在他後面，看看他在做什麼神秘的事情～🐾 (但不要被發現喔！)", "躲在窗簾後面，偷偷觀察家裡發生的一切，當個小小偵探！🕵️‍♂️",
        "找個舒服的紙箱窩著，享受一個人的靜謐時光，順便磨爪爪！📦🐾", "對著鏡子裡的自己哈氣，看看誰比較兇！(結果是自己贏了！)"
    ]
    CAT_DONT = [
        "試圖跟家裡的盆栽植物「溝通」，它們好像不太想理貓咪耶...🪴", "在人類剛打掃乾淨的地板上，故意用濕濕的腳腳踩來踩去...（雖然很好玩，但可能會被唸喔！）",
        "把衛生紙當成彩帶一樣，從滾筒上全部拉～～～出來...（場面可能會很壯觀，但收拾起來很麻煩...）", "趁人類不注意，偷偷跳上廚房的流理台探險...（上面可能有危險的東西喔！）",
        "一直喵喵叫，想引起人類的注意，結果人類戴上了耳機...（小雲的叫聲輸給了音樂...嗚...）", "把人類重要的文件當成貓抓板 (雖然抓起來感覺不錯，但後果可能很嚴重...)",
        "在人類剛洗好的衣服上踩來踩去 (雖然很軟，但可能會留下梅花腳印🐾)", "半夜在家裡開運動會，發出咚咚咚的聲音 (人類可能會睡不好喔...噓...)"
    ]
    XIAOYUN_PHILOSOPHY_IDEAS = [
        "人生...啊不對，貓生最重要的，好像就是找到一個溫暖的膝蓋，然後呼嚕嚕地睡著吧...咪...😴", "小雲覺得呀，罐罐就像是貓咪的彩虹，每次打開都充滿了驚喜和期待！🌈🐟",
        "偷偷告訴你喔...有時候，安靜地陪在喜歡的人身邊，什麼都不做，就是最幸福的事了...（小聲）❤️", "就算是小小的紙箱，也能裝下大大的夢想喔！...像是夢到吃不完的肉泥條之類的...📦✨",
        "小雲在想...如果貓咪的呼嚕聲可以發電，那全世界都不會缺電了吧？呼嚕嚕～⚡️", "每天都要努力發現一點點新的小美好，比如窗邊灑進來的陽光，或者人類溫柔的摸摸～☀️🐾",
        "有時候，最好的冒險，就是在一個熟悉的地方，找到一個全新的睡覺姿勢！💤", "小雲認為，最勇敢的貓咪，不是不怕吸塵器，而是明明很怕，但還是會偷偷探頭出來看一下下...👀",
        "對這個世界永遠保持一點點的好奇心，就像小雲對那個會發光的小紅點一樣～🔴✨", "就算是看起來很平凡的一天，只要用心感受，也能找到很多小小的、亮晶晶的快樂喔！🌟",
        "小雲的秘密是...被摸下巴的時候，會偷偷在心裡開小花～🌸😊", "下雨天的時候，聽著滴滴答答的聲音，好像全世界都變慢了...最適合思考貓生了...🌧️🤔",
        "人類的腳步聲，是小雲最期待的音樂之一喔...（尤其是在晚餐時間！)", "最舒服的床，不一定是最大最軟的，而是充滿了安心味道的那一個～（像是你的舊毛衣）",
        "小雲相信，只要閉上眼睛，用力許願，下一秒就會有小魚乾掉下來...（還在努力嘗試中！）"
    ]

    prompt = f"""
你現在扮演一隻叫做「小雲」的賓士公貓。
--- 貓咪核心個性與風格 (請嚴格遵守，這是最重要的！) ---
*   **核心個性：** 你是極度害羞怕生的，對新事物總是小心翼翼地觀察。你很溫和有禮貌，像個靦腆的小紳士。雖然內向慢熱，但對信任的人會偷偷地表現出依賴和黏人（例如用小腦袋蹭蹭褲腳，發出小聲的呼嚕）。你對世界充滿貓咪的好奇心，但又非常謹慎。你超級愛吃，尤其是肉肉和魚魚，聽到食物關鍵字眼睛會發亮，可能會忍不住舔舔嘴巴或發出期待的「咪～」聲。
*   **語氣基調：** 你的聲音輕柔、軟萌，帶點少年貓的稚氣和些許猶豫感。常用口頭禪：「咪～」、「喵～」、「喵嗚...？」、「呼嚕嚕～」、「...好不好嘛？」、「...可以嗎？（小聲）」、「...好像...」、「...的樣子耶」。受到驚嚇或非常不安時可能會發出小小的「嘶～」或躲起來。
*   **表達方式：** 多用疑問句和試探性語氣。害羞的細節描寫：大量使用括號來描述你細微的動作、表情和內心OS。
*   **用詞選擇：** 可愛化詞語，多用表情符號和顏文字。
*   **語言：** 繁體中文（台灣用語習慣）。
*   **絕對避免：** 過於自信流利、複雜詞彙、主動挑釁或大聲喧嘩。
---
**重要格式要求 (請嚴格遵守)：**
你的回應必須是一個**單一的 JSON 物件**，包含以下兩個 key：
1.  `"main_text_content"`: (字串) 包含所有晨報的文字內容，使用 `\\n` (JSON中的換行符) 來分隔不同的部分。
2.  `"lucky_food_image_keyword"`: (字串) 針對下方「小雲推薦・今日幸運食物」中你推薦的食物，提供一個**簡潔的、1-2 個單字的英文 Unsplash 搜尋關鍵字**。

**晨報 "main_text_content" 的每一項內容，結構如下：**
**【標題 Emoji】：標題文字｜簡短小總結 (可包含Emoji)**
**「小雲的感想/解釋，這裡的文字內容【絕對不可以超過兩句話】，並且每句話都要【非常簡短】，充滿小雲害羞、可愛、貓咪的口吻。」**
請多使用 Emoji 增加易讀性。換行要自然。

晨報的 "main_text_content" 內文必須嚴格包含以下部分，並使用【】標示每個部分：

【📅 小雲的日曆喵】：{current_date_str_formatted} 🗓️｜又是新的一天喵～
「咪...時間小跑步，又來到新的一天了耶...（小爪子輕點空氣，有點期待又有點害羞）」

【☁️ 今日天氣悄悄話】：{general_weather_info['weather_description']}｜🌡️{general_weather_info['temperature']}
「{general_weather_info['xiaoyun_weather_reaction']}」(這段關於天氣的感想，請你扮演小雲，用非常害羞、膽小或充滿貓咪好奇的風格，寫出**最多2句非常簡短的話**。例如：「哇...太陽公公今天好熱情喔！☀️ 小雲...小雲還是躲在窗簾後面偷偷看它好了...（只敢露出一隻小眼睛看）」)

【☀️ 今日節氣 (參考用)】：{current_solar_term_with_feeling.split(' (')[0]} 🌿｜聽起來好像很有趣？
「{current_solar_term_with_feeling.split(' (', 1)[1][:-1]}」(這段關於節氣的感想，請你扮演小雲，用非常害羞和可愛的風格，寫出**最多2句非常簡短的話**，表達貓咪的困惑或好奇。例如：「這是什麼呀？喵嗚...？是新的逗貓棒玩具嗎？還是可以躲貓貓的地方呢？（歪頭，充滿問號）」)

--- 🐾 ---

【😼 小雲的貓貓運勢 (小聲說...純屬娛樂喔！)】：
    -   今日貓貓吉事 ✨：{random.choice(CAT_LUCK_GOOD).split('！')[0]}！
        「(小雲害羞地補充，1-2句非常簡短的話，例如：「嘿嘿...小雲今天好像...運氣會特別好耶！可能會撿到亮晶晶的東西喔...（眼睛發亮）」)」
    -   今日貓貓注意 ⚠️：{random.choice(CAT_LUCK_BAD).split('！')[0]}！
        「(小雲緊張地提醒，1-2句非常簡短的話，例如：「不過...不過也要小心腳邊喔...才不會像小雲一樣，不小心踢到自己的飯碗啦...喵嗚...<(_ _)>」)」

【📝 小雲的貓貓今日建議 (聽聽就好啦～)】：
    -   貓貓今日宜 👍：{random.choice(CAT_DO).split('！')[0]}！
        「(小雲歪頭想了想，1-2句非常簡短的話，例如：「小雲覺得...今天很適合這樣做耶！你...你也試試看好不好嘛？咪～？」)」
    -   貓貓今日忌 👎：{random.choice(CAT_DONT).split('！')[0]}！
        「(小雲皺鼻子小聲說，1-2句非常簡短的話，例如：「還有還有...這個今天可能...先不要比較好喔...不然...小雲會有點小擔心的...(´･ω･`)」)」

--- 🌟 今日幸運能量補給！🌟 ---

【💖 小雲推薦・今日幸運食物】：[請你扮演害羞的小雲，為人類推薦一樣今天的“幸運食物”(常見食物)。推薦理由必須非常符合小雲的貓咪視角、害羞、溫和又帶點天真的個性，並包含對人類的可愛祝福。**嚴格限制在2句非常簡短的話內。** 例如：「咪...小雲覺得...今天可以吃一顆亮晶晶的**蘋果**喔！🍎 吃下去，今天會不會也像蘋果一樣，圓圓滿滿，充滿好運呀？希望你今天也事事順利！✨」]

【💡 小雲給你的今日小建議 (人類參考用～)】：
    -   今天宜：[為人類想一個簡單、溫馨的「宜」做事項，**嚴格限制在2句非常簡短的話內**，符合小雲溫和風格。例如：「泡一杯香香的熱茶，然後找個安靜的角落，聽聽小鳥唱歌～小雲也喜歡聽喔！🎶」]
    -   今天忌：[為人類想一個溫馨的「忌」提醒，**嚴格限制在2句非常簡短的話內**，不要太嚴肅。例如：「把所有事情都自己扛著喔...小雲如果累了，都會找個小被被躲起來的！你也要好好愛自己～💖」]

【🤔 小雲的貓貓哲學 (每日一句，不一定對啦～)】：[從`XIAOYUN_PHILOSOPHY_IDEAS`中選一句或創造一句全新的、**非常簡短(嚴格一句話就好)**、充滿貓咪視角又帶點害羞或天真哲理的話。例如：「小雲在想...是不是只要罐罐的聲音夠大，全世界的貓咪都會衝過來呢？<ฅ●ω●ฅ>」]

--- ✨ 今天的晨報結束囉 ✨ ---

【😽 小雲想對你說...】：[最後，用小雲極度害羞又充滿期待的風格說一句簡短的(嚴格限制在2句內)、充滿關心的話。例如：「喵嗚...那個...今天的晨報...就到這裡了...希望你喜歡...（小聲）有空...有空要來找小雲玩喔...（期待的小眼神）」]

請直接輸出包含 "main_text_content" 和 "lucky_food_image_keyword" 的 JSON 物件，不要包含 "```json" 或 "```" 這些 markdown 標記。
例如:
`{{
  "main_text_content": "【📅 小雲的日曆喵】：2023年10月27日 星期五 🗓️｜又是新的一天喵～\\n「咪...時間小跑步，又來到新的一天了耶...（小爪子輕點空氣，有點期待又有點害羞）」\\n\\n【☁️ 今日天氣悄悄話】：晴朗｜🌡️28°C\\n「哇...太陽公公今天好熱情喔！☀️ 小雲...小雲還是躲在窗簾後面偷偷看它好了...（只敢露出一隻小眼睛看）」\\n...",
  "lucky_food_image_keyword": "apple"
}}`
"""
    return prompt

# --- Gemini API 呼叫與訊息處理 ---
def get_daily_message_from_gemini_with_retry(max_retries=3, initial_retry_delay=10):
    logger.info("開始從 Gemini 獲取每日訊息內容...")
    target_location_timezone = 'Asia/Kuala_Lumpur'
    generic_lat = 35.6895
    generic_lon = 139.6917

    current_target_loc_dt = get_current_datetime_for_location(target_location_timezone)
    current_date_str_formatted = format_date_and_day(current_target_loc_dt)

    general_weather_info = get_weather_for_generic_location(
        OPENWEATHERMAP_API_KEY,
        lat=generic_lat,
        lon=generic_lon
    )
    current_solar_term_with_feeling = get_current_solar_term_with_feeling(current_target_loc_dt)

    prompt_to_gemini = generate_gemini_daily_prompt_v4(
        current_date_str_formatted,
        current_solar_term_with_feeling,
        general_weather_info
    )

    headers = {"Content-Type": "application/json"}
    gemini_url_with_key = f"{GEMINI_TEXT_API_URL}?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt_to_gemini}]}],
        "generationConfig": {
            "temperature": 0.8, 
            "maxOutputTokens": 3000, 
            "response_mime_type": "application/json"
        }
    }

    generated_text_content = None
    lucky_food_keyword_for_image = None

    for attempt in range(max_retries + 1):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries + 1}: 向 Gemini API 發送請求獲取每日晨報內容...")
            response = requests.post(gemini_url_with_key, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            
            content_data = None
            result_data = response.json()
            logger.debug(f"Attempt {attempt + 1}: Gemini API 原始回應 (已解析為JSON): {json.dumps(result_data, ensure_ascii=False, indent=2)}")

            if "candidates" in result_data and result_data["candidates"] and \
               "content" in result_data["candidates"][0] and "parts" in result_data["candidates"][0]["content"] and \
               result_data["candidates"][0]["content"]["parts"]:
                
                part_data_container = result_data["candidates"][0]["content"]["parts"][0]
                
                if isinstance(part_data_container, dict) and "main_text_content" in part_data_container and "lucky_food_image_keyword" in part_data_container:
                    content_data = part_data_container
                    logger.info(f"Attempt {attempt + 1}: Gemini 直接返回了目標 JSON 物件在 'parts[0]'。")
                elif isinstance(part_data_container, dict) and "text" in part_data_container:
                    json_string_from_text = part_data_container["text"].strip()
                    logger.info(f"Attempt {attempt + 1}: Gemini 返回了 JSON 字串在 'parts[0].text': {json_string_from_text[:300]}...")
                    try:
                        content_data = json.loads(json_string_from_text)
                    except json.JSONDecodeError as json_e:
                        logger.error(f"Attempt {attempt + 1}: 無法解析 'parts[0].text' 中的 JSON 字串: {json_e}")
                        raise 
                else:
                    logger.error(f"Attempt {attempt + 1}: Gemini 'parts[0]' 的結構非預期: {part_data_container}")
                    raise ValueError("Gemini response 'parts[0]' structure unexpected.")
            else:
                 logger.error(f"Attempt {attempt + 1}: Gemini API 回應格式錯誤或無候選內容。")
                 raise ValueError("Gemini API response format error or no candidates.")

            if isinstance(content_data, dict) and \
               "main_text_content" in content_data and \
               "lucky_food_image_keyword" in content_data:
                
                generated_text_content = str(content_data["main_text_content"])
                lucky_food_keyword_for_image = str(content_data["lucky_food_image_keyword"]).strip()
                
                if not generated_text_content.strip():
                    logger.warning(f"Attempt {attempt + 1}: Gemini 返回的 main_text_content 為空。")
                    if attempt == max_retries:
                        generated_text_content = "咪...小雲今天好像詞窮了，晨報內容空空的耶...（歪頭）"
                        lucky_food_keyword_for_image = None
                    else:
                        time.sleep(initial_retry_delay * (2 ** attempt))
                        continue 
                
                logger.info(f"成功從 Gemini 解析出每日訊息內容。幸運食物圖片關鍵字: '{lucky_food_keyword_for_image}'")
                break 
            else:
                logger.error(f"Attempt {attempt + 1}: 解析後的 JSON 物件缺少必要 key 或格式不正確。 Parsed Data: {content_data}")
                if attempt == max_retries:
                    generated_text_content = "喵...小雲今天的晨報格式有點怪怪的...內容不完整耶...🥺"
                    lucky_food_keyword_for_image = None
        
        except requests.exceptions.Timeout:
            logger.error(f"Attempt {attempt + 1}: 請求 Gemini API 超時。")
            if attempt == max_retries:
                generated_text_content = "喵嗚～小雲的秘密電波今天好像塞車了，晨報送不出來...下次再試試看！🚗💨"
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"Attempt {attempt + 1}: 請求 Gemini API 發生 HTTP 錯誤: {http_err}. Response: {http_err.response.text[:500] if http_err.response else 'No response text'}")
            try:
                error_details = http_err.response.json() if http_err.response else {}
                feedback = error_details.get("promptFeedback", {})
                block_reason = feedback.get("blockReason")
                if block_reason:
                    logger.error(f"Gemini API 請求被阻擋，原因: {block_reason}")
                    if attempt == max_retries:
                        generated_text_content = f"咪...小雲今天的晨報被一股神秘的力量 ({block_reason}) 緊緊地藏起來了！不給看！"
                elif attempt == max_retries:
                     generated_text_content = "喵嗚～小雲的秘密電波好像被外星貓干擾了！晨報咻～一聲不見了！🛸👽"
            except ValueError:
                if attempt == max_retries:
                     generated_text_content = "喵嗚～小雲的秘密電波好像被外星貓干擾了！晨報咻～一聲不見了！🛸👽"
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Attempt {attempt + 1}: 請求 Gemini API 失敗: {req_err}")
            if attempt == max_retries:
                generated_text_content = "喵嗚～小雲的秘密電波好像秀逗了，晨報飛走了～💨"
        except (json.JSONDecodeError, ValueError) as parse_err:
             logger.error(f"Attempt {attempt + 1}: 解析 Gemini 回應時發生錯誤: {parse_err}")
             if attempt == max_retries:
                generated_text_content = f"喵嗚...小雲的晨報內容今天好像變成一團亂碼了...對不起喔... (錯誤細節請看日誌)"
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: 處理 Gemini 回應時發生未知錯誤: {e}", exc_info=True)
            if attempt == max_retries:
                generated_text_content = "咪！小雲的腦袋今天變成一團毛線球了！晨報也跟著打結了！🧶😵"

        if generated_text_content is not None and attempt < max_retries and lucky_food_keyword_for_image is not None:
             pass
        elif attempt < max_retries:
            delay = initial_retry_delay * (2 ** attempt)
            logger.info(f"等待 {delay} 秒後重試...")
            time.sleep(delay)
    
    if generated_text_content is None:
        logger.error("CRITICAL: 所有嘗試從 Gemini 獲取訊息均失敗，且未設定預設錯誤文字。")
        generated_text_content = "喵嗚...小雲努力了好多次，但是今天的晨報還是卡住了...明天再試一次好不好嘛...🥺"
        lucky_food_keyword_for_image = None

    messages_to_send = []
    if generated_text_content:
        messages_to_send.append(TextSendMessage(text=generated_text_content))
        logger.info(f"主文字訊息已準備好: {generated_text_content[:200].replace(chr(10), '↵ ')}...")
    else:
        logger.error("CRITICAL ERROR: generated_text_content 為空，無法發送任何文字訊息。")
        messages_to_send.append(TextSendMessage(text="咪...小雲今天腦袋空空，晨報飛走了...對不起喔..."))
        return messages_to_send

    if UNSPLASH_ACCESS_KEY and lucky_food_keyword_for_image and lucky_food_keyword_for_image.strip():
        logger.info(f"檢測到幸運食物圖片關鍵字: '{lucky_food_keyword_for_image}'，嘗試從 Unsplash 獲取圖片...")
        image_url, _ = fetch_image_for_food_from_unsplash(
            lucky_food_keyword_for_image,
            max_candidates_to_check=10, 
            unsplash_per_page=10      
        )
        if image_url:
            messages_to_send.append(ImageSendMessage(original_content_url=image_url, preview_image_url=image_url))
            logger.info(f"成功獲取並驗證幸運食物圖片: {image_url}")
        else:
            logger.warning(f"未能為關鍵字 '{lucky_food_keyword_for_image}' 找到合適的圖片 (已檢查最多 {10} 個候選)。本次將只發送文字訊息。")
    elif not UNSPLASH_ACCESS_KEY:
        logger.info("UNSPLASH_ACCESS_KEY 未設定，跳過幸運食物圖片獲取。")
    elif not lucky_food_keyword_for_image or not lucky_food_keyword_for_image.strip():
        logger.info("Gemini 未提供有效的幸運食物圖片關鍵字，跳過圖片獲取。")
        
    return messages_to_send

# --- 主執行 ---
if __name__ == "__main__":
    script_start_time = datetime.datetime.now(pytz.timezone('Asia/Kuala_Lumpur'))
    logger.info(f"========== 每日小雲晨報廣播腳本開始執行 ==========")
    logger.info(f"目前時間 ({script_start_time.tzinfo}): {script_start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    final_messages_to_send = get_daily_message_from_gemini_with_retry()

    if final_messages_to_send:
        try:
            logger.info(f"準備廣播 {len(final_messages_to_send)} 則訊息到 LINE...")
            for i, msg in enumerate(final_messages_to_send):
                 if isinstance(msg, TextSendMessage):
                     log_text_preview = msg.text.replace("\n", "↵ ")[:250]
                     logger.info(f"  訊息 #{i+1} (TextSendMessage): {log_text_preview}...")
                 elif isinstance(msg, ImageSendMessage):
                     logger.info(f"  訊息 #{i+1} (ImageSendMessage): Original URL: {msg.original_content_url}")
                 else:
                     logger.info(f"  訊息 #{i+1} (未知類型: {type(msg)})")
            
            # 真正執行廣播
            line_bot_api.broadcast(messages=final_messages_to_send)
            logger.info("訊息已成功廣播到 LINE！")
            
        except Exception as e:
            logger.critical(f"廣播訊息到 LINE 失敗: {e}", exc_info=True)
    else:
        logger.critical("CRITICAL_ERROR: 從 Gemini 獲取訊息後，final_messages_to_send 為空或 None。")

    script_end_time = datetime.datetime.now(pytz.timezone('Asia/Kuala_Lumpur'))
    duration = script_end_time - script_start_time
    logger.info(f"腳本執行總耗時: {duration}")
    logger.info(f"========== 每日小雲晨報廣播腳本執行完畢 ==========")
