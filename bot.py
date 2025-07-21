import os
import sys
import logging
import asyncio
from aiohttp import web
from telegram.ext import ApplicationBuilder, CommandHandler
from bot_commands import get_handlers

from commands import start, ping, today, tomorrow, week

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- Конфигурация ---
try:
    TOKEN = os.environ["BOT_TOKEN"]
except KeyError:
    print("\u274c BOT_TOKEN not found in environment variables", file=sys.stderr)
    sys.exit(1)

WEBHOOK_PATH = "/"
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

# --- Веб-сервер ---
async def handle(request):
    try:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.initialize()
        await app.process_update(update)
        return web.Response(text="ok")
    except Exception as e:
        logging.error(f"\u274c Ошибка обработки запроса: {e}")
        return web.Response(status=500, text="error")

# --- Запуск ---
async def main():
    global app
    logging.info("\ud83d\ude80 Бот запускается через вебхук...")

    app = ApplicationBuilder().token(TOKEN).build()
    for handler in get_handlers():
    app.add_handler(handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("tomorrow", tomorrow))
    app.add_handler(CommandHandler("week", week))

    if WEBHOOK_URL:
        try:
            await app.bot.set_webhook(url=WEBHOOK_URL)
            logging.info(f"\u2705 Webhook установлен: {WEBHOOK_URL}")
        except Exception as e:
            logging.error(f"\u274c Ошибка установки вебхука: {e}")

    aio_app = web.Application()
    aio_app.router.add_post(WEBHOOK_PATH, handle)
    logging.info("\ud83c\udf10 Сервер слушает порт 10000")
    web.run_app(aio_app, port=10000)

if __name__ == "__main__":
    asyncio.run(main())
