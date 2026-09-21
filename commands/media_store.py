import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from poll_store import PollStore, create_store

STATE_PATH = "state/media.json"
ANIMATION_EXT = {".gif", ".mp4"}
PHOTO_EXT = {".jpg", ".jpeg", ".png"}
TG_PREFIX = "tg:"  # медиа, присланное боту напрямую, хранится как «tg:вид:file_id»
TG_KINDS = {"animation", "photo", "video"}

_store = None
_cache = {}  # ключ блока -> список медиа (ссылки и tg:...); читается синхронно, обновляется при добавлении


def get_store() -> PollStore:
    global _store
    if _store is None:
        _store = create_store(STATE_PATH)
    return _store


def encode_tg(kind: str, file_id: str) -> str:
    return f"{TG_PREFIX}{kind}:{file_id}"


def media_kind(media: str):
    """'animation' / 'photo' / 'video' для медиа из чата или для прямой ссылки; None, если ссылка не подходит."""
    if media.startswith(TG_PREFIX):
        kind = media[len(TG_PREFIX):].split(":", 1)[0]
        return kind if kind in TG_KINDS else None
    parsed = urlparse(media)
    if parsed.scheme not in ("http", "https"):
        return None
    suffix = Path(parsed.path).suffix.lower()
    if suffix in ANIMATION_EXT:
        return "animation"
    if suffix in PHOTO_EXT:
        return "photo"
    return None


def media_source(media: str) -> str:
    """Что передавать Telegram: file_id или ссылку."""
    return media.split(":", 2)[2] if media.startswith(TG_PREFIX) else media


async def send_media(message, media: str, caption: str = None, parse_mode=None):
    """Отвечает на сообщение картинкой, гифкой или видео. Ошибку отправки не глотает: решает вызывающий."""
    source = media_source(media)
    kind = media_kind(media)
    if kind == "animation":
        return await message.reply_animation(animation=source, caption=caption, parse_mode=parse_mode)
    if kind == "video":
        return await message.reply_video(video=source, caption=caption, parse_mode=parse_mode)
    return await message.reply_photo(photo=source, caption=caption, parse_mode=parse_mode)


def load_links(path: Path) -> list:
    """Прямые ссылки на гифки или картинки из текстового файла (по одной на строку, # начинает комментарий)."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return []
    except Exception as e:
        logging.warning(f"Не удалось прочитать {path.name}: {e}")
        return []
    links = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if media_kind(line):
            links.append(line)
        else:
            logging.warning(f"{path.name}: ссылка пропущена (нужна прямая ссылка на .gif/.mp4/.jpg/.png): {line}")
    return list(dict.fromkeys(links))


def stored(key: str) -> list:
    """Медиа, добавленное через /media, для блока key."""
    return list(_cache.get(key, []))


def _remember(data: dict):
    _cache.clear()
    for key, items in data.get("items", {}).items():
        _cache[key] = [item["media"] for item in items]


async def refresh_cache():
    """Подтягивает сохранённое медиа из хранилища. Вызывается при старте бота."""
    _remember(await get_store().read())


async def add_item(key: str, media: str, unique: str, user_id: int):
    """Записывает медиа в блок. Возвращает (добавлено ли, сколько теперь в блоке). Повтор того же файла не добавляется."""
    result = {}

    def add(data):
        items = data.setdefault("items", {}).setdefault(key, [])
        result["added"] = all(item["unique"] != unique for item in items)
        if result["added"]:
            items.append({"media": media, "unique": unique, "by": user_id, "at": datetime.now(timezone.utc).isoformat()})
        result["total"] = len(items)

    await get_store().mutate(add)
    _remember(await get_store().read())
    return result["added"], result["total"]
