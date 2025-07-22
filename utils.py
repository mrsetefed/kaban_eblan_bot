import os
import json
import logging
import requests

SCHEDULE_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/main/schedule.csv"

# --- Чтение расписания ---
async def fetch_schedule():
    try:
        response = requests.get(SCHEDULE_URL)
        response.raise_for_status()
        lines = response.text.strip().split("\n")
        schedule = {}
        for line in lines:
            parts = line.strip().split(",", maxsplit=1)
            if len(parts) == 2:
                date_str, text = parts
                schedule[date_str.strip()] = text.strip()
        return schedule
    except Exception as e:
        logging.error(f"Не удалось получить расписание: {e}")
        return {}
     

# --- Чтение всех расписаний из папки schedules ---
USER_SCHEDULE_URLS = {
    "nekit": "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/test/schedules/nekit.json",
    "kiros": "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/test/schedules/kiros.json",
    "amir": "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/test/schedules/amir.json",
    "kaban": "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/test/schedules/kaban.json"
}

def fetch_all_json_schedules():
    schedules = {}
    for username, url in USER_SCHEDULE_URLS.items():
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            schedules[username] = data
        except Exception as e:
            logging.error(f"Не удалось загрузить расписание для {username}: {e}")
    return schedules
    
# --- Работа с ролями из ENV ---
def get_roles():
    try:
        roles_json = os.environ.get("USER_ROLES", "{}")
        return json.loads(roles_json)
    except Exception as e:
        logging.error(f"Не удалось загрузить роли: {e}")
        return {}

def get_user_role(user_id):
    roles = get_roles()
    return roles.get(str(user_id))

def is_allowed(user_id, allowed_roles):
    return get_user_role(user_id) in allowed_roles