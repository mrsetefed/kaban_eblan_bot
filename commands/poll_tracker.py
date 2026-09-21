import copy
import hmac
import logging
import os
import random
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import asyncio
from aiohttp import web
from telegram import Chat, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from poll_store import PollStore, create_store
from utils import get_roles, mention_html

STATE_PATH = "state/polls.json"
MSK = timezone(timedelta(hours=3))
REMINDER_HOUR = 17  # во сколько по Москве напоминать за день до игры

# Первая проверка через случайное время после запуска опроса, вторая тоже через случайное время после первой
FIRST_CHECK_HOURS = (8, 10)
SECOND_CHECK_HOURS = (8, 10)
# Не голосовавшим напоминаем в сроки выше, а «проголосовали ли уже все» проверяем каждый час с момента запуска опроса,
# и как только все на месте, сразу пишем итог, не дожидаясь очередного срока. Так до самого финала.
PROBE_INTERVAL = timedelta(hours=1)
GAME_TITLES = {"kogda_dnd": "ДнД", "kogda_kamputer": "Кампутер", "kogda_wd": "ВД", "kogda_strad": "Страд"}
KEEP_FINISHED_DAYS = 14
MAX_SEND_FAILURES = 5  # столько раз пробуем отправить итог, потом сдаёмся (например, бота выгнали из чата)
RETRY_AFTER_FAILURE = timedelta(minutes=10)

SETEFED_TAG = "@setefed"
NOTHING_FITS = 0  # индекс варианта «Ничего не подходит»
NOTHING_FITS_TEXT = "Ничего не подходит"
MAX_POLL_OPTIONS = 10  # лимит Telegram

NAG_TEMPLATES = [
    "{who}, вы ещё не проголосовали. Тыкните в опрос, остальные ждут",
    "Эй, {who}! Опрос сам себя не заполнит. Проголосуйте, пожалуйста",
    "{who}, ваш голос до сих пор не засчитан. Поторопитесь, пока не засчитали как прогул",
]
UNANIMOUS_TEMPLATES = [
    "Решено единогласно, играем: {dates} 🎲",
    "Все проголосовали, мнения сошлись. Играем: {dates}",
    "Единогласно! Играем: {dates}",
]
NO_COMMON_ALL_VOTED = "Проголосовали все, но варианта, который подошёл бы каждому, нет. {setefed}, разруливай"
NO_COMMON_MISSING = "Время вышло, а {who} так и не проголосовали. Общего варианта нет. {setefed}, разбирайся"

REMINDER_TEMPLATES = [
    "Завтра ({date}) собираемся! {who}, не забудьте 🎲",
    "Напоминаю: завтра ({date}) играем. {who}, готовьтесь",
    "{who}, завтра ({date}) сбор! Кто отвалится, тот ишак",
]
MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

_store = None
_process_lock = asyncio.Lock()
_last_probe = {}  # id голосования -> номер уже сделанной отметки. После перезапуска проверит ещё раз, это безопасно


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_store() -> PollStore:
    global _store
    if _store is None:
        _store = create_store(STATE_PATH)
    return _store


def format_date_ru(iso: str) -> str:
    """'2026-09-21' -> '21 сентября, пн'"""
    day = date.fromisoformat(iso)
    return f"{day.day} {MONTHS_GENITIVE[day.month - 1]}, {WEEKDAYS_SHORT[day.weekday()]}"


def resolve_participants(role_names):
    """Ищет в USER_ROLES telegram id по названиям ролей. Возвращает ({id: роль}, [роли без id])."""
    roles_by_id = get_roles()
    found, unresolved = {}, []
    for role in role_names:
        user_id = None
        for uid, user_roles in roles_by_id.items():
            user_roles = [user_roles] if isinstance(user_roles, str) else (user_roles or [])
            if role in user_roles:
                user_id = uid
                break
        if user_id is None:
            unresolved.append(role)
        else:
            found[str(user_id)] = role
    return found, unresolved


