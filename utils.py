import os
import json
import logging
import requests
import base64
import time

SCHEDULE_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/setefed.json"

async def fetch_schedule():
    try:
        # Добавляем "костыль" для обхода кэша GitHub (добавляем уникальный GET-параметр)
        url = SCHEDULE_URL + f"?_={int(time.time())}"
        headers = {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()  
    except Exception as e:
        logging.error(f"Не удалось получить расписание: {e}")
        return {}
     

# --- Чтение всех расписаний из папки schedules ---
USER_SCHEDULE_URLS = {
    "nekit": "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/nekit.json",
    "kiros": "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/kiros.json",
    "amir": "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/amir.json",
    "kaban": "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/kaban.json",
    "andrey": "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/andrey.json",
    "setefed": "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/schedule/schedules/setefed.json"
}

def fetch_selected_json_schedules(usernames):
    schedules = {}
    for username in usernames:
        url = USER_SCHEDULE_URLS.get(username)
        if not url:
            logging.warning(f"Нет ссылки на расписание для пользователя: {username}")
            continue
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()  # ожидается {"2025-07-24": "+", ...}
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
    user_roles = get_user_role(user_id)
    # Приводим к списку если строка (например "admin"), иначе если None — пустой список
    if isinstance(user_roles, str):
        user_roles = [user_roles]
    elif not isinstance(user_roles, list):
        user_roles = []
    # Теперь можно проверить, есть ли хотя бы одна роль в allowed_roles
    return any(role in allowed_roles for role in user_roles)
    
    # - обновление файлов на гитхабе
    


def update_github_schedule(username, new_schedule_dict, commit_message="Update schedule via bot"):
    """
    Обновляет файл расписания пользователя username на GitHub через API.

    Аргументы:
    - username: "nekit", "kiros", "amir", "kaban" (имя пользователя/файла)
    - new_schedule_dict: словарь, который надо записать в .json (например, {"2025-07-24": "+", ...})
    - commit_message: текст коммита на GitHub

    Токен и repo задаются через ENV: GITHUB_TOKEN и GITHUB_REPO
    """
    # 1. Настройки (лучше вынести в ENV на Render)
    GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]  # токен добавить в Render Env
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "mrsetefed/kaban_eblan_bot")  # или зашить жёстко

    # 2. Путь к файлу в репе
    branch = "schedule"  # если нужно — поменяй на "main" или другой
    path = f"schedules/{username}.json"
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"

    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    # 3. Получаем SHA текущей версии файла (нужно для обновления!)
    resp = requests.get(f"{api_url}?ref={branch}", headers=headers)
    if resp.status_code == 200:
        sha = resp.json()["sha"]
    elif resp.status_code == 404:
        sha = None  # файла нет — создаём новый
    else:
        raise Exception(f"GitHub GET failed: {resp.text}")

    # 4. Кодируем новое содержимое файла
    json_str = json.dumps(new_schedule_dict, ensure_ascii=False, indent=2)
    encoded_content = base64.b64encode(json_str.encode()).decode()

    # 5. Собираем payload
    payload = {
        "message": commit_message,
        "content": encoded_content,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    # 6. PUT — обновить/создать файл
    put_resp = requests.put(api_url, headers=headers, data=json.dumps(payload))
    if put_resp.status_code not in (200, 201):
        raise Exception(f"GitHub PUT failed: {put_resp.text}")
    return put_resp.json()