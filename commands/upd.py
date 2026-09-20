import base64
import calendar
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from utils import get_roles, get_user_role

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = "mrsetefed/kaban_eblan_bot"
SCHEDULES_BRANCH = "schedule"
SCHEDULES_PATH = "schedules"
SCHEDULE_ROLES = ["nekit", "kiros", "hench", "kaban", "andrey", "kapo", "panda"]  # чьи расписания можно менять
NOTIFY_ROLE = "setefed"  # кому в личку приходит «X обновил расписание»

MSK = timezone(timedelta(hours=3))
MONTHS_NOMINATIVE = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
CHECK, CROSS = "✅", "❌"

PICKER_TEXT = "В каком месяце меняем?"
NOOP = "u|n"  # кнопка-заглушка (дни недели, пустые клетки календаря)
STALE_TEXT = "Кнопка устарела, вызови /upd заново"

USAGE_TEXT = (
    "Используй формат:\n"
    "/upd 8-1 +, 8-2 -, 8-4 +\n"
    "или чтобы заполнить месяц целиком:\n"
    "/upd 8 +\n"
    "\nЭта команда проставит, что 1го и 4го августа ты свободен, а 2го занят.\n"
    "Можно смешивать и отдельно добавлять даты после месяца!\n"
    "\nИли просто напиши /upd без параметров, и я покажу кнопки."
)


def today_msk() -> date:
    return datetime.now(MSK).date()


# ---------------------------------------------------------------- роли и GitHub

def find_schedule_role(roles):
    roles = [roles] if isinstance(roles, str) else (roles or [])
    return next((r for r in roles if r in SCHEDULE_ROLES), None)


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20)


def github_headers() -> dict:
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}


