import logging
import re
from datetime import date, datetime

from telegram import Update
from telegram.ext import ContextTypes

from utils import get_user_role
from .poll_tracker import MSK, format_date_ru, get_store, unpin_polls, utcnow
from .skoro import describe_games, game_title, upcoming_by_game

ALLOWED_ROLES = {"GM", "setefed"}
DENIED_TEXT = "Отменять игры и голосования может только GM."

# как можно назвать игру в команде
GAME_ALIASES = {
    "dnd": "kogda_dnd", "днд": "kogda_dnd",
    "kamputer": "kogda_kamputer", "кампутер": "kogda_kamputer",
    "wd": "kogda_wd", "вд": "kogda_wd",
    "strad": "kogda_strad", "страд": "kogda_strad",
}
USAGE = (
    "Отменить игру: /otmena 25 (ближайшее 25-е) или /otmena 25.09. Если игр несколько, добавь название: /otmena днд 25.\n"
    "Отменить идущее голосование: ответь командой /otmena на сообщение с опросом."
)

DATE_RE = re.compile(r"(\d{1,2})(?:[./](\d{1,2}))?")


def parse_args(args):
    """(команда-игра или None, день, месяц или None). None, если разобрать не удалось."""
    tokens = [t.lower() for t in args or []]
    game = None
    if tokens and tokens[0] in GAME_ALIASES:
        game = GAME_ALIASES[tokens.pop(0)]
    if len(tokens) != 1:
        return None
    match = DATE_RE.fullmatch(tokens[0])
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2)) if match.group(2) else None
    if not (1 <= day <= 31) or (month is not None and not 1 <= month <= 12):
        return None
    return game, day, month


def can_cancel(user_id: int) -> bool:
    roles = get_user_role(str(user_id))
    roles = [roles] if isinstance(roles, str) else (roles or [])
    return bool(ALLOWED_ROLES & set(roles))


def find_events(data: dict, today: date, game, day: int, month):
    """Будущие события, подходящие под запрос, от ближайшего: [(id, событие)]."""
    found = []
    for event_id, event in data.get("events", {}).items():
        when = date.fromisoformat(event["date"])
        if when < today or when.day != day or (month is not None and when.month != month):
            continue
        if game is not None and event.get("command") != game:
            continue
        found.append((event_id, event))
    return sorted(found, key=lambda item: item[1]["date"])


async def otmena(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет решённую дату игры (по дате) или идущее голосование (ответом на опрос)."""
    if not can_cancel(update.effective_user.id):
        await update.message.reply_text(DENIED_TEXT)
        return

    store = get_store()
    today = datetime.now(MSK).date()
    data = await store.read()
    replied = update.message.reply_to_message
    if replied is not None and not context.args:
        await cancel_poll(update, context, data, replied.message_id)
        return

    parsed = parse_args(context.args)
    if parsed is None:
        text = f"{USAGE}\n\n{describe_games(upcoming_by_game(data, today), today)}"
        active = active_groups(data, update.effective_chat.id)
        if active:
            text += "\n\nИдут голосования:\n" + "\n".join(f"• {describe_group(g)}" for _, g in active)
        await update.message.reply_text(text)
        return

    game, day, month = parsed
    found = find_events(data, today, game, day, month)
    if not found:
        await update.message.reply_text("Такой игры в планах нет. Что есть, покажет /skoro.")
        return

    nearest = found[0][1]["date"]
    same_day = [(event_id, event) for event_id, event in found if event["date"] == nearest]
    if len(same_day) > 1:
        titles = ", ".join(game_title(event.get("command", "")) for _, event in same_day)
        await update.message.reply_text(f"На эту дату несколько игр: {titles}. Напиши название, например /otmena днд {day}.")
        return

    event_id, event = same_day[0]

    def remove(current):
        current.get("events", {}).pop(event_id, None)

    try:
        await store.mutate(remove)
    except Exception as e:
        logging.exception("Не удалось отменить игру")
        await update.message.reply_text(f"Не смог отменить: хранилище недоступно ({str(e)[:150]})")
        return

    title, day_text = game_title(event.get("command", "")), format_date_ru(event["date"])
    await update.message.reply_text(f"Отменил игру {title}: {day_text}. Напоминания по ней больше не придут.")
    if event["chat_id"] != update.effective_chat.id:
        try:
            await context.bot.send_message(chat_id=event["chat_id"], text=f"Игра {title} {day_text} отменена.")
        except Exception:
            logging.warning(f"Не удалось сообщить об отмене в чат {event['chat_id']}")


def active_groups(data: dict, chat_id: int):
    return [(gid, g) for gid, g in data.get("groups", {}).items() if not g.get("done") and g["chat_id"] == chat_id]


def find_group_by_message(data: dict, chat_id: int, message_id: int):
    for gid, group in active_groups(data, chat_id):
        if any(p["message_id"] == message_id for p in group["polls"]):
            return gid, group
    return None, None


def describe_group(group: dict) -> str:
    created = datetime.fromisoformat(group["created_at"]).astimezone(MSK)
    voted = sum(1 for uid in group["participants"] if any(a.get(uid) for a in group["answers"].values()))
    return f"{game_title(group['command'])}, создан {created:%d.%m в %H:%M} по МСК, проголосовали {voted} из {len(group['participants'])}"


async def cancel_poll(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict, message_id: int):
    """Проверки и напоминания по голосованию прекращаются, опрос закрывается и откреплается."""
    chat_id = update.effective_chat.id
    gid, group = find_group_by_message(data, chat_id, message_id)
    if group is None:
        await update.message.reply_text("Это не отслеживаемый опрос (или он уже завершён). Что можно отменить, покажет /otmena без аргументов.")
        return

    def cancel(current):
        g = current["groups"][gid]
        g["done"], g["cancelled"], g["finished_at"] = True, True, utcnow().isoformat()

    try:
        await get_store().mutate(cancel)
    except Exception as e:
        logging.exception("Не удалось отменить голосование")
        await update.message.reply_text(f"Не смог отменить: хранилище недоступно ({str(e)[:150]})")
        return

    for poll in group["polls"]:
        try:
            await context.bot.stop_poll(chat_id=chat_id, message_id=poll["message_id"])
        except Exception as e:
            logging.warning(f"Не удалось закрыть опрос {poll['message_id']}: {e}")
    await unpin_polls(context.bot, group)
    await update.message.reply_text(f"Голосование отменено ({describe_group(group)}). Проверок и напоминаний по нему больше не будет.")
