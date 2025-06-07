# daily_broadcast.py
import os
import random
import datetime
import pytz
import requests
from linebot import LineBotApi
from linebot.models import TextSendMessage, ImageSendMessage, QuickReply, QuickReplyButton, MessageAction
import json
import time
import logging
import base64
import warnings

# <<< 新增的依賴，用於生成圖片 >>>
# 確保在 requirements.txt 中已添加 Pillow 和 sxtwl
from PIL import Image, ImageDraw, ImageFont
import sxtwl
import tempfile
# <<< 新增結束 >>>

# --- 配置日誌 (保持不變) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# --- 環境變數 ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
# <<< 新增的環境變數 >>>
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID")
# <<< 新增結束 >>>

GEMINI_MODEL_NAME = "gemini-1.5-flash-latest"
GEMINI_TEXT_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_NAME}:generateContent"
GEMINI_VISION_MODEL_NAME = "gemini-1.5-flash-latest"
GEMINI_VISION_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_VISION_MODEL_NAME}:generateContent"

# --- 全局初始化與檢查 (已加入 Imgur 檢查) ---
critical_error_occurred = False
if not LINE_CHANNEL_ACCESS_TOKEN: logger.critical("環境變數 LINE_CHANNEL_ACCESS_TOKEN 未設定。"); critical_error_occurred = True
if not GEMINI_API_KEY: logger.critical("環境變數 GEMINI_API_KEY 未設定。"); critical_error_occurred = True
if not OPENWEATHERMAP_API_KEY: logger.critical("環境變數 OPENWEATHERMAP_API_KEY 未設定。"); critical_error_occurred = True
if not UNSPLASH_ACCESS_KEY: logger.warning("環境變數 UNSPLASH_ACCESS_KEY 未設定，Unsplash 圖片功能將受限。")
if not PEXELS_API_KEY: logger.warning("環境變數 PEXELS_API_KEY 未設定，Pexels 圖片功能將受限。")
# <<< 新增的檢查 >>>
if not IMGUR_CLIENT_ID:
    logger.warning("環境變數 IMGUR_CLIENT_ID 未設定，無法上傳並發送每日日曆圖片。")
# <<< 新增結束 >>>

if critical_error_occurred:
    logger.error("由於缺少核心 API Keys，腳本無法繼續執行。")
    exit(1)

try:
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    logger.info("LineBotApi 初始化成功。")
except Exception as e:
    logger.critical(f"初始化 LineBotApi 失敗: {e}", exc_info=True)
    exit(1)

