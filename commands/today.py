from utils import fetch_selected_json_schedules
from datetime import datetime

async def today(update, context):
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    schedule = await fetch_json_schedules("setefed")
    message = schedule.get(today_str, "Сегодня график не задан")
    await update.message.reply_text(f"📅 Сегодня: {message}")