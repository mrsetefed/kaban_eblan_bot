import html
import logging
import random
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from telegram import Chat, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from poll_store import create_store
from utils import mention_html

STATS_PATH = "state/krutometr.json"
MSK = timezone(timedelta(hours=3))
POST_HOUR = 12  # в понедельник в это время (МСК) бот пишет итоги прошлой недели
KEEP_DAYS = 35
KEEP_POSTED_WEEKS = 8
MAX_LIST = 10
MAX_SEND_FAILURES = 5
RETRY_AFTER_FAILURE = timedelta(minutes=10)

CHAMPION_LINES = [
    "👑 Крутой недели: {who}. Клуб крутых кланяется",
    "👑 Крутой недели: {who}. Курьеры уже несут дары",
    "👑 Крутой недели: {who}. Аура слепит, надевай очки",
]
DONKEY_LINES = [
    "🫏 Ишак недели: {who}. Поздравляем с титулом",
    "🫏 Ишак недели: {who}. Клуб крутых рассмотрел заявку и отказал",
    "🫏 Ишак недели: {who}. В следующий раз повезёт, а может и нет",
]
MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

_store = None


def get_store():
    global _store
    if _store is None:
        _store = create_store(STATS_PATH)
    return _store


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


async def record_roll(update: Update, score: int, day: str):
    """Запоминает, что человек сегодня крутил крутометр в этом чате (только группы). Нужен для топа недели."""
    chat = update.effective_chat
    if chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        return
    user = update.effective_user
    chat_key, user_key = str(chat.id), str(user.id)

    store = get_store()
    data = await store.read()
    if data.get("chats", {}).get(chat_key, {}).get("days", {}).get(day, {}).get(user_key):
        return  # уже записан, лишний коммит в GitHub не нужен

    def add(current):
        entry = current.setdefault("chats", {}).setdefault(chat_key, {"days": {}, "posted_weeks": []})
        entry["days"].setdefault(day, {})[user_key] = {
            "score": score, "name": user.full_name, "username": user.username,
        }
        oldest = (date.fromisoformat(day) - timedelta(days=KEEP_DAYS)).isoformat()
        for old_day in [d for d in entry["days"] if d < oldest]:
            del entry["days"][old_day]

    await store.mutate(add)


def week_standings(entry: dict, start: date, end: date) -> list:
    """Средний результат за дни, когда человек крутил, в период [start, end). По убыванию."""
    people = {}
    for day_str, users in entry.get("days", {}).items():
        if not (start <= date.fromisoformat(day_str) < end):
            continue
        for uid, roll in users.items():
            person = people.setdefault(uid, {"uid": uid, "scores": []})
            person["scores"].append(roll["score"])
            person["name"], person["username"] = roll["name"], roll.get("username")  # берём самое свежее имя

    standings = [
        {
            "uid": p["uid"], "name": p["name"], "username": p["username"],
            "avg": round(sum(p["scores"]) / len(p["scores"]), 1), "days": len(p["scores"]),
        }
        for p in people.values()
    ]
    return sorted(standings, key=lambda s: (-s["avg"], -s["days"], s["name"].lower()))


def who_text(person: dict, tag: bool) -> str:
    if tag:
        return mention_html(SimpleNamespace(id=int(person["uid"]), username=person["username"], full_name=person["name"]))
    return f"<b>{html.escape(person['name'])}</b>"


def period_text(start: date) -> str:
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS_GENITIVE[end.month - 1]}"
    return f"{start.day} {MONTHS_GENITIVE[start.month - 1]} – {end.day} {MONTHS_GENITIVE[end.month - 1]}"


