import logging

from poll_store import PollStore, create_store

# Запоминает чаты, где бот видел хоть одно сообщение: нужно для /broadcast, чтобы знать, куда можно разослать.
STATE_PATH = "state/chats.json"

_store = None
_chats = {}  # chat_id (str) -> {"type": ..., "title": ...}


def get_store() -> PollStore:
    global _store
    if _store is None:
        _store = create_store(STATE_PATH)
    return _store


def all_chats() -> dict:
    return dict(_chats)


async def refresh_cache():
    _chats.clear()
    _chats.update((await get_store().read()).get("chats", {}))


async def remember(chat):
    if chat is None:
        return
    key = str(chat.id)
    info = {"type": chat.type, "title": chat.effective_name or key}
    if _chats.get(key) == info:
        return
    _chats[key] = info
    try:
        def save(data):
            data.setdefault("chats", {})[key] = info
        await get_store().mutate(save)
    except Exception:
        logging.exception("Не удалось сохранить чат")


async def track(update, context):
    """Отдельная группа обработчиков: срабатывает на каждое сообщение и не мешает командам."""
    try:
        await remember(update.effective_chat)
    except Exception:
        logging.exception("Ошибка запоминания чата")
