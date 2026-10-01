import calendar
import logging
import time
from datetime import date

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from telegram.ext.filters import MessageFilter

from utils import get_user_role, mention_html
from . import upd as U
from .skoro import plural_days
from .vlas_schedule import (
    BUSY, FILE_ROLE, FREE, effective_status, entry_comment, format_day, today_utc, write_changes,
)

ALLOWED_ROLE = "setefed"  # команда только для этой роли
DENIED_TEXT = "Эта команда только для роли setefed, тебе сюда нельзя."
PREFIX = "v"
PICKER_TEXT = "В каком месяце меняем?"
COMMENT_MAX = 200
PENDING_TTL = 30 * 60  # сколько секунд бот ждёт комментарий
_now = time.monotonic

# Ждём комментарий: (chat_id, id сообщения-запроса) -> {owner, day, calendar_message_id, key, current, initial, created}.
# Хранится в памяти: ждать комментарий приходится секунды, а при перезапуске бота остаётся кнопка «Отмена».
PENDING = {}

USAGE_TEXT = (
    "Просто напиши /vlasuka без параметров, и я покажу кнопки: выбираешь месяц, жмёшь ✅ и ❌ по дням, "
    "а «💬 Добавить комментарий» пришьёт к нужному дню текст.\n\n"
    "Текстом тоже можно:\n"
    "/vlasuka 8-1 свободен, 8-2 болею, 8-4 +\n"
    "или чтобы заполнить месяц целиком:\n"
    "/vlasuka 8 в отпуске\n"
    "\n+ и - ставят статус (свободен и занят), любые другие слова уходят в комментарий к дню."
)


def cb(*parts) -> str:
    return U.cb(*parts, prefix=PREFIX)


def is_allowed(user_id) -> bool:
    roles = get_user_role(str(user_id))
    roles = [roles] if isinstance(roles, str) else (roles or [])
    return ALLOWED_ROLE in roles


# ---------------------------------------------------------------- экраны

def calendar_text(year: int, month: int, note: str = "") -> str:
    text = f"Меняй что нужно ({U.MONTHS_NOMINATIVE[month - 1]} {year})\n{U.CHECK} свободен, {U.CROSS} занят"
    return f"{note}\n\n{text}" if note else text


def calendar_markup(owner: int, year: int, month: int, current: int, initial: int, today: date) -> InlineKeyboardMarkup:
    key = U.month_key(year, month)
    comment_row = [InlineKeyboardButton(
        "💬 Добавить комментарий", callback_data=cb("c", owner, key, f"{current:x}", f"{initial:x}")
    )]
    return U.days_markup(owner, year, month, current, initial, today, prefix=PREFIX, extra_rows=[comment_row])


def mask_from_days(days) -> int:
    return sum(1 << (d - 1) for d in days)


def days_from_mask(mask: int, candidates: list) -> list:
    return [d for d in candidates if mask & (1 << (d - 1))]


def to_dative(n: int) -> str:
    """'дню' для одного дня, 'дням' для нескольких (после предлога «к»)."""
    return "дню" if n % 10 == 1 and n % 100 != 11 else "дням"


def comment_picker_text(year: int, month: int, selected: int, total: int) -> str:
    count = bin(selected).count("1")
    return (
        f"Выбери дни, к которым нужен один и тот же комментарий ({U.MONTHS_NOMINATIVE[month - 1]} {year}).\n"
        f"💬 — комментарий уже есть, ✅ — выбран для записи.\nВыбрано: {count} из {total}."
    )


def comment_picker_markup(
    owner: int, year: int, month: int, current: int, initial: int, today: date, commented: int, selected: int
) -> InlineKeyboardMarkup:
    key = U.month_key(year, month)
    hexes = f"{current:x}", f"{initial:x}"

    def day_button(day):
        bit = 1 << (day - 1)
        label = ("✅" if selected & bit else "") + str(day) + ("💬" if commented & bit else "")
        return InlineKeyboardButton(label, callback_data=cb("p", owner, key, *hexes, f"{selected:x}", f"{commented:x}", day))

    rows = U.calendar_rows(year, month, set(U.editable_days(year, month, today)), day_button, f"{PREFIX}|n")
    footer = []
    if selected:
        footer.append(InlineKeyboardButton(
            f"Написать комментарий ({bin(selected).count('1')})",
            callback_data=cb("w", owner, key, *hexes, f"{selected:x}", f"{commented:x}"),
        ))
    footer.append(InlineKeyboardButton("Назад", callback_data=cb("r", owner, key, *hexes)))
    rows.append(footer)
    return InlineKeyboardMarkup(rows)


