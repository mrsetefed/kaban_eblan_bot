from datetime import timedelta

from telegram import Update
from telegram.ext import ContextTypes

from .vlas_schedule import WEEKDAYS_SHORT, describe, fetch_schedule, today_utc


async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule, error = await fetch_schedule()
    if schedule is None:
        await update.message.reply_text(error)
        return

    start = today_utc()
    lines = []
    for i in range(7):
        day = start + timedelta(days=i)
        text = describe(schedule.get(day.isoformat()))
        lines.append(f"{day:%d.%m} ({WEEKDAYS_SHORT[day.weekday()]}): {text or 'нет информации'}")
    await update.message.reply_text("Расписание на неделю:\n\n" + "\n".join(lines))
