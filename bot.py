import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from aiohttp import web

TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_PATH = "/"  # Render по умолчанию прокидывает на /
PORT = int(os.environ.get("PORT", 8080))  # Render требует слушать этот порт

# Создаём бота
app = ApplicationBuilder().token(TOKEN).build()

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отъебись.")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ping", ping))

# Создаём aiohttp-приложение
aio_app = web.Application()
aio_app.add_routes([web.post(WEBHOOK_PATH, app.webhook_handler())])

# Устанавливаем вебхук на нужный URL (только при старте, если не установлен)
async def on_startup(app_: web.Application):
    webhook_url = f"https://kaban-eblan-bot.onrender.com{WEBHOOK_PATH}"
    await app.bot.set_webhook(webhook_url)
    print(f"✅ Webhook установлен: {webhook_url}")

aio_app.on_startup.append(on_startup)

# Запуск
if __name__ == '__main__':
    print("🚀 Bot is starting via webhook...")
    web.run_app(aio_app, port=PORT)