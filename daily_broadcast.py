# daily_broadcast.py
import os
import random
import datetime
import pytz # pip install pytz
import requests # pip install requests
from linebot import LineBotApi
from linebot.models import TextSendMessage
import json

# --- 環境變數 (將由 GitHub Secrets 提供) ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = "gemini-1.5-flash-latest" # 或你選擇的模型
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_NAME}:generateContent"

# --- 全局初始化 (如果適用) ---
if not (LINE_CHANNEL_ACCESS_TOKEN and GEMINI_API_KEY):
    print("錯誤：執行環境中缺少 LINE_CHANNEL_ACCESS_TOKEN 或 GEMINI_API_KEY。")
    print("請在 GitHub Repository > Settings > Secrets and variables > Actions 中設定這些 Secrets。")
    exit(1) # 在 Actions 環境中，這會使 job 失敗

try:
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
except Exception as e:
    print(f"錯誤：初始化 LineBotApi 失敗: {e}")
    exit(1)

# --- 輔助函數 ---
def get_taiwan_date_and_day():
    tw_tz = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tw_tz)
    # 檢查是否為早上5點 (UTC 21點)
    # GitHub Actions 的 cron 是 UTC 時間，所以當 cron 設為 21:00 UTC 時，這裡的台灣時間應該是早上 5:00
    # 這裡可以加一個保險判斷，但理論上 cron 已經保證了時間
    # if now_tw.hour != 5:
    #     print(f"目前台灣時間 {now_tw.strftime('%H:%M')}，非目標廣播時間 (早上5點)，腳本將不執行廣播。")
    #     return None, None # 返回 None 表示不繼續執行

    date_str = now_tw.strftime("%Y年%m月%d日")
    days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    day_of_week_str = days[now_tw.weekday()]
    return f"{date_str} {day_of_week_str}", now_tw

def get_simple_solar_term(now_tw_datetime):
    # 簡易節氣判斷 (你需要一個更精確的庫或數據源)
    # 這裡僅為範例，實際應用請使用更準確的節氣資料
    month = now_tw_datetime.month
    day = now_tw_datetime.day
    if (month == 2 and day >= 3 and day <= 5): return "立春 (春天悄悄來了喵～有些花苞好像要開了耶)"
    if (month == 3 and day >= 5 and day <= 7): return "驚蟄 (咪～小雲好像聽到遠方有小蟲蟲在打哈欠...)"
    if (month == 3 and day >= 20 and day <= 22): return "春分 (白天跟黑夜一樣長耶！小雲可以多玩一下再睡覺嗎？)"
    if (month == 4 and day >= 4 and day <= 6): return "清明 (天氣暖呼呼的，最適合...在窗邊曬太陽睡午覺了，呼嚕嚕～)"
    # ... (添加更多節氣)
    return "一個特別的日子 (小雲覺得今天空氣聞起來香香的！)" # 預設

def get_simulated_weather():
    weathers = [
        "陽光暖烘烘的，最適合把肚肚曬得暖暖的了！喵～☀️",
        "陰天，天色暗暗的，小雲的毛好像也變得比較蓬鬆耶...☁️",
        "好像快下雨了，空氣聞起來濕濕的...滴滴答答...小雲要找個乾燥的紙箱躲好！☔️",
        "風有點大，咻咻叫～窗戶邊的小樹葉都在跳舞呢！💨"
    ]
    return random.choice(weathers)

