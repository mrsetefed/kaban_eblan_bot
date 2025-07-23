from utils import fetch_schedule_json
from datetime import datetime, timedelta

async def tomorrow(update, context):
    username = "setefed"  # если нужно — получай из аргументов или профиля
    schedule = await fetch_schedule_json(username)
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    message = schedule.get(tomorrow_str, "Завтра график не задан")
    await update.message.reply_text(f"📅 Завтра: {message}")