def prune(data: dict, now: datetime):
    groups = data.get("groups", {})
    for gid in [
        gid for gid, g in groups.items()
        if g.get("done") and now - datetime.fromisoformat(g["finished_at"]) > timedelta(days=KEEP_FINISHED_DAYS)
    ]:
        del groups[gid]

    events = data.get("events", {})
    oldest_day = now.astimezone(MSK).date() - timedelta(days=KEEP_FINISHED_DAYS)
    for eid in [eid for eid, e in events.items() if date.fromisoformat(e["date"]) < oldest_day]:
        del events[eid]


def group_roles(group: dict) -> list:
    """Роли, которых ждём в голосовании. У голосований, созданных до появления поля roles, берём их из самой игры."""
    if group.get("roles"):
        return group["roles"]
    if group["command"] == "kogda_dnd":
        from .kogda_dnd import PLAYERS  # состав ДнД мог поменяться после создания голосования
        return list(PLAYERS)
    return list(group["participants"].values()) + list(group.get("unresolved", []))


def sync_participants(group: dict) -> bool:
    """Заново ищет id ролей в USER_ROLES, чтобы добавленные позже игроки попали в идущее голосование.
    Возвращает True, если состав изменился."""
    roles = group_roles(group)
    found, unresolved = resolve_participants(roles)
    if not found:  # USER_ROLES пуст или сломан: лучше оставить старый состав, чем считать, что ждать некого
        return False
    changed = found != group["participants"] or unresolved != group.get("unresolved", []) or group.get("roles") != roles
    if changed:
        group["participants"], group["unresolved"], group["roles"] = found, unresolved, roles
    return changed


async def sync_active_groups(store: PollStore):
    data = await store.read()
    stale = [gid for gid, g in data.get("groups", {}).items() if not g.get("done") and sync_participants(copy.deepcopy(g))]
    if not stale:
        return

    def apply(current):
        for gid in stale:
            group = current.get("groups", {}).get(gid)
            if group and not group.get("done"):
                sync_participants(group)

    await store.mutate(apply)


async def register_group(chat_id: int, command: str, polls: list, participant_roles: list, note: str = None):
    participants, unresolved = resolve_participants(participant_roles)
    if unresolved:
        logging.warning(f"{command}: нет telegram id в USER_ROLES для ролей {unresolved}")
    if not participants:
        logging.warning(f"{command}: некого отслеживать, проверка голосования не запланирована")
        return

    now = utcnow()
    group = {
        "chat_id": chat_id,
        "command": command,
        "note": note,
        "created_at": now.isoformat(),
        "next_check_at": (now + timedelta(hours=random.uniform(*FIRST_CHECK_HOURS))).isoformat(),
        "stage": 0,
        "done": False,
        "failures": 0,
        "roles": list(participant_roles),
        "participants": participants,
        "unresolved": unresolved,
        "polls": polls,
        "answers": {},
    }

    def add(data):
        prune(data, now)
        data.setdefault("groups", {})[polls[0]["poll_id"]] = group

    await get_store().mutate(add)


async def send_date_polls(
    update: Update,
    options: list,
    participant_roles: list,
    command: str,
    option_dates: dict = None,
    note: str = None,
    track: bool = True,
):
    """Отправляет опросы с датами (по 9 дат в опросе) и ставит голосование на проверку.
    option_dates: {подпись варианта: 'ГГГГ-ММ-ДД'}, нужны, чтобы после единогласия поставить напоминание о сборе.
    note: пометка, например название месяца, когда подряд идут опросы за разные месяцы (в вариантах только числа).
    track=False: только отправить опросы, без проверки голосования и напоминаний."""
    option_dates = option_dates or {}
    question = "Когда играем?" + (f" ({note})" if note else "")
    chunk_size = MAX_POLL_OPTIONS - 1  # -1 под «Ничего не подходит»
    polls = []
    for i in range(0, len(options), chunk_size):
        chunk = options[i:i + chunk_size]
        poll_options = [NOTHING_FITS_TEXT] + chunk
        message = await update.message.reply_poll(
            question=question,
            options=poll_options,
            is_anonymous=False,
            allows_multiple_answers=True,
        )
        polls.append({
            "poll_id": message.poll.id,
            "message_id": message.message_id,
            "options": poll_options,
            "dates": [None] + [option_dates.get(label) for label in chunk],  # параллельно options
        })

    if not track:
        return

    # в личке с ботом голосуют для себя, напоминать там некому
    if update.effective_chat.type == Chat.PRIVATE:
        return

    try:
        await pin_polls(update.get_bot(), update.effective_chat.id, polls)
    except Exception:
        logging.exception("Не удалось закрепить опросы")
    try:
        await register_group(update.effective_chat.id, command, polls, participant_roles, note)
    except Exception:
        # опросы уже в чате, поэтому сбой хранилища не должен ломать команду
        logging.exception("Не удалось поставить голосование на проверку")


