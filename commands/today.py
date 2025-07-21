from utils import fetch_schedule
from datetime import datetime

async def today(update, context):
    schedule = await fetch_schedule()
    today_str = datetime.now().strftime("%Y-%m-%d")
    message = schedule.get(today_str, "Сегодня график не задан")
    await update.message.reply_text(f"📅 Сегодня: {message}")