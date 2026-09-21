import logging

from telegram import Update
from telegram.ext import ContextTypes

from poll_store import PollStore, create_store

# Запоминаем, какому telegram id принадлежит @тег: в тексте команды (/mog @ник) id не приходит, а роль определяется по id.
# Пополняется сообщениями и голосами, которые видит бот, хранится в GitHub, поэтому переживает перезапуски.
STATE_PATH = "state/users.json"

_store = None
_ids = {}  # ник в нижнем регистре -> telegram id


def get_store() -> PollStore:
    global _store
    if _store is None:
        _store = create_store(STATE_PATH)
    return _store


def lookup(username):
    """telegram id по @тегу (регистр и @ не важны) или None, если этот человек боту пока не попадался."""
    return _ids.get((username or "").lstrip("@").lower()) or None


async def refresh_cache():
    """Подтягивает известных пользователей из своего файла и из голосований (там тоже сохраняются ники)."""
    _ids.clear()
    for uid, info in (await get_store().read()).get("users", {}).items():
        if info.get("username"):
            _ids[info["username"].lower()] = int(uid)
    try:
        from .poll_tracker import get_store as polls_store
        for uid, info in (await polls_store().read()).get("users", {}).items():
            if info.get("username"):
                _ids.setdefault(info["username"].lower(), int(uid))
    except Exception:
        logging.exception("Не удалось прочитать ники из голосований")


async def remember(user):
    """Запоминает ник пользователя. В хранилище пишет, только если ник новый или сменился."""
    if user is None or user.is_bot or not user.username:
        return
    name = user.username.lower()
    if _ids.get(name) == user.id:
        return
    _ids[name] = user.id
    try:
        def save(data):
            users = data.setdefault("users", {})
            users[str(user.id)] = {"username": user.username}
            # если ник раньше принадлежал другому id (ник сменили или передали), старую запись убираем
            for uid in [uid for uid, info in users.items() if uid != str(user.id) and (info.get("username") or "").lower() == name]:
                del users[uid]
        await get_store().mutate(save)
    except Exception:
        logging.exception("Не удалось сохранить ник пользователя")


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отдельная группа обработчиков: срабатывает на каждое сообщение и не мешает командам."""
    try:
        message = update.effective_message
        await remember(update.effective_user)
        if message and message.reply_to_message:
            await remember(message.reply_to_message.from_user)
    except Exception:
        logging.exception("Ошибка запоминания пользователя")
