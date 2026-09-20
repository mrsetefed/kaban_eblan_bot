import os
import sys
import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from commands.get_handlers import get_handlers
from commands.poll_tracker import handle_tick, process_due
from utils import fetch_schedule_json

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


# --- HTTP обработка запросов от Telegram ---
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


# --- Проверка голосований ---
DUE_CHECK_INTERVAL = 60  # секунд между проверками, пока бот не спит


async def tick(request):
    # внешний будильник (cron-job.org, GitHub Actions) будит бота и заодно запускает проверку
    await app.initialize()
    return await handle_tick(request, app.bot)


async def health(request):
    return web.Response(text="ok")


async def due_check_loop():
    while True:
        try:
            await app.initialize()
            await process_due(app.bot)
        except Exception:
            logging.exception("Ошибка фоновой проверки голосований")
        await asyncio.sleep(DUE_CHECK_INTERVAL)


async def start_background(aio_app):
    aio_app["due_check_loop"] = asyncio.create_task(due_check_loop())


async def stop_background(aio_app):
    aio_app["due_check_loop"].cancel()


# --- Ошибки в командах: пишем в лог и отвечаем, чтобы не было тишины ---
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Ошибка в обработчике", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Что-то сломалось, скинь ошибку кабану.")


# --- Основной запуск ---
async def main():
    global app
    logging.info("🚀 Бот запускается через вебхук...")

    app = ApplicationBuilder().token(TOKEN).build()

    for handler in get_handlers():
        app.add_handler(handler)
    app.add_error_handler(on_error)

    if WEBHOOK_URL:
        try:
            await app.bot.set_webhook(url=WEBHOOK_URL)
            logging.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
        except Exception as e:
            logging.error(f"Ошибка установки вебхука: {e}")


if __name__ == "__main__":
    # aiohttp-сервер
    aio_app = web.Application()
    aio_app.router.add_post(WEBHOOK_PATH, handle)
    aio_app.router.add_get("/tick", tick)
    aio_app.router.add_get("/health", health)
    aio_app.on_startup.append(start_background)
    aio_app.on_cleanup.append(stop_background)

    # Запуск
    asyncio.run(main())
    logging.info("🌐 Сервер слушает порт 10000")
    web.run_app(aio_app, port=10000)