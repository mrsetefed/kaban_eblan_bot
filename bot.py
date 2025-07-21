import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from aiohttp import web

TOKEN = os.environ["BOT_TOKEN"]
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_PATH = "/"  # путь, на который Telegram шлёт запросы

# Создаём бота
app = ApplicationBuilder().token(TOKEN).build()

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отъебись.")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ping", ping))

# Обработчик Telegram webhook-а
async def handle(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response(text="OK")

# aiohttp-приложение
aio_app = web.Application()
aio_app.add_routes([web.post(WEBHOOK_PATH, handle)])

# Установка вебхука
async def on_startup(app_):
    webhook_url = f"https://kaban-eblan-bot.onrender.com{WEBHOOK_PATH}"
    await app.bot.set_webhook(webhook_url)
    print(f"✅ Webhook установлен: {webhook_url}")

aio_app.on_startup.append(on_startup)

# Запуск
if __name__ == "__main__":
    print("🚀 Бот запускается через вебхук...")
    web.run_app(aio_app, port=PORT)