def schedule_url(role: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{SCHEDULES_PATH}/{role}.json"


async def load_schedule(client, role: str):
    """Возвращает (ответ GitHub, расписание или None, sha или None)."""
    response = await client.get(f"{schedule_url(role)}?ref={SCHEDULES_BRANCH}", headers=github_headers())
    if response.status_code != 200:
        return response, None, None
    data = response.json()
    try:
        schedule = json.loads(base64.b64decode(data["content"]).decode("utf-8"))
        if not isinstance(schedule, dict):
            schedule = {}
    except Exception:
        schedule = {}
    return response, schedule, data["sha"]


def merge_schedule(schedule: dict, updates: list, today: date):
    """Чистит даты старше «вчера» и применяет обновления. Возвращает (расписание, граница очистки)."""
    cutoff = (today - timedelta(days=1)).isoformat()
    merged = {d: status for d, status in schedule.items() if d >= cutoff}
    for day, status in updates:
        merged[day] = status
    return dict(sorted(merged.items())), cutoff


async def write_updates(role: str, updates: list):
    """Читает расписание из GitHub, применяет обновления и записывает обратно.
    Возвращает (стадия 'ok' / 'load' / 'commit', ответ GitHub, граница очистки)."""
    async with make_client() as client:
        response, schedule, sha = await load_schedule(client, role)
        if schedule is None:
            return "load", response, None

        merged, cutoff = merge_schedule(schedule, updates, today_msk())
        payload = {
            "message": f"update {role} schedule",
            "content": base64.b64encode(json.dumps(merged, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8"),
            "sha": sha,
            "branch": SCHEDULES_BRANCH,
        }
        response = await client.put(schedule_url(role), headers=github_headers(), json=payload)
        return ("ok" if response.status_code in (200, 201) else "commit"), response, cutoff


async def notify_setefed(bot, role: str, user_id):
    """Сообщает в личку тем, у кого роль setefed, что расписание обновили. Самого редактирующего не оповещаем."""
    recipients = set()
    for uid, user_roles in get_roles().items():
        user_roles = [user_roles] if isinstance(user_roles, str) else (user_roles or [])
        if str(user_id) != uid and NOTIFY_ROLE in user_roles:
            recipients.add(uid)
    for recipient in recipients:
        try:
            await bot.send_message(chat_id=int(recipient), text=f"{role} обновил расписание.", parse_mode=ParseMode.HTML)
        except Exception:
            pass


# ---------------------------------------------------------------- старый текстовый формат

def parse_args(args):
    entries = []
    text = " ".join(args)
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if len(tokens) == 2 and "-" in tokens[0]:
            date_token, status_token = tokens
            entries.append((date_token, status_token))
        elif len(tokens) == 2:
            month_token, status_token = tokens
            entries.append((month_token, status_token))
        else:
            if "-" in part and ("+" in part or "-" in part):
                d, s = part[:-1], part[-1]
                entries.append((d, s))
    return entries


def expand_month(month, status):
    year = today_msk().year
    days = calendar.monthrange(year, int(month))[1]
    return [(f"{year}-{int(month):02d}-{d:02d}", status) for d in range(1, days + 1)]


async def upd_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE, role: str):
    try:
        entries = parse_args(context.args)
        updates = []
        for date_token, status_token in entries:
            status = status_token.strip()[0]
            if "-" in date_token:
                # поддержка mm-dd
                month, day = map(int, date_token.split("-"))
                year = today_msk().year
                updates.append((f"{year}-{month:02d}-{day:02d}", status))
            else:
                updates += expand_month(int(date_token), status)
        if not updates:
            raise ValueError
    except Exception:
        await update.message.reply_text(USAGE_TEXT)
        return

    stage, response, cutoff = await write_updates(role, updates)
    if stage == "load":
        await update.message.reply_text(f"Ошибка загрузки расписания ({response.status_code})")
    elif stage == "commit":
        await update.message.reply_text(f"Ошибка обновления: {response.status_code} {response.text}")
    else:
        result = "\n".join(f"{day} — {status}" for day, status in updates)
        await update.message.reply_text(f"Спасибо, внес в расписание (старые даты очищены до {cutoff}):\n\n{result}")
        await notify_setefed(context.bot, role, update.effective_user.id)


# ---------------------------------------------------------------- кнопки

def add_months(year: int, month: int, delta: int):
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_key(year: int, month: int) -> str:
    return f"{year}{month:02d}"


def parse_month_key(key: str):
    return int(key[:-2]), int(key[-2:])


def editable_days(year: int, month: int, today: date) -> list:
    """Дни месяца, которые имеет смысл менять: в текущем месяце только сегодняшний и дальше."""
    last = calendar.monthrange(year, month)[1]
    return [d for d in range(1, last + 1) if date(year, month, d) >= today]


def read_mask(schedule: dict, year: int, month: int, days: list) -> int:
    """Битовая маска дней месяца: бит (день-1) = 1, если в расписании «+». Нет записи считается как «занят»."""
    return sum(1 << (d - 1) for d in days if schedule.get(date(year, month, d).isoformat()) == "+")


def cb(*parts) -> str:
    return "|".join(["u", *map(str, parts)])


def picker_markup(owner: int, today: date) -> InlineKeyboardMarkup:
    cur = (today.year, today.month)
    nxt = add_months(*cur, 1)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"Текущий: {MONTHS_NOMINATIVE[cur[1] - 1]}", callback_data=cb("m", owner, month_key(*cur))),
            InlineKeyboardButton(f"Следующий: {MONTHS_NOMINATIVE[nxt[1] - 1]}", callback_data=cb("m", owner, month_key(*nxt))),
        ],
        [InlineKeyboardButton("Отменить", callback_data=cb("x", owner))],
    ])


def days_text(year: int, month: int) -> str:
    return f"Меняй что нужно ({MONTHS_NOMINATIVE[month - 1]} {year})\n{CHECK} можешь играть, {CROSS} занят"


def days_markup(owner: int, year: int, month: int, current: int, initial: int, today: date) -> InlineKeyboardMarkup:
    """Календарь месяца: дни недели сверху, дни лежат в своих колонках. Состояние (маски) хранится в самих кнопках."""
    editable = set(editable_days(year, month, today))
    key = month_key(year, month)
    last = calendar.monthrange(year, month)[1]

    rows = [[InlineKeyboardButton(name, callback_data=NOOP) for name in WEEKDAYS]]
    cells = [None] * date(year, month, 1).weekday() + list(range(1, last + 1))
    cells += [None] * (-len(cells) % 7)
    for start in range(0, len(cells), 7):
        row = []
        for day in cells[start:start + 7]:
            if day is None or day not in editable:
                row.append(InlineKeyboardButton(" ", callback_data=NOOP))
            else:
                mark = CHECK if (current >> (day - 1)) & 1 else CROSS
                row.append(InlineKeyboardButton(
                    f"{day}{mark}", callback_data=cb("t", owner, key, f"{current:x}", f"{initial:x}", day)
                ))
        rows.append(row)

    rows.append([
        InlineKeyboardButton("Назад", callback_data=cb("b", owner)),
        InlineKeyboardButton("Сохранить", callback_data=cb("s", owner, key, f"{current:x}", f"{initial:x}")),
    ])
    return InlineKeyboardMarkup(rows)


async def edit(query, text: str, markup=None):
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