def read_mask(schedule: dict, year: int, month: int, days: list) -> int:
    """Бит дня = 1 (✅), если он свободен. По умолчанию свободны все дни, ❌ только там, где отмечено «занят»."""
    return sum(1 << (d - 1) for d in days if effective_status(schedule.get(date(year, month, d).isoformat())) == FREE)


def commented_days(schedule: dict, year: int, month: int, days: list) -> set:
    return {d for d in days if entry_comment(schedule.get(date(year, month, d).isoformat()))}


async def load_current():
    """(ответ GitHub, график или None)."""
    async with U.make_client() as client:
        response, schedule, _ = await U.load_schedule(client, FILE_ROLE)
    return response, schedule


# ---------------------------------------------------------------- ожидание комментария

def prune_pending():
    limit = _now() - PENDING_TTL
    for key in [k for k, v in PENDING.items() if v["created"] < limit]:
        del PENDING[key]


def drop_pending(chat_id: int, calendar_message_id: int):
    """Забывает ожидание для этого календаря и возвращает id сообщения-запроса, чтобы его можно было удалить."""
    for key, value in list(PENDING.items()):
        if key[0] == chat_id and value["calendar_message_id"] == calendar_message_id:
            del PENDING[key]
            return key[1]
    return None


async def cleanup_pending(bot, chat_id: int, calendar_message_id: int):
    prompt_id = drop_pending(chat_id, calendar_message_id)
    if prompt_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=prompt_id)
        except Exception:
            pass


class PendingReply(MessageFilter):
    """Ответ владельца календаря на сообщение-запрос комментария. Чужие и обычные сообщения не перехватывает."""

    def filter(self, message) -> bool:
        replied = message.reply_to_message
        if not replied or not message.text or message.text.startswith("/") or not message.from_user:
            return False
        pending = PENDING.get((message.chat_id, replied.message_id))
        return bool(
            pending and message.from_user.id == pending["owner"] and _now() - pending["created"] < PENDING_TTL
        )


PENDING_REPLY = PendingReply()


def format_days_phrase(year: int, month: int, days: list) -> str:
    """Список дат для сообщения: все подряд, если их немного, иначе счёт и крайние даты."""
    labels = [format_day(date(year, month, d)) for d in days]
    if len(labels) <= 6:
        return ", ".join(labels)
    return f"{plural_days(len(labels))} ({labels[0]} — {labels[-1]})"


async def start_comment(query, context, owner: int, key: str, current: int, initial: int, days: list, today: date):
    year, month = U.parse_month_key(key)
    days = sorted(d for d in days if d in U.editable_days(year, month, today))
    if not days:
        await query.answer(U.STALE_TEXT, show_alert=True)
        return

    isos = [date(year, month, d).isoformat() for d in days]
    response, schedule = await load_current()
    if schedule is None:
        await query.answer(f"Не смог загрузить график ({response.status_code}), попробуй ещё раз", show_alert=True)
        return

    days_phrase = format_days_phrase(year, month, days)
    existing_count = sum(1 for iso in isos if entry_comment(schedule.get(iso)))
    lines = [f"{mention_html(query.from_user)}, напиши комментарий к {to_dative(len(days))}: {days_phrase} (до {COMMENT_MAX} символов)."]
    if existing_count:
        lines.append(f"У {existing_count} из {len(days)} уже есть комментарий, он будет заменён этим.")
    lines.append("Чтобы убрать комментарий везде, отправь минус.")

    chat_id = query.message.chat_id
    prompt = await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=ForceReply(selective=True, input_field_placeholder="Комментарий"),
    )
    prune_pending()
    PENDING[(chat_id, prompt.message_id)] = {
        "owner": owner, "isos": isos, "calendar_message_id": query.message.message_id,
        "key": key, "current": current, "initial": initial, "created": _now(),
    }
    await query.answer()
    cancel = InlineKeyboardMarkup([[InlineKeyboardButton(
        "Отмена", callback_data=cb("r", owner, key, f"{current:x}", f"{initial:x}")
    )]])
    await U.edit(
        query,
        f"✍️ Жду комментарий к {to_dative(len(days))}: {days_phrase}. Напиши его в ответ на сообщение ниже.",
        cancel,
    )


