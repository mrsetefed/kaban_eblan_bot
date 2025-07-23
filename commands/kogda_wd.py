from telegram import Update
from telegram.ext import ContextTypes
from utils import is_allowed, fetch_selected_json_schedules

ALLOWED_ROLE = "GM"
USERS_TO_CHECK = ["kaban", "nekit", "andrey"]

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

        MAX_OPTIONS = 10
        chunk_size = MAX_OPTIONS - 1

        for i in range(0, len(options), chunk_size):
            chunk = options[i:i + chunk_size]
            poll_options = ["Ничего не подходит"] + chunk
            await update.message.reply_poll(
                question="Когда играем?",
                options=poll_options,
                is_anonymous=False,
                allows_multiple_answers=True
            )
    else:
        await update.message.reply_text("В поиграть отказано. Нет подходящих дат")