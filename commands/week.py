from utils import fetch_schedule
from datetime import datetime, timedelta

async def week(update, context):
    schedule = await fetch_schedule()
    today = datetime.now()
    lines = []
    for i in range(7):
        date = today + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        pretty = date.strftime("%d.%m (%a)")
        text = schedule.get(date_str, "—")
        lines.append(f"{pretty}: {text}")
    await update.message.reply_text("\n".join(lines))