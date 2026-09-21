import logging
import re
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes
from telegram.ext.filters import MessageFilter

from utils import get_user_role
from . import media_store
from .krutometr import BANDS, band_folder_name
from .media_store import media_kind

ALLOWED_ROLES = {"GM", "setefed"}
DENIED_TEXT = "Наполнять медиа может только GM."
PENDING_MINUTES = 15  # сколько бот ждёт медиа после выбора блока

# блок -> подпись. У крутометра дальше выбирается диапазон.
CATEGORIES = [
    ("krutometr", "Крутометр"),
    ("taro", "Сова в /taro"),
    ("six_seven", "Ответ на 67"),
]
TITLES = dict(CATEGORIES)
URL_RE = re.compile(r"https?://\S+")
NOT_DIRECT_LINK = "Нужна прямая ссылка на файл: она заканчивается на .gif, .mp4, .jpg, .jpeg или .png. Страницы Tenor и Giphy не подойдут."

_pending = {}  # (чат, пользователь) -> {"key", "title", "until"}


def can_add(user_id: int) -> bool:
    roles = get_user_role(str(user_id))
    roles = [roles] if isinstance(roles, str) else (roles or [])
    return bool(ALLOWED_ROLES & set(roles))


def band_title(index: int) -> str:
    return band_folder_name(index)


def category_markup(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(title, callback_data=f"m|{uid}|c|{key}")] for key, title in CATEGORIES])


def band_markup(uid: int) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(band_title(i), callback_data=f"m|{uid}|b|{i}") for i in range(len(BANDS))]
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton("Любой результат", callback_data=f"m|{uid}|b|any")])
    return InlineKeyboardMarkup(rows)


def done_markup(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Готово", callback_data=f"m|{uid}|x")]])


def get_pending(chat_id: int, user_id: int):
    entry = _pending.get((chat_id, user_id))
    if entry and entry["until"] < time.monotonic():
        del _pending[(chat_id, user_id)]
        return None
    return entry


class PendingMedia(MessageFilter):
    """Сообщение с медиа или ссылкой от того, кто сейчас наполняет блок. Остальные сообщения проходят мимо."""

    def filter(self, message: Message) -> bool:
        user = message.from_user
        if not user or get_pending(message.chat_id, user.id) is None:
            return False
        if message.animation or message.photo or message.video:
            return True
        return bool(URL_RE.search(message.text or message.caption or ""))


PENDING_INPUT = PendingMedia()


async def media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открывает меню: в какой блок добавить медиа. Дальше бот принимает фото, гифки, видео и прямые ссылки."""
    user = update.effective_user
    if not can_add(user.id):
        await update.message.reply_text(DENIED_TEXT)
        return
    _pending.pop((update.effective_chat.id, user.id), None)
    await update.message.reply_text("К какому блоку добавить медиа?", reply_markup=category_markup(user.id))


def start_waiting(chat_id: int, user_id: int, key: str, title: str):
    _pending[(chat_id, user_id)] = {"key": key, "title": title, "until": time.monotonic() + PENDING_MINUTES * 60}


async def media_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, uid, action, *rest = query.data.split("|")
    if query.from_user.id != int(uid):
        await query.answer("Это меню открыл другой человек", show_alert=True)
        return
    if not can_add(query.from_user.id):
        await query.answer(DENIED_TEXT, show_alert=True)
        return
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id

    if action == "c" and rest[0] == "krutometr":
        await query.edit_message_text("Для какого результата крутометра?", reply_markup=band_markup(user_id))
        return

    if action == "c" and rest[0] in TITLES:
        key, title = rest[0], TITLES[rest[0]]
    elif action == "b":
        band = rest[0]
        if band == "any":
            key, title = "krutometr/any", "Крутометр, любой результат"
        elif band.isdigit() and int(band) < len(BANDS):
            name = band_title(int(band))
            key, title = f"krutometr/{name}", f"Крутометр, результат {name}"
        else:
            return
    elif action == "x":
        entry = _pending.pop((chat_id, user_id), None)
        await query.edit_message_text(f"Готово. Блок «{entry['title']}» сохранён." if entry else "Готово.")
        return
    else:
        return

    start_waiting(chat_id, user_id, key, title)
    await query.edit_message_text(
        f"Блок: {title}.\nПрисылай сюда фото, гифки, видео или прямые ссылки на файлы (.gif, .mp4, .jpg, .png). "
        f"Когда закончишь, нажми «Готово». Если пауза больше {PENDING_MINUTES} минут, я перестану ждать.",
        reply_markup=done_markup(user_id),
    )


def extract_items(message: Message):
    """Что прислали: [(media, unique)] и [тексты ошибок для неподходящих ссылок]."""
    items, errors = [], []
    if message.animation:
        a = message.animation
        items.append((media_store.encode_tg("animation", a.file_id), a.file_unique_id))
    elif message.video:
        v = message.video
        items.append((media_store.encode_tg("video", v.file_id), v.file_unique_id))
    elif message.photo:
        p = message.photo[-1]  # последний размер самый большой
        items.append((media_store.encode_tg("photo", p.file_id), p.file_unique_id))

    for url in URL_RE.findall(message.text or message.caption or ""):
        url = url.rstrip(".,;)")
        if media_kind(url):
            items.append((url, url))
        else:
            errors.append(NOT_DIRECT_LINK)
    return items, list(dict.fromkeys(errors))


async def on_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    entry = get_pending(message.chat_id, message.from_user.id)
    if entry is None:
        return
    items, errors = extract_items(message)

    lines = []
    for media_value, unique in items:
        try:
            added, total = await media_store.add_item(entry["key"], media_value, unique, message.from_user.id)
        except Exception as e:
            logging.exception("Не удалось сохранить медиа")
            lines.append(f"Не смог сохранить: хранилище недоступно ({str(e)[:150]})")
            continue
        lines.append(f"✅ Добавил в «{entry['title']}». Всего через бота: {total}" if added else "Такое уже есть, второй раз не добавляю")
    lines.extend(errors)
    if lines:
        await message.reply_text("\n".join(lines), reply_markup=done_markup(message.from_user.id))
