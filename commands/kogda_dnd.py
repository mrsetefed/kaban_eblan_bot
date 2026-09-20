from datetime import date, datetime, timedelta, timezone
from telegram import Update
from telegram.ext import ContextTypes
from utils import is_allowed
from .poll_tracker import send_date_polls

ALLOWED_ROLE = "GM"
# Роли игроков в USER_ROLES: по ним бот находит telegram id, чтобы следить за голосованием и тегать
PLAYERS = ["kaban", "nekit", "ilya", "amir", "ksusha"]
MSK = timezone(timedelta(hours=3))

# Опорные даты для циклических правил. Это реальные календарные даты,
# от них считается разница в днях — работает в любом месяце и году.
NEKIT_FREE_ANCHOR = date(2026, 9, 20)    # первый из двух свободных дней подряд
KSUSHA_FREE_ANCHOR = date(2026, 9, 21)   # свободный день, дальше каждый 4-й


def is_kaban_free(d: date) -> bool:
    return True


def is_nekit_free(d: date) -> bool:
    # 2 дня свободен, 2 дня занят, по кругу
    return (d - NEKIT_FREE_ANCHOR).days % 4 in (0, 1)


def is_ilya_amir_free(d: date) -> bool:
    return d.weekday() not in (1, 3)  # вторник=1, четверг=3


def is_ksusha_free(d: date) -> bool:
    return (d - KSUSHA_FREE_ANCHOR).days % 4 == 0


def is_everyone_free(d: date) -> bool:
    return (
        is_kaban_free(d)
        and is_nekit_free(d)
        and is_ilya_amir_free(d)
        and is_ksusha_free(d)
    )


def free_dates_until_month_end(today: date) -> list[date]:
    next_month_first = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
    last_day = next_month_first - timedelta(days=1)
    days = (last_day - today).days + 1
    return [d for d in (today + timedelta(days=i) for i in range(days)) if is_everyone_free(d)]


async def kogda_dnd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id, [ALLOWED_ROLE]):
        await update.message.reply_text("Ошибка: ты недостаточно крут. Проверь свою крутость /krutometr")
        return

    available_days = free_dates_until_month_end(datetime.now(MSK).date())
    if not available_days:
        await update.message.reply_text("В этом месяце совпадающих свободных дат больше нет.")
        return

    options = [str(d.day) for d in available_days]

    await send_date_polls(update, options, PLAYERS, "kogda_dnd")
