from bs4 import BeautifulSoup
from telegram import Bot
import requests
import re
import datetime as dt
import asyncio
import os
import sys

# Telegram Configuration
TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHANNEL = '@safeorsorrytw'

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }

def get_travel_advisory(country="taiwan"):
    country = country.lower().replace(' ', '-')
    url = f"https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories/{country}-travel-advisory.html"
    try:
        response = requests.get(url, headers=get_headers())
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        text = soup.get_text()
        level = re.search(rf'{country.title().replace("-", " ")} - (Level \d+: [^\n]+)', text).group(1)
        
        alert = soup.find('div', class_='tsg-rwd-emergency-alert-text')
        description = alert.find_all('p')[1].get_text(strip=True) if (alert and len(alert.find_all('p')) > 1) else 'No reason found'

        reasons = {
            i.get_text(strip=True, separator=' ') : i.get('data-tooltip').replace('\xa0', ' ').strip() \
            for i in soup.find_all(class_='showThreat')
        }
            
        return {'country': country.title(), 'level_num': int(level.split(':')[0].split(' ')[1]), 'level_text': level, 'description': description, 'reasons': reasons}
        
    except requests.RequestException as e:
        return {"error": f"Error fetching data: {str(e)}"}

def get_ait_alert():
    url = "https://www.ait.org.tw/category/alert/"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    return [{
        'title': article.find('a').get_text(strip=True),
        'link': article.find('a')['href'],
    } for article in soup.find_all(class_='entry-title') if any(text in article.find('a').get_text(strip=True) for text in [
        "Alert", 
        "Department of State Presence",
        "Message for U.S. Citizens",
        "Message to U.S. Citizens",
    ])]

def generate_ait_alert_message(ait_alert:list):    

    alert_map = {
        "Security Alert  Worldwide Caution": "🌍⚠️ 全球安全",
        "Security": "⚠️ 安全",
        "Weather": "🌧️ 天氣", 
        "Earthquake": "🌋 地震",
        "Typhoon": "🌀 颱風",
        "Health": "🏥 健康",
        "Public Gather": "👥 集會",
        "Heightened": "⬆️ 提高警戒",
        "Voting": "🗳️ 美國公民記得去投票",
        "Elections": "🗳️ 美國公民記得去投票",
        "Ballot": "🗳️ 美國公民記得去投票",
        "Air Defense Exercise": "🛡️ 防空演習",
        "Department of State Presence": "💀 撤僑",
    }
    def find_alert_type(alert, alert_map):
        for k, v in alert_map.items():
            if k in alert['title']:
                return v
        return '❓未知'

    message = f"🚨 AIT 發布警戒 🚨 \n\n"
    message += f"警戒類型: {find_alert_type(ait_alert, alert_map)}\n\n"
    message += f"原始訊息: \n{ait_alert['title']}\n{ait_alert['link']}\n\n"
    
    current_time = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    message += f"更新時間: {current_time}"
    return message

def generate_travel_advisory_message(travel_adv:dict, levels_map=None):
    
    current_time = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    weekday_phrase = '乖乖去上班吧' if current_time.weekday() < 5 else '好好享受假日吧'
    current_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    levels_map = {
        1: f'今天很安全，{weekday_phrase}。',
        2: f'🟡🟡 警戒升級！建議提高警覺！',
        3: f'🟠🟠🟠 非常危險！請立即採取應對措施！！！',
        4: f'🔴🔴🔴🔴 極度危險！請立即採取應對措施！！！',
    } if levels_map is None else levels_map
    reasons_map = {
        "C": "犯罪率",
        "T": "恐怖主義活動",
        "U": "社會動盪",
        "N": "天災",
        "H": "衛生健康問題",
        "K": "綁架或扣押人質",
        "D": "不正當拘留",
        "O": "其他",
    }
    message = f"{levels_map[travel_adv['level_num']]}\n\n"
    if travel_adv['reasons']!={}:
        message += f"警戒原因：{'、'.join(reasons_map[k] for k in sorted(travel_adv['reasons'].keys()))}。\n\n"
    message += f"原始訊息: \n{travel_adv['country']} - {travel_adv['level_text']}\n"
    if travel_adv['reasons']!={}:
        message += '\n'
        for k, v in travel_adv['reasons'].items():
            message += f"{k}: {v}\n"
    message += f"\n{travel_adv['description']}\n\n"
    message += f"更新時間: {current_time}"

    return message

async def send_telegram_message(token, channel, text):
    try:
        bot = Bot(token=token)
        await bot.send_message(chat_id=channel, text=text)
    except Exception as e:
        print(f"Error sending telegram message: {str(e)}", file=sys.stderr)
        sys.exit(1)