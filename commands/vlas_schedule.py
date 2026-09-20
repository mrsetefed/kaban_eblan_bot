import base64
import json
from datetime import date, datetime, timedelta, timezone

from . import upd as U

# Личный график для Власа: schedules/setefed.json. Его правит /vlasuka, читают /today, /tomorrow и /week.
FILE_ROLE = "setefed"
RAW_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/setefed.json"

FREE, BUSY = "+", "-"
STATUS_LABELS = {FREE: "✅ свободен", BUSY: "❌ занят"}

MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def today_utc() -> date:
    """День у бота меняется в полночь по UTC. У Власа это 7 утра, как и сказано в справке."""
    return datetime.now(timezone.utc).date()


def format_day(day: date) -> str:
    """21 сентября, пн"""
    return f"{day.day} {MONTHS_GENITIVE[day.month - 1]}, {WEEKDAYS_SHORT[day.weekday()]}"


# ---------------------------------------------------------------- записи по дням
# Запись бывает трёх видов:
#   "хуй"                                  — старый свободный текст, считаем его комментарием без статуса
#   "+" или "-"                            — старый статус без комментария
#   {"status": "+", "comment": "рано уйду"} — новый формат, статус и комментарий необязательны

def entry_status(value):
    if isinstance(value, dict):
        status = value.get("status")
        return status if status in (FREE, BUSY) else None
    return value if value in (FREE, BUSY) else None


def entry_comment(value) -> str:
    if isinstance(value, dict):
        return str(value.get("comment") or "")
    if isinstance(value, str) and value not in (FREE, BUSY):
        return value
    return ""


def make_entry(status, comment):
    entry = {}
    if status:
        entry["status"] = status
    if comment:
        entry["comment"] = comment
    return entry or None


def with_status(value, status):
    """Меняет статус, комментарий (в том числе старый текст) остаётся."""
    return make_entry(status, entry_comment(value))


def with_comment(value, comment: str):
    """Меняет комментарий, статус остаётся. Пустой комментарий убирает его, а запись без статуса пропадает совсем."""
    return make_entry(entry_status(value), comment)


def effective_status(value) -> str:
    """По умолчанию все дни свободны: занят только тот день, где это отмечено явно."""
    return BUSY if entry_status(value) == BUSY else FREE


def describe(value) -> str:
    """Как день выглядит для человека: «✅ свободен» или «❌ занят», после тире комментарий, если он есть."""
    label = STATUS_LABELS[effective_status(value)]
    comment = entry_comment(value)
    return f"{label} — {comment}" if comment else label


# ---------------------------------------------------------------- GitHub

async def fetch_schedule():
    """Свежий график через GitHub API (raw-ссылки кешируются около 5 минут). Возвращает (график, текст ошибки)."""
    async with U.make_client() as client:
        response, schedule, _ = await U.load_schedule(client, FILE_ROLE)
        if schedule is not None:
            return schedule, None
        fallback = await client.get(RAW_URL)
    if fallback.status_code != 200:
        return None, f"Ошибка загрузки: {fallback.status_code}"
    try:
        data = json.loads(fallback.content.decode("utf-8"))
        return (data if isinstance(data, dict) else {}), None
    except Exception:
        return None, "Ошибка чтения файла"


async def write_changes(status_changes: dict, comment_changes: dict):
    """status_changes: {дата: '+' | '-'}, comment_changes: {дата: текст, пустая строка убирает комментарий}.
    Правит записи по дням, вычищает дни старше вчерашнего. Возвращает (стадия 'ok' / 'load' / 'commit', ответ GitHub)."""
    async with U.make_client() as client:
        response, schedule, sha = await U.load_schedule(client, FILE_ROLE)
        if schedule is None:
            return "load", response

        cutoff = (today_utc() - timedelta(days=1)).isoformat()
        schedule = {day: value for day, value in schedule.items() if day >= cutoff}
        for day, status in status_changes.items():
            schedule[day] = with_status(schedule.get(day), status)
        for day, comment in comment_changes.items():
            entry = with_comment(schedule.get(day), comment)
            if entry is None:
                schedule.pop(day, None)
            else:
                schedule[day] = entry

        payload = {
            "message": "update vlasuka schedule",
            "content": base64.b64encode(
                json.dumps(dict(sorted(schedule.items())), ensure_ascii=False, indent=2).encode("utf-8")
            ).decode("utf-8"),
            "sha": sha,
            "branch": U.SCHEDULES_BRANCH,
        }
        response = await client.put(U.schedule_url(FILE_ROLE), headers=U.github_headers(), json=payload)
        return ("ok" if response.status_code in (200, 201) else "commit"), response
