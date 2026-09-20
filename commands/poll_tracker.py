import hmac
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import asyncio
from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from poll_store import FileBackend, GithubBackend, PollStore, STATE_PATH
from utils import get_roles, mention_html

# Первая проверка через случайное время после запуска опроса, вторая через сутки после первой
FIRST_CHECK_HOURS = (10, 16)
SECOND_CHECK_HOURS = 24
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
NO_COMMON_MISSING = "Прошли сутки, а {who} так и не проголосовали. Общего варианта нет. {setefed}, разбирайся"

_store = None
_process_lock = asyncio.Lock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_store() -> PollStore:
    global _store
    if _store is None:
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            backend = GithubBackend(token, os.environ.get("GITHUB_REPO", "mrsetefed/kaban_eblan_bot"))
        else:
            logging.warning("GITHUB_TOKEN не задан: состояние опросов хранится в локальном файле и пропадёт при перезапуске")
            backend = FileBackend(STATE_PATH)
        _store = PollStore(backend)
    return _store


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


async def register_group(chat_id: int, command: str, polls: list, participant_roles: list):
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
        "created_at": now.isoformat(),
        "next_check_at": (now + timedelta(hours=random.uniform(*FIRST_CHECK_HOURS))).isoformat(),
        "stage": 0,
        "done": False,
        "failures": 0,
        "participants": participants,
        "unresolved": unresolved,
        "polls": polls,
        "answers": {},
    }

    def add(data):
        prune(data, now)
        data.setdefault("groups", {})[polls[0]["poll_id"]] = group

    await get_store().mutate(add)


async def send_date_polls(update: Update, options: list, participant_roles: list, command: str):
    """Отправляет опросы с датами (по 9 дат в опросе) и ставит голосование на проверку."""
    chunk_size = MAX_POLL_OPTIONS - 1  # -1 под «Ничего не подходит»
    polls = []
    for i in range(0, len(options), chunk_size):
        poll_options = [NOTHING_FITS_TEXT] + options[i:i + chunk_size]
        message = await update.message.reply_poll(
            question="Когда играем?",
            options=poll_options,
            is_anonymous=False,
            allows_multiple_answers=True,
        )
        polls.append({"poll_id": message.poll.id, "message_id": message.message_id, "options": poll_options})

    try:
        await register_group(update.effective_chat.id, command, polls, participant_roles)
    except Exception:
        # опросы уже в чате, поэтому сбой хранилища не должен ломать команду
        logging.exception("Не удалось поставить голосование на проверку")


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
    if not gid or str(user.id) not in data["groups"][gid]["participants"]:
        return

    def apply(current):
        group = current.get("groups", {}).get(gid)
        if not group or group.get("done"):
            return
        poll_answers = group["answers"].setdefault(answer.poll_id, {})
        if answer.option_ids:
            poll_answers[str(user.id)] = list(answer.option_ids)
        else:
            poll_answers.pop(str(user.id), None)  # человек снял голос
        current.setdefault("users", {})[str(user.id)] = {"name": user.full_name, "username": user.username}

    await store.mutate(apply)


def analyse(group: dict):
    """Возвращает (id тех, кто голосовал не во всех опросах, [варианты, за которые проголосовали все])."""
    participants = group["participants"]
    answers = group["answers"]
    missing = [
        uid for uid in participants
        if not all(answers.get(p["poll_id"], {}).get(uid) for p in group["polls"])
    ]

    unanimous = []
    if not missing:
        for poll in group["polls"]:
            poll_answers = answers[poll["poll_id"]]
            for index, label in enumerate(poll["options"]):
                if index != NOTHING_FITS and all(index in poll_answers[uid] for uid in participants):
                    unanimous.append(label)
    return missing, unanimous


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


async def send_to_group(bot, group: dict, text: str):
    await bot.send_message(
        chat_id=group["chat_id"],
        text=text,
        parse_mode=ParseMode.HTML,
        reply_to_message_id=group["polls"][0]["message_id"],
        allow_sending_without_reply=True,
    )


async def check_group(bot, store: PollStore, gid: str, now: datetime):
    data = await store.read()
    group = data["groups"][gid]
    missing, unanimous = analyse(group)

    if not missing:
        if unanimous:
            text = random.choice(UNANIMOUS_TEMPLATES).format(dates=format_list(unanimous))
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
        await send_to_group(bot, group, text + unresolved_note(group))
    except Exception:
        logging.exception(f"Не удалось отправить сообщение по голосованию {gid}")

        def failed(current):
            g = current["groups"][gid]
            g["failures"] = g.get("failures", 0) + 1
            g["next_check_at"] = (now + RETRY_AFTER_FAILURE).isoformat()
            if g["failures"] >= MAX_SEND_FAILURES:
                g["done"], g["finished_at"] = True, now.isoformat()

        await store.mutate(failed)
        return

    def advance(current):
        g = current["groups"][gid]
        g["failures"] = 0
        if finished:
            g["done"], g["finished_at"] = True, now.isoformat()
        else:
            g["stage"] = 1
            g["next_check_at"] = (now + timedelta(hours=SECOND_CHECK_HOURS)).isoformat()

    await store.mutate(advance)


async def process_due(bot, now: datetime = None) -> int:
    """Проверяет все голосования, у которых подошло время. Возвращает, сколько обработано."""
    now = now or utcnow()
    async with _process_lock:
        store = get_store()
        data = await store.read()
        due = [
            gid for gid, g in data.get("groups", {}).items()
            if not g.get("done") and datetime.fromisoformat(g["next_check_at"]) <= now
        ]
        for gid in due:
            try:
                await check_group(bot, store, gid, now)
            except Exception:
                logging.exception(f"Ошибка проверки голосования {gid}")
        return len(due)


async def handle_tick(request: web.Request, bot) -> web.Response:
    """Точка входа для внешнего «будильника» (cron-job.org, GitHub Actions): будит бота и проверяет голосования."""
    secret = os.environ.get("TICK_SECRET")
    if not secret:
        return web.Response(status=503, text="tick disabled: TICK_SECRET is not set")
    given = request.headers.get("X-Tick-Key") or request.query.get("key", "")
    if not hmac.compare_digest(given.encode(), secret.encode()):
        return web.Response(status=403, text="forbidden")
    processed = await process_due(bot)
    return web.Response(text=f"ok, processed={processed}")
