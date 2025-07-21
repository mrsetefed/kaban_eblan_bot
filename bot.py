import os
import sys
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Получаем токен
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    print("❌ BOT_TOKEN not found in environment variables", file=sys.stderr)
    sys.exit(1)

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://kaban-eblan-bot.onrender.com{WEBHOOK_PATH}"

# Создаем app
app = ApplicationBuilder().token(TOKEN).build()

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("👉 /start получен")
    await update.message.reply_text("Бот на связи!")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("👉 /ping получен")
    await update.message.reply_text("pong")

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ping", ping))

# Webhook handler
async def handle(request):
    try:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
    except Exception as e:
        print("❌ Ошибка в webhook handler:", e)
    return web.Response()

# aiohttp-приложение
aio_app = web.Application()
aio_app.add_routes([web.post(WEBHOOK_PATH, handle)])

# Главный запуск
async def main():
    print("🚀 Бот запускается через вебхук...")
    await app.initialize()
    await app.bot.set_webhook(url=WEBHOOK_URL)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()
    print(f"✅ Webhook установлен: {WEBHOOK_URL}")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())