async def on_comment_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat_id
    prompt_id = message.reply_to_message.message_id
    pending = PENDING[(chat_id, prompt_id)]
    isos = pending["isos"]

    text = message.text.strip()
    if text in ("-", "—", "–"):
        comment = ""
    elif len(text) > COMMENT_MAX:
        await message.reply_text(f"Слишком длинно ({len(text)} из {COMMENT_MAX} символов), сократи и отправь ещё раз.")
        return
    else:
        comment = text

    stage, response = await write_changes({}, {iso: comment for iso in isos})
    if stage != "ok":
        logging.error(f"vlasuka: не удалось сохранить комментарий: {stage} {response.status_code} {response.text}")
        await message.reply_text(f"Не получилось сохранить ({response.status_code}). Отправь комментарий ещё раз.")
        return

    PENDING.pop((chat_id, prompt_id), None)
    for message_id in (prompt_id, message.message_id):        # чат не засоряем, если хватает прав
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    year, month = U.parse_month_key(pending["key"])
    days_phrase = format_days_phrase(year, month, sorted(date.fromisoformat(iso).day for iso in isos))
    note = f"💬 Комментарий к {to_dative(len(isos))}: {days_phrase} {'сохранён' if comment else 'убран'}."
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=pending["calendar_message_id"],
            text=calendar_text(year, month, note),
            reply_markup=calendar_markup(pending["owner"], year, month, pending["current"], pending["initial"], today_utc()),
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            await message.reply_text(note)
    except Exception:
        await message.reply_text(note)


# ---------------------------------------------------------------- кнопки

async def on_month_chosen(query, owner: int, key: str, today: date):
    year, month = U.parse_month_key(key)
    if (year, month) not in ((today.year, today.month), U.add_months(today.year, today.month, 1)):
        await query.answer(U.STALE_TEXT, show_alert=True)
        return

    response, schedule = await load_current()
    if schedule is None:
        await query.answer(f"Не смог загрузить график ({response.status_code}), попробуй ещё раз", show_alert=True)
        return

    initial = read_mask(schedule, year, month, U.editable_days(year, month, today))
    await query.answer()
    await U.edit(query, calendar_text(year, month), calendar_markup(owner, year, month, initial, initial, today))


async def render_comment_picker(query, owner: int, year: int, month: int, current: int, initial: int, today: date, commented: int, selected: int):
    await U.edit(
        query,
        comment_picker_text(year, month, selected, len(U.editable_days(year, month, today))),
        comment_picker_markup(owner, year, month, current, initial, today, commented, selected),
    )


async def on_comment_picker(query, owner: int, key: str, current: int, initial: int, today: date):
    year, month = U.parse_month_key(key)
    response, schedule = await load_current()
    if schedule is None:
        await query.answer(f"Не смог загрузить график ({response.status_code}), попробуй ещё раз", show_alert=True)
        return

    days = U.editable_days(year, month, today)
    commented = mask_from_days(commented_days(schedule, year, month, days))
    await query.answer()
    await render_comment_picker(query, owner, year, month, current, initial, today, commented, 0)


async def on_comment_toggle(query, owner: int, key: str, current: int, initial: int, selected: int, commented: int, day: int, today: date):
    year, month = U.parse_month_key(key)
    if day not in U.editable_days(year, month, today):
        await query.answer(U.STALE_TEXT, show_alert=True)
        return
    selected ^= 1 << (day - 1)
    await query.answer()
    await render_comment_picker(query, owner, year, month, current, initial, today, commented, selected)


async def on_comment_write(query, context, owner: int, key: str, current: int, initial: int, selected: int, today: date):
    year, month = U.parse_month_key(key)
    days = days_from_mask(selected, U.editable_days(year, month, today))
    if not days:
        await query.answer(U.STALE_TEXT, show_alert=True)
        return
    await start_comment(query, context, owner, key, current, initial, days, today)


async def on_save(query, owner: int, key: str, current: int, initial: int, today: date):
    year, month = U.parse_month_key(key)
    days = U.editable_days(year, month, today)
    changed = U.changed_days(current, initial, days)
    if not changed:
        await query.answer()
        await U.edit(query, "Статусы не менялись, писать нечего. Комментарии сохраняются сразу, так что они уже на месте.")
        return

    await query.answer("Сохраняю…")
    changes = {date(year, month, d).isoformat(): FREE if (current >> (d - 1)) & 1 else BUSY for d in changed}
    stage, response = await write_changes(changes, {})
    if stage != "ok":
        logging.error(f"vlasuka: не удалось сохранить график: {stage} {response.status_code} {response.text}")
        await U.edit(
            query,
            f"⚠️ Не удалось сохранить ({response.status_code}). Нажми «Сохранить» ещё раз.\n\n" + calendar_text(year, month),
            calendar_markup(owner, year, month, current, initial, today),
        )
        return

    free = [str(d) for d in changed if (current >> (d - 1)) & 1]
    busy = [str(d) for d in changed if not (current >> (d - 1)) & 1]
    lines = [f"Записал в график, {U.MONTHS_NOMINATIVE[month - 1]} {year}:"]
    if free:
        lines.append(f"{U.CHECK} свободен: {', '.join(free)}")
    if busy:
        lines.append(f"{U.CROSS} занят: {', '.join(busy)}")
    await U.edit(query, "\n".join(lines))


