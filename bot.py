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
    print("❌ BOT_TOKEN not found", file=sys.stderr)
    sys.exit(1)

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отъебись.")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

# Фейковый веб-сервер
async def keep_alive():
    async def handler(_):
        return web.Response(text="OK")
    app = web.Application()
    app.router.add_get("/", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=8080)
    await site.start()

# Запуск
async def main():
    await keep_alive()  # запускаем фейковый сервер
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    print("🚀 Bot is running...")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())