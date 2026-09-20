from datetime import date, datetime

from telegram import Update
from telegram.ext import ContextTypes

from .poll_tracker import MSK, format_date_ru, get_store

SHOW_NEXT = 3  # сколько ближайших игр показывать


def plural_days(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} дня"
    return f"{n} дней"


def when_text(day: date, today: date) -> str:
    left = (day - today).days
    if left == 0:
        return "сегодня"
    if left == 1:
        return "завтра"
    return f"через {plural_days(left)}"


def describe(dates: list, today: date) -> str:
    """dates: отсортированные будущие даты игр (ГГГГ-ММ-ДД). Пустой список — игр в планах нет."""
    if not dates:
        return "Ближайшей игры в планах нет. Запусти /kogda_dnd, выберем дату."

    first = date.fromisoformat(dates[0])
    if first == today:
        text = f"Игра сегодня, {format_date_ru(dates[0])}! Собирайтесь 🎲"
    else:
        text = f"Ближайшая игра: {format_date_ru(dates[0])}, {when_text(first, today)} 🎲"

    later = [f"{format_date_ru(d)} ({when_text(date.fromisoformat(d), today)})" for d in dates[1:1 + SHOW_NEXT - 1]]
    if later:
        text += "\nПотом: " + ", ".join(later)
    return text


async def skoro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await get_store().read()
    today = datetime.now(MSK).date()
    chat_id = update.effective_chat.id
    dates = sorted(
        {e["date"] for e in data.get("events", {}).values()
         if e["chat_id"] == chat_id and date.fromisoformat(e["date"]) >= today}
    )
    await update.message.reply_text(describe(dates, today))
