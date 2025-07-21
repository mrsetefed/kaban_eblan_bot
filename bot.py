import os
import sys
import csv
import requests
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ BOT_TOKEN not found.")
    sys.exit(1)

RAW_CSV_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/main/schedule.csv"

# ================= Команды =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отъебись.")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

# ================= Парсинг расписания =================

async def fetch_schedule():
    try:
        response = requests.get(RAW_CSV_URL)
        lines = response.text.strip().splitlines()
        return dict(line.split(",", 1) for line in lines if "," in line)
    except Exception as e:
        return {}

def get_day(offset=0):
    return (datetime.utcnow() + timedelta(days=offset)).date().isoformat()

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    date = get_day(0)
    reply = schedule.get(date, "График на сегодня не задан.")
    await update.message.reply_text(f"📅 {date}\n{reply}")

async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    date = get_day(1)
    reply = schedule.get(date, "График на завтра не задан.")
    await update.message.reply_text(f"📅 {date}\n{reply}")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    reply = ""
    for i in range(7):
        date = get_day(i)
        reply += f"📅 {date}\n{schedule.get(date, '—')}\n"
    await update.message.reply_text(reply.strip())

# ================= Запуск =================

if __name__ == '__main__':
    print("🚀 Бот запускается (polling)...")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("tomorrow", tomorrow))
    app.add_handler(CommandHandler("week", week))

    app.run_polling()