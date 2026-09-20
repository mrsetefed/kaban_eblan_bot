from telegram import Update
from telegram.ext import ContextTypes

from .vlas_schedule import describe, fetch_schedule, today_utc


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule, error = await fetch_schedule()
    if schedule is None:
        await update.message.reply_text(error)
        return

    text = describe(schedule.get(today_utc().isoformat()))
    await update.message.reply_text(f"Сегодня: {text or 'график не задан'}")
