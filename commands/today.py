import httpx
import json
from telegram import Update
from telegram.ext import ContextTypes

# Укажи свой путь к файлу
GITHUB_FILE_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/setefed.json"

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(GITHUB_FILE_URL, headers={"Cache-Control": "no-cache"})
            response.raise_for_status()
            schedule = response.json()
    except Exception as e:
        await update.message.reply_text(f"Ошибка загрузки файла: {e}")
        return

    if not schedule:
        await update.message.reply_text("Нет информации о графике.")
        return

    # Формируем красивый вывод
    result_lines = []
    for date, text in sorted(schedule.items()):
        result_lines.append(f"{date}: {text}")

    result = "\n".join(result_lines)
    await update.message.reply_text(f"Полный график:\n\n{result}")