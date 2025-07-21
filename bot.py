import os
import sys
import csv
import datetime
import logging
import requests

from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен и URL GitHub файла
try:
    TOKEN = os.environ["BOT_TOKEN"]
except KeyError:
    print("❌ BOT_TOKEN not found", file=sys.stderr)
    sys.exit(1)

CSV_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/main/schedule.csv"

# Функция загрузки расписания
async def fetch_schedule():
    try:
        response = requests.get(CSV_URL)
        response.raise_for_status()
        decoded = response.content.decode("utf-8").splitlines()
        reader = csv.DictReader(decoded)
        return {row["date"]: row["text"] for row in reader}
    except Exception as e:
        logging.error(f"Ошибка при загрузке расписания: {e}")
        return {}

# Команды
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date = datetime.date.today().isoformat()
    schedule = await fetch_schedule()
    msg = schedule.get(date, "На сегодня ничего нет.")
    await update.message.reply_text(msg)

async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    schedule = await fetch_schedule()
    msg = schedule.get(date, "На завтра ничего нет.")
    await update.message.reply_text(msg)

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.date.today()
    schedule = await fetch_schedule()
    msgs = []
    for i in range(7):
        day = today + datetime.timedelta(days=i)
        key = day.isoformat()
        entry = schedule.get(key)
        if entry:
            msgs.append(f"{key}: {entry}")
    if msgs:
        await update.message.reply_text("\n".join(msgs))
    else:
        await update.message.reply_text("На неделю ничего нет.")

async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.date.today()
    schedule = await fetch_schedule()
    msgs = []
    for i in range(31):
        day = today + datetime.timedelta(days=i)
        key = day.isoformat()
        entry = schedule.get(key)
        if entry:
            msgs.append(f"{key}: {entry}")
    if msgs:
        await update.message.reply_text("\n".join(msgs))
    else:
        await update.message.reply_text("На месяц ничего нет.")

# Веб-сервер
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("ping", ping))
app.add_handler(CommandHandler("today", today))
app.add_handler(CommandHandler("tomorrow", tomorrow))
app.add_handler(CommandHandler("week", week))
app.add_handler(CommandHandler("month", month))

WEBHOOK_PATH = "/"  # Render использует путь /
PORT = int(os.environ.get("PORT", 10000))

async def handle(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response()

aio_app = web.Application()
aio_app.add_routes([web.post(WEBHOOK_PATH, handle)])

if __name__ == "__main__":
    print("🚀 Бот запускается через вебхук...")
    # Устанавливаем вебхук
    webhook_url = f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/"
    app.bot.set_webhook(url=webhook_url)
    web.run_app(aio_app, port=PORT)