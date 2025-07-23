from utils import fetch_schedule_json
from datetime import datetime

async def today(update, context):
    today_str = datetime.now().strftime("%Y-%m-%d")
    schedule = await fetch_schedule_json()
    message = schedule.get(today_str, "Сегодня график не задан")
    await update.message.reply_text(f"📅 Сегодня: {message}")