from telegram import Update
from telegram.ext import ContextTypes
from utils import is_allowed, fetch_selected_json_schedules
from .poll_tracker import send_date_polls

ALLOWED_ROLE = "GM"
USERS_TO_CHECK = ["kaban", "nekit", "andrey", "hench", "kiros"]

async def kogda_wd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id, [ALLOWED_ROLE]):
        await update.message.reply_text("Ошибка: ты недостаточно крут. Проверь свою крутость /krutometr")
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
        # Преобразуем YYYY-MM-DD в DD
        options = [str(int(date.split("-")[2])) for date in available_days]
        # Удаляем дубликаты и сортируем
        options = sorted(set(options), key=int)

        option_dates = {}
        for day in available_days:
            option_dates.setdefault(str(int(day.split("-")[2])), day)
        await send_date_polls(update, options, USERS_TO_CHECK, "kogda_wd", option_dates)
    else:
        await update.message.reply_text("В поиграть отказано. Нет подходящих дат")