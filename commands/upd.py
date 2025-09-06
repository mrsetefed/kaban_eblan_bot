import os
import httpx
import json
from telegram import Update
from telegram.ext import ContextTypes
from utils import get_user_role  # твоя функция
import base64
from datetime import datetime, timedelta          # NEW
from zoneinfo import ZoneInfo                     # NEW

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = "mrsetefed/kaban_eblan_bot"
SCHEDULES_BRANCH = "schedule"
SCHEDULES_PATH = "schedules"

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
    import calendar
    # Лучше не хардкодить год; возьмём текущий по Стокгольму
    year = datetime.now(ZoneInfo("Europe/Moscow")).year   # NEW
    days = calendar.monthrange(year, int(month))[1]
    return [(f"{year}-{int(month):02d}-{d:02d}", status) for d in range(1, days+1)]

async def upd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    roles = get_user_role(user_id)
    if not roles:
        await update.message.reply_text("У тебя нет доступа к изменению расписания. Проверь: /verify")
        return

    role = None
    for r in roles:
        if r in ["nekit", "kiros", "hench", "kaban", "andrey", "admin"]:  # FIX: пусть admin тоже можно
            role = r
            break
    if not role:
        await update.message.reply_text("Ты кто бля? Нихуя не понятно, проверь /verify и скинь кабану")
        return

    # --- разбор аргументов
    try:
        entries = parse_args(context.args)
        updates = []
        for date_token, status_token in entries:
            status = status_token.strip()[0]
            if "-" in date_token:
                # поддержка mm-dd
                month, day = map(int, date_token.split("-"))
                year = datetime.now(ZoneInfo("Europe/Stockholm")).year
                date_str = f"{year}-{month:02d}-{day:02d}"
                updates.append((date_str, status))
            else:
                month = int(date_token)
                updates += expand_month(month, status)
        if not updates:
            raise ValueError
    except Exception:
        await update.message.reply_text(
            "Используй формат:\n"
            "/upd 8-1 +, 8-2 -, 8-4 +\n"
            "или чтобы заполнить месяц целиком:\n"
            "/upd 8 +\n"
            "\nЭта команда проставит, что 1го и 4го августа ты свободен, а 2го занят.\n"
            "Можно смешивать и отдельно добавлять даты после месяца!"
        )
        return

    file_path = f"{SCHEDULES_PATH}/{role}.json"
    file_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}?ref={SCHEDULES_BRANCH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(file_url, headers=headers)
        if r.status_code != 200:
            await update.message.reply_text(f"Ошибка загрузки расписания ({r.status_code})")
            return
        data = r.json()
        content = data['content']
        sha = data['sha']
        decoded = base64.b64decode(content).decode("utf-8")

        # ---- НАДЁЖНАЯ загрузка и ОЧИСТКА старых дат
        try:
            schedule = json.loads(decoded)
            if not isinstance(schedule, dict):
                schedule = {}
        except Exception:
            schedule = {}

        # Чистим всё раньше «вчера» по Europe/Moscow
        tz = ZoneInfo("Europe/Moscow")                    # NEW
        cutoff = (datetime.now(tz).date() - timedelta(days=1)).isoformat()  # NEW  (вчера)
        schedule = {date: status for date, status in schedule.items() if date >= cutoff}  # NEW

        # Применяем апдейты
        for date_str, status in updates:
            schedule[date_str] = status

        # Можно отсортировать ключи для удобства диффов (опционально)
        schedule_sorted = dict(sorted(schedule.items()))     # NEW

        new_content = base64.b64encode(
            json.dumps(schedule_sorted, ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("utf-8")

        commit_msg = f"update {role} schedule"               # FIX: отступ
        update_data = {
            "message": commit_msg,
            "content": new_content,
            "sha": sha,
            "branch": SCHEDULES_BRANCH
        }
        put_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
        r2 = await client.put(put_url, headers=headers, json=update_data)
        if r2.status_code in (200, 201):
            result = "\n".join([f"{date} — {status}" for date, status in updates])
            await update.message.reply_text(
                f"Спасибо, внес в расписание (старые даты очищены до {cutoff}):\n\n{result}"
            )
            # --- ОПОВЕЩЕНИЕ АДМИНОВ ---
            from telegram.constants import ParseMode
            from utils import get_roles
            admin_ids = []
            roles_dict = get_roles()
            for uid, user_roles in roles_dict.items():
                if user_id == uid:
                    continue
                if isinstance(user_roles, str) and user_roles == "admin" and role != "admin":
                    admin_ids.append(uid)
                if isinstance(user_roles, list) and "admin" in user_roles and role != "admin":
                    admin_ids.append(uid)
            if role != "admin":
                for admin_id in set(admin_ids):
                    try:
                        await context.bot.send_message(
                            chat_id=int(admin_id),
                            text=f"{role} обновил расписание.",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass
        else:
            await update.message.reply_text(f"Ошибка обновления: {r2.status_code} {r2.text}")