import os
import sys
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Получаем токен
try:
    TOKEN = os.environ["BOT_TOKEN"]
except KeyError:
    print("❌ BOT_TOKEN not found in environment", file=sys.stderr)
    sys.exit(1)

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отъебись.")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

# Сервер, чтобы Render не засыпал
async def handle(_):
    return web.Response(text="OK")

async def run():
    # Telegram Bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    await app.initialize()
    await app.start()

    # Aiohttp Webserver
    web_app = web.Application()
    web_app.router.add_get("/", handle)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, port=8080)
    await site.start()

    print("✅ Bot is running with keep-alive server")

    # Ждём бесконечно
    while True:
        await asyncio.sleep(3600)

# Запуск
if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(run())