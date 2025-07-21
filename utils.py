import requests
import logging

SCHEDULE_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/refs/heads/main/schedule.csv"

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