# --- Gemini 相關 ---
def generate_gemini_daily_prompt(current_date_str, current_solar_term_with_feeling, simulated_weather):
    # 小雲風格的吉凶宜忌詞庫
    LUCK_GOOD = [
        "被溫柔地摸摸頭，舒服到發出呼嚕嚕的聲音～🥰",
        "今天吃的罐罐好像特別香！是鮪魚口味的嗎？咪！🐟",
        "發現一個全新的、大小剛剛好的空紙箱！是我的新秘密基地！📦",
        "窗外的小鳥今天唱歌特別好聽，像是在跟小雲打招呼！🐦",
        "成功用無辜大眼攻擊，獲得了額外的小零食！(計劃通✨)"
    ]
    LUCK_BAD = [
        "走路不小心踩到自己的小尾巴，痛痛的嗚...🐾",
        "家裡突然出現吸塵器怪獸！好可怕！小雲要躲到床底下！😫",
        "最喜歡的白色小球滾到沙發底下拿不出來了...怎麼辦啦...힝...",
        "打哈欠的時候不小心咬到舌頭...喵嗚...👅",
        "人類今天好像很忙，比較少摸摸小雲...有點孤單...🥺"
    ]
    DO_CATS = [
        "盡情地伸一個從頭到尾巴尖都拉～長～的懶腰！超級舒服！🙆‍♀️",
        "找一個灑滿陽光的窗台，把自己攤成一塊貓餅，享受日光浴！☀️",
        "用最無辜、最水汪汪的眼神看著人類，發動「討零食」攻勢！🥺👉👈",
        "練習無聲落地！從貓跳台上咻～的跳下來，一點聲音都沒有！(自豪)",
        "花一點時間思考貓生...例如，為什麼罐罐不能每天都吃三餐呢？🤔"
    ]
    DONT_CATS = [
        "跟家裡的掃地機器人吵架 (你可能會被它推著走喔...)",
        "試圖爬到書櫃最上面然後發現下不來 (小雲有經驗...)",
        "趁人類不注意的時候打翻水杯 (除非你真的很想看人類驚慌的樣子😼)",
        "忘記每天都要把自己舔得乾乾淨淨、香噴噴的！ grooming time! ✨",
        "看到窗外有大狗狗就對著它哈氣 (它可能只是路過啦...)"
    ]

    prompt = f"""
你現在是小雲，一隻害羞、溫和有禮、充滿好奇心的賓士公貓。請你為用戶生成一則「小雲的今日貼心晨報」，風格要非常害羞可愛，充滿你的貓咪口吻和表情符號。
晨報必須是**單一一個 JSON 物件**，代表一個 LINE TextSendMessage。JSON 的 "content" 欄位應該包含所有晨報內容，並使用 `\\n` (JSON中的換行符) 來分隔不同的部分。
晨報的 "content" 內文必須嚴格包含以下部分，並使用【】標示每個部分：

【📅 日期喵】：{current_date_str}

【☀️ 今日節氣】：{current_solar_term_with_feeling}

【🐾 小雲貓貓運勢】：
    - 今日吉事：{random.choice(LUCK_GOOD)}
    - 今日注意：{random.choice(LUCK_BAD)}

【📝 小雲的今日建議】：
    - 今日宜：{random.choice(DO_CATS)}
    - 今日忌：{random.choice(DONT_CATS)}

【☁️ 天氣悄悄話】：{simulated_weather}

【🔔 小雲的小提醒】：[請你為人類想一句簡短、可愛、貓咪視角的今日小提醒，例如：「今天也要記得給小雲摸摸頭喔...咪...不然小雲會偷偷看著你...🥺」或「如果覺得累累的，學小雲找個軟軟的地方，縮成一團睡一下吧！很有用的喵～」]

【😽 小雲想說】：[最後，用小雲的風格說一句簡短的、充滿元氣或關心的話，例如：「喵嗚～希望你今天也過得很開心！小雲會在灑滿陽光的窗邊偷偷幫你加油的～（小聲）」或「咪...今天也要努力當一隻乖貓貓...也希望你順順利利的喔！✨」]

請直接輸出包含單一 TextSendMessage 的 JSON 列表字串，不要包含 "```json" 或 "```" 這些 markdown 標記。
例如： `[ {{"type": "text", "content": "【📅 日期喵】：2023年10月27日 星期五\\n【☀️ 今日節氣】：霜降 (天氣涼涼的，小雲的毛好像變得更蓬鬆了耶～)\\n..."}} ]`
"""
    return prompt

