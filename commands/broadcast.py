import asyncio
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes
from telegram.ext.filters import MessageFilter

from utils import is_allowed
from . import known_chats

ALLOWED_ROLES = ["admin"]
DENIED_TEXT = "Рассылку может запускать только админ."
PRIVATE_ONLY_TEXT = "Рассылка доступна только в личке с ботом, чтобы её не увидели в общем чате."
PENDING_MINUTES = 15
TITLE_LIMIT = 40

_pending = {}   # user_id -> {"target": "all" | chat_id, "until": ...}
_ready = {}     # user_id -> Message, если /broadcast вызвали ответом на сообщение (контент уже готов)


def can_broadcast(user_id) -> bool:
    return is_allowed(str(user_id), ALLOWED_ROLES)


def resolve_targets(target: str) -> list:
    chats = known_chats.all_chats()
    if target == "all":
        return [int(cid) for cid, info in chats.items() if info.get("type") != ChatType.PRIVATE]
    return [int(target)]


def targets_markup(uid: int) -> InlineKeyboardMarkup:
    chats = known_chats.all_chats()
    others = [(cid, info) for cid, info in chats.items() if cid != str(uid)]
    groups = [c for c in others if c[1].get("type") != ChatType.PRIVATE]
    rows = [[InlineKeyboardButton(f"Во все чаты ({len(groups)})", callback_data=f"bc|{uid}|all")]]
    for cid, info in sorted(others, key=lambda item: item[1].get("title", "")):
        label = (info.get("title") or cid)[:TITLE_LIMIT]
        rows.append([InlineKeyboardButton(label, callback_data=f"bc|{uid}|{cid}")])
    rows.append([InlineKeyboardButton("Отмена", callback_data=f"bc|{uid}|x")])
    return InlineKeyboardMarkup(rows)


async def send_broadcast(source_message, target_ids: list) -> str:
    """Копирует source_message в каждый чат (без пометки «переслано»). Возвращает итог для админа."""
    ok, failed = 0, []
    for chat_id in target_ids:
        try:
            await source_message.copy(chat_id)
            ok += 1
        except Exception as e:
            failed.append((chat_id, str(e)[:80]))
            logging.warning(f"Рассылка: не удалось отправить в {chat_id}: {e}")
        await asyncio.sleep(0.05)   # не превышать лимиты Telegram (~30 сообщений в секунду)

    text = f"Готово: доставлено в {ok} из {len(target_ids)}."
    if failed:
        text += "\nНе доставлено: " + ", ".join(str(cid) for cid, _ in failed[:10])
        if len(failed) > 10:
            text += f" и ещё {len(failed) - 10}"
    return text


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает меню «куда разослать». Ответ на сообщение сразу готовит его как содержимое рассылки."""
    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text(PRIVATE_ONLY_TEXT)
        return
    if not can_broadcast(update.effective_user.id):
        await update.message.reply_text(DENIED_TEXT)
        return

    uid = update.effective_user.id
    replied = update.message.reply_to_message
    if replied:
        _ready[uid] = replied
        note = " Содержимое уже готово — из сообщения, на которое ты ответил."
    else:
        _ready.pop(uid, None)
        note = ""
    await update.message.reply_text(f"Куда разослать?{note}", reply_markup=targets_markup(uid))


def get_pending(uid: int):
    entry = _pending.get(uid)
    if entry and entry["until"] < time.monotonic():
        del _pending[uid]
        return None
    return entry


class PendingBroadcast(MessageFilter):
    """Сообщение в личке от админа, который только что выбрал, куда рассылать, и теперь присылает содержимое."""

    def filter(self, message) -> bool:
        user = message.from_user
        return bool(user and message.chat.type == ChatType.PRIVATE and get_pending(user.id))


PENDING_INPUT = PendingBroadcast()


async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, uid_text, target = (query.data or "").split("|", 2)
    uid = int(uid_text)
    if query.from_user.id != uid:
        await query.answer("Это не твоя кнопка", show_alert=True)
        return
    if not can_broadcast(uid):
        await query.answer(DENIED_TEXT, show_alert=True)
        return

    if target == "x":
        _ready.pop(uid, None)
        _pending.pop(uid, None)
        await query.answer()
        await query.edit_message_text("Отменено.")
        return

    await query.answer()
    ids = resolve_targets(target)
    if not ids:
        _ready.pop(uid, None)
        await query.edit_message_text("Чатов для рассылки нет — бот пока нигде не отмечен.")
        return

    ready = _ready.pop(uid, None)
    if ready is not None:
        await query.edit_message_text(f"Рассылаю в {len(ids)} чат(ов)…")
        text = await send_broadcast(ready, ids)
        await context.bot.send_message(chat_id=uid, text=text)
        return

    _pending[uid] = {"target": target, "until": time.monotonic() + PENDING_MINUTES * 60}
    label = "во все чаты" if target == "all" else "в этот чат"
    await query.edit_message_text(
        f"Пришли следующим сообщением то, что разослать {label} — текст, фото, гифку, что угодно. "
        f"Если пауза больше {PENDING_MINUTES} минут, я перестану ждать."
    )


async def on_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    entry = get_pending(message.from_user.id)
    if entry is None:
        return
    _pending.pop(message.from_user.id, None)

    ids = resolve_targets(entry["target"])
    if not ids:
        await message.reply_text("Чатов для рассылки нет — бот пока нигде не отмечен.")
        return
    status = await message.reply_text(f"Рассылаю в {len(ids)} чат(ов)…")
    text = await send_broadcast(message, ids)
    try:
        await status.edit_text(text)
    except Exception:
        await message.reply_text(text)
