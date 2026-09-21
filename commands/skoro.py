from datetime import date, datetime

from telegram import Update
from telegram.ext import ContextTypes

from .poll_tracker import GAME_TITLES, MSK, format_date_ru, get_store

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


def game_title(command: str) -> str:
    return GAME_TITLES.get(command, command or "Игра")


def upcoming_by_game(data: dict, today: date) -> dict:
    """{команда-игра: отсортированные будущие даты}. Игра одна на все чаты, поэтому смотрим события всех чатов."""
    games = {}
    for event in data.get("events", {}).values():
        if date.fromisoformat(event["date"]) >= today:
            games.setdefault(event.get("command", ""), set()).add(event["date"])
    return {game: sorted(dates) for game, dates in games.items()}


def describe_games(games: dict, today: date) -> str:
    if not games:
        return describe([], today)
    if len(games) == 1:
        return describe(next(iter(games.values())), today)  # одна игра: без названия, как раньше
    ordered = sorted(games.items(), key=lambda item: item[1][0])
    return "\n\n".join(f"{game_title(game)}:\n{describe(dates, today)}" for game, dates in ordered)


async def skoro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ближайшие игры. Одинаково в любом чате и в личке с ботом."""
    data = await get_store().read()
    today = datetime.now(MSK).date()
    await update.message.reply_text(describe_games(upcoming_by_game(data, today), today))
