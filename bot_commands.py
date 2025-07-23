from telegram.ext import CommandHandler
from commands import start, ping, today, tomorrow, week, verify, krutometr, kogda_strad, upd

def get_handlers():
    return [
        CommandHandler("start", start),
        CommandHandler("ping", ping),
        CommandHandler("today", today),
        CommandHandler("tomorrow", tomorrow),
        CommandHandler("week", week),
        CommandHandler("verify", verify),
        CommandHandler("krutometr", krutometr),
        CommandHandler("kogda_strad", kogda_strad),
        CommandHandler("upd", upd),
    ]