import os
import sys
import csv
import logging
from datetime import datetime, timedelta
from aiohttp import web
import requests
import asyncio

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- Конфигурация ---
try:
    TOKEN = os.environ["BOT_TOKEN"]
except KeyError:
    print("❌ BOT_TOKEN not found in environment variables", file=sys.stderr)
    sys.exit(1)

WEBHOOK_PATH = "/"
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

SCHEDULE_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/main/schedule.csv"

# --- Чтение расписания ---
async def fetch_schedule():
    try:
        response = requests.get(SCHEDULE_URL)
        response.raise_for_status()
        lines = response.text.strip().split("\n")
        schedule = {}
        for line in lines:
            parts = line.strip().split(",", maxsplit=1)
            if len(parts) == 2:
                date_str, text = parts
                schedule[date_str.strip()] = text.strip()
        return schedule
    except Exception as e:
        logging.error(f"Не удалось получить расписание: {e}")
        return {}

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отъебись.")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    today_str = datetime.now().strftime("%Y-%m-%d")
    message = schedule.get(today_str, "Сегодня график не задан")
    await update.message.reply_text(f"📅 Сегодня: {message}")

async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    message = schedule.get(tomorrow_str, "На завтра график не задан")
    await update.message.reply_text(f"📅 Завтра: {message}")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# --- Веб-сервер ---
async def handle(request):
    try:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.initialize()
        await app.process_update(update)
        return web.Response(text="ok")
    except Exception as e:
        logging.error(f"Ошибка обработки запроса: {e}")
        return web.Response(status=500, text="error")

# --- Запуск ---
async def main():
    global app
    logging.info("🚀 Бот запускается через вебхук...")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("tomorrow", tomorrow))
    app.add_handler(CommandHandler("week", week))

    if WEBHOOK_URL:
        try:
            await app.bot.set_webhook(url=WEBHOOK_URL)
            logging.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
        except Exception as e:
            logging.error(f"Ошибка установки вебхука: {e}")

    aio_app = web.Application()
    aio_app.router.add_post(WEBHOOK_PATH, handle)

    # Вместо web.run_app
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, port=10000)
    await site.start()

    logging.info("🌐 Сервер слушает порт 10000")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())