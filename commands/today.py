import httpx
import json
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

RAW_JSON_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/setefed.json"

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with httpx.AsyncClient() as client:
        r = await client.get(RAW_JSON_URL)
        if r.status_code != 200:
            await update.message.reply_text(f"Ошибка загрузки: {r.status_code}")
            return
        try:
            schedule = json.loads(r.content.decode("utf-8"))
        except Exception:
            await update.message.reply_text("Ошибка чтения файла")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        message = schedule.get(today_str, "Сегодня график не задан")
        await update.message.reply_text(f"Сегодня: {message}")