async def pin_polls(bot, chat_id: int, polls: list):
    """Закрепляет опросы без уведомления. Нужны права на закрепление; если их нет, просто не закрепляем."""
    for poll in polls:
        try:
            await bot.pin_chat_message(chat_id=chat_id, message_id=poll["message_id"], disable_notification=True)
            poll["pinned"] = True
        except Exception as e:
            logging.warning(f"Не удалось закрепить опрос в чате {chat_id}: {e}")


async def unpin_polls(bot, group: dict):
    """Снимает закрепление с опросов, которые закрепил сам бот."""
    for poll in group["polls"]:
        if not poll.get("pinned"):
            continue
        try:
            await bot.unpin_chat_message(chat_id=group["chat_id"], message_id=poll["message_id"])
        except Exception as e:
            logging.warning(f"Не удалось открепить опрос в чате {group['chat_id']}: {e}")


def find_group_id(data: dict, poll_id: str):
    for gid, group in data.get("groups", {}).items():
        if not group.get("done") and any(p["poll_id"] == poll_id for p in group["polls"]):
            return gid
    return None


async def on_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    user = answer.user
    if user is None:
        return

    store = get_store()
    data = await store.read()
    gid = find_group_id(data, answer.poll_id)
    if not gid:
        return

    def apply(current):
        group = current.get("groups", {}).get(gid)
        if not group or group.get("done"):
            return
        # голоса пишем от всех, а не только от известных участников: если роль игрока добавят позже, его голос уже будет учтён
        sync_participants(group)
        poll_answers = group["answers"].setdefault(answer.poll_id, {})
        if answer.option_ids:
            poll_answers[str(user.id)] = list(answer.option_ids)
        else:
            poll_answers.pop(str(user.id), None)  # человек снял голос
        current.setdefault("users", {})[str(user.id)] = {"name": user.full_name, "username": user.username}

    await store.mutate(apply)


def analyse(group: dict):
    """Возвращает (id тех, кто голосовал не во всех опросах, [варианты, за которые проголосовали все],
    [полные даты этих вариантов, если они известны])."""
    participants = group["participants"]
    answers = group["answers"]
    missing = [
        uid for uid in participants
        if not all(answers.get(p["poll_id"], {}).get(uid) for p in group["polls"])
    ]

    unanimous, dates = [], []
    if not missing:
        for poll in group["polls"]:
            poll_answers = answers[poll["poll_id"]]
            poll_dates = poll.get("dates") or [None] * len(poll["options"])
            for index, label in enumerate(poll["options"]):
                if index != NOTHING_FITS and all(index in poll_answers[uid] for uid in participants):
                    unanimous.append(label)
                    if poll_dates[index]:
                        dates.append(poll_dates[index])
    return missing, unanimous, dates


def make_events(group: dict, dates: list, now: datetime) -> dict:
    """События «игра в такой-то день»: по ним идёт напоминание за день до игры и команда /skoro."""
    today = now.astimezone(MSK).date()
    events = {}
    for iso in dates:
        if date.fromisoformat(iso) < today:
            continue
        remind_at = datetime.combine(
            date.fromisoformat(iso) - timedelta(days=1), time(REMINDER_HOUR), tzinfo=MSK
        ).astimezone(timezone.utc)
        # игра одна на все чаты: событие привязано к команде (игре) и дате, а не к чату
        events[f"{group['command']}:{iso}"] = {
            "command": group["command"],
            "chat_id": group["chat_id"],  # куда слать напоминание
            "date": iso,
            "remind_at": remind_at.isoformat(),
            "reminded": remind_at <= now,  # время уже прошло (решили поздно): не напоминаем, но игру помним
            "failures": 0,
            "participants": group["participants"],
            "reply_to": group["polls"][0]["message_id"],
        }
    return events


