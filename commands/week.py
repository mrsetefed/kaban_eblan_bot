import httpx
import json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

RAW_JSON_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/setefed.json"

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        today = datetime.now()
        messages = []
        for i in range(7):
            date = today + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            pretty = date.strftime("%d.%m (%A)")
            text = schedule.get(date_str, "нет информации")
            messages.append(f"{pretty}: {text}")
        await update.message.reply_text(
            "Расписание на неделю:\n\n" + "\n".join(messages)
        )