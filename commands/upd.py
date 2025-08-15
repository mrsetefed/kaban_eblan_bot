import os
import httpx
import json
from telegram import Update
from telegram.ext import ContextTypes
from utils import get_user_role  # твоя функция
import base64

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
    days = calendar.monthrange(2025, int(month))[1]
    return [(f"2025-{int(month):02d}-{d:02d}", status) for d in range(1, days+1)]

async def upd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    roles = get_user_role(user_id)
    if not roles:
        await update.message.reply_text("У тебя нет доступа к изменению расписания. Проверь: /verify")
        return

    # Определяем роль-файл
    role = None
    for r in roles:
        if r in ["nekit", "kiros", "hench", "kaban", "andrey"]:
            role = r
            break
    if not role:
        await update.message.reply_text("Ты кто бля? Нихуя не понятно, проверь /verify и скинь кабану")
        return

    # Парсим аргументы
    try:
        entries = parse_args(context.args)
        updates = []
        for date_token, status_token in entries:
            status = status_token.strip()[0]
            if "-" in date_token:
                month, day = map(int, date_token.split("-"))
                date_str = f"2025-{month:02d}-{day:02d}"
                updates.append((date_str, status))
            else:
                month = int(date_token)
                updates += expand_month(month, status)
        if not updates:
            raise ValueError
    except Exception as e:
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
        try:
            schedule = json.loads(decoded)
        except Exception:
            schedule = {}
            
            today = datetime.now().strftime("%Y-%m-%d")
            schedule = {date: status for date, status in schedule.items() if date >= today}

        for date_str, status in updates:
            schedule[date_str] = status

        new_content = base64.b64encode(
            json.dumps(schedule, ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("utf-8")

        commit_msg = f"update {role} schedule"
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
                f"Спасибо, внес в расписание:\n\n{result}"
            )
            # --- ОПОВЕЩЕНИЕ АДМИНОВ ---
            from telegram.constants import ParseMode
            from utils import get_roles
            admin_ids = []
            roles_dict = get_roles()
            for uid, user_roles in roles_dict.items():
                # если роль admin есть, и не равна текущей роли, и не сам пользователь
                # можно поменять на isinstance(user_roles, list) если роли — список
                if user_id == uid:
                    continue
                if isinstance(user_roles, str) and user_roles == "admin" and role != "admin":
                    admin_ids.append(uid)
                if isinstance(user_roles, list) and "admin" in user_roles and role != "admin":
                    admin_ids.append(uid)
            # Исключение: НЕ уведомлять если обновляет сам admin
            if role != "admin":
                for admin_id in set(admin_ids):
                    try:
                        await context.bot.send_message(
                            chat_id=int(admin_id),
                            text=f"Пользователь {role} обновил расписание.",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception as e:
                        # Не кричать на ошибку (например, если нет чата)
                        pass
        else:
            await update.message.reply_text(f"Ошибка обновления: {r2.status_code} {r2.text}")