def format_list(items: list) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " и " + items[-1]


async def mention_for(bot, group: dict, users: dict, uid: str) -> str:
    known = users.get(uid)
    if known:
        return mention_html(SimpleNamespace(id=int(uid), username=known.get("username"), full_name=known["name"]))
    try:
        member = await bot.get_chat_member(group["chat_id"], int(uid))
        return mention_html(member.user)
    except Exception:
        # имени нет (человек ещё не голосовал и бот не админ), тегаем по id, а текстом ставим роль
        return mention_html(SimpleNamespace(id=int(uid), username=None, full_name=group["participants"][uid]))


def unresolved_note(group: dict) -> str:
    if not group.get("unresolved"):
        return ""
    return f"\n\n⚠️ Не смог отследить: {', '.join(group['unresolved'])} (их нет в USER_ROLES), их голоса не учтены."


def reply_target(group: dict, missing: list) -> int:
    """На какой опрос отвечать: на первый, где ещё не хватает голосов, чтобы не искать его. Если не хватает нигде, на первый."""
    for poll in group["polls"]:
        answers = group["answers"].get(poll["poll_id"], {})
        if any(not answers.get(uid) for uid in missing):
            return poll["message_id"]
    return group["polls"][0]["message_id"]


async def send_to_group(bot, group: dict, text: str, reply_to: int = None):
    await bot.send_message(
        chat_id=group["chat_id"],
        text=text,
        parse_mode=ParseMode.HTML,
        reply_to_message_id=reply_to or group["polls"][0]["message_id"],
        allow_sending_without_reply=True,
    )


async def check_group(bot, store: PollStore, gid: str, now: datetime, probe_only: bool = False) -> bool:
    """probe_only: плановой проверки нет, просто смотрим, не проголосовали ли уже все. Если не все, ничего не делаем.
    Возвращает True, если что-то отправлено или изменено."""
    data = await store.read()
    group = data["groups"][gid]
    missing, unanimous, unanimous_dates = analyse(group)
    if probe_only and missing:
        return False

    if not missing:
        if unanimous:
            dates_text = format_list(unanimous) + (f" ({group['note']})" if group.get("note") else "")
            text = random.choice(UNANIMOUS_TEMPLATES).format(dates=dates_text)
            everyone = [await mention_for(bot, group, data.get("users", {}), uid) for uid in group["participants"]]
            text += "\n" + " ".join(everyone)  # тегаем всех, чтобы никто не пропустил
        else:
            text = NO_COMMON_ALL_VOTED.format(setefed=SETEFED_TAG)
        finished = True
    else:
        who = format_list([await mention_for(bot, group, data.get("users", {}), uid) for uid in missing])
        if group["stage"] == 0:
            text = random.choice(NAG_TEMPLATES).format(who=who)
            finished = False
        else:
            text = NO_COMMON_MISSING.format(who=who, setefed=SETEFED_TAG)
            finished = True

    try:
        await send_to_group(bot, group, text + unresolved_note(group), reply_target(group, missing))
    except Exception:
        logging.exception(f"Не удалось отправить сообщение по голосованию {gid}")

        def failed(current):
            g = current["groups"][gid]
            g["failures"] = g.get("failures", 0) + 1
            g["next_check_at"] = (now + RETRY_AFTER_FAILURE).isoformat()
            if g["failures"] >= MAX_SEND_FAILURES:
                g["done"], g["finished_at"] = True, now.isoformat()

        await store.mutate(failed)
        return True

    second_check_at = now + timedelta(hours=random.uniform(*SECOND_CHECK_HOURS))
    events = make_events(group, unanimous_dates, now) if finished and unanimous else {}

    def advance(current):
        g = current["groups"][gid]
        g["failures"] = 0
        for event_id, event in events.items():
            current.setdefault("events", {}).setdefault(event_id, event)
        if finished:
            g["done"], g["finished_at"] = True, now.isoformat()
        else:
            g["stage"] = 1
            g["next_check_at"] = second_check_at.isoformat()

    await store.mutate(advance)
    if finished:
        await unpin_polls(bot, group)
    return True


def probe_mark(group: dict, now: datetime) -> int:
    """Сколько полных периодов PROBE_INTERVAL прошло с запуска опроса. Смена этого числа значит «пора проверить»."""
    return int((now - datetime.fromisoformat(group["created_at"])) / PROBE_INTERVAL)


async def send_reminder(bot, store: PollStore, event_id: str, now: datetime):
    data = await store.read()
    event = data["events"][event_id]

    def mark(change):
        def apply(current):
            change(current["events"][event_id])
        return apply

    # игра уже сегодня или прошла: «завтра собираемся» было бы неправдой
    if date.fromisoformat(event["date"]) <= now.astimezone(MSK).date():
        await store.mutate(mark(lambda e: e.update(reminded=True)))
        return

    who = format_list([await mention_for(bot, event, data.get("users", {}), uid) for uid in event["participants"]])
    text = random.choice(REMINDER_TEMPLATES).format(who=who, date=format_date_ru(event["date"]))
    try:
        await bot.send_message(
            chat_id=event["chat_id"],
            text=text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=event["reply_to"],
            allow_sending_without_reply=True,
        )
    except Exception:
        logging.exception(f"Не удалось отправить напоминание {event_id}")

        def failed(e):
            e["failures"] = e.get("failures", 0) + 1
            e["remind_at"] = (now + RETRY_AFTER_FAILURE).isoformat()
            if e["failures"] >= MAX_SEND_FAILURES:
                e["reminded"] = True

        await store.mutate(mark(failed))
        return

    await store.mutate(mark(lambda e: e.update(reminded=True, failures=0)))


async def process_due(bot, now: datetime = None) -> int:
    """Проверяет голосования и напоминания о сборе, у которых подошло время. Возвращает, сколько обработано."""
    now = now or utcnow()
    async with _process_lock:
        store = get_store()
        try:
            await sync_active_groups(store)
        except Exception:
            logging.exception("Не удалось обновить состав участников голосований")
        data = await store.read()
        due = []
        for gid, group in data.get("groups", {}).items():
            if group.get("done"):
                continue
            timed = datetime.fromisoformat(group["next_check_at"]) <= now
            mark = probe_mark(group, now)
            if timed or (mark >= 1 and mark > _last_probe.get(gid, 0)):
                due.append((gid, timed, mark))

        if due:
            # перед проверкой перечитываем состояние из GitHub, чтобы учесть правки файла вручную
            try:
                await store.refresh()
                await sync_active_groups(store)
            except Exception:
                logging.exception("Не удалось перечитать состояние голосований, работаю с тем, что в памяти")
            data = await store.read()

        acted = 0
        for gid, timed, mark in due:
            group = data.get("groups", {}).get(gid)
            if not group or group.get("done"):
                continue
            _last_probe[gid] = mark
            try:
                if await check_group(bot, store, gid, now, probe_only=not timed):
                    acted += 1
            except Exception:
                logging.exception(f"Ошибка проверки голосования {gid}")

        # события могли появиться только что, поэтому список берём заново
        data = await store.read()
        due_events = [
            eid for eid, e in data.get("events", {}).items()
            if not e["reminded"] and datetime.fromisoformat(e["remind_at"]) <= now
        ]
        for eid in due_events:
            try:
                await send_reminder(bot, store, eid, now)
            except Exception:
                logging.exception(f"Ошибка напоминания {eid}")
        return acted + len(due_events)


async def handle_tick(request: web.Request, bot, runner=None) -> web.Response:
    """Точка входа для внешнего «будильника» (cron-job.org): будит бота и запускает все отложенные проверки."""
    secret = os.environ.get("TICK_SECRET")
    if not secret:
        return web.Response(status=503, text="tick disabled: TICK_SECRET is not set")
    given = request.headers.get("X-Tick-Key") or request.query.get("key", "")
    if not hmac.compare_digest(given.encode(), secret.encode()):
        return web.Response(status=403, text="forbidden")
    processed = await (runner or process_due)(bot)
    return web.Response(text=f"ok, processed={processed}")