def changed_days(current: int, initial: int, days: list) -> list:
    return [d for d in days if ((current ^ initial) >> (d - 1)) & 1]


async def on_month_chosen(query, owner: int, key: str, today: date):
    year, month = parse_month_key(key)
    if (year, month) not in (
        (today.year, today.month), add_months(today.year, today.month, 1)
    ):
        await query.answer(STALE_TEXT, show_alert=True)
        return

    role = find_schedule_role(get_user_role(owner))
    if not role:
        await query.answer("У тебя нет доступа к изменению расписания", show_alert=True)
        return

    async with make_client() as client:
        response, schedule, _ = await load_schedule(client, role)
    if schedule is None:
        await query.answer(f"Не смог загрузить расписание ({response.status_code}), попробуй ещё раз", show_alert=True)
        return

    initial = read_mask(schedule, year, month, editable_days(year, month, today))
    await query.answer()
    await edit(query, days_text(year, month), days_markup(owner, year, month, initial, initial, today))


async def on_save(query, context, owner: int, key: str, current: int, initial: int, today: date):
    year, month = parse_month_key(key)
    days = editable_days(year, month, today)
    changed = changed_days(current, initial, days)
    if not changed:
        await query.answer()
        await edit(query, "Ничего не изменилось, так что ничего не записал.")
        return

    role = find_schedule_role(get_user_role(owner))
    if not role:
        await query.answer("У тебя нет доступа к изменению расписания", show_alert=True)
        return

    await query.answer("Сохраняю…")
    updates = [
        (date(year, month, d).isoformat(), "+" if (current >> (d - 1)) & 1 else "-") for d in changed
    ]
    stage, response, _ = await write_updates(role, updates)
    if stage != "ok":
        logging.error(f"upd: не удалось сохранить расписание {role}: {stage} {response.status_code} {response.text}")
        await edit(
            query,
            f"⚠️ Не удалось сохранить ({response.status_code}). Нажми «Сохранить» ещё раз.\n\n" + days_text(year, month),
            days_markup(owner, year, month, current, initial, today),
        )
        return

    free = [str(d) for d in changed if (current >> (d - 1)) & 1]
    busy = [str(d) for d in changed if not (current >> (d - 1)) & 1]
    lines = [f"Записал в расписание ({role}), {MONTHS_NOMINATIVE[month - 1]} {year}:"]
    if free:
        lines.append(f"{CHECK} свободен: {', '.join(free)}")
    if busy:
        lines.append(f"{CROSS} занят: {', '.join(busy)}")
    await edit(query, "\n".join(lines))
    await notify_setefed(context.bot, role, owner)


async def upd_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split("|")
    try:
        action = parts[1]
        if action == "n":
            await query.answer()
            return
        owner = int(parts[2])
    except (IndexError, ValueError):
        await query.answer(STALE_TEXT, show_alert=True)
        return

    if query.from_user.id != owner:
        await query.answer("Это не твоя кнопка")
        return

    today = today_msk()
    try:
        if action == "x":
            await query.answer()
            await edit(query, "Отменено")
        elif action == "b":
            await query.answer()
            await edit(query, PICKER_TEXT, picker_markup(owner, today))
        elif action == "m":
            await on_month_chosen(query, owner, parts[3], today)
        elif action == "t":
            key, current, initial, day = parts[3], int(parts[4], 16), int(parts[5], 16), int(parts[6])
            year, month = parse_month_key(key)
            if day not in editable_days(year, month, today):
                await query.answer(STALE_TEXT, show_alert=True)
                return
            current ^= 1 << (day - 1)
            await query.answer()
            await edit(query, days_text(year, month), days_markup(owner, year, month, current, initial, today))
        elif action == "s":
            await on_save(query, context, owner, parts[3], int(parts[4], 16), int(parts[5], 16), today)
        else:
            await query.answer(STALE_TEXT, show_alert=True)
    except (IndexError, ValueError):
        await query.answer(STALE_TEXT, show_alert=True)


# ---------------------------------------------------------------- команда

async def upd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    roles = get_user_role(str(user_id))
    if not roles:
        await update.message.reply_text("У тебя нет доступа к изменению расписания. Проверь: /verify")
        return

    role = find_schedule_role(roles)
    if not role:
        await update.message.reply_text("Ты кто бля? Нихуя не понятно, проверь /verify и скинь кабану")
        return

    if context.args:
        await upd_from_text(update, context, role)
        return

    await update.message.reply_text(PICKER_TEXT, reply_markup=picker_markup(user_id, today_msk()))
