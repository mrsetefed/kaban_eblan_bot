import logging
import random
import time

from telegram import Message, Update
from telegram.constants import DiceEmoji
from telegram.ext import ContextTypes
from telegram.ext.filters import MessageFilter

SLOT = DiceEmoji.SLOT_MACHINE  # 🎰

# Минимальная пауза между спинами бота в одном чате. Нужна, чтобы при спаме 🎰 бот не упёрся в лимиты Telegram
# (в группах около 20 сообщений в минуту) и сам не засорял чат.
COOLDOWN_SECONDS = 4
# Шанс, что бот ответит на 🎰. Если не выпало, пауза не запускается: следующий 🎰 снова получает свой шанс.
SPIN_CHANCE = 0.4
_last_spin = {}


def is_slot_emoji(value) -> bool:
    """Клиенты иногда дописывают к эмодзи невидимый селектор U+FE0F, поэтому сравниваем без него."""
    return bool(value) and value.replace("️", "").strip() == SLOT


class SlotMessage(MessageFilter):
    """Сообщение, в котором прислали 🎰: анимированный кубик, стикер-эмодзи или просто текст. Пересланные не считаем."""

    def filter(self, message: Message) -> bool:
        if message.forward_origin:
            return False
        if message.dice:
            return is_slot_emoji(message.dice.emoji)
        if message.sticker:
            return is_slot_emoji(message.sticker.emoji)
        return is_slot_emoji(message.text)


SLOT_MESSAGE = SlotMessage()


async def react(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кто-то отправил 🎰: бот крутит свой автомат в ответ."""
    message = update.message
    if message.from_user and message.from_user.is_bot:
        return  # не отвечаем другим ботам, чтобы не устроить бесконечную перекличку

    now = time.monotonic()
    chat_id = message.chat_id
    if now - _last_spin.get(chat_id, -COOLDOWN_SECONDS) < COOLDOWN_SECONDS:
        logging.info("🎰 в чате %s: пауза, пропускаю", chat_id)
        return
    if random.random() >= SPIN_CHANCE:
        logging.info("🎰 в чате %s: шанс не выпал", chat_id)
        return
    _last_spin[chat_id] = now

    try:
        await message.reply_dice(emoji=SLOT)
        logging.info("🎰 в чате %s: ответил", chat_id)
    except Exception:
        logging.exception("Не удалось отправить 🎰")
