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

from bot_commands import get_handlers

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
    logging.info("🌐 Сервер слушает порт 10000")
    web.run_app(aio_app, port=10000)

if __name__ == "__main__":
    asyncio.run(main())
