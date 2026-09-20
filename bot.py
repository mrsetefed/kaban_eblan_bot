import os
import sys
import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from commands.get_handlers import get_handlers
from commands.jobs import process_all
from commands.poll_tracker import handle_tick
from poll_store import check_storage
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


# Какие события Telegram присылает боту. Задаём явно: если не указать, Telegram оставляет прежнюю настройку.
ALLOWED_UPDATES = ["message", "callback_query", "poll_answer"]


def describe_update(update: Update) -> str:
    """Что пришло боту, без текста сообщений: для диагностики в логах."""
    if update.poll_answer:
        return "poll_answer"
    if update.callback_query:
        return "callback_query"
    message = update.effective_message
    if not message:
        return "другое событие"
    if message.dice:
        kind = f"кубик {message.dice.emoji}"
    elif message.sticker:
        kind = f"стикер {message.sticker.emoji}"
    elif message.text:
        kind = "команда" if message.text.startswith("/") else "текст"
    else:
        kind = "прочее"
    return f"сообщение ({message.chat.type}): {kind}"


# --- HTTP обработка запросов от Telegram ---
async def handle(request):
    try:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        logging.info("Апдейт: %s", describe_update(update))
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
    return await handle_tick(request, app.bot, process_all)


async def health(request):
    return web.Response(text="ok")


async def due_check_loop():
    while True:
        try:
            await app.initialize()
            await process_all(app.bot)
        except Exception:
            logging.exception("Ошибка фоновой проверки голосований")
        await asyncio.sleep(DUE_CHECK_INTERVAL)


async def report_storage():
    # одна строка в логах при каждом запуске: сразу видно, работает ли запись состояния в GitHub
    logging.info(await check_storage())


async def start_background(aio_app):
    aio_app["storage_report"] = asyncio.create_task(report_storage())
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
            await app.bot.set_webhook(url=WEBHOOK_URL, allowed_updates=ALLOWED_UPDATES)
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