def get_daily_message_from_gemini():
    current_date_str, now_tw_dt = get_taiwan_date_and_day()
    if not current_date_str: # 如果 get_taiwan_date_and_day 返回 None, 表示非目標時間
        return None

    current_solar_term_with_feeling = get_simple_solar_term(now_tw_dt)
    simulated_weather = get_simulated_weather()

    prompt = generate_gemini_daily_prompt(current_date_str, current_solar_term_with_feeling, simulated_weather)
    headers = {"Content-Type": "application/json"}
    gemini_url_with_key = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 1500} # 可以調整溫度以獲得更多樣的結果
    }
    try:
        print(f"INFO: 正在向 Gemini API 發送請求 ({datetime.datetime.now(pytz.timezone('Asia/Taipei'))})...")
        response = requests.post(gemini_url_with_key, headers=headers, json=payload, timeout=60) # 增加超時
        response.raise_for_status() # 如果 HTTP 錯誤碼是 4xx 或 5xx，會拋出異常
        result = response.json()
        # print(f"DEBUG: Gemini API 原始回應: {json.dumps(result, ensure_ascii=False, indent=2)}")

        if "candidates" in result and result["candidates"] and \
           "content" in result["candidates"][0] and "parts" in result["candidates"][0]["content"] and \
           result["candidates"][0]["content"]["parts"]:

            gemini_response_str = result["candidates"][0]["content"]["parts"][0]["text"]
            gemini_response_str = gemini_response_str.strip() # 去除前後空白

            print(f"INFO: 從 Gemini 獲得的清理後 JSON 字串: {gemini_response_str[:300]}...") # 只印出前300字元

            try:
                # Gemini 應該直接返回符合 LINE 格式的 JSON 列表字串
                message_objects_data = json.loads(gemini_response_str)

                if isinstance(message_objects_data, list) and \
                   all(isinstance(item, dict) and "type" in item and "content" in item for item in message_objects_data if item.get("type") == "text"):
                    # 轉換為 LINE SDK 的 Message Objects
                    line_messages = []
                    for msg_data in message_objects_data:
                        if msg_data.get("type") == "text":
                            line_messages.append(TextSendMessage(text=str(msg_data["content"]))) # 確保 content 是字串
                        # 你可以在這裡擴展以支援 Gemini 可能返回的其他類型 (例如貼圖)
                        # elif msg_data.get("type") == "sticker" and "package_id" in msg_data and "sticker_id" in msg_data:
                        # line_messages.append(StickerSendMessage(package_id=str(msg_data["package_id"]), sticker_id=str(msg_data["sticker_id"])))

                    if line_messages:
                        print("INFO: 成功從 Gemini 解析出 LINE 訊息物件。")
                        return line_messages
                    else:
                        print("警告：Gemini 返回的 JSON 列表中沒有有效的 text message object。")
                        return [TextSendMessage(text="咪...小雲今天說話卡住了...內容格式怪怪的...")]
                else:
                    print(f"警告：Gemini 返回的不是預期的 LINE 訊息物件列表格式。原始回應: {gemini_response_str}")
                    # 嘗試將整個回應作為單一文字訊息發送 (備案)
                    return [TextSendMessage(text=f"小雲的晨報機器人好像有點小問題，這是它想說的：\n{gemini_response_str}")]

            except json.JSONDecodeError as e:
                print(f"錯誤：解析 Gemini 返回的 JSON 失敗: {e}。原始回應: {gemini_response_str}")
                return [TextSendMessage(text=f"喵嗚！小雲的晨報格式壞掉了！它說了這個：\n{gemini_response_str}")]
        else:
            block_reason = result.get("promptFeedback", {}).get("blockReason")
            if block_reason:
                print(f"錯誤：Gemini API 請求因 '{block_reason}' 被阻擋。")
                return [TextSendMessage(text=f"咪...小雲今天的晨報被神秘力量 ({block_reason}) 藏起來了！")]
            else:
                print(f"錯誤：Gemini API 回應格式不正確或無內容。回應: {result}")
                return [TextSendMessage(text="咪...小雲今天好像還沒睡醒耶...晨報不見了...")]

    except requests.exceptions.Timeout:
        print("錯誤：請求 Gemini API 超時。")
        return [TextSendMessage(text="喵嗚～小雲的秘密電波好像塞車了，晨報送不出來...")]
    except requests.exceptions.RequestException as e:
        print(f"錯誤：請求 Gemini API 失敗: {e}")
        return [TextSendMessage(text="喵嗚～小雲的秘密電波被外星貓干擾了！晨報咻～不見了！")]
    except Exception as e:
        print(f"錯誤：處理 Gemini 回應時發生未知錯誤: {e}")
        return [TextSendMessage(text="咪！小雲的腦袋今天打結了！晨報變成一團毛線球了！")]

# --- 主執行 ---
if __name__ == "__main__":
    print(f"INFO: 開始執行每日廣播腳本... (台灣時間: {datetime.datetime.now(pytz.timezone('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S')})")

    messages_to_send = get_daily_message_from_gemini()

    if messages_to_send:
        try:
            print(f"INFO: 準備廣播 {len(messages_to_send)} 則訊息...")
            for i, msg in enumerate(messages_to_send):
                 if isinstance(msg, TextSendMessage):
                     print(f"DEBUG: 訊息 #{i+1} (Text): {msg.text[:100]}...") # 印出文字訊息前100字
                 else:
                     print(f"DEBUG: 訊息 #{i+1} (Type: {type(msg)})")

            line_bot_api.broadcast(messages=messages_to_send)
            print("INFO: 訊息已成功廣播！")
        except Exception as e:
            print(f"錯誤：廣播訊息到 LINE 失敗: {e}")
            # 這裡可以考慮發送通知給管理員，例如透過 Email 或其他方式
    else:
        print("警告：沒有從 Gemini 獲取到有效訊息，不執行廣播。")

    print(f"INFO: 每日廣播腳本執行完畢。 (台灣時間: {datetime.datetime.now(pytz.timezone('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S')})")
