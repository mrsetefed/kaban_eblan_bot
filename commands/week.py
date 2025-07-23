from utils import fetch_schedule_json
from datetime import datetime, timedelta

async def week(update, context):
    username = "setefed"
    schedule = await fetch_schedule_json(username)
    start_date = datetime.now()
    days = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        pretty = day.strftime("%d.%m (%a)")  # например, 23.07 (Tue)
        value = schedule.get(day_str, "нет данных")
        days.append(f"{pretty}: {value}")
    message = "\n".join(days)
    await update.message.reply_text(f"📅 Неделя:\n{message}")