from telegram import Update
from telegram.ext import ContextTypes
import requests
from datetime import datetime

SCHEDULE_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/setefed.json"  # твой json

async def kogda_strad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get(SCHEDULE_URL)
        response.raise_for_status()
        data = response.json()  # {"2025-07-24": "+", ...}

        today_str = datetime.now().strftime("%Y-%m-%d")
        value = data.get(today_str, "Нет данных на сегодня")
        text = f"{today_str} — {value}"

        await update.message.reply_text(text)

    except Exception as e:
        await update.message.reply_text(f"Ошибка загрузки расписания: {e}")