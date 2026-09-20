from datetime import date, datetime, timedelta, timezone
from telegram import Update
from telegram.ext import ContextTypes
from utils import is_allowed
from .poll_tracker import send_date_polls

ALLOWED_ROLE = "GM"
# Роли игроков в USER_ROLES: по ним бот находит telegram id, чтобы следить за голосованием и тегать
PLAYERS = ["kaban", "nekit", "ilya", "amir", "ksusha"]
MSK = timezone(timedelta(hours=3))
NEXT_MONTH_TEXT = "Месяц заканчивается, вот на следующий. Давайте сразу решим"
MONTHS_NOMINATIVE = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

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


def month_bounds(day: date) -> tuple[date, date]:
    """Первый и последний день месяца, в котором лежит day."""
    first = day.replace(day=1)
    next_first = date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)
    return first, next_first - timedelta(days=1)


def is_last_week_of_month(today: date) -> bool:
    """Последние 7 дней месяца (а не календарная неделя): сегодня и ещё не более 6 дней впереди."""
    return (month_bounds(today)[1] - today).days < 7


def free_dates_between(first: date, last: date) -> list[date]:
    """Дни от first до last включительно, когда свободны все игроки."""
    return [d for d in (first + timedelta(days=i) for i in range((last - first).days + 1)) if is_everyone_free(d)]


def free_dates_until_month_end(today: date) -> list[date]:
    return free_dates_between(today, month_bounds(today)[1])


async def send_month_polls(
    update: Update, dates: list[date], no_dates_text: str, month_note: str = None, track: bool = True
):
    """Опросы по свободным датам или сообщение, что дат нет. track=False: без проверки и напоминаний."""
    if not dates:
        await update.message.reply_text(no_dates_text)
        return
    options = [str(d.day) for d in dates]
    option_dates = {str(d.day): d.isoformat() for d in dates}
    await send_date_polls(update, options, PLAYERS, "kogda_dnd", option_dates, month_note, track)


async def kogda_dnd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_allowed(user_id, [ALLOWED_ROLE]):
        await update.message.reply_text("Ошибка: ты недостаточно крут. Проверь свою крутость /krutometr")
        return

    today = datetime.now(MSK).date()
    this_month_dates = free_dates_until_month_end(today)

    if not is_last_week_of_month(today):
        await send_month_polls(update, this_month_dates, "В этом месяце совпадающих свободных дат больше нет.")
        return

    # Месяц скоро кончится: сначала итог по нему, потом сразу следующий месяц, чтобы не ждать 1-го числа.
    # Проверка голосования и напоминания идут только для следующего месяца: до конца этого остаются считанные дни.
    # В вопросе указан месяц, потому что в вариантах только числа.
    await send_month_polls(
        update, this_month_dates, "В этом месяце совпадающих свободных дат больше нет.",
        MONTHS_NOMINATIVE[today.month - 1], track=False,
    )
    await update.message.reply_text(NEXT_MONTH_TEXT)

    next_first = month_bounds(today)[1] + timedelta(days=1)
    next_dates = free_dates_between(next_first, month_bounds(next_first)[1])
    await send_month_polls(
        update, next_dates, "В следующем месяце совпадающих свободных дат нет.", MONTHS_NOMINATIVE[next_first.month - 1]
    )
