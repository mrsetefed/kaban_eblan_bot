import os
import sys

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

# Запуск
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("schedule", schedule))
    app.add_handler(CommandHandler("ping", ping))
    app.run_polling()
