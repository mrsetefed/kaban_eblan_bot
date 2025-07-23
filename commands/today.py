from utils import fetch_selected_json_schedules
from datetime import datetime

async def today(update, context):
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    schedule = fetch_selected_json_schedules(["setefed"])
    message = schedule.get("setefed", {}).get(today_str, "Сегодня график не задан")
    await update.message.reply_text(f"📅 Сегодня: {message}")
