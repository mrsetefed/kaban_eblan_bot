import logging

from telegram import MessageEntity, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from poll_store import PollStore, create_store
from utils import get_user_role, is_allowed, mention_html
from . import known_users

STATE_PATH = "state/moderation.json"
ALLOWED_ROLES = ["admin"]  # кто может банить и випить — та же роль, что управляет /media
DENIED_TEXT = "Банить и вип-ить может только админ."
USAGE = "Ответь командой на сообщение человека или напиши тег: /ban @ник"
NOT_FOUND_TEXT = (
    "Не смог узнать id {name}: он ещё ни разу не писал боту и не отвечал на голосования, а по тегу Telegram его не отдаёт.\n"
    "Пусть напишет что угодно боту или в чат с ним, тогда получится. Либо впиши его id вручную в state/users.json "
    "(см. username в USER_ROLES или спроси его самого)."
)

# роли в USER_ROLES, которые дают тот же эффект без команды — для совместимости со старым способом настройки
ENV_ROLES = {"ban": "ban", "vip": "vip"}

_store = None
_flags = {"ban": set(), "vip": set()}


def get_store() -> PollStore:
    global _store
    if _store is None:
        _store = create_store(STATE_PATH)
    return _store


def can_moderate(user_id) -> bool:
    return is_allowed(str(user_id), ALLOWED_ROLES)


def _has_env_role(user_id, role: str) -> bool:
    roles = get_user_role(str(user_id)) if user_id else None
    roles = [roles] if isinstance(roles, str) else (roles or [])
    return role in roles


def is_banned(user_id) -> bool:
    return bool(user_id) and (str(user_id) in _flags["ban"] or _has_env_role(user_id, ENV_ROLES["ban"]))


def is_vip(user_id) -> bool:
    return bool(user_id) and (str(user_id) in _flags["vip"] or _has_env_role(user_id, ENV_ROLES["vip"]))


async def refresh_cache():
    data = await get_store().read()
    _flags["ban"] = set(data.get("ban", []))
    _flags["vip"] = set(data.get("vip", []))


async def set_flag(user_id: int, flag: str, value: bool):
    uid = str(user_id)

    def change(data):
        ids = set(data.get(flag, []))
        if value:
            ids.add(uid)
        else:
            ids.discard(uid)
        data[flag] = sorted(ids)

    await get_store().mutate(change)
    if value:
        _flags[flag].add(uid)
    else:
        _flags[flag].discard(uid)


# ---------------------------------------------------------------- команды

async def resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(html-имя, id или None, username или None) цели по реплаю, текстовому тегу или @нику в аргументах."""
    message = update.message
    replied = message.reply_to_message
    if replied and replied.from_user and not replied.forum_topic_created:
        user = replied.from_user
        await known_users.remember(user)
        return mention_html(user), user.id, (user.username or "").lower() or None

    for entity, text in message.parse_entities([MessageEntity.TEXT_MENTION, MessageEntity.MENTION]).items():
        if entity.type == MessageEntity.TEXT_MENTION and entity.user:
            await known_users.remember(entity.user)
            return mention_html(entity.user), entity.user.id, (entity.user.username or "").lower() or None
        if entity.type == MessageEntity.MENTION:
            username = text.lstrip("@").lower()
            uid = await known_users.lookup_or_fetch(context.bot, username)
            return f"@{username}", uid, username

    if context.args:
        username = context.args[0].lstrip("@").lower()
        uid = await known_users.lookup_or_fetch(context.bot, username)
        return f"@{username}", uid, username
    return None


async def _toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, flag: str, value: bool, verb: str):
    if not can_moderate(update.effective_user.id):
        await update.message.reply_text(DENIED_TEXT)
        return

    target = await resolve_target(update, context)
    if not target:
        await update.message.reply_text(USAGE)
        return

    name, uid, _ = target
    if uid is None:
        await update.message.reply_text(NOT_FOUND_TEXT.format(name=name))
        return

    try:
        await set_flag(uid, flag, value)
    except Exception as e:
        logging.exception(f"Не удалось изменить флаг {flag}")
        await update.message.reply_text(f"Не смог сохранить: хранилище недоступно ({str(e)[:150]})")
        return

    await update.message.reply_text(f"{name} {verb}.", parse_mode=ParseMode.HTML)


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Банит человека: в /mog у него всегда худший результат, а на свои команды бота он получает только ')'."""
    await _toggle(update, context, "ban", True, "забанен: в /mog теперь всегда худший результат, команды бота ему больше не отвечают")


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _toggle(update, context, "ban", False, "разбанен")


async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Делает человека вип-ом: в /mog у него всегда 100%, в остальном бот работает с ним как обычно."""
    await _toggle(update, context, "vip", True, "вип: в /mog теперь всегда 100%")


async def unvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _toggle(update, context, "vip", False, "больше не вип")
