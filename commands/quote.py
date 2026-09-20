import html
import logging
import random
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from poll_store import create_store

QUOTES_PATH = "state/quotes.json"
MSK = timezone(timedelta(hours=3))
MAX_QUOTE_LENGTH = 1000
MAX_QUOTES_PER_CHAT = 1500
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
        quotes = data.setdefault("chats", {}).setdefault(chat_key, [])
        if any(q["message_id"] == quote["message_id"] for q in quotes):
            outcome["result"] = "duplicate"
        elif len(quotes) >= MAX_QUOTES_PER_CHAT:
            outcome["result"] = "full"
        else:
            quotes.append(quote)
            outcome.update(result="saved", number=len(quotes))

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
    await update.message.reply_text(format_quote(quotes[index], index + 1), parse_mode=ParseMode.HTML)


async def quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    replied = update.message.reply_to_message
    # в форумах ответ «в никуда» приходит как реплай на служебное сообщение о создании темы
    if replied and not replied.forum_topic_created:
        await save_quote(update, replied)
    else:
        await random_quote(update)
