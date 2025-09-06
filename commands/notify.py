import asyncio
import os
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

ALLOWED_ROLE = "GM"

reminders = {
    "wd": {},
    "strad": {}
}

# === Проверка роли GM ===
def is_gm(update: Update) -> bool:
    username = update.effective_user.username
    return username in GM_USERS

# === Парсер даты с автоподстановкой года ===
def parse_date(date_str: str) -> str:
    # Формат ДД-ММ
    try:
        date_obj = datetime.strptime(date_str, "%d-%m")
        date_obj = date_obj.replace(year=datetime.now().year)
        return date_obj.strftime("%Y-%m-%d")
    except ValueError:
        # Формат YYYY-MM-DD
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return date_obj.strftime("%Y-%m-%d")
        except ValueError:
            return None

# === Команды ===
async def set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id, [ALLOWED_ROLE]):
        await update.message.reply_text("Ошибка: ты недостаточно крут. Проверь свою крутость /krutometr")
        return
        
    if len(context.args) < 3:
        await update.message.reply_text("Формат: /set <wd|strad> <ДД-ММ или YYYY-MM-DD> <текст>")
        return

    folder = context.args[0].lower()
    if folder not in reminders:
        await update.message.reply_text("Ошибка: нужно указать wd или strad")
        return

    date_str = parse_date(context.args[1])
    if not date_str:
        await update.message.reply_text("Дата должна быть в формате ДД-ММ или YYYY-MM-DD")
        return

    text = " ".join(context.args[2:])
    chat_id = update.effective_chat.id

    reminders[folder][chat_id] = {"date": date_str, "text": text}
    await update.message.reply_text(f"Напоминание для {folder} на {date_str} установлено.")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id, [ALLOWED_ROLE]):
        await update.message.reply_text("Ошибка: ты недостаточно крут. Проверь свою крутость /krutometr")
        return
       
    if len(context.args) < 1:
        await update.message.reply_text("Формат: /remove <wd|strad>")
        return

    folder = context.args[0].lower()
    if folder not in reminders:
        await update.message.reply_text("Ошибка: нужно указать wd или strad")
        return

    chat_id = update.effective_chat.id
    if chat_id in reminders[folder]:
        del reminders[folder][chat_id]
        await update.message.reply_text(f"Напоминание в {folder} удалено.")
    else:
        await update.message.reply_text("Напоминания для этого чата нет.")

async def list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id, [ALLOWED_ROLE]):
        await update.message.reply_text("Ошибка: ты недостаточно крут. Проверь свою крутость /krutometr")
        return
       

    output = []
    for folder, chats in reminders.items():
        for cid, data in chats.items():
            output.append(f"{folder} | Chat {cid} → {data['date']}: {data['text']}")
    if output:
        await update.message.reply_text("\n".join(output))
    else:
        await update.message.reply_text("Напоминаний нет.")

# === Автопроверка ===
async def reminder_loop(application):
    while True:
        today_str = datetime.now().strftime("%Y-%m-%d")
        for folder in list(reminders.keys()):
            for chat_id, data in list(reminders[folder].items()):
                if data["date"] == today_str:
                    try:
                        await application.bot.send_message(chat_id=chat_id, text=f"📢 {data['text']}")
                    except Exception as e:
                        print(f"Ошибка отправки в чат {chat_id}: {e}")
                    del reminders[folder][chat_id]
        await asyncio.sleep(3600)  # проверка каждый час