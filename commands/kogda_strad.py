from telegram import Update
from telegram.ext import ContextTypes
from utils import is_allowed, fetch_selected_json_schedules

ALLOWED_ROLE = "GM"
USERS_TO_CHECK = ["kiros", "nekit"]

async def kogda_strad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id, [ALLOWED_ROLE]):
        await update.message.reply_text("Ошибка: ты недостаточно крут. Проверь свою крутость /krutotest")
        return

    schedules = fetch_selected_json_schedules(USERS_TO_CHECK)
    if not schedules:
        await update.message.reply_text("Ошибка загрузки расписаний.")
        return

    shared_dates = set(schedules[USERS_TO_CHECK[0]].keys())
    for name in USERS_TO_CHECK[1:]:
        shared_dates &= set(schedules[name].keys())

    available_days = [date for date in sorted(shared_dates)
                      if all(schedules[user][date] == "+" for user in USERS_TO_CHECK)]

    if available_days:
        result = "\n".join(available_days)
        await update.message.reply_text(f"🎲 Возможные даты для Страда:\n{result}")
    else:
        await update.message.reply_text("В страде отказано. Нет подходящих дат")