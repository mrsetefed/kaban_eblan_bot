from telegram import Update
from telegram.ext import ContextTypes
from utils import is_allowed, fetch_selected_json_schedules
from .poll_tracker import send_date_polls

ALLOWED_ROLES = ["GM", "panda", "nekit", "kapo"]
USERS_TO_CHECK = ["nekit", "kaban", "panda", "hench", "kapo"]

async def kogda_kamputer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id, ALLOWED_ROLES):
        await update.message.reply_text("Ошибка: ты недостаточно крут. Проверь свою крутость /krutometr")
        return

    schedules = fetch_selected_json_schedules(USERS_TO_CHECK)
    missing = [name for name in USERS_TO_CHECK if name not in schedules]
    if missing:
        await update.message.reply_text(f"Ошибка загрузки расписаний: {', '.join(missing)}")
        return

    shared_dates = set(schedules[USERS_TO_CHECK[0]].keys())
    for name in USERS_TO_CHECK[1:]:
        shared_dates &= set(schedules[name].keys())

    available_days = [date for date in sorted(shared_dates)
                      if all(schedules[user][date] == "+" for user in USERS_TO_CHECK)]

    if available_days:
        # Преобразуем YYYY-MM-DD в DD
        options = [str(int(date.split("-")[2])) for date in available_days]
        # Удаляем дубликаты и сортируем
        options = sorted(set(options), key=int)

        await send_date_polls(update, options, USERS_TO_CHECK, "kogda_kamputer")
    else:
        await update.message.reply_text("А хуй вам, отказано. Дополнительных дат нет, играем как обычно")