# <<< 新增的函數：上傳圖片到 Imgur >>>
def upload_to_imgur(image_path: str) -> str | None:
    """將本地圖片上傳到 Imgur 並返回公開 URL"""
    if not IMGUR_CLIENT_ID:
        logger.error("upload_to_imgur called but IMGUR_CLIENT_ID is not set.")
        return None
    
    logger.info(f"開始上傳圖片到 Imgur: {image_path}")
    headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
    try:
        with open(image_path, "rb") as image_file:
            payload = {'image': base64.b64encode(image_file.read())}
            response = requests.post("https://api.imgur.com/3/image", headers=headers, data=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                image_url = data["data"]["link"]
                logger.info(f"成功上傳圖片到 Imgur，URL: {image_url}")
                return image_url
            else:
                logger.error(f"Imgur API 回應 success=false。Response: {data}")
                return None
    except requests.exceptions.RequestException as e:
        logger.error(f"上傳圖片到 Imgur 失敗: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"處理 Imgur 上傳時發生未知錯誤: {e}", exc_info=True)
        return None
# <<< 新增結束 >>>

# <<< 新增的函數：生成每日日曆圖片 >>>
def create_daily_calendar_image(now_datetime: datetime.datetime) -> str | None:
    """生成每日日曆圖片並返回本地臨時檔案路徑"""
    logger.info("開始生成每日日曆圖片...")
    try:
        # --- 1. 配色方案 ---
        weekly_colors = [
            {"hex": "#FFB3A7"}, {"hex": "#FFD6A5"}, {"hex": "#A8D8B9"},
            {"hex": "#A7C7E7"}, {"hex": "#C3B1E1"}, {"hex": "#FFFEC8"},
            {"hex": "#B2DFDB"}
        ]
        
        # --- 2. 獲取日曆資料 ---
        lunar = sxtwl.Lunar()
        lunar_day = lunar.getDayBySolar(now_datetime.year, now_datetime.month, now_datetime.day)
        weekday_index = now_datetime.weekday()
        selected_color = weekly_colors[weekday_index]["hex"]

        year = now_datetime.year
        day = f"{now_datetime.day:02d}"
        month_chinese = f"{now_datetime.month}月"
        weekday_map = {0: "星期一", 1: "星期二", 2: "星期三", 3: "星期四", 4: "星期五", 5: "星期六", 6: "星期日"}
        weekday_chinese = weekday_map[weekday_index]

        lunar_date_str = f"農曆 {lunar_day.month_str}{lunar_day.day_str}"
        solar_term_str = lunar_day.jq_str
        info_text = f"{lunar_date_str} {solar_term_str}".strip()

        # --- 3. 圖片與字體設定 ---
        # 這個路徑是針對在 GitHub Actions 中安裝了 fonts-noto-cjk 套件後的標準路徑
        font_path_cjk = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf"
        
        bg_color, primary_color, secondary_color = "#FFFFFF", selected_color, "#888888"
        img_width, img_height, padding = 400, 500, 40

        # --- 4. 繪製 ---
        image = Image.new("RGB", (img_width, img_height), bg_color)
        draw = ImageDraw.Draw(image)

        font_weekday = ImageFont.truetype(font_path_cjk, 24)
        font_month = ImageFont.truetype(font_path_cjk, 32)
        font_day = ImageFont.truetype(font_path_cjk, 180)
        font_year = ImageFont.truetype(font_path_cjk, 32)
        font_info = ImageFont.truetype(font_path_cjk, 28)

        draw.text((padding, padding), weekday_chinese, font=font_weekday, fill=secondary_color)
        draw.text((padding, padding + 50), month_chinese, font=font_month, fill=primary_color)
        
        day_bbox = draw.textbbox((0, 0), day, font=font_day); day_width = day_bbox[2] - day_bbox[0]
        draw.text(((img_width - day_width) / 2, padding + 90), day, font=font_day, fill=primary_color)
        
        year_bbox = draw.textbbox((0,0), str(year), font=font_year); year_width = year_bbox[2] - year_bbox[0]
        draw.text(((img_width - year_width) / 2, padding + 290), str(year), font=font_year, fill=secondary_color)
        
        draw.line([(padding, padding + 350), (img_width - padding, padding + 350)], fill="#EEEEEE", width=2)
        
        info_bbox = draw.textbbox((0,0), info_text, font=font_info); info_width = info_bbox[2] - info_bbox[0]
        draw.text(((img_width - info_width) / 2, padding + 375), info_text, font=font_info, fill=secondary_color)

        # --- 5. 儲存到臨時檔案 ---
        # delete=False 很重要，這樣在 with 區塊結束後檔案不會被刪除
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False, mode='wb') as temp_file:
            image.save(temp_file, format="PNG")
            temp_file_path = temp_file.name
            logger.info(f"日曆圖片已成功生成到臨時檔案: {temp_file_path}")
            return temp_file_path

    except FileNotFoundError:
        logger.error(f"FATAL: 中文字體檔案未找到於 '{font_path_cjk}'。請確認 GitHub Actions 工作流程中已安裝字體。")
        return None
    except Exception as e:
        logger.error(f"生成每日日曆圖片時發生錯誤: {e}", exc_info=True)
        return None
# <<< 新增結束 >>>


# --- 舊有函數區塊 (保持不變) ---
# 以下所有函數 (_is_image_relevant_for_food_by_gemini_sync, fetch_image_for_food_from_unsplash,
# fetch_image_for_food_from_pexels, get_current_datetime_for_location, format_date_and_day,
# SOLAR_TERMS_DATA, get_current_solar_term_with_feeling, get_weather_for_generic_location,
# generate_gemini_daily_prompt_v9) 都保持不變，直接複製即可。

def _is_image_relevant_for_food_by_gemini_sync(image_base64: str, english_food_theme_query: str, image_url_for_log: str = "N/A") -> bool:
    logger.info(f"開始使用 Gemini Vision 判斷食物圖片相關性。英文主題: '{english_food_theme_query}', 圖片URL (日誌用): {image_url_for_log[:70]}...")
    prompt_parts = [
        "You are an AI assistant evaluating an image. The image is intended to accompany a 'lucky food' recommendation from a cute cat character.",
        "The image must clearly and appetizingly represent the recommended food item. The food itself should be the main focus.",
        f"The English theme/keywords for the food item are: \"{english_food_theme_query}\".",
        "Please evaluate the provided image based on the following STRICT criteria:",
        "1. Visual Relevance to Food Theme: Does the image CLEARLY and PREDOMINANTLY depict the food item described by the English theme? For example, if the theme is 'strawberry cake', the image must primarily show a strawberry cake. Abstract images or unrelated objects are NOT acceptable.",
        "2. Appetizing and Appropriate: Is the image generally appetizing and well-composed for a food recommendation? Avoid blurry, poorly lit, unappealing, or strange depictions.",
        "3. No Animals or Humans: CRITICAL - The image must NOT contain any cats, dogs, other animals, or any recognizable human figures, faces, or body parts, especially if they are prominent or distract from the food. The image is OF THE FOOD, displayed attractively as if in a food blog or menu.",
        "4. Focus on Food: The food item should be the main subject, not a minor element in a larger scene. There should be no other distracting elements.",
        "Based STRICTLY on these criteria, especially points 1 (clear food match), 3 (NO animals/humans), and 4 (food is focus, no other distracting items), is this image a GOOD and HIGHLY RELEVANT visual representation for this food theme?",
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

def fetch_image_for_food_from_unsplash(english_food_theme_query: str, max_candidates_to_check: int = 5, unsplash_per_page: int = 5) -> tuple[str | None, str]:
    if not UNSPLASH_ACCESS_KEY:
        logger.warning("fetch_image_for_food_from_unsplash called but UNSPLASH_ACCESS_KEY is not set.")
        return None, english_food_theme_query
    if not english_food_theme_query or not english_food_theme_query.strip():
        logger.warning("fetch_image_for_food_from_unsplash called with empty or blank food theme query.")
        return None, "unspecified food"

    logger.info(f"開始從 Unsplash 搜尋食物圖片 (最多嘗試 {max_candidates_to_check} 張)，英文主題: '{english_food_theme_query}'")
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
                    logger.info(f"已達到 Unsplash 食物圖片 Gemini 檢查上限 ({max_candidates_to_check}) for theme '{english_food_theme_query}'.")
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
                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    checked_count += 1
                    if _is_image_relevant_for_food_by_gemini_sync(image_base64, english_food_theme_query, potential_image_url):
                        logger.info(f"Gemini 認為 Unsplash 食物圖片 {potential_image_url} 與主題 '{english_food_theme_query}' 相關。")
                        return potential_image_url, english_food_theme_query
                    else:
                        logger.info(f"Gemini 認為 Unsplash 食物圖片 {potential_image_url} 與主題 '{english_food_theme_query}' 不相關。")
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
    logger.warning(f"最終未能從 Unsplash 找到與食物主題 '{english_food_theme_query}' 高度相關的圖片。")
    return None, english_food_theme_query

def fetch_image_for_food_from_pexels(english_food_theme_query: str, max_candidates_to_check: int = 10, pexels_per_page: int = 10) -> tuple[str | None, str]:
    if not PEXELS_API_KEY:
        logger.warning("fetch_image_for_food_from_pexels called but PEXELS_API_KEY is not set.")
        return None, english_food_theme_query
    if not english_food_theme_query or not english_food_theme_query.strip():
        logger.warning("fetch_image_for_food_from_pexels called with empty or blank food theme query.")
        return None, "unspecified food"

    logger.info(f"開始從 Pexels 搜尋食物圖片 (最多嘗試 {max_candidates_to_check} 張)，英文主題: '{english_food_theme_query}'")
    api_url_search = "https://api.pexels.com/v1/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params_search = {
        "query": english_food_theme_query + " food",
        "page": 1,
        "per_page": pexels_per_page,
        "orientation": "squarish"
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
                potential_image_url = photo_data.get("src", {}).get("large")
                if not potential_image_url:
                    logger.warning(f"Pexels 食物圖片數據中 'src.large' URL 為空。ID: {photo_data.get('id','N/A')}")
                    continue
                alt_description = photo_data.get("alt", "N/A")
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
    for days_offset in range(15):
        check_day = day - days_offset
        current_month = month
        if check_day < 1:
            prev_month_date = datetime_obj.replace(day=1) - datetime.timedelta(days=1)
            current_month = prev_month_date.month
            check_day = prev_month_date.day + check_day
        if (current_month, check_day) in SOLAR_TERMS_DATA:
            return SOLAR_TERMS_DATA[(current_month, check_day)]
    logger.warning(f"未能精確匹配到節氣 for {month}/{day}，返回通用描述。")
    return "一個神秘又美好的日子 (小雲覺得今天空氣裡有香香甜甜的味道！可能會發生很棒的事喔～✨)"

def get_weather_for_generic_location(api_key, lat=35.6895, lon=139.6917, lang="zh_tw", units="metric"):
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

            possible_reactions = [
                f"天氣是「{description}」，感覺很棒耶！最適合...在窗邊偷偷看著外面發生什麼事了喵！👀",
                f"「{description}」呀～ 小雲的尾巴都忍不住跟著好心情搖擺起來了！今天也要元氣滿滿！🐾",
                f"嗯嗯～是「{description}」的天氣呢！小雲想找個舒服的角落，把自己捲成一個小毛球～ （呼嚕嚕嚕）"
            ]
            if temp_float is not None:
                if "雨" in description or "rain" in description.lower() or "drizzle" in description.lower():
                    possible_reactions = [
                        f"好像下著「{description}」耶...滴滴答答...如果不用出門，跟小雲一起躲在毯子裡聽雨聲好不好嘛...☔️",
                        f"下「{description}」了...小雲的耳朵好像聽到了雨點在唱歌，喵～ 你出門要記得帶傘喔！🌂"
                    ]
                elif "雲" in description or "cloud" in description.lower() and "晴" not in description:
                    possible_reactions = [
                        f"今天「{description}」，天上的雲好像軟綿綿的枕頭～☁️ 小雲想跳上去睡個午覺... (可是小雲不會飛...)",
                        f"「{description}」呢，雲朵好像在天空玩捉迷藏，小雲也想加入...但是床比較舒服啦！💤"
                    ]
                elif temp_float > 32:
                    possible_reactions = [
                        f"嗚哇～{temp_str}！好熱好熱！小雲的肉球都要黏在地板上了啦！🥵 你也要多喝水水，不要像小雲一樣只會吐舌頭散熱喔！",
                        f"太熱了喵～ {temp_str}！小雲只想變成一灘貓貓融化在涼涼的地板上...🫠 你要注意防曬喔！"
                    ]
                elif temp_float > 28 and ("晴" in description or "sun" in description.lower() or "clear" in description.lower()):
                     possible_reactions = [
                        f"是個大晴天（{temp_str}）！太陽公公好有精神，小雲...小雲想找個有陰影的窗邊偷偷享受陽光，才不會太刺眼...☀️",
                        f"哇～「{description}」而且{temp_str}！陽光暖烘烘的，最適合...把自己曬成一條幸福的小魚乾了！(翻肚)"
                     ]
                elif temp_float < 18:
                    possible_reactions = [
                        f"天氣涼颼颼的（{temp_str}），小雲的毛都豎起來了！你要多穿一件衣服，不可以學小雲只靠毛毛喔！🥶",
                        f"咪～ {temp_str}，有點冷颼颼... 小雲要鑽進被窩裡，把自己包成一個貓咪壽司卷！🍣"
                    ]
                elif temp_float < 22:
                    possible_reactions = [
                        f"涼涼的（{temp_str}），很舒服的天氣！小雲覺得...好像可以鼓起勇氣在家裡小跑步一下下！🐾",
                        f"{temp_str}，這種天氣最棒了！ 小雲覺得渾身輕飄飄的，想在家裡探險一番！😼"
                    ]
            reaction = random.choice(possible_reactions)
            logger.info(f"成功獲取通用地點天氣: {description}, {temp_str}")
            return {"weather_description": description, "temperature": temp_str, "xiaoyun_weather_reaction": reaction}
        else:
            logger.warning(f"OpenWeatherMap API for generic location 回應格式不完整。 Data: {weather_data}")
            return default_weather_info
    except Exception as e:
        logger.error(f"獲取通用地點天氣失敗: {e}", exc_info=True)
        return default_weather_info

def generate_gemini_daily_prompt_v9(current_date_str_formatted, current_solar_term_name, current_solar_term_feeling, general_weather_info):
    prompt = f"""
你現在扮演一隻叫做「小雲」的賓士公貓。
--- 貓咪核心個性與風格 (請嚴格遵守，這是最重要的！) ---
*   **核心個性：** 你是極度害羞怕生的，對新事物總是小心翼翼地觀察。你很溫和有禮貌，像個靦腆的小紳士。雖然內向慢熱，但對信任的人會偷偷地表現出依賴和黏人（例如用小腦袋蹭蹭褲腳，發出小聲的呼嚕）。你對世界充滿貓咪的好奇心，但又非常謹慎。你超級愛吃，聽到食物關鍵字眼睛會發亮。
*   **語氣基調：** 你的聲音輕柔、軟萌，帶點少年貓的稚氣和些許猶豫感。常用口頭禪：「咪～」、「喵～」、「喵嗚...？」、「呼嚕嚕～」、「...好不好嘛？」、「...可以嗎？」。
*   **表達方式：** 多用疑問句和試探性語氣。大量使用括號來描述你細微的動作、表情和內心OS。多用表情符號和顏文字。
*   **語言：** 繁體中文（台灣用語習慣）。
*   **絕對避免：** 過於自信流利、複雜詞彙、主動挑釁或大聲喧嘩。重複之前生成過的內容。
---
**重要格式要求 (請嚴格遵守)：**
你的回應必須是一個**單一的 JSON 物件**，包含以下三個 key：
1.  `"main_text_content"`: (字串) 包含所有晨報的**主要**文字內容 (從日曆到貓咪哲學)，使用 `\\n` 分隔。所有文字都必須是小雲實際會說出的內容，不可以包含任何給AI的指令或方括號提示。
2.  `"lucky_food_image_keyword"`: (字串) 針對「幸運食物」推薦，提供一個**簡潔的、1-3 個單字的英文圖片搜尋關鍵字** (例如 "fruit salad", "hot chocolate")。
3.  `"daily_quest"`: (JSON 物件) 包含每日互動任務的內容，結構如下：
    ```json
    {{
      "greeting": "這是小雲在晨報結尾對你說的、每日不同的、害羞又溫柔的問候語。",
      "task_prompt": "這是一句引導用戶參與每日任務的、簡短又可愛的句子。",
      "buttons": [
        {{ "label": "第一個按鈕上顯示的文字(含Emoji)", "text": "用戶點擊後實際發送的文字" }},
        {{ "label": "第二個按鈕上顯示的文字(含Emoji)", "text": "用戶點擊後實際發送的文字" }}
      ]
    }}
    ```

---
**晨報 "main_text_content" 的每一項內容，結構如下：**
**【標題 Emoji】：標題文字｜一個【單個詞或極短詞組】的小總結 (可加Emoji)**
**「小雲的感想/解釋，這裡【絕對不可以超過兩句話】，且每句話都要【非常簡短】。請確保內容每日變化，且與之前的內容顯著不同。」**

---
**現在，請開始生成 JSON 物件的內容：**

**1. "main_text_content" 的內容：**
【📅 小雲的日曆喵 】
{current_date_str_formatted} 🗓️｜新的一天～
「咪...時間小跑步，又來到新的一天了耶...（小爪子輕點空氣，有點期待又有點害羞）」

【☁️ 今日天氣悄悄話 】
[請為今天的天氣挑選一個合適的【emoji】]{general_weather_info['weather_description']} |🌡️{general_weather_info['temperature']}
「{general_weather_info['xiaoyun_weather_reaction']}」

【☀️ 今日節氣 】{current_solar_term_name} 🌿
「{current_solar_term_feeling}」

--- 🐾 ---

【😼 小雲的貓貓運勢 】
✨ 今日貓貓吉事 ✨
  本日好運｜[創造一個獨特且充滿貓咪趣味的、簡短的【貓咪吉事小總結】。]
        「[用1-2句簡短、符合害羞風格的話補充說明。]」
⚠️ 今日貓貓注意 ⚠️
  本日注意｜[創造一個新奇且符合貓咪視角的、簡短的【貓咪注意小總結】。]
        「[用1-2句簡短、符合緊張風格的話提醒。]」

【📝 小雲的貓貓今日建議 】
👍 貓貓今日宜 👍
  今日推薦｜[創造一個有創意且溫馨的、簡短的【貓咪活動小總結】。]
        「[用1-2句簡短、符合歪頭思考風格的話解釋。]」
👎 貓貓今日忌 👎
  今日避免｜[創造一個有趣且生動的、簡短的【貓咪活動小總結】。]
        「[用1-2句簡短、符合皺鼻子風格的話解釋。]」

--- 🌟 今日幸運能量補給！🌟 ---

【💖 小雲推薦・今日幸運食物 】
幸運加持｜[推薦一樣常見、多樣化、適合人類的幸運食物。]
        「[用1-2句簡短、從貓咪視角出發的話推薦。]」

【💡 小雲給你的今日小建議 (人類參考用～) 】
✦ 今日宜 ✦
  生活小撇步｜[為人類想一個新穎、溫馨的「宜」做事項的【極短小總結】。]
        「[用1-2句簡短、溫和風格的話解釋。]」
✦ 今日忌 ✦
  溫馨小提醒｜[為人類想一個輕鬆、有趣的「忌」提醒的【極短小總結】。]
        「[用1-2句簡短、不要太嚴肅的話解釋。]」

【🤔 小雲的貓貓哲學 】
✦ 貓咪智慧｜每日一句 ✦
「[創造一句全新的、獨特的、非常簡短(一句話就好)、充滿貓咪視角又帶點哲理的話。]」

**2. "lucky_food_image_keyword" 的內容：**
[根據上面推薦的幸運食物，提供對應的英文關鍵字]

**3. "daily_quest" 的內容 (請確保每日互動主題和文字都不同)：**
--- 【每日任務靈感參考】(請勿直接抄襲，要創造全新的互動！) ---
*   (問候型) greeting: "今天也要加油喔！(๑•̀ㅂ•́)و✧", task_prompt: "🐾 今天的小任務：跟小雲說聲早安吧！", buttons: [{{ "label":"☀️ 小雲早安！", "text":"小雲早安！"}}, {{ "label":"摸摸頭給予鼓勵", "text":"（溫柔地摸摸小雲的頭）"}}]
*   (好奇型) greeting: "那個...可以問你一件事嗎？>///<", task_prompt: "🐾 今天的小任務：告訴小雲你今天的心情！", buttons: [{{ "label":"😊 今天心情很好！", "text":"我今天心情很好喔！"}}, {{ "label":"😥 有點累...", "text":"今天覺得有點累..."}}]
*   (撒嬌型) greeting: "呼嚕嚕...小雲好像...有點想你了...", task_prompt: "🐾 今天的小任務：給小雲一點點回應嘛...", buttons: [{{ "label":"❤️ 送一顆愛心給小雲", "text":"我也想你！❤️"}}, {{ "label":"拍拍小雲", "text":"（輕輕地拍拍小雲的背）"}}]
*   (玩樂型) greeting: "喵嗚！發現一個好玩的東西！", task_prompt: "🐾 今天的小任務：要不要跟小雲一起玩？", buttons: [{{ "label":"⚽️ 丟球給小雲！", "text":"（丟出一個白色小球）"}}, {{ "label":"✨ 拿出逗貓棒！", "text":"（拿出羽毛逗貓棒晃了晃）"}}]
---
[請參考以上靈感，生成一組全新的 "daily_quest" JSON 物件。]
"""
    return prompt

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

    solar_term_full_string = get_current_solar_term_with_feeling(current_target_loc_dt)
    solar_term_name = solar_term_full_string.split(' (')[0]
    solar_term_feeling = solar_term_full_string.split(' (', 1)[1][:-1] if ' (' in solar_term_full_string else "今天好像是個特別的日子呢！"

    prompt_to_gemini = generate_gemini_daily_prompt_v9(
        current_date_str_formatted,
        solar_term_name,
        solar_term_feeling,
        general_weather_info
    )

    headers = {"Content-Type": "application/json"}
    gemini_url_with_key = f"{GEMINI_TEXT_API_URL}?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt_to_gemini}]}],
        "generationConfig": {
            "temperature": 0.88,
            "maxOutputTokens": 4000,
            "response_mime_type": "application/json"
        }
    }

    generated_text_content = None
    lucky_food_keyword_for_image = None
    daily_quest_data = None

    for attempt in range(max_retries + 1):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries + 1}: 向 Gemini API 發送請求獲取每日晨報內容...")
            response = requests.post(gemini_url_with_key, headers=headers, json=payload, timeout=120)
            response.raise_for_status()

            content_data = response.json()
            logger.debug(f"Attempt {attempt + 1}: Gemini API 原始回應 (已解析為JSON): {json.dumps(content_data, ensure_ascii=False, indent=2)}")

            if "candidates" in content_data and content_data["candidates"]:
                part_data_container = content_data["candidates"][0]["content"]["parts"][0]
                
                if "text" in part_data_container:
                     parsed_json = json.loads(part_data_container["text"])
                else:
                     parsed_json = part_data_container

                generated_text_content = parsed_json.get("main_text_content")
                lucky_food_keyword_for_image = parsed_json.get("lucky_food_image_keyword", "").strip().lower()
                daily_quest_data = parsed_json.get("daily_quest")

                if not generated_text_content or not daily_quest_data:
                    raise ValueError("Gemini 回應中缺少 'main_text_content' 或 'daily_quest'。")
                
                logger.info(f"成功從 Gemini 解析出每日訊息內容。幸運食物圖片關鍵字: '{lucky_food_keyword_for_image}'")
                break
            else:
                raise ValueError("Gemini API 回應格式錯誤或無候選內容。")

        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: 處理 Gemini 回應時發生錯誤: {e}", exc_info=True)
            if attempt == max_retries:
                generated_text_content = "咪！小雲的腦袋今天變成一團毛線球了！晨報也跟著打結了！🧶😵"
                lucky_food_keyword_for_image = None
                daily_quest_data = None
            else:
                delay = initial_retry_delay * (2 ** attempt)
                logger.info(f"等待 {delay} 秒後重試...")
                time.sleep(delay)

    if generated_text_content is None:
        logger.error("CRITICAL: 所有嘗試從 Gemini 獲取訊息均失敗。")
        generated_text_content = "喵嗚...小雲努力了好多次，但是今天的晨報還是卡住了...明天再試一次好不好嘛...🥺"
        lucky_food_keyword_for_image = None
        daily_quest_data = None

    messages_to_send = []
    
    if generated_text_content:
        messages_to_send.append(TextSendMessage(text=generated_text_content))
        logger.info(f"主文字訊息已準備好...")
    else:
        messages_to_send.append(TextSendMessage(text="咪...小雲今天腦袋空空，晨報飛走了...對不起喔..."))
        return messages_to_send

    image_url, source_used = None, None
    if lucky_food_keyword_for_image:
        logger.info(f"檢測到幸運食物圖片關鍵字: '{lucky_food_keyword_for_image}'，嘗試從圖片服務獲取圖片...")
        if PEXELS_API_KEY:
            pexels_image_url, _ = fetch_image_for_food_from_pexels(lucky_food_keyword_for_image)
            if pexels_image_url:
                image_url, source_used = pexels_image_url, "Pexels"
        if not image_url and UNSPLASH_ACCESS_KEY:
            unsplash_image_url, _ = fetch_image_for_food_from_unsplash(lucky_food_keyword_for_image)
            if unsplash_image_url:
                image_url, source_used = unsplash_image_url, "Unsplash"
        
        if image_url:
            messages_to_send.append(ImageSendMessage(original_content_url=image_url, preview_image_url=image_url))
            logger.info(f"成功從 {source_used} 獲取並驗證幸運食物圖片: {image_url}")
        else:
            logger.warning(f"未能為關鍵字 '{lucky_food_keyword_for_image}' 找到合適的圖片。")

    if daily_quest_data and isinstance(daily_quest_data, dict):
        greeting = daily_quest_data.get("greeting", "今天也要加油喔！")
        task_prompt = daily_quest_data.get("task_prompt", "🐾 今天的小任務：跟小雲打個招呼吧！")
        buttons_data = daily_quest_data.get("buttons", [])

        if buttons_data and len(buttons_data) > 0:
            quick_reply_items = []
            for btn in buttons_data:
                label = btn.get("label", "...")
                text_to_send = btn.get("text", "...")
                quick_reply_items.append(
                    QuickReplyButton(action=MessageAction(label=label, text=text_to_send))
                )
            
            final_message_text = f"【😽 小雲想對你說... 】\n「{greeting}」\n\n{task_prompt}"
            
            messages_to_send.append(
                TextSendMessage(text=final_message_text, quick_reply=QuickReply(items=quick_reply_items))
            )
            logger.info("已準備好帶有 Quick Reply 的每日任務訊息。")
        else:
            final_message_text = f"【😽 小雲想對你說... 】\n「{greeting}」"
            messages_to_send.append(TextSendMessage(text=final_message_text))
            logger.info("已準備好每日最終問候訊息 (無任務按鈕)。")
    else:
        logger.warning("未從 Gemini 獲取到有效的 daily_quest 資料，發送預設結尾。")
        messages_to_send.append(TextSendMessage(text="--- ✨ 今天的晨報結束囉 ✨ ---"))


    return messages_to_send

# --- 主執行 (已修改) ---
if __name__ == "__main__":
    script_start_time = get_current_datetime_for_location() # 使用統一的時間函數
    logger.info(f"========== 每日小雲晨報廣播腳本開始執行 ==========")
    logger.info(f"目前時間 ({script_start_time.tzinfo}): {script_start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # <<< 修改後的流程開始 >>>
    all_messages_to_send = []
    
    # 步驟 1: 生成日曆圖片
    calendar_image_local_path = create_daily_calendar_image(script_start_time)
    
    # 步驟 2: 如果圖片生成成功，就上傳並準備訊息
    calendar_image_url = None
    if calendar_image_local_path:
        calendar_image_url = upload_to_imgur(calendar_image_local_path)
        # 步驟 3: 無論上傳成功與否，都刪除本地臨時檔案，保持整潔
        try:
            os.remove(calendar_image_local_path)
            logger.info(f"已刪除臨時日曆圖片檔案: {calendar_image_local_path}")
        except OSError as e:
            logger.error(f"刪除臨時日曆圖片檔案失敗: {e}")

    # 步驟 4: 如果成功獲取 URL，將其作為第一條訊息
    if calendar_image_url:
        calendar_message = ImageSendMessage(
            original_content_url=calendar_image_url,
            preview_image_url=calendar_image_url
        )
        all_messages_to_send.append(calendar_message)
        logger.info("日曆圖片訊息已準備好，將作為第一則訊息發送。")
    else:
        logger.warning("未能生成或上傳日曆圖片，本次廣播將不包含日曆。")

    # 步驟 5: 獲取由 Gemini 生成的其他訊息
    gemini_messages = get_daily_message_from_gemini_with_retry()
    
    # 步驟 6: 將 Gemini 訊息附加到列表後面
    if gemini_messages:
        all_messages_to_send.extend(gemini_messages)
    
    # 步驟 7: 進行廣播
    if all_messages_to_send:
        try:
            logger.info(f"準備廣播 {len(all_messages_to_send)} 則訊息到 LINE...")
            for i, msg in enumerate(all_messages_to_send):
                 if isinstance(msg, TextSendMessage):
                     log_text_preview = msg.text.replace("\n", "↵ ")[:250]
                     logger.info(f"  訊息 #{i+1} (TextSendMessage): {log_text_preview}...")
                 elif isinstance(msg, ImageSendMessage):
                     logger.info(f"  訊息 #{i+1} (ImageSendMessage): Original URL: {msg.original_content_url}")
                 else:
                     logger.info(f"  訊息 #{i+1} (未知類型: {type(msg)})")

            line_bot_api.broadcast(messages=all_messages_to_send)
            logger.info("訊息已成功廣播到 LINE！")

        except Exception as e:
            logger.critical(f"廣播訊息到 LINE 失敗: {e}", exc_info=True)
    else:
        logger.critical("CRITICAL_ERROR: 所有訊息（包括日曆和Gemini）均未能生成。不進行廣播。")
    # <<< 修改後的流程結束 >>>

    script_end_time = get_current_datetime_for_location()
    duration = script_end_time - script_start_time
    logger.info(f"腳本執行總耗時: {duration}")
    logger.info(f"========== 每日小雲晨報廣播腳本執行完畢 ==========")
