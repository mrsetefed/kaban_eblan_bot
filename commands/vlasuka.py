import os
import httpx
import json
from telegram import Update
from telegram.ext import ContextTypes
import base64
from datetime import datetime

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
        if len(tokens) >= 2 and "-" in tokens[0]:
            date_token = tokens[0]
            status_token = " ".join(tokens[1:])
            entries.append((date_token, status_token))
        elif len(tokens) >= 2:
            month_token = tokens[0]
            status_token = " ".join(tokens[1:])
            entries.append((month_token, status_token))
        else:
            if "-" in part and (part[-1] == "+" or part[-1] == "-"):
                d, s = part[:-1], part[-1]
                entries.append((d, s))
    return entries

def expand_month(month, status):
    import calendar
    days = calendar.monthrange(2025, int(month))[1]
    return [(f"2025-{int(month):02d}-{d:02d}", status) for d in range(1, days+1)]

async def vlasuka(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # *** убрали всю проверку ролей и выбор файла по роли ***
    # Теперь всегда работаем с файлом vlasuka.json
    file_name = "vlasuka"  # <-- тут имя твоего файла (без .json)
    
    try:
        entries = parse_args(context.args)
        updates = []
        for date_token, status_token in entries:
            status = status_token.strip()
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
            "/vlasuka 8-1 свободен, 8-2 болею, 8-4 +\n"
            "или чтобы заполнить месяц целиком:\n"
            "/vlasuka 8 в отпуске\n"
            "\nЭта команда запишет в твой график любые слова на нужные даты.\n"
            "Можно смешивать стили и отдельно добавлять даты после месяца!"
        )
        return

    file_path = f"{SCHEDULES_PATH}/{setefed}.json"
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
        schedule = {date: text for date, text in schedule.items() if date >= today}

        for date_str, status in updates:
            schedule[date_str] = status

        new_content = base64.b64encode(
            json.dumps(schedule, ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("utf-8")

        commit_msg = f"update vlasuka schedule"
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
        else:
            await update.message.reply_text(f"Ошибка обновления: {r2.status_code} {r2.text}")