async def vlasuka_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split("|")
    try:
        action = parts[1]
        if action == "n":
            await query.answer()
            return
        owner = int(parts[2])
    except (IndexError, ValueError):
        await query.answer(U.STALE_TEXT, show_alert=True)
        return

    if query.from_user.id != owner:
        await query.answer("Это не твоя кнопка")
        return
    if not is_allowed(owner):                                   # например, роль отозвали, пока календарь был открыт
        await query.answer(DENIED_TEXT, show_alert=True)
        return

    today = today_utc()
    chat_id, message_id = query.message.chat_id, query.message.message_id
    try:
        if action == "x":
            await cleanup_pending(context.bot, chat_id, message_id)
            await query.answer()
            await U.edit(query, "Отменено")
        elif action == "b":
            await cleanup_pending(context.bot, chat_id, message_id)
            await query.answer()
            await U.edit(query, PICKER_TEXT, U.picker_markup(owner, today, PREFIX))
        elif action == "m":
            await on_month_chosen(query, owner, parts[3], today)
        elif action == "t":
            key, current, initial, day = parts[3], int(parts[4], 16), int(parts[5], 16), int(parts[6])
            year, month = U.parse_month_key(key)
            if day not in U.editable_days(year, month, today):
                await query.answer(U.STALE_TEXT, show_alert=True)
                return
            current ^= 1 << (day - 1)
            await query.answer()
            await U.edit(query, calendar_text(year, month), calendar_markup(owner, year, month, current, initial, today))
        elif action == "c":
            await on_comment_picker(query, owner, parts[3], int(parts[4], 16), int(parts[5], 16), today)
        elif action == "p":
            key, current, initial, selected, commented, day = (
                parts[3], int(parts[4], 16), int(parts[5], 16), int(parts[6], 16), int(parts[7], 16), int(parts[8])
            )
            await on_comment_toggle(query, owner, key, current, initial, selected, commented, day, today)
        elif action == "w":
            key, current, initial, selected = parts[3], int(parts[4], 16), int(parts[5], 16), int(parts[6], 16)
            await on_comment_write(query, context, owner, key, current, initial, selected, today)
        elif action == "r":
            key, current, initial = parts[3], int(parts[4], 16), int(parts[5], 16)
            year, month = U.parse_month_key(key)
            calendar.monthrange(year, month)                   # заодно проверяет, что месяц настоящий
            await cleanup_pending(context.bot, chat_id, message_id)
            await query.answer()
            await U.edit(query, calendar_text(year, month), calendar_markup(owner, year, month, current, initial, today))
        elif action == "s":
            await on_save(query, owner, parts[3], int(parts[4], 16), int(parts[5], 16), today)
        else:
            await query.answer(U.STALE_TEXT, show_alert=True)
    except (IndexError, ValueError):
        await query.answer(U.STALE_TEXT, show_alert=True)


# ---------------------------------------------------------------- старый текстовый формат

def parse_args(args):
    entries = []
    for part in " ".join(args).split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if len(tokens) >= 2:
            entries.append((tokens[0], " ".join(tokens[1:])))
        elif "-" in part and part[-1] in (FREE, BUSY):
            entries.append((part[:-1], part[-1]))
    return entries


async def vlasuka_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        status_changes, comment_changes, shown = {}, {}, []
        year = today_utc().year
        for date_token, text in parse_args(context.args):
            text = text.strip()
            if "-" in date_token:
                month, day = map(int, date_token.split("-"))
                days = [date(year, month, day)]
            else:
                month = int(date_token)
                days = [date(year, month, d) for d in range(1, calendar.monthrange(year, month)[1] + 1)]
            for day in days:
                target = status_changes if text in (FREE, BUSY) else comment_changes
                target[day.isoformat()] = text
                shown.append(f"{day.isoformat()} — {text}")
        if not shown:
            raise ValueError
    except Exception:
        await update.message.reply_text(USAGE_TEXT)
        return

    stage, response = await write_changes(status_changes, comment_changes)
    if stage == "load":
        await update.message.reply_text(f"Ошибка загрузки расписания ({response.status_code})")
    elif stage == "commit":
        await update.message.reply_text(f"Ошибка обновления: {response.status_code} {response.text}")
    else:
        await update.message.reply_text("Спасибо, внес в расписание:\n\n" + "\n".join(shown))


# ---------------------------------------------------------------- команда

async def vlasuka(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text(DENIED_TEXT)
        return
    if context.args:
        await vlasuka_from_text(update, context)
        return
    await update.message.reply_text(
        PICKER_TEXT, reply_markup=U.picker_markup(update.effective_user.id, today_utc(), PREFIX)
    )
