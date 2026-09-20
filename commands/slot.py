import logging
import random
import time

from telegram import Update
from telegram.constants import DiceEmoji
from telegram.ext import ContextTypes

# Минимальная пауза между спинами бота в одном чате. Нужна, чтобы при спаме 🎰 бот не упёрся в лимиты Telegram
# (в группах около 20 сообщений в минуту) и сам не засорял чат.
COOLDOWN_SECONDS = 4
# Шанс, что бот ответит на 🎰. Если не выпало, пауза не запускается: следующий 🎰 снова получает свой шанс.
SPIN_CHANCE = 0.4
_last_spin = {}


async def react(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кто-то отправил 🎰: бот крутит свой автомат в ответ."""
    message = update.message
    if message.from_user and message.from_user.is_bot:
        return  # не отвечаем другим ботам, чтобы не устроить бесконечную перекличку

    now = time.monotonic()
    chat_id = message.chat_id
    if now - _last_spin.get(chat_id, -COOLDOWN_SECONDS) < COOLDOWN_SECONDS:
        return
    if random.random() >= SPIN_CHANCE:
        return
    _last_spin[chat_id] = now

    try:
        await message.reply_dice(emoji=DiceEmoji.SLOT_MACHINE)
    except Exception:
        logging.exception("Не удалось отправить 🎰")
