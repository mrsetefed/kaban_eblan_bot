from utils import fetch_schedule
from datetime import datetime, timedelta

async def tomorrow(update, context):
    schedule = await fetch_schedule()
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    message = schedule.get(tomorrow_str, "На завтра график не задан")
    await update.message.reply_text(f"📅 Завтра: {message}")