def build_top_text(standings: list, start: date, final: bool) -> str:
    """final=True: итоги прошедшей недели, победителей тегаем. False: неделя ещё идёт, без тегов."""
    title = "🏆 <b>Топ крутости за неделю</b>" if final else "📊 <b>Топ крутости, неделя ещё идёт</b>"
    lines = [f"{title} ({period_text(start)})", ""]
    medals = ["🥇", "🥈", "🥉"]
    for i, person in enumerate(standings[:MAX_LIST]):
        place = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{place} {html.escape(person['name'])}: {person['avg']}% ({person['days']} дн.)")

    best, worst = standings[0], standings[-1]
    lines.append("")
    if final:
        if len(standings) == 1:
            lines.append(f"На этой неделе крутил только {who_text(best, True)}, так что он и крутой, и ишак одновременно")
        else:
            lines.append(random.choice(CHAMPION_LINES).format(who=who_text(best, True)))
            lines.append(random.choice(DONKEY_LINES).format(who=who_text(worst, True)))
    elif len(standings) == 1:
        lines.append(f"Пока крутил только {who_text(best, False)}")
    else:
        lines.append(f"Пока впереди: {who_text(best, False)}")
        lines.append(f"Пока позади: {who_text(worst, False)}")
    return "\n".join(lines)


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Текущий топ недели по запросу (без тегов)."""
    today = datetime.now(MSK).date()
    start = week_start(today)
    data = await get_store().read()
    entry = data.get("chats", {}).get(str(update.effective_chat.id), {})
    standings = week_standings(entry, start, start + timedelta(days=7))
    if not standings:
        await update.message.reply_text("На этой неделе в чате ещё никто не крутил крутометр. Начни с /krutometr")
        return
    await update.message.reply_text(build_top_text(standings, start, final=False), parse_mode=ParseMode.HTML)


async def post_week(bot, store, chat_id: str, start: date, now: datetime):
    data = await store.read()
    entry = data["chats"][chat_id]
    standings = week_standings(entry, start, start + timedelta(days=7))
    week_key = start.isoformat()

    def mark_posted(current):
        e = current["chats"][chat_id]
        e.get("post_failures", {}).pop(week_key, None)
        e["posted_weeks"] = (e.get("posted_weeks", []) + [week_key])[-KEEP_POSTED_WEEKS:]

    try:
        await bot.send_message(
            chat_id=int(chat_id), text=build_top_text(standings, start, final=True), parse_mode=ParseMode.HTML
        )
    except Exception:
        logging.exception(f"Не удалось отправить топ недели в чат {chat_id}")

        def failed(current):
            e = current["chats"][chat_id]
            failures = e.setdefault("post_failures", {})
            failures[week_key] = failures.get(week_key, 0) + 1
            e["retry_at"] = (now + RETRY_AFTER_FAILURE).isoformat()
            if failures[week_key] >= MAX_SEND_FAILURES:
                mark_posted(current)

        await store.mutate(failed)
        return

    await store.mutate(mark_posted)


async def process_due(bot, now: datetime = None) -> int:
    """В понедельник после POST_HOUR (МСК) отправляет итоги прошлой недели в чаты, где кто-то крутил.
    Если в чате никто не крутил, ничего не пишет. Возвращает, сколько сообщений отправлено."""
    now = now or datetime.now(timezone.utc)
    now_msk = now.astimezone(MSK)
    this_week = week_start(now_msk.date())
    if now_msk < datetime.combine(this_week, time(POST_HOUR), tzinfo=MSK):
        return 0  # для этой недели итоги считаются на следующий понедельник, а за прошлую пишем после полудня

    prev_week = this_week - timedelta(days=7)
    store = get_store()
    data = await store.read()
    posted = 0
    for chat_id, entry in list(data.get("chats", {}).items()):
        if prev_week.isoformat() in entry.get("posted_weeks", []):
            continue
        if entry.get("retry_at") and datetime.fromisoformat(entry["retry_at"]) > now:
            continue
        if not week_standings(entry, prev_week, this_week):
            continue  # на прошлой неделе никто не крутил, молчим
        try:
            await post_week(bot, store, chat_id, prev_week, now)
            posted += 1
        except Exception:
            logging.exception(f"Ошибка топа недели для чата {chat_id}")
    return posted
