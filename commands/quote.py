import html
import logging
import random
import re
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from poll_store import create_store
from utils import get_user_role

QUOTES_PATH = "state/quotes.json"
MSK = timezone(timedelta(hours=3))
MAX_QUOTE_LENGTH = 1000
MAX_QUOTES_PER_CHAT = 1500
PRIVILEGED_ROLES = {"GM", "setefed"}  # эти роли могут удалять любые цитаты, остальные только свои
PREVIEW_LENGTH = 60
MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

_store = None


def get_store():
    global _store
    if _store is None:
        _store = create_store(QUOTES_PATH)
    return _store


def ensure_numbers(data: dict, chat_key: str) -> list:
    """Цитаты чата с постоянными номерами. Номер выдаётся один раз и после удаления не переиспользуется,
    поэтому номера остальных цитат не сдвигаются. Цитаты без номера (записаны старой версией) нумеруются по порядку."""
    quotes = data.setdefault("chats", {}).setdefault(chat_key, [])
    counters = data.setdefault("counters", {})
    last = max([q["number"] for q in quotes if "number" in q] + [counters.get(chat_key, 0)])
    for quote in quotes:
        if "number" not in quote:
            last += 1
            quote["number"] = last
    counters[chat_key] = last
    return quotes


def can_delete(user_id: int, quote: dict) -> bool:
    roles = get_user_role(str(user_id))
    roles = [roles] if isinstance(roles, str) else (roles or [])
    return quote.get("saved_by") == user_id or bool(PRIVILEGED_ROLES & set(roles))


def author_name(message) -> str:
    if message.from_user:
        return message.from_user.full_name
    if getattr(message, "sender_chat", None):
        return message.sender_chat.title or "Аноним"
    return "Аноним"


def format_quote(quote: dict, number: int) -> str:
    when = datetime.fromisoformat(quote["date"]).astimezone(MSK)
    return (
        f"📜 <b>Цитата №{number}</b>\n"
        f"«{html.escape(quote['text'])}»\n"
        f"— {html.escape(quote['author'])}, {when.day} {MONTHS_GENITIVE[when.month - 1]} {when.year}"
    )


async def save_quote(update: Update, replied):
    text = replied.text or replied.caption
    if not text:
        await update.message.reply_text("В цитатник можно сохранять только текст или подпись к картинке.")
        return
    if len(text) > MAX_QUOTE_LENGTH:
        await update.message.reply_text(f"Слишком длинно для цитаты (больше {MAX_QUOTE_LENGTH} символов).")
        return

    chat_key = str(update.effective_chat.id)
    quote = {
        "message_id": replied.message_id,
        "text": text,
        "author": author_name(replied),
        "date": replied.date.isoformat(),
        "saved_by": update.effective_user.id,
    }
    store = get_store()
    outcome = {}

    def add(data):
        quotes = ensure_numbers(data, chat_key)
        if any(q["message_id"] == quote["message_id"] for q in quotes):
            outcome["result"] = "duplicate"
        elif len(quotes) >= MAX_QUOTES_PER_CHAT:
            outcome["result"] = "full"
        else:
            data["counters"][chat_key] += 1
            quote["number"] = data["counters"][chat_key]
            quotes.append(quote)
            outcome.update(result="saved", number=quote["number"])

    try:
        await store.mutate(add)
    except Exception as e:
        logging.exception("Не удалось сохранить цитату")
        await update.message.reply_text(f"Не смог сохранить цитату: хранилище недоступно ({str(e)[:150]})")
        return

    if outcome["result"] == "duplicate":
        await update.message.reply_text("Эта цитата уже есть в цитатнике.")
    elif outcome["result"] == "full":
        await update.message.reply_text("Цитатник переполнен, больше не влезает.")
    else:
        await update.message.reply_text(
            f"Записал в цитатник (№{outcome['number']}): {author_name(replied)} 📜"
        )


async def random_quote(update: Update):
    try:
        data = await get_store().read()
    except Exception as e:
        logging.exception("Не удалось прочитать цитатник")
        await update.message.reply_text(f"Не смог открыть цитатник: хранилище недоступно ({str(e)[:150]})")
        return
    quotes = data.get("chats", {}).get(str(update.effective_chat.id), [])
    if not quotes:
        await update.message.reply_text(
            "Цитатник пуст. Ответь командой /quote на смешное сообщение, и я его запомню."
        )
        return
    index = random.randrange(len(quotes))
    number = quotes[index].get("number", index + 1)  # без номера бывают только цитаты старой версии, до первой записи
    await update.message.reply_text(format_quote(quotes[index], number), parse_mode=ParseMode.HTML)


UNQUOTE_USAGE = (
    "Напиши /unquote и номер цитаты, например /unquote 5. Номер стоит в заголовке цитаты («Цитата №5»)."
)


def parse_number(args):
    """'5', '№5' и '#5' дают 5. Всё остальное None."""
    match = re.fullmatch(r"[№#]?(\d{1,9})", "".join(args or []).strip())
    return int(match.group(1)) if match else None


async def unquote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет цитату по номеру. Удалить может тот, кто её добавил, а также GM и setefed."""
    number = parse_number(context.args)
    if number is None:
        await update.message.reply_text(UNQUOTE_USAGE)
        return

    chat_key = str(update.effective_chat.id)
    user_id = update.effective_user.id
    outcome = {}

    def remove(data):
        quotes = ensure_numbers(data, chat_key)
        target = next((q for q in quotes if q["number"] == number), None)
        if target is None:
            outcome["result"] = "missing"
        elif not can_delete(user_id, target):
            outcome["result"] = "denied"
        else:
            quotes.remove(target)
            outcome.update(result="deleted", text=target["text"])

    try:
        await get_store().mutate(remove)
    except Exception as e:
        logging.exception("Не удалось удалить цитату")
        await update.message.reply_text(f"Не смог удалить цитату: хранилище недоступно ({str(e)[:150]})")
        return

    if outcome["result"] == "missing":
        await update.message.reply_text(f"Цитаты №{number} нет. Номер смотри в заголовке цитаты («Цитата №…»).")
    elif outcome["result"] == "denied":
        await update.message.reply_text("Удалить цитату может только тот, кто её добавил, или GM.")
    else:
        text = outcome["text"]
        preview = text if len(text) <= PREVIEW_LENGTH else text[:PREVIEW_LENGTH].rstrip() + "…"
        await update.message.reply_text(f"Удалил цитату №{number}: «{preview}»")


async def quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    replied = update.message.reply_to_message
    # в форумах ответ «в никуда» приходит как реплай на служебное сообщение о создании темы
    if replied and not replied.forum_topic_created:
        await save_quote(update, replied)
    else:
        await random_quote(update)
