import logging
import random
import re
import time
from pathlib import Path

from telegram import Message, ReplyParameters, Update
from telegram.ext import ContextTypes
from telegram.ext.filters import MessageFilter

from . import media_store

KEY = "six_seven"  # блок в /media
LINKS_FILE = Path(__file__).resolve().parent.parent / "media" / "six_seven_links.txt"
STATIC_LINKS = media_store.load_links(LINKS_FILE)
FALLBACK_TEXT = "6️⃣7️⃣"  # если в блоке ещё нет ни одной гифки

# Пауза между ответами в одном чате, чтобы бот не засорял переписку, если 67 повторяют подряд
COOLDOWN_SECONDS = 20
_last_reply = {}

# 67 где угодно в тексте (в том числе 167 или 5,67), а также 6 и 7 через любые знаки и пробелы (до трёх подряд):
# 6 7, 6-7, 6,7, 6/7, 6...7 и так далее. Плюс «шесть семь» и «six seven».
SIX_SEVEN_RE = re.compile(r"67|6[\W_]{0,3}7|шесть[\W_]{0,3}семь|six[\W_]{0,3}seven", re.IGNORECASE)


def is_six_seven(text) -> bool:
    return bool(text) and bool(SIX_SEVEN_RE.search(text))


class SixSevenMessage(MessageFilter):
    """Сообщение (подпись к картинке или цитата в ответе), где встречается 67 в любом написании."""

    def filter(self, message: Message) -> bool:
        # ответ с цитатой (quote) тоже считается: цитируют именно 67, а сам ответ может быть любым
        quote = getattr(message, "quote", None)
        return is_six_seven(message.text or message.caption) or bool(quote and is_six_seven(quote.text))


SIX_SEVEN_MESSAGE = SixSevenMessage()


def pool() -> list:
    return list(dict.fromkeys(STATIC_LINKS + media_store.stored(KEY)))


def quote_parameters(message):
    """Ответ с цитатой: в ответе Telegram подсвечивает само найденное «67», а не всё сообщение. None, если цитировать нечего
    (например, 67 нашлось только в цитате чужого ответа)."""
    text = getattr(message, "text", None) or getattr(message, "caption", None)
    match = SIX_SEVEN_RE.search(text) if text else None
    message_id = getattr(message, "message_id", None)
    if not match or message_id is None:
        return None
    # позиция цитаты задаётся в единицах UTF-16, как в Telegram (эмодзи занимают две)
    position = len(text[:match.start()].encode("utf-16-le")) // 2
    return ReplyParameters(message_id=message_id, quote=match.group(0), quote_position=position, allow_sending_without_reply=True)


async def send_reaction(message, reply_parameters=None):
    """Отвечает на сообщение случайной гифкой из блока 67. Если блок пуст или файл не отправился, отвечает текстом."""
    options = pool()
    if options:
        media = random.choice(options)
        # если Telegram не принял цитату (например, изменили текст), повторяем обычным ответом
        for params in ([reply_parameters, None] if reply_parameters is not None else [None]):
            try:
                await media_store.send_media(message, media, reply_parameters=params)
                return
            except Exception as e:
                logging.warning(f"Не удалось отправить гифку для 67 ({media[:60]}, цитата: {params is not None}): {e}")
    await message.reply_text(FALLBACK_TEXT)


async def react(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.from_user and message.from_user.is_bot:
        return  # другим ботам не отвечаем, чтобы не устроить бесконечную перекличку

    now = time.monotonic()
    if now - _last_reply.get(message.chat_id, -COOLDOWN_SECONDS) < COOLDOWN_SECONDS:
        return
    _last_reply[message.chat_id] = now
    await send_reaction(message, quote_parameters(message))
