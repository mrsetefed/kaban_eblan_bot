import os
import sys
import asyncio

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Получаем токен из переменной окружения
try:
    TOKEN = os.environ["BOT_TOKEN"]
except KeyError:
    print("❌ BOT_TOKEN not found in environment variables", file=sys.stderr)
    sys.exit(1)

# Расписание
MY_SCHEDULE = """
🗓 Мой график:

Понедельник — 12:00–20:00  
Вторник — выходной  
Среда — 8:00–16:00  
Четверг — 12:00–20:00  
Пятница — 12:00–18:00  
Суббота — по записи  
Воскресенье — выходной
"""

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отъебись.")

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MY_SCHEDULE)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

# -------------------------------
# 💡 Минимальный HTTP-сервер для Render
# -------------------------------
from aiohttp import web

async def handle(request):
    return web.Response(text="Bot is alive")

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()
# -------------------------------

# Запуск
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("schedule", schedule))
    app.add_handler(CommandHandler("ping", ping))

    # Запускаем всё в одном asyncio loop
    async def main():
        # Стартуем фейковый HTTP-сервер
        await run_web_server()
        # Запускаем бота
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        print("🤖 Бот запущен (polling + фейковый HTTP)!")

    asyncio.run(main())