from telegram import Update
from telegram.ext import ContextTypes
from utils import fetch_all_json_schedules, is_allowed

ALLOWED_ROLES = ["GM"]
USERS_TO_COMPARE = ["kiros", "nekit"]

async def kogda_strad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_allowed(user_id, ALLOWED_ROLES):
        await update.message.reply_text("Ты недостаточно крут.")
        return

    schedules = fetch_all_json_schedules()
    
    if not all(user in schedules for user in USERS_TO_COMPARE):
        await update.message.reply_text("Не удалось загрузить все расписания.")
        return

    kiros_days = schedules["kiros"]
    nekit_days = schedules["nekit"]

    matching_days = []
    for date, value in kiros_days.items():
        if value == "+" and nekit_days.get(date) == "+":
            matching_days.append(date)

    if matching_days:
        message = "📅 Совпадающие даты:\n" + "\n".join(sorted(matching_days))
    else:
        message = "😞 Нет совпадающих дат."

    await update.message.reply_text(message)