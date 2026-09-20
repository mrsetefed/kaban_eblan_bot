import logging
from datetime import datetime

from . import krutometr_stats, poll_tracker


async def process_all(bot, now: datetime = None) -> int:
    """Все отложенные дела бота: проверка голосований, напоминания о сборе, итоги недели крутометра.
    Вызывается и фоновым циклом, и внешним будильником через /tick."""
    total = 0
    for runner in (poll_tracker.process_due, krutometr_stats.process_due):
        try:
            total += await runner(bot, now)
        except Exception:
            logging.exception(f"Ошибка в {runner.__module__}.{runner.__name__}")
    return total
