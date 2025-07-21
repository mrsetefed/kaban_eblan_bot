import os
import sys
import csv
import requests
import datetime

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Получаем токен из переменной окружения
try:
    TOKEN = os.environ["BOT_TOKEN"]
except KeyError:
    print("❌ BOT_TOKEN not found in environment variables", file=sys.stderr)
    sys.exit(1)

# Ссылка на raw CSV файл
CSV_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/main/schedule.csv"

# Загрузка расписания с GitHub
async def fetch_schedule():
    try:
        print("📥 Загружаем расписание...")
        response = requests.get(CSV_URL)
        response.encoding = "utf-8"
        lines = response.text.strip().splitlines()

        # Выводим первые строки для отладки
        for i, line in enumerate(lines[:3]):
            print(f"[CSV строка {i}]: {line}")

        reader = csv.DictReader(lines)
        schedule = {row["date"]: row["text"] for row in reader}
        print("✅ Расписание загружено.")
        return schedule

    except Exception as e:
        print(f"❌ Ошибка при загрузке расписания: {e}")
        return {}

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Бот работает.")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    print(f"📅 Сегодня: {today_str}")

    if today_str in schedule:
        await update.message.reply_text(f"📆 Сегодня: {schedule[today_str]}")
    else:
        await update.message.reply_text("📭 Сегодня график не задан.")

# Запуск
if __name__ == '__main__':
    print("🚀 Bot is running...")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("today", today))
    app.run_polling()