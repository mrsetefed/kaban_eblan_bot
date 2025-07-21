from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from schedule_utils import fetch_schedule, get_today_str, get_tomorrow_str, get_next_7_days

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отъебись.")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    today_str = get_today_str()
    message = schedule.get(today_str, "Сегодня график не задан")
    await update.message.reply_text(f"📅 Сегодня: {message}")

async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    tomorrow_str = get_tomorrow_str()
    message = schedule.get(tomorrow_str, "На завтра график не задан")
    await update.message.reply_text(f"📅 Завтра: {message}")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    dates = get_next_7_days()
    lines = []
    for date_obj, date_str, pretty in dates:
        text = schedule.get(date_str, "—")
        lines.append(f"{pretty}: {text}")
    await update.message.reply_text("\n".join(lines))

def get_handlers():
    return [
        CommandHandler("start", start),
        CommandHandler("ping", ping),
        CommandHandler("today", today),
        CommandHandler("tomorrow", tomorrow),
        CommandHandler("week", week),
    ]
