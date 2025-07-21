import os
import sys
import csv
import logging
from datetime import datetime, timedelta
from aiohttp import web
import requests
import asyncio

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes

from commands.get_handlers import get_handlers

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

# --- Глобальная переменная приложения ---
app = None

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

async def run_web_server(aio_app):
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=10000)
    await site.start()
    logging.info("🌐 Сервер слушает порт 10000")
    while True:
        await asyncio.sleep(3600)

# --- Запуск ---
async def main():
    global app
    logging.info("🚀 Бот запускается через вебхук...")

    app = ApplicationBuilder().token(TOKEN).build()

    for handler in get_handlers():
        app.add_handler(handler)

    if WEBHOOK_URL:
        try:
            await app.bot.set_webhook(url=WEBHOOK_URL)
            logging.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
        except Exception as e:
            logging.error(f"Ошибка установки вебхука: {e}")

    aio_app = web.Application()
    aio_app.router.add_post(WEBHOOK_PATH, handle)
    await run_web_server(aio_app)

if __name__ == "__main__":
